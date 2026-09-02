import os
from neo4j import GraphDatabase
from dotenv import load_dotenv
from agent.anthropic_client import get_anthropic_client
from agent.cypher_safety import (
    enforce_result_limit,
    strip_markdown_fences,
    validate_read_only_cypher,
)
from agent.latency import measure_ms
from agent.token_usage import usage_from_response
from schema.graph_manifest import unloaded_labels_rule_line

load_dotenv(override=True)

MODEL = "claude-sonnet-4-5"

_SCHEMA_CONTEXT_BASE = """
Graph schema (property types matter — use the correct type in filters):

Customer:
  - customer_id: string (PRIMARY identifier for filtering customers; e.g. 'ALFKI', 'VINET', 'SAVEA')
  - company_name: string (display name only; do NOT use for customer filters)
  - country: string

Order:
  - order_id: integer (PRIMARY identifier; use unquoted numbers, e.g. 10248, not '10248')
  - order_date: string

Product:
  - product_id: integer (PRIMARY identifier; use unquoted numbers)
  - product_name: string
  - unit_price: float

SupportTicket:
  - ticket_id: string
  - text: string

Relationships:
  - (Customer)-[:PLACED]->(Order)
  - (Order)-[:CONTAINS {quantity: integer}]->(Product)
  - (Customer)-[:FILED]->(SupportTicket)
  - (SupportTicket)-[:REFERENCES]->(Order)

Example — filter by customer identifier (not company name):
  MATCH (c:Customer {customer_id: 'VINET'})-[:PLACED]->(o:Order)
  RETURN count(o)

Example — filter by integer order_id:
  MATCH (o:Order {order_id: 10248})-[:CONTAINS]->(p:Product)
  RETURN p.product_name

Rules:
- Use read-only Cypher only (MATCH/RETURN/WITH). Never use CREATE, MERGE, DELETE, SET, or REMOVE.
- Filter customers by customer_id, not company_name.
- Use integer literals (no quotes) for order_id and product_id.
"""

SCHEMA_CONTEXT = (
    _SCHEMA_CONTEXT_BASE.rstrip() + "\n" + unloaded_labels_rule_line() + "\n"
).strip()

MAX_CYPHER_RETRIES = 1

class NLToCypherAgent:
    def __init__(self, max_results: int = 100):
        self.client = get_anthropic_client()
        self.max_results = max_results
        self.driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
        )

    def close(self):
        self.driver.close()

    def generate_cypher(self, question: str) -> str:
        cypher, _, _ = self._generate_cypher_with_usage(question)
        return cypher

    def _generate_cypher_with_usage(self, question: str):
        with measure_ms() as timing:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=300,
                temperature=0,
                messages=[{
                    "role": "user",
                    "content": f"""{SCHEMA_CONTEXT}

Write ONLY a read-only Cypher query (no explanation, no markdown fences) that answers this question:
{question}"""
                }]
            )
        cypher = strip_markdown_fences(response.content[0].text.strip())
        cypher = validate_read_only_cypher(cypher)
        cypher = enforce_result_limit(cypher, self.max_results)
        usage = usage_from_response(response, step="cypher_generation", model=MODEL)
        return cypher, usage, timing["ms"]

    def repair_cypher(self, question: str, failed_cypher: str, error: str) -> str:
        cypher, _, _ = self._repair_cypher_with_usage(question, failed_cypher, error)
        return cypher

    def _repair_cypher_with_usage(self, question: str, failed_cypher: str, error: str):
        with measure_ms() as timing:
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=300,
                temperature=0,
                messages=[{
                    "role": "user",
                    "content": f"""{SCHEMA_CONTEXT}

The following read-only Cypher query failed when executed against Neo4j.

Question: {question}

Failed query:
{failed_cypher}

Neo4j error:
{error}

Write ONLY a corrected read-only Cypher query (no explanation, no markdown fences) that answers the question.
The corrected query must still obey all schema and security rules."""
                }]
            )
        cypher = strip_markdown_fences(response.content[0].text.strip())
        cypher = validate_read_only_cypher(cypher)
        cypher = enforce_result_limit(cypher, self.max_results)
        usage = usage_from_response(response, step="cypher_repair", model=MODEL)
        return cypher, usage, timing["ms"]

    def run_query(self, cypher: str):
        safe_cypher = validate_read_only_cypher(cypher)
        safe_cypher = enforce_result_limit(safe_cypher, self.max_results)
        with measure_ms() as timing:
            with self.driver.session() as session:
                result = session.run(safe_cypher)
                rows = [record.data() for record in result]
                if len(rows) > self.max_results:
                    rows = rows[: self.max_results]
        return rows, timing["ms"]

    def answer(self, question: str):
        cypher = None
        repair_attempts = 0
        usage_calls = []
        latency_ms = {
            "cypher_generation": 0.0,
            "cypher_repair": 0.0,
            "neo4j_execution": 0.0,
        }
        try:
            cypher, gen_usage, gen_ms = self._generate_cypher_with_usage(question)
            usage_calls.append(gen_usage)
            latency_ms["cypher_generation"] = gen_ms
            last_error = None
            for attempt in range(MAX_CYPHER_RETRIES + 1):
                try:
                    results, neo4j_ms = self.run_query(cypher)
                    latency_ms["neo4j_execution"] += neo4j_ms
                    return {
                        "question": question,
                        "cypher": cypher,
                        "results": results,
                        "error": None,
                        "repair_attempts": repair_attempts,
                        "token_usage_calls": usage_calls,
                        "latency_ms": latency_ms,
                    }
                except Exception as e:
                    last_error = str(e)
                    if attempt >= MAX_CYPHER_RETRIES:
                        raise
                    cypher, repair_usage, repair_ms = self._repair_cypher_with_usage(
                        question, cypher, last_error
                    )
                    usage_calls.append(repair_usage)
                    latency_ms["cypher_repair"] += repair_ms
                    repair_attempts += 1
        except Exception as e:
            return {
                "question": question,
                "cypher": cypher,
                "results": None,
                "error": str(e),
                "repair_attempts": repair_attempts,
                "token_usage_calls": usage_calls,
                "latency_ms": latency_ms,
            }


if __name__ == "__main__":
    agent = NLToCypherAgent()
    test_question = "Which customers have filed more than one support ticket?"
    result = agent.answer(test_question)
    print(result)
    agent.close()
