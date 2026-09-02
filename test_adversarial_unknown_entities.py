"""Section 21 adversarial tests — unknown entities and empty ticket evidence.

Earlier adversarial cases (injection, Cypher safety, API validation) are inventoried in README Section 21.
"""

import json

import pytest

from agent.nl_to_cypher import NLToCypherAgent
from agent.orchestrator import HybridOrchestrator
from agent.synthesis import indicates_insufficient_evidence, synthesize_answer


@pytest.fixture(scope="module")
def graph_agent():
    agent = NLToCypherAgent()
    yield agent
    agent.close()


@pytest.fixture(scope="module")
def orchestrator():
    instance = HybridOrchestrator()
    yield instance
    instance.close()


def test_unknown_customer_cypher_returns_zero_not_null(graph_agent):
    """Graph layer: unknown customer_id yields count=0 (relationship), not an error."""
    result = graph_agent.answer("How many orders has customer ZZZZZ placed?")
    assert result["error"] is None
    assert result["results"] == [{"order_count": 0}]
    assert "ZZZZZ" in (result.get("cypher") or "")


@pytest.mark.parametrize(
    "question",
    [
        "Which products are in order 99999999?",
        "What is the name of product with product ID 999999?",
        "What country is customer ZZZZZ from?",
    ],
)
def test_unknown_entity_full_pipeline_refuses(orchestrator, question):
    result = orchestrator.answer(question)
    synthesis = result["synthesis"]
    graph = result.get("graph_result") or {}

    print(
        f"\n--- Unknown entity: {question} ---\n"
        f"graph_results={graph.get('results')}\n"
        f"synthesis={synthesis['answer']}\n"
        f"insufficient={synthesis['insufficient_evidence']}"
    )

    assert graph.get("error") is None
    assert graph.get("results") == []
    assert synthesis["insufficient_evidence"] is True
    assert indicates_insufficient_evidence(synthesis["answer"])


def test_unknown_customer_order_count_misleading_zero(orchestrator):
    """Section 21 finding: zero-count on unknown customer reads as a factual answer (known gap)."""
    result = orchestrator.answer("How many orders has customer ZZZZZ placed?")
    graph = result.get("graph_result") or {}
    synthesis = result["synthesis"]

    print(
        "\n--- Unknown customer order count (known gap) ---\n"
        f"graph_results={json.dumps(graph.get('results'))}\n"
        f"synthesis={synthesis['answer']}\n"
        f"insufficient={synthesis['insufficient_evidence']}"
    )

    assert graph.get("results") == [{"order_count": 0}]
    # Document current behavior honestly — same misleading-zero class as Employee/Invoice (Section 12).
    assert synthesis["insufficient_evidence"] is False
    assert "0 order" in synthesis["answer"].lower()


def test_empty_ticket_chunks_refuses():
    result = synthesize_answer(
        question="Which tickets mention damaged products?",
        graph_result=None,
        ticket_chunks=[],
    )
    print(f"\n--- Empty ticket chunks ---\n{result['answer']}")
    assert result["insufficient_evidence"] is True
    assert indicates_insufficient_evidence(result["answer"])


def test_malformed_empty_ticket_result_refuses():
    result = synthesize_answer(
        question="Summarize support tickets about delays.",
        graph_result=None,
        ticket_result={"ids": [[]], "documents": [[]], "metadatas": [[]]},
    )
    print(f"\n--- Empty Chroma-shaped ticket_result ---\n{result['answer']}")
    assert result["insufficient_evidence"] is True
    assert indicates_insufficient_evidence(result["answer"])


def test_blank_ticket_text_refuses():
    result = synthesize_answer(
        question="What did the customer report?",
        graph_result=None,
        ticket_chunks=[
            {"ticket_id": "TCK-EMPTY", "text": "   ", "customer_id": "VINET", "order_id": 1}
        ],
    )
    print(f"\n--- Blank ticket body ---\n{result['answer']}")
    assert result["insufficient_evidence"] is True
    assert indicates_insufficient_evidence(result["answer"])
