import os

import pytest
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

pytestmark = pytest.mark.neo4j


def test_neo4j_connection():
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
    )
    with driver.session() as session:
        result = session.run("RETURN 1 AS test")
        assert result.single()["test"] == 1
    driver.close()
