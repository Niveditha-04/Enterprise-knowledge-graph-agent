"""Capture real before/after transcripts for the API credential-leak fix.

Run: PYTHONPATH=. python eval/capture_exception_leak_transcripts.py
"""

from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

TRIGGER_QUESTION = "How many customers are there?"
LEAK_MESSAGE = (
    "SECRET_PATH=/Users/nivedithabalasubramanian/Downloads/Enterprise Knowledge Graph Agent/.env "
    "NEO4J_PASSWORD=supersecret Traceback (most recent call last): "
    "File '/Users/nivedithabalasubramanian/Downloads/Enterprise Knowledge Graph Agent/api/main.py'"
)


class Question(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)


def capture_before_response() -> TestClient:
    app_before = FastAPI()

    @app_before.post("/ask")
    def ask_before(question: Question):
        try:
            raise RuntimeError(LEAK_MESSAGE)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return TestClient(app_before).post("/ask", json={"text": TRIGGER_QUESTION})


def capture_after_response():
    from agent.orchestrator import HybridOrchestrator
    from api import main as api_main
    from api.main import app as hardened_app
    from api.security import GENERIC_INTERNAL_ERROR

    if api_main.orchestrator is None:
        api_main.orchestrator = HybridOrchestrator()

    def boom(_question: str):
        raise RuntimeError(LEAK_MESSAGE)

    api_main.orchestrator.answer = boom
    response = TestClient(hardened_app).post("/ask", json={"text": TRIGGER_QUESTION})
    return response, GENERIC_INTERNAL_ERROR


def main() -> None:
    before = capture_before_response()
    after, _ = capture_after_response()

    print("=== BEFORE (old handler: detail=str(exc)) ===")
    print(f"HTTP {before.status_code}")
    print(json.dumps(before.json(), indent=2))
    print("\n=== AFTER (hardened api/security.py) ===")
    print(f"HTTP {after.status_code}")
    print(json.dumps(after.json(), indent=2))


if __name__ == "__main__":
    main()
