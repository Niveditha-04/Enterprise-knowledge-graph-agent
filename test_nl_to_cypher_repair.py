"""Tests for bounded NL→Cypher repair loop."""

from unittest.mock import patch

import pytest

from agent.nl_to_cypher import MAX_CYPHER_RETRIES, NLToCypherAgent


@pytest.fixture
def agent():
    instance = NLToCypherAgent()
    yield instance
    instance.close()


def test_repair_recovers_from_neo4j_syntax_error(agent):
    """First execution fails with a Neo4j syntax error; repair should recover."""
    run_calls = {"count": 0}
    real_run_query = agent.run_query

    def flaky_run_query(cypher):
        run_calls["count"] += 1
        if run_calls["count"] == 1:
            raise Exception(
                "Invalid input 'RETURN': expected 'ORDER BY', 'CALL', 'CREATE'..."
            )
        return real_run_query(cypher)

    with patch.object(agent, "run_query", side_effect=flaky_run_query):
        result = agent.answer("How many customers are there?")

    assert result["error"] is None, f"Repair failed: {result}"
    assert result["results"] is not None
    assert result["repair_attempts"] == 1
    assert run_calls["count"] == 2


def test_repair_fails_after_max_retries(agent):
    """If repair cannot fix the query, return an error after MAX_CYPHER_RETRIES."""
    def always_fail(cypher):
        raise Exception("Invalid syntax at line 1")

    with patch.object(agent, "generate_cypher", return_value="MATCH (c:Customer RETURN c"):
        with patch.object(agent, "repair_cypher", return_value="MATCH (c:Customer RETURN c"):
            with patch.object(agent, "run_query", side_effect=always_fail):
                result = agent.answer("How many customers are there?")

    assert result["error"] is not None
    assert result["results"] is None
    assert result["repair_attempts"] == MAX_CYPHER_RETRIES


def test_malicious_repair_attempt_is_blocked(agent):
    """A repair that tries to return a write query must be blocked by validation."""
    run_calls = {"count": 0}
    real_run_query = agent.run_query

    def first_fails_then_validate(cypher):
        run_calls["count"] += 1
        if run_calls["count"] == 1:
            raise Exception("Invalid syntax")
        return real_run_query(cypher)

    fake_usage = {"step": "test", "input_tokens": 0, "output_tokens": 0}

    with patch.object(
        agent,
        "_generate_cypher_with_usage",
        return_value=("MATCH (c:Customer RETURN c", fake_usage, 0.0),
    ):
        with patch.object(
            agent,
            "_repair_cypher_with_usage",
            return_value=("MATCH (n) DETACH DELETE n", fake_usage, 0.0),
        ):
            with patch.object(agent, "run_query", side_effect=first_fails_then_validate):
                result = agent.answer("How many customers are there?")

    assert result["error"] is not None
    assert "Forbidden" in result["error"]
    assert result["results"] is None
    assert run_calls["count"] == 2
