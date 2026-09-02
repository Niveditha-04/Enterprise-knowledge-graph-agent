"""Semantic correctness tests for NL→Cypher agent.

Ground truth in eval/nl_to_cypher_semantic_cases.json was verified independently
against Neo4j using the ground_truth_query fields before these tests were written.
"""

import json
from pathlib import Path

import pytest

from agent.nl_to_cypher import NLToCypherAgent
from eval.nl_to_cypher_semantic_checks import is_unsupported_response, semantic_match

CASES_PATH = Path(__file__).parent / "eval" / "nl_to_cypher_semantic_cases.json"
CASES = json.loads(CASES_PATH.read_text())

SEMANTIC_CASES = [c for c in CASES if c["expected"]["type"] not in {"unsupported", "ambiguous"}]
UNSUPPORTED_CASES = [c for c in CASES if c["expected"]["type"] == "unsupported"]
AMBIGUOUS_CASES = [c for c in CASES if c["expected"]["type"] == "ambiguous"]


@pytest.fixture(scope="module")
def agent():
    instance = NLToCypherAgent()
    yield instance
    instance.close()


@pytest.mark.parametrize("case", SEMANTIC_CASES, ids=[c["id"] for c in SEMANTIC_CASES])
def test_nl_to_cypher_semantic_correctness(agent, case):
    result = agent.answer(case["question"])
    assert result.get("error") is None, f"Query failed: {result.get('error')}\nCypher: {result.get('cypher')}"
    assert semantic_match(result.get("results"), case["expected"]), (
        f"Semantic mismatch for {case['id']}\n"
        f"Question: {case['question']}\n"
        f"Expected: {case['expected']}\n"
        f"Cypher: {result.get('cypher')}\n"
        f"Results: {result.get('results')}"
    )


@pytest.mark.parametrize("case", UNSUPPORTED_CASES, ids=[c["id"] for c in UNSUPPORTED_CASES])
def test_nl_to_cypher_unsupported_questions(agent, case):
    result = agent.answer(case["question"])
    assert is_unsupported_response(result), (
        f"Unsupported question produced a fabricated/non-empty answer\n"
        f"Question: {case['question']}\n"
        f"Cypher: {result.get('cypher')}\n"
        f"Results: {result.get('results')}\n"
        f"Error: {result.get('error')}"
    )


@pytest.mark.parametrize("case", AMBIGUOUS_CASES, ids=[c["id"] for c in AMBIGUOUS_CASES])
def test_nl_to_cypher_ambiguous_questions_execute(agent, case, capsys):
    result = agent.answer(case["question"])
    assert result.get("error") is None, f"Ambiguous question failed to execute: {result.get('error')}"
    print(
        f"AMBIGUOUS INTERPRETATION [{case['id']}]: "
        f"cypher={result.get('cypher')!r} results={result.get('results')!r}"
    )
