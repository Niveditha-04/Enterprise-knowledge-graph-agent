"""Section 19/20 regression tests for graceful error-boundary degradation."""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from anthropic import APIStatusError
from fastapi.testclient import TestClient

from agent.errors import (
    AI_SERVICE_UNAVAILABLE_MESSAGE,
    TICKET_INDEX_UNAVAILABLE_ERROR,
)
from agent.orchestrator import HybridOrchestrator
from agent.synthesis import indicates_insufficient_evidence
from api import main as api_main
from api.main import app
from api.security import GENERIC_INTERNAL_ERROR
from eval.api_pacing import EvaluationAbortedDueToRateLimit, run_with_pacing


def _api_529(*_args, **_kwargs):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(529, request=request, text="overloaded")
    raise APIStatusError("Overloaded", response=response, body={"error": {"type": "overloaded_error"}})


def _with_chroma_removed():
    chroma_path = Path("chroma_db")
    backup = Path("chroma_db_pytest_backup")
    if backup.exists():
        shutil.rmtree(backup)
    if chroma_path.exists():
        shutil.move(str(chroma_path), str(backup))
    return chroma_path, backup


def _restore_chroma(chroma_path: Path, backup: Path) -> None:
    if backup.exists():
        if chroma_path.exists():
            shutil.rmtree(chroma_path)
        shutil.move(str(backup), str(chroma_path))


def test_chroma_unavailable_degrades_gracefully():
    chroma_path, backup = _with_chroma_removed()
    try:
        api_main.orchestrator = HybridOrchestrator()
        client = TestClient(app)
        try:
            resp = client.post(
                "/ask",
                json={"text": "Which support tickets mention damaged products?"},
            )
        finally:
            api_main.orchestrator.close()
            api_main.orchestrator = None

        body = resp.json()
        print("\n--- Chroma unavailable (after fix) ---")
        print(f"HTTP {resp.status_code}")
        print(json.dumps(body, indent=2)[:2000])

        assert resp.status_code == 200
        assert body["ticket_result"]["error"] == TICKET_INDEX_UNAVAILABLE_ERROR
        assert "Collection" not in resp.text
        assert body["synthesis"]["insufficient_evidence"] is True
        assert indicates_insufficient_evidence(body["synthesis"]["answer"])
    finally:
        _restore_chroma(chroma_path, backup)


def test_anthropic_529_returns_clear_503():
    api_main.orchestrator = HybridOrchestrator()
    client = TestClient(app)
    try:
        with patch.object(api_main.orchestrator.client.messages, "create", side_effect=_api_529):
            resp = client.post("/ask", json={"text": "How many customers are there?"})
        body = resp.json()
        print("\n--- Anthropic 529 (after fix) ---")
        print(f"HTTP {resp.status_code}")
        print(json.dumps(body, indent=2))

        assert resp.status_code == 503
        assert body["detail"] == AI_SERVICE_UNAVAILABLE_MESSAGE
        assert body["detail"] != GENERIC_INTERNAL_ERROR
        assert "insufficient evidence" not in resp.text.lower()
    finally:
        api_main.orchestrator.close()
        api_main.orchestrator = None


def test_eval_harness_aborts_after_529_retries():
    with pytest.raises(EvaluationAbortedDueToRateLimit, match="529"):
        run_with_pacing(lambda: (_ for _ in ()).throw(_api_529()), max_attempts=2)
