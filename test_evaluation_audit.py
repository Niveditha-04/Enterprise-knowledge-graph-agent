"""Tests for evaluation ground-truth audit (no Anthropic API)."""

import json
from pathlib import Path

import pytest

from eval.answer_checks import contains_expected
from eval.evaluation_audit import audit_evaluation_set


@pytest.fixture(scope="module")
def evaluation_items():
    path = Path(__file__).parent / "eval" / "evaluation_set.json"
    return json.loads(path.read_text())


def test_all_ground_truths_independently_verified():
    report = audit_evaluation_set()
    print("\n" + json.dumps(report["methodology_notes"], indent=2))
    assert report["ground_truth_failed"] == 0, report["verifications"]
    assert report["total_items"] >= 23
    assert report["scored_items"] >= 21
    assert report["ambiguous_items"] >= 2
    assert report["unsupported_items"] >= 2


def test_substring_false_positive_example_documented():
    """Short numeric expected values can match unrelated numbers in longer ids."""
    assert contains_expected("order 10248", "1")
    assert contains_expected("order 10248", "10248")


def test_hybrid_chai_damaged_accepts_any_valid_customer_id():
    from eval.answer_checks import check_item

    orch = {
        "route": "BOTH",
        "graph_result": {
            "results": [{"c.customer_id": "SAVEA", "c.company_name": "Save-a-lot Markets"}],
            "error": None,
        },
        "ticket_result": {"documents": [["Customer SAVEA escalated — product arrived damaged"]]},
        "synthesis": {"answer": "SAVEA ordered Chai and filed a damaged-product ticket."},
    }
    item = {
        "accepted_answer_contains": ["BERGS", "SAVEA", "HILAA"],
        "score_type": "substring",
    }
    checks = check_item(orch, {}, item)
    assert checks["hybrid_match"] is True
    assert checks["graph_branch_match"] is True


def test_evaluation_set_has_required_metadata(evaluation_items):
    for item in evaluation_items:
        assert "id" in item
        assert "ground_truth" in item
        assert "category" in item
        assert "scored" in item
