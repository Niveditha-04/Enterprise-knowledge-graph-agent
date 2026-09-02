from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

def get_driver():
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
    )

def test_customers_loaded():
    driver = get_driver()
    with driver.session() as session:
        count = session.run("MATCH (c:Customer) RETURN count(c) AS n").single()["n"]
        assert count > 0
    driver.close()

def test_relationships_exist():
    driver = get_driver()
    with driver.session() as session:
        count = session.run(
            "MATCH (:Customer)-[:PLACED]->(:Order) RETURN count(*) AS n"
        ).single()["n"]
        assert count > 0
    driver.close()

def test_support_tickets_linked():
    driver = get_driver()
    with driver.session() as session:
        count = session.run(
            "MATCH (:SupportTicket)-[:REFERENCES]->(:Order) RETURN count(*) AS n"
        ).single()["n"]
        assert count > 0
    driver.close()
