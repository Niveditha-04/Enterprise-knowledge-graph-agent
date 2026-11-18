import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)


def _neo4j_available() -> bool:
    uri = os.getenv("NEO4J_URI")
    user = os.getenv("NEO4J_USER")
    password = os.getenv("NEO4J_PASSWORD")
    if not (uri and user and password):
        return False
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(uri, auth=(user, password))
        try:
            driver.verify_connectivity()
            return True
        finally:
            driver.close()
    except Exception:
        return False


def _anthropic_available() -> bool:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return False
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        return True
    except Exception:
        return False


def _chroma_db_built() -> bool:
    return (ROOT / "chroma_db").exists()


NEO4J_AVAILABLE = _neo4j_available()
ANTHROPIC_AVAILABLE = _anthropic_available()
CHROMA_AVAILABLE = _chroma_db_built()


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "neo4j: requires a live Neo4j connection")
    config.addinivalue_line("markers", "anthropic: requires ANTHROPIC_API_KEY")
    config.addinivalue_line("markers", "chroma: requires a built chroma_db index")
    config.addinivalue_line("markers", "slow: long-running, makes many live API calls")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_neo4j = pytest.mark.skip(reason="Neo4j is not reachable (set NEO4J_URI/USER/PASSWORD and start the database)")
    skip_anthropic = pytest.mark.skip(reason="ANTHROPIC_API_KEY is not set or not authenticating")
    skip_chroma = pytest.mark.skip(reason="chroma_db index is not built (run rag/build_index.py)")

    for item in items:
        if "neo4j" in item.keywords and not NEO4J_AVAILABLE:
            item.add_marker(skip_neo4j)
        if "anthropic" in item.keywords and not ANTHROPIC_AVAILABLE:
            item.add_marker(skip_anthropic)
        if "chroma" in item.keywords and not CHROMA_AVAILABLE:
            item.add_marker(skip_chroma)
