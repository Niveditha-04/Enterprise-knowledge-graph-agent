from agent.nl_to_cypher import NLToCypherAgent

def test_agent_generates_valid_cypher():
    agent = NLToCypherAgent()
    result = agent.answer("How many orders does each customer have?")
    assert result["error"] is None, f"Query failed: {result['error']}"
    assert result["results"] is not None
    agent.close()
