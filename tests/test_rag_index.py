import pytest

from rag.query_index import query_tickets

pytestmark = pytest.mark.chroma


def test_rag_returns_relevant_results():
    results = query_tickets("Which orders had damaged products?")
    assert len(results["documents"][0]) > 0
