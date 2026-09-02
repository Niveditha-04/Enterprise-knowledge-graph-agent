"""Graph indexing and scale analysis (Section 16).

Inspects the live Neo4j catalog when available and reasons about query behavior
at larger order volumes. No fabricated latency benchmarks — extrapolation only.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

# Measured on current demo load (2026-09-02).
CURRENT_COUNTS = {
    "Customer": 91,
    "Order": 830,
    "Product": 77,
    "SupportTicket": 200,
    "PLACED": 830,
    "CONTAINS": 2155,
    "FILED": 200,
    "REFERENCES": 200,
}

AVG_LINES_PER_ORDER = CURRENT_COUNTS["CONTAINS"] / CURRENT_COUNTS["Order"]


@dataclass(frozen=True)
class QueryPattern:
    id: str
    category: str
    example: str
    index_use: str
    scales_with: str


QUERY_PATTERNS: tuple[QueryPattern, ...] = (
    QueryPattern(
        id="point_customer",
        category="point_lookup",
        example="MATCH (c:Customer {customer_id: 'ALFKI'}) RETURN c.country",
        index_use="customer_id uniqueness → RANGE index",
        scales_with="O(log customers) — fine at 10M+ customers",
    ),
    QueryPattern(
        id="point_order",
        category="point_lookup",
        example="MATCH (o:Order {order_id: 10248})-[:CONTAINS]->(p:Product) RETURN p",
        index_use="order_id uniqueness → RANGE index",
        scales_with="O(log orders + degree of order) — fine at 10M+ orders",
    ),
    QueryPattern(
        id="customer_order_count",
        category="scoped_traversal",
        example="MATCH (c:Customer {customer_id: 'VINET'})-[:PLACED]->(o) RETURN count(o)",
        index_use="customer_id index anchors traversal",
        scales_with="O(customer order volume), not global order count",
    ),
    QueryPattern(
        id="count_global",
        category="global_scan",
        example="MATCH (c:Customer) RETURN count(c)",
        index_use="label scan (no property index needed for pure count)",
        scales_with="O(nodes of label) — linear; acceptable to ~low millions on modest hardware",
    ),
    QueryPattern(
        id="agg_top_customer",
        category="global_aggregation",
        example="MATCH (c:Customer)-[:PLACED]->(o) RETURN c.customer_id, count(o) ORDER BY count(o) DESC LIMIT 1",
        index_use="traverses all PLACED edges",
        scales_with="O(orders) — dominant cost at 1M–10M; may need pre-aggregation or limits",
    ),
    QueryPattern(
        id="filter_country",
        category="property_filter",
        example="MATCH (c:Customer) WHERE c.country = 'Brazil' RETURN count(c)",
        index_use="no index on country today — full Customer label scan + filter",
        scales_with="O(customers); add RANGE index on country before 100K+ customers if common",
    ),
    QueryPattern(
        id="product_name_join",
        category="property_filter + join",
        example="MATCH (p:Product) WHERE p.product_name CONTAINS 'Chai' MATCH (o)-[:CONTAINS]->(p) RETURN count(DISTINCT o)",
        index_use="no index on product_name — scans Product then expands CONTAINS",
        scales_with="O(products + matching line items); text index at 1M+ orders if product-filter queries are frequent",
    ),
)


def _driver():
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
    )


def inspect_catalog() -> dict[str, Any]:
    driver = _driver()
    try:
        with driver.session() as session:
            constraints = [dict(r) for r in session.run("SHOW CONSTRAINTS")]
            indexes = [dict(r) for r in session.run("SHOW INDEXES")]
            counts = {}
            for label in ("Customer", "Order", "Product", "SupportTicket"):
                counts[label] = session.run(
                    f"MATCH (n:{label}) RETURN count(n) AS n"
                ).single()["n"]
            for rel in ("PLACED", "CONTAINS", "FILED", "REFERENCES"):
                counts[rel] = session.run(
                    f"MATCH ()-[r:{rel}]->() RETURN count(r) AS n"
                ).single()["n"]
    finally:
        driver.close()
    return {"constraints": constraints, "indexes": indexes, "counts": counts}


def project_counts(order_count: int) -> dict[str, int]:
    """Rough projection holding product catalog fixed, scaling orders and customers."""
    order_ratio = order_count / CURRENT_COUNTS["Order"]
    return {
        "Order": order_count,
        "CONTAINS": int(round(order_count * AVG_LINES_PER_ORDER)),
        "PLACED": order_count,
        "Customer": int(round(CURRENT_COUNTS["Customer"] * order_ratio)),
        "Product": CURRENT_COUNTS["Product"],
        "SupportTicket": int(round(CURRENT_COUNTS["SupportTicket"] * order_ratio)),
    }


def scale_assessment(order_count: int) -> dict[str, str]:
    projected = project_counts(order_count)
    if order_count <= 100_000:
        tier = "100K"
        graph_query = (
            "Current id indexes suffice for NL→Cypher point lookups and scoped traversals. "
            "Global counts/aggregations remain sub-second on single-instance Neo4j. "
            "Loader row-by-row ingest becomes the operational bottleneck before query-time indexes do."
        )
        indexes = (
            "Optional: RANGE index on Customer.country if country-filter questions stay common. "
            "Batch UNWIND loader for ingest."
        )
    elif order_count <= 1_000_000:
        tier = "1M"
        graph_query = (
            "Id-anchored queries still healthy. Global top-customer aggregation scans ~1M PLACED edges — "
            "noticeable but usually acceptable on indexed ids + adequate RAM. "
            "Product-name filters without an index scan the catalog then fan out on CONTAINS."
        )
        indexes = (
            "Add RANGE or TEXT index on Product.product_name if name-based joins are frequent. "
            "Consider RANGE on Customer.country. Monitor agg query latency; cap NL→Cypher result limits (already 100)."
        )
    else:
        tier = "10M"
        graph_query = (
            "Point lookups by order_id/customer_id remain viable with existing uniqueness constraints. "
            "Global aggregations and unindexed property filters become the primary risk — not NL→Cypher quality "
            "but Cypher execution time and heap pressure (~26M CONTAINS at demo line-item ratio)."
        )
        indexes = (
            "Require ingest pipeline redesign (bulk load), likely read replicas, and precomputed rollups "
            "(orders per customer, catalog stats) for dashboard-style questions. "
            "Ticket text stays in Chroma — graph scale does not bound ticket RAG."
        )

    return {
        "tier": tier,
        "projected_orders": str(projected["Order"]),
        "projected_contains": str(projected["CONTAINS"]),
        "projected_customers": str(projected["Customer"]),
        "graph_query_outlook": graph_query,
        "index_recommendations": indexes,
    }


def build_report() -> dict[str, Any]:
    catalog = inspect_catalog()
    operational_indexes = [
        i
        for i in catalog["indexes"]
        if i.get("type") == "RANGE" and i.get("owningConstraint")
    ]
    return {
        "current_counts": catalog["counts"],
        "constraints": catalog["constraints"],
        "operational_indexes": operational_indexes,
        "lookup_indexes": [
            i for i in catalog["indexes"] if i.get("type") == "LOOKUP"
        ],
        "missing_indexes_for_eval_patterns": [
            "Customer.country (used by filter_brazil, filter_germany semantic cases)",
            "Product.product_name (used by multihop_ticket_chai_* and traversal cases)",
            "SupportTicket.text — not indexed in Neo4j; ticket body search is ChromaDB's job",
        ],
        "query_patterns": [p.__dict__ for p in QUERY_PATTERNS],
        "scale_projections": {
            "100_000_orders": scale_assessment(100_000),
            "1_000_000_orders": scale_assessment(1_000_000),
            "10_000_000_orders": scale_assessment(10_000_000),
        },
        "loader_note": (
            "graph/load_graph.py issues one session.run per row — ~3k writes today, "
            "would be prohibitive at 1M+ orders without UNWIND batching or neo4j-admin import."
        ),
    }


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Graph indexing & scale analysis (Section 16)",
        "=" * 60,
        "",
        "Current Neo4j counts:",
    ]
    for k, v in report["current_counts"].items():
        lines.append(f"  {k}: {v}")

    lines.extend(["", "Operational indexes (RANGE, backed by uniqueness constraints):"])
    for idx in report["operational_indexes"]:
        labels = idx.get("labelsOrTypes")
        props = idx.get("properties")
        lines.append(f"  {labels}.{props} ({idx.get('name')})")

    lines.extend(["", "Gaps vs evaluation query patterns:"])
    for gap in report["missing_indexes_for_eval_patterns"]:
        lines.append(f"  - {gap}")

    lines.extend(["", "Scale projections (not benchmarked — structural reasoning only):"])
    for key, assessment in report["scale_projections"].items():
        lines.append(f"\n  {key}:")
        lines.append(f"    orders: {assessment['projected_orders']}, CONTAINS: {assessment['projected_contains']}")
        lines.append(f"    {assessment['graph_query_outlook']}")
        lines.append(f"  Indexes: {assessment['index_recommendations']}")

    lines.extend(["", f"Loader: {report['loader_note']}"])
    return "\n".join(lines)


if __name__ == "__main__":
    report = build_report()
    print(format_report(report))
    out = os.path.join(os.path.dirname(__file__), "graph_scale_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nWrote {out}")
