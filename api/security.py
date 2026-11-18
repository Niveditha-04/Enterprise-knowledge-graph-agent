from __future__ import annotations

import logging
import re
from typing import Any

from agent.errors import TICKET_INDEX_UNAVAILABLE_ERROR

logger = logging.getLogger(__name__)

GENERIC_INTERNAL_ERROR = "An internal error occurred while processing the request."
GRAPH_UNAVAILABLE_ERROR = "Graph database is currently unavailable."

_PATH_PATTERN = re.compile(r"(/Users/|/home/|\\)[^\s\"']+")
_SECRET_PATTERN = re.compile(
    r"(password|api[_-]?key|secret|token)\s*[=:]\s*\S+",
    re.IGNORECASE,
)


def sanitize_error_message(message: str | None, *, fallback: str = GENERIC_INTERNAL_ERROR) -> str:
    if not message:
        return fallback
    if "Traceback (most recent call last)" in message:
        return fallback
    cleaned = _PATH_PATTERN.sub("[redacted-path]", message)
    cleaned = _SECRET_PATTERN.sub("[redacted-secret]", cleaned)
    if len(cleaned) > 300:
        cleaned = cleaned[:300] + "..."
    return cleaned


def sanitize_graph_result(graph_result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not graph_result:
        return graph_result
    sanitized = dict(graph_result)
    if sanitized.get("error"):
        lowered = sanitized["error"].lower()
        if "connection refused" in lowered or "couldn't connect" in lowered:
            sanitized["error"] = GRAPH_UNAVAILABLE_ERROR
        else:
            sanitized["error"] = sanitize_error_message(sanitized["error"])
    return sanitized


def sanitize_ticket_result(ticket_result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not ticket_result:
        return ticket_result
    if ticket_result.get("error"):
        return {"error": TICKET_INDEX_UNAVAILABLE_ERROR}
    return ticket_result


def sanitize_orchestrator_result(result: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(result)
    if "graph_result" in sanitized:
        sanitized["graph_result"] = sanitize_graph_result(sanitized.get("graph_result"))
    if "ticket_result" in sanitized:
        sanitized["ticket_result"] = sanitize_ticket_result(sanitized.get("ticket_result"))
    return sanitized
