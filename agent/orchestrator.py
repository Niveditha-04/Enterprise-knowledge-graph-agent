import logging
import time

from agent.errors import AIServiceUnavailableError, anthropic_unavailable_error
from agent.nl_to_cypher import NLToCypherAgent
from agent.anthropic_client import get_anthropic_client
from agent.latency import measure_ms
from agent.synthesis import synthesize_answer
from agent.token_usage import aggregate_usage, usage_from_response
from agent.errors import TICKET_INDEX_UNAVAILABLE_ERROR
from rag.query_index import query_tickets
from dotenv import load_dotenv

load_dotenv(override=True)

MODEL = "claude-sonnet-4-5"
logger = logging.getLogger(__name__)


class HybridOrchestrator:
    def __init__(self):
        self.client = get_anthropic_client()
        self.graph_agent = NLToCypherAgent()

    def close(self):
        self.graph_agent.close()

    def _raise_if_anthropic_unavailable(self, exc: BaseException) -> None:
        mapped = anthropic_unavailable_error(exc)
        if mapped is not None:
            raise mapped from exc
        raise exc

    def classify_question(self, question: str) -> tuple[str, dict, float]:
        try:
            with measure_ms() as timing:
                response = self.client.messages.create(
                    model=MODEL,
                    max_tokens=10,
                    temperature=0,
                    messages=[{
                        "role": "user",
                        "content": f"""Classify this question as one of: GRAPH, TICKETS, BOTH.
GRAPH = answerable from structured graph records (customers, orders, products, support ticket counts/links).
TICKETS = answerable only from free-text support ticket content.
BOTH = needs both structured graph data and ticket text.

Question: {question}
Answer with exactly one word: GRAPH, TICKETS, or BOTH."""
                    }]
                )
        except Exception as exc:
            self._raise_if_anthropic_unavailable(exc)
        route = response.content[0].text.strip().upper()
        for valid in ("GRAPH", "TICKETS", "BOTH"):
            if valid in route:
                return valid, usage_from_response(response, step="routing", model=MODEL), timing["ms"]
        resolved = route.split()[0] if route else "GRAPH"
        return resolved, usage_from_response(response, step="routing", model=MODEL), timing["ms"]

    def answer(self, question: str):
        started = time.perf_counter()
        try:
            classification, routing_usage, routing_ms = self.classify_question(question)
        except AIServiceUnavailableError:
            raise
        except Exception as exc:
            self._raise_if_anthropic_unavailable(exc)

        result = {"question": question, "route": classification}
        usage_calls = [routing_usage]
        latency_ms = {
            "routing": routing_ms,
            "cypher_generation": None,
            "cypher_repair": None,
            "neo4j_execution": None,
            "chroma_retrieval": None,
            "synthesis": None,
        }

        graph_result = None
        ticket_result = None

        if classification in ("GRAPH", "BOTH"):
            try:
                graph_result = self.graph_agent.answer(question)
            except Exception as exc:
                self._raise_if_anthropic_unavailable(exc)
            result["graph_result"] = graph_result
            usage_calls.extend(graph_result.get("token_usage_calls", []))
            graph_latency = graph_result.get("latency_ms", {})
            latency_ms["cypher_generation"] = graph_latency.get("cypher_generation")
            latency_ms["cypher_repair"] = graph_latency.get("cypher_repair")
            latency_ms["neo4j_execution"] = graph_latency.get("neo4j_execution")
        if classification in ("TICKETS", "BOTH"):
            with measure_ms() as chroma_timing:
                try:
                    ticket_result = query_tickets(question)
                except Exception as exc:
                    logger.warning("Chroma ticket retrieval failed: %s", exc)
                    ticket_result = {"error": TICKET_INDEX_UNAVAILABLE_ERROR}
            latency_ms["chroma_retrieval"] = chroma_timing["ms"]
            result["ticket_result"] = ticket_result

        try:
            synthesis = synthesize_answer(
                question=question,
                graph_result=graph_result,
                ticket_result=ticket_result,
            )
        except Exception as exc:
            self._raise_if_anthropic_unavailable(exc)

        result["synthesis"] = synthesis
        usage_calls.append(synthesis.pop("token_usage"))
        latency_ms["synthesis"] = synthesis.pop("latency_ms")
        result["token_usage"] = aggregate_usage(usage_calls)
        latency_ms["total"] = (time.perf_counter() - started) * 1000
        result["latency_ms"] = latency_ms

        return result


if __name__ == "__main__":
    orchestrator = HybridOrchestrator()
    print(orchestrator.answer("Which customers had orders delayed due to carrier issues?"))
    orchestrator.close()
