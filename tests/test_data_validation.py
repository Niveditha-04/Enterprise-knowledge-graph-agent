import json

import pandas as pd

from data.csv_utils import read_orders
from eval.answer_checks import check_item, graph_answer_text, hybrid_answer_text


def test_orders_parser_count_matches_expected():
    orders = read_orders()
    assert len(orders) == 830


def test_support_ticket_count():
    tickets = json.load(open("data/support_tickets.json"))
    assert len(tickets) == 200


def test_customers_count():
    customers = pd.read_csv("data/customers.csv")
    assert len(customers) == 91


def test_products_count():
    products = pd.read_csv("data/products.csv")
    assert len(products) == 77


def test_graph_answer_text_uses_results_not_cypher():
    graph_result = {
        "cypher": "MATCH (p:Product) RETURN p.product_name AS name ORDER BY p.unit_price DESC LIMIT 1",
        "results": [{"name": "Côte de Blaye"}],
        "error": None,
    }
    text = graph_answer_text(graph_result)
    assert "Côte de Blaye" in text
    assert "MATCH" not in text


def test_hybrid_answer_check_matches_unicode_product_name():
    orchestrator_result = {
        "route": "GRAPH",
        "graph_result": {
            "results": [{"p": {"product_name": "Côte de Blaye"}}],
            "error": None,
        },
    }
    checks = check_item(
        orchestrator_result,
        {},
        {"expected_answer_contains": "Côte de Blaye"},
    )
    assert checks["hybrid_match"] is True


def test_ticket_answer_check_uses_documents_only():
    orchestrator_result = {
        "route": "TICKETS",
        "ticket_result": {
            "documents": [["Customer AROUT escalated order 10864 — product arrived damaged, replacement requested."]]
        },
    }
    checks = check_item(
        orchestrator_result,
        {},
        {"expected_answer_contains": "damaged"},
    )
    assert checks["hybrid_match"] is True
    assert checks["ticket_branch_match"] is True
