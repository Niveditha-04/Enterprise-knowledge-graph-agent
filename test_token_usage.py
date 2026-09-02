"""Token usage instrumentation from real Anthropic SDK response fields."""

import json

import pytest

from agent.orchestrator import HybridOrchestrator


@pytest.fixture(scope="module")
def orchestrator():
    instance = HybridOrchestrator()
    yield instance
    instance.close()


def test_token_usage_captured_from_real_api_responses(orchestrator, capsys):
    result = orchestrator.answer("How many customers are there?")

    print("\n--- Token usage (from Anthropic SDK response.usage) ---")
    print(json.dumps(result["token_usage"], indent=2))

    usage = result["token_usage"]
    assert usage["total_input_tokens"] > 0
    assert usage["total_output_tokens"] > 0
    assert usage["total_tokens"] == usage["total_input_tokens"] + usage["total_output_tokens"]

    steps = {call["step"] for call in usage["calls"]}
    assert "routing" in steps
    assert "cypher_generation" in steps
    assert "synthesis" in steps

    for call in usage["calls"]:
        assert call["input_tokens"] > 0
        assert call["output_tokens"] >= 0
        assert call["model"] == "claude-sonnet-4-5"
        assert isinstance(call["input_tokens"], int)
        assert isinstance(call["output_tokens"], int)
