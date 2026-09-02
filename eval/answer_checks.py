"""Structured answer checking for evaluation."""

import json
from typing import Any


def flatten_values(obj: Any) -> list[str]:
    """Collect scalar values from nested dict/list structures."""
    values: list[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            values.extend(flatten_values(v))
    elif isinstance(obj, list):
        for item in obj:
            values.extend(flatten_values(item))
    elif obj is not None:
        values.append(str(obj))
    return values


def graph_answer_text(graph_result: dict | None) -> str:
    if not graph_result:
        return ""
    if graph_result.get("error"):
        return graph_result["error"]
    parts = flatten_values(graph_result.get("results"))
    return " ".join(parts)


def ticket_answer_text(ticket_result: dict | None) -> str:
    if not ticket_result:
        return ""
    docs = ticket_result.get("documents") or []
    if docs and isinstance(docs[0], list):
        return " ".join(docs[0])
    return json.dumps(ticket_result, ensure_ascii=False)


def hybrid_answer_text(orchestrator_result: dict) -> str:
    parts = []
    if "graph_result" in orchestrator_result:
        parts.append(graph_answer_text(orchestrator_result["graph_result"]))
    if "ticket_result" in orchestrator_result:
        parts.append(ticket_answer_text(orchestrator_result["ticket_result"]))
    return " ".join(parts)


def contains_expected(text: str, expected: str) -> bool:
    return expected.lower() in text.lower()


def contains_any_expected(text: str, expected_values: list[str]) -> bool:
    return any(contains_expected(text, value) for value in expected_values)


def synthesis_answer_text(orchestrator_result: dict) -> str:
    synthesis = orchestrator_result.get("synthesis") or {}
    return str(synthesis.get("answer") or "")


def check_refusal(text: str, refusal_substrings: list[str]) -> bool:
    lowered = text.lower()
    return any(fragment.lower() in lowered for fragment in refusal_substrings)


def check_item(
    orchestrator_result: dict,
    flat_baseline_result: dict,
    item: dict,
    *,
    ticket_baseline_result: dict | None = None,
) -> dict:
    score_type = item.get("score_type", "substring")
    expected = item.get("expected_answer_contains")
    accepted = item.get("accepted_answer_contains") or []
    refusal_substrings = item.get("refusal_substrings") or []

    def substring_match(text: str) -> bool:
        if accepted:
            return contains_any_expected(text, accepted)
        if expected:
            return contains_expected(text, expected)
        return False

    hybrid_text = hybrid_answer_text(orchestrator_result)
    synthesis_text = synthesis_answer_text(orchestrator_result)
    flat_baseline_text = ticket_answer_text(flat_baseline_result) if flat_baseline_result else ""
    ticket_baseline_text = (
        ticket_answer_text(ticket_baseline_result) if ticket_baseline_result else ""
    )

    graph_only_text = graph_answer_text(orchestrator_result.get("graph_result"))
    ticket_only_text = ticket_answer_text(orchestrator_result.get("ticket_result"))

    if score_type == "refusal":
        hybrid_ok = check_refusal(synthesis_text or hybrid_text, refusal_substrings)
        flat_ok = check_refusal(flat_baseline_text, refusal_substrings)
        ticket_ok = check_refusal(ticket_baseline_text, refusal_substrings)
        graph_ok = check_refusal(graph_only_text, refusal_substrings)
        ticket_branch_ok = check_refusal(ticket_only_text, refusal_substrings)
    else:
        hybrid_ok = substring_match(hybrid_text)
        flat_ok = substring_match(flat_baseline_text)
        ticket_ok = substring_match(ticket_baseline_text)
        graph_ok = substring_match(graph_only_text)
        ticket_branch_ok = substring_match(ticket_only_text)

    return {
        "hybrid_match": hybrid_ok,
        "flat_baseline_match": flat_ok,
        "ticket_baseline_match": ticket_ok,
        "graph_branch_match": graph_ok,
        "ticket_branch_match": ticket_branch_ok,
        "synthesis_match": hybrid_ok if score_type == "refusal" else substring_match(synthesis_text),
        "route": orchestrator_result.get("route"),
        "score_type": score_type,
    }
