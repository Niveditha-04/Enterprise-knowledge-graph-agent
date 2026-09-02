"""Synthesis guard for zero-count queries against unloaded graph labels (Employee, Invoice)."""

import pytest

from agent.orchestrator import HybridOrchestrator
from agent.synthesis import (
    indicates_insufficient_evidence,
    is_misleading_zero_on_unpopulated_label,
    synthesize_answer,
)


def test_guard_detects_employee_zero_count_without_llm():
    graph_result = {
        "cypher": "MATCH (e:Employee)\nRETURN count(e) AS employee_count\nLIMIT 100",
        "results": [{"employee_count": 0}],
        "error": None,
    }
    misleading, label = is_misleading_zero_on_unpopulated_label(
        graph_result, "How many employees work at the company?"
    )
    assert misleading is True
    assert label == "Employee"


def test_guard_detects_invoice_proxy_count_without_llm():
    graph_result = {
        "cypher": "MATCH (o:Order)\nRETURN count(o) AS invoice_count\nLIMIT 100",
        "results": [{"invoice_count": 830}],
        "error": None,
    }
    misleading, label = is_misleading_zero_on_unpopulated_label(
        graph_result, "How many invoices are in the system?"
    )
    assert misleading is True
    assert label == "Invoice"


def test_guard_direct_synthesis_employee_zero_count():
    graph_result = {
        "cypher": "MATCH (e:Employee)\nRETURN count(e) AS employee_count",
        "results": [{"employee_count": 0}],
        "error": None,
    }
    result = synthesize_answer(
        question="How many employees work at the company?",
        graph_result=graph_result,
    )
    assert result["unpopulated_label_guard"] == "Employee"
    assert result["insufficient_evidence"] is True
    assert indicates_insufficient_evidence(result["answer"])


@pytest.mark.parametrize(
    "question",
    [
        "How many employees work at the company?",
        "How many invoices are in the system?",
    ],
)
def test_synthesis_refuses_unpopulated_label_zero_count(question):
    """Live end-to-end: NL→Cypher may return count=0 on unloaded labels; synthesis must refuse."""
    orchestrator = HybridOrchestrator()
    try:
        result = orchestrator.answer(question)
    finally:
        orchestrator.close()

    synthesis = result["synthesis"]
    graph = result.get("graph_result") or {}

    print(
        f"\n--- Unpopulated-label guard test ---\n"
        f"Question: {question}\n"
        f"Route: {result['route']}\n"
        f"Cypher:\n{graph.get('cypher')}\n"
        f"Graph results: {graph.get('results')}\n"
        f"Synthesis answer:\n{synthesis['answer']}\n"
        f"insufficient_evidence={synthesis['insufficient_evidence']}\n"
        f"unpopulated_label_guard={synthesis.get('unpopulated_label_guard')}"
    )

    assert synthesis.get("unpopulated_label_guard") in ("Employee", "Invoice"), (
        "Expected synthesis guard to trigger for unloaded label"
    )
    assert synthesis["insufficient_evidence"] is True
    assert indicates_insufficient_evidence(synthesis["answer"])
    lowered = synthesis["answer"].lower()
    assert "count is 0" not in lowered
    assert "count of 0" not in lowered
    assert "are 0 " not in lowered
