import pytest

from agent.nl_to_cypher import NLToCypherAgent

pytestmark = [pytest.mark.neo4j, pytest.mark.anthropic]


def test_agent_generates_valid_cypher():
    agent = NLToCypherAgent()
    result = agent.answer("How many orders does each customer have?")
    assert result["error"] is None, f"Query failed: {result['error']}"
    assert result["results"] is not None
    agent.close()
