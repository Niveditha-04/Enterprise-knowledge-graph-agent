"""Extract token usage from Anthropic SDK responses."""

from __future__ import annotations

from typing import Any


def usage_from_response(response: Any, *, step: str, model: str) -> dict[str, int | str]:
    usage = response.usage
    return {
        "step": step,
        "model": model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
    }


def aggregate_usage(calls: list[dict[str, int | str]]) -> dict[str, Any]:
    total_input = sum(int(c["input_tokens"]) for c in calls)
    total_output = sum(int(c["output_tokens"]) for c in calls)
    return {
        "calls": calls,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
    }
