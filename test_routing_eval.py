"""Routing evaluation: independently-labeled expected routes vs classifier output.

Ground-truth routes in eval/routing_cases.json were assigned by reading each
question and reasoning about required data sources — not by running the router.
"""

import json

import pytest

from agent.orchestrator import HybridOrchestrator
from eval.routing_eval import (
    ROUTES,
    ambiguous_cases,
    clear_cases,
    evaluate_routing,
    format_report,
    load_routing_cases,
)

CASES = load_routing_cases()
CLEAR_CASES = clear_cases(CASES)
AMBIGUOUS_CASES = ambiguous_cases(CASES)


@pytest.fixture(scope="module")
def orchestrator():
    instance = HybridOrchestrator()
    yield instance
    instance.close()


@pytest.fixture(scope="module")
def routing_report(orchestrator):
    return evaluate_routing(orchestrator.classify_question, CASES)


def test_routing_dataset_has_required_coverage():
    by_expected: dict[str, int] = {r: 0 for r in ROUTES}
    adversarial = []
    for case in CLEAR_CASES:
        if case.get("adversarial"):
            adversarial.append(case)
            continue
        by_expected[case["expected_route"]] += 1
    for route, count in by_expected.items():
        assert 4 <= count <= 5, f"Expected 4-5 clear {route} cases, got {count}"
    assert 2 <= len(adversarial) <= 3


@pytest.mark.parametrize("case", CLEAR_CASES, ids=[c["id"] for c in CLEAR_CASES])
def test_routing_clear_cut_case(orchestrator, case):
    from eval.routing_eval import _predict_route

    predicted = _predict_route(orchestrator.classify_question, case["question"])
    for route in ROUTES:
        if route in predicted:
            predicted = route
            break
    assert predicted == case["expected_route"], (
        f"Routing mismatch for {case['id']}\n"
        f"Question: {case['question']}\n"
        f"Expected: {case['expected_route']}\n"
        f"Predicted: {predicted}\n"
        f"Rationale: {case.get('rationale', '')}"
    )


def test_routing_report_and_ambiguous_cases(orchestrator, routing_report, capsys):
    print("\n" + format_report(routing_report))

    for case in AMBIGUOUS_CASES:
        from eval.routing_eval import _predict_route

        predicted = _predict_route(orchestrator.classify_question, case["question"])
        for route in ROUTES:
            if route in predicted:
                predicted = route
                break
        print(
            f"AMBIGUOUS [{case['id']}]: predicted={predicted} "
            f"defensible={case.get('defensible_routes')} "
            f"rationale={case.get('rationale', '')}"
        )


if __name__ == "__main__":
    orch = HybridOrchestrator()
    report = evaluate_routing(orch.classify_question, CASES)
    print(format_report(report))
    orch.close()
