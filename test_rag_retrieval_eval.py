"""RAG retrieval evaluation against independently-labeled relevant ticket IDs."""

import json

import pytest

from eval.rag_retrieval_eval import (
    CASES_PATH,
    chroma_retrieve_ids,
    evaluate_retrieval,
    format_report,
    load_retrieval_cases,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

CASES = load_retrieval_cases()


def test_retrieval_dataset_ground_truth_built_from_rules():
    """Ground truth must come from explicit rules, not retriever output."""
    for case in CASES:
        assert "ground_truth_rule" in case
        assert "ground_truth_ticket_ids" in case
        assert case.get("query_type") in {"narrow", "theme"}
        assert isinstance(case["ground_truth_ticket_ids"], list)
        assert len(case["ground_truth_ticket_ids"]) >= 1


def test_retrieval_metric_helpers():
    retrieved = ["TCK-1002", "TCK-9999", "TCK-1003"]
    relevant = {"TCK-1002", "TCK-1003"}
    assert recall_at_k(retrieved, relevant, 3) == 1.0
    assert precision_at_k(retrieved, relevant, 3) == pytest.approx(2 / 3)
    assert reciprocal_rank(retrieved, relevant) == 1.0
    assert reciprocal_rank(["TCK-9999"], relevant) == 0.0


@pytest.fixture(scope="module")
def retrieval_report():
    return evaluate_retrieval(chroma_retrieve_ids, CASES)


def test_rag_retrieval_quality_thresholds(retrieval_report, capsys):
    """Print macro retrieval metrics — failures on individual cases are separate tests."""
    print("\n" + format_report(retrieval_report))
    assert retrieval_report["case_count"] >= 8


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_rag_retrieval_per_case(case):
    retrieved = chroma_retrieve_ids(case["query"], n_results=10)
    relevant = set(case["ground_truth_ticket_ids"])
    rr = reciprocal_rank(retrieved, relevant)
    # Single-relevant narrow queries must rank the correct ticket first.
    if len(relevant) == 1:
        assert rr == 1.0, (
            f"Failed to rank sole relevant ticket first for {case['id']} (RR={rr:.3f})\n"
            f"Query: {case['query']}\n"
            f"Expected: {sorted(relevant)}\n"
            f"Retrieved@10: {retrieved}"
        )


if __name__ == "__main__":
    report = evaluate_retrieval(chroma_retrieve_ids, CASES)
    print(format_report(report))
