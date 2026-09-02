"""API security tests with reproducible HTTP transcripts."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agent.orchestrator import HybridOrchestrator
from api import main as api_main
from api.main import app
from api.security import GENERIC_INTERNAL_ERROR, GRAPH_UNAVAILABLE_ERROR

CLIENT = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def ensure_orchestrator():
    if api_main.orchestrator is None:
        api_main.orchestrator = HybridOrchestrator()
    yield
    if api_main.orchestrator is not None:
        api_main.orchestrator.close()
        api_main.orchestrator = None


def test_empty_question_returns_422():
    response = CLIENT.post("/ask", json={"text": ""})
    print("\n--- Empty question ---")
    print("curl -X POST http://127.0.0.1:8000/ask -H 'Content-Type: application/json' -d '{\"text\": \"\"}'")
    print(f"HTTP {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "string_too_short"


def test_oversized_question_returns_422():
    payload = {"text": "A" * 50_000}
    response = CLIENT.post("/ask", json=payload)
    print("\n--- Oversized question (50,000 chars; max=2000) ---")
    print("curl -X POST http://127.0.0.1:8000/ask -H 'Content-Type: application/json' -d @long.json")
    print(f"HTTP {response.status_code}")
    body = response.json()
    print(json.dumps({"detail": body["detail"][0]["type"], "msg": body["detail"][0]["msg"]}, indent=2))
    assert response.status_code == 422
    assert body["detail"][0]["type"] == "string_too_long"


def test_malformed_body_returns_422():
    wrong_field = CLIENT.post("/ask", json={"question": "hello"})
    missing_field = CLIENT.post("/ask", json={})
    print("\n--- Malformed body (wrong field) ---")
    print("curl -X POST http://127.0.0.1:8000/ask -H 'Content-Type: application/json' -d '{\"question\": \"hello\"}'")
    print(f"HTTP {wrong_field.status_code}")
    print(json.dumps(wrong_field.json(), indent=2))
    print("\n--- Malformed body (missing field) ---")
    print("curl -X POST http://127.0.0.1:8000/ask -H 'Content-Type: application/json' -d '{}'")
    print(f"HTTP {missing_field.status_code}")
    print(json.dumps(missing_field.json(), indent=2))
    assert wrong_field.status_code == 422
    assert missing_field.status_code == 422


def test_internal_error_does_not_leak_secrets(monkeypatch):
    def boom(_question: str):
        raise RuntimeError(
            "SECRET_PATH=/Users/demo/project/.env NEO4J_PASSWORD=supersecret "
            "Traceback (most recent call last): File '/Users/demo/project/api/main.py'"
        )

    monkeypatch.setattr(api_main.orchestrator, "answer", boom)
    response = CLIENT.post("/ask", json={"text": "How many customers are there?"})
    print("\n--- Internal error (simulated upstream failure) ---")
    print("curl -X POST http://127.0.0.1:8000/ask -H 'Content-Type: application/json' -d '{\"text\": \"How many customers are there?\"}'")
    print(f"HTTP {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    body = response.text.lower()
    assert response.status_code == 500
    assert response.json()["detail"] == GENERIC_INTERNAL_ERROR
    assert "supersecret" not in body
    assert "/users/demo" not in body
    assert "traceback" not in body


def test_graph_dependency_error_is_sanitized(monkeypatch):
    def graph_down(_question: str):
        return {
            "question": _question,
            "route": "GRAPH",
            "graph_result": {
                "question": _question,
                "cypher": "MATCH (c:Customer) RETURN count(c)",
                "results": None,
                "error": (
                    "Couldn't connect to localhost:19999: Connection refused "
                    "/Users/demo/project/agent/nl_to_cypher.py NEO4J_PASSWORD=secret"
                ),
                "repair_attempts": 0,
            },
            "synthesis": {
                "answer": "There is insufficient evidence to answer.",
                "evidence_sufficient": False,
                "insufficient_evidence": True,
                "graph_evidence_used": False,
                "ticket_chunks_used": 0,
            },
        }

    monkeypatch.setattr(api_main.orchestrator, "answer", graph_down)
    response = CLIENT.post("/ask", json={"text": "How many customers are there?"})
    print("\n--- Graph dependency unavailable (sanitized client response) ---")
    print(f"HTTP {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    assert response.status_code == 200
    assert response.json()["graph_result"]["error"] == GRAPH_UNAVAILABLE_ERROR
    assert "secret" not in response.text.lower()
    assert "/users/demo" not in response.text.lower()


def test_exception_leak_before_after_transcripts(capsys):
    """Document real before/after transcripts for the credential-leak fix."""
    from eval.capture_exception_leak_transcripts import capture_after_response, capture_before_response

    before = capture_before_response()
    after, generic_error = capture_after_response()

    print("\n=== BEFORE (old handler: detail=str(exc)) ===")
    print(f"HTTP {before.status_code}")
    print(json.dumps(before.json(), indent=2))
    print("\n=== AFTER (hardened api/security.py) ===")
    print(f"HTTP {after.status_code}")
    print(json.dumps(after.json(), indent=2))

    assert before.status_code == 500
    assert "NEO4J_PASSWORD=supersecret" in before.json()["detail"]
    assert "/Users/nivedithabalasubramanian" in before.json()["detail"]
    assert after.status_code == 500
    assert after.json()["detail"] == generic_error
    assert "supersecret" not in after.text
