"""Error handling audit at external boundaries (Section 19).

Post-fix: Chroma degrades to HTTP 200 with ticket_result.error; Anthropic 529 → HTTP 503.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
from anthropic import APIStatusError
from fastapi.testclient import TestClient

from agent.errors import AI_SERVICE_UNAVAILABLE_MESSAGE, TICKET_INDEX_UNAVAILABLE_ERROR
from agent.nl_to_cypher import MAX_CYPHER_RETRIES, NLToCypherAgent
from agent.orchestrator import HybridOrchestrator
from agent.synthesis import synthesize_answer
from api import main as api_main
from api.main import app
from api.security import GENERIC_INTERNAL_ERROR, GRAPH_UNAVAILABLE_ERROR
from eval.api_pacing import EvaluationAbortedDueToRateLimit, run_with_pacing


def _api_529(*_args, **_kwargs) -> None:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(529, request=request, text="overloaded")
    raise APIStatusError("Overloaded", response=response, body={"error": {"type": "overloaded_error"}})


def audit_chroma_unavailable() -> dict[str, Any]:
    chroma_path = Path("chroma_db")
    backup = Path("chroma_db_audit_backup")
    if backup.exists():
        shutil.rmtree(backup)
    if chroma_path.exists():
        shutil.move(str(chroma_path), str(backup))

    result: dict[str, Any] = {}
    try:
        api_main.orchestrator = HybridOrchestrator()
        client = TestClient(app)
        try:
            resp = client.post(
                "/ask",
                json={"text": "Which support tickets mention damaged products?"},
            )
            body = resp.json()
            result["api"] = {
                "status_code": resp.status_code,
                "ticket_result_error": body.get("ticket_result", {}).get("error"),
                "synthesis_insufficient": body.get("synthesis", {}).get("insufficient_evidence"),
                "synthesis_answer": body.get("synthesis", {}).get("answer"),
            }
        finally:
            api_main.orchestrator.close()
            api_main.orchestrator = None
    finally:
        if backup.exists():
            if chroma_path.exists():
                shutil.rmtree(chroma_path)
            shutil.move(str(backup), str(chroma_path))

    result["expected"] = {
        "status_code": 200,
        "ticket_result_error": TICKET_INDEX_UNAVAILABLE_ERROR,
        "synthesis_insufficient": True,
    }
    return result


def audit_anthropic_529() -> dict[str, Any]:
    api_main.orchestrator = HybridOrchestrator()
    client = TestClient(app)
    try:
        with patch.object(api_main.orchestrator.client.messages, "create", side_effect=_api_529):
            resp = client.post("/ask", json={"text": "How many customers are there?"})
        out = {
            "api": {"status_code": resp.status_code, "body": resp.json()},
            "expected": {
                "status_code": 503,
                "detail": AI_SERVICE_UNAVAILABLE_MESSAGE,
            },
        }
    finally:
        api_main.orchestrator.close()
        api_main.orchestrator = None

    try:
        run_with_pacing(lambda: (_ for _ in ()).throw(_api_529()), max_attempts=2)
        out["eval_harness"] = {"raised": False}
    except EvaluationAbortedDueToRateLimit as exc:
        out["eval_harness"] = {"raised": True, "message": str(exc)}

    return out


def audit_malformed_cypher() -> dict[str, Any]:
    agent = NLToCypherAgent()
    try:
        with patch.object(agent, "generate_cypher", return_value="MATCH (c:Customer RETURN c"):
            with patch.object(agent, "repair_cypher", return_value="MATCH (c:Customer RETURN c"):
                with patch.object(
                    agent,
                    "run_query",
                    side_effect=Exception("Invalid input 'RETURN': expected 'ORDER BY'"),
                ):
                    graph = agent.answer("How many customers are there?")
    finally:
        agent.close()

    synthesis = synthesize_answer("How many customers are there?", graph_result=graph)
    return {
        "graph_result": {
            "error": graph.get("error"),
            "repair_attempts": graph.get("repair_attempts"),
        },
        "synthesis_insufficient": synthesis.get("insufficient_evidence"),
        "tests": "test_nl_to_cypher_repair.py",
        "max_cypher_retries": MAX_CYPHER_RETRIES,
    }


def build_report() -> dict[str, Any]:
    return {
        "chroma_unavailable": audit_chroma_unavailable(),
        "anthropic_529": audit_anthropic_529(),
        "malformed_cypher": audit_malformed_cypher(),
        "neo4j_unavailable": {
            "covered_in": "Section 9 / test_api_security.py",
            "graph_result_error": GRAPH_UNAVAILABLE_ERROR,
        },
        "before_fix_reference": {
            "chroma": {"status_code": 500, "detail": GENERIC_INTERNAL_ERROR},
            "anthropic_529": {"status_code": 500, "detail": GENERIC_INTERNAL_ERROR},
        },
    }


if __name__ == "__main__":
    report = build_report()
    print(json.dumps(report, indent=2))
    out = Path(__file__).parent / "error_boundary_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")
