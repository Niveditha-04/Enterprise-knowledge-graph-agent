import pytest

from agent.cypher_safety import (
    enforce_result_limit,
    strip_markdown_fences,
    validate_read_only_cypher,
)


def test_strip_markdown_fences():
    raw = "```cypher\nMATCH (c:Customer) RETURN c\n```"
    assert strip_markdown_fences(raw) == "MATCH (c:Customer) RETURN c"


def test_allows_read_query():
    cypher = "MATCH (c:Customer) RETURN count(c)"
    assert validate_read_only_cypher(cypher) == cypher


def test_blocks_delete():
    with pytest.raises(ValueError, match="Forbidden"):
        validate_read_only_cypher("MATCH (n) DETACH DELETE n")


def test_blocks_create():
    with pytest.raises(ValueError, match="Forbidden"):
        validate_read_only_cypher("CREATE (n:Customer {customer_id: 'X'}) RETURN n")


def test_blocks_merge():
    with pytest.raises(ValueError, match="Forbidden"):
        validate_read_only_cypher("MERGE (c:Customer {customer_id: 'X'}) RETURN c")


def test_blocks_set():
    with pytest.raises(ValueError, match="Forbidden"):
        validate_read_only_cypher("MATCH (c:Customer) SET c.country = 'X' RETURN c")


def test_enforce_result_limit_appends_limit():
    cypher = "MATCH (c:Customer) RETURN c"
    limited = enforce_result_limit(cypher, 50)
    assert "LIMIT 50" in limited


def test_enforce_result_limit_preserves_existing_limit():
    cypher = "MATCH (c:Customer) RETURN c LIMIT 5"
    assert enforce_result_limit(cypher, 50) == cypher


def test_allows_forbidden_keyword_inside_quoted_string():
    cypher = 'MATCH (c:Customer) WHERE c.company_name CONTAINS "Merge" RETURN c'
    assert validate_read_only_cypher(cypher) == cypher


def test_allows_forbidden_keyword_inside_single_quoted_string():
    cypher = "MATCH (c:Customer) WHERE c.company_name CONTAINS 'DELETE' RETURN c"
    assert validate_read_only_cypher(cypher) == cypher


def test_blocks_use_system():
    with pytest.raises(ValueError, match="Forbidden"):
        validate_read_only_cypher("USE system\nMATCH (n) RETURN count(n)")


def test_blocks_use_neo4j():
    with pytest.raises(ValueError, match="Forbidden"):
        validate_read_only_cypher("USE neo4j\nMATCH (c:Customer) RETURN count(c)")
