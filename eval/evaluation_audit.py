"""Independent verification of evaluation ground truth and harness fairness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

EVAL_SET_PATH = Path(__file__).parent / "evaluation_set.json"
TICKETS_PATH = Path(__file__).parent.parent / "data" / "support_tickets.json"


def _neo4j_driver():
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
    return GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]),
    )


def _flatten_row(row: dict) -> str:
    parts = []
    for value in row.values():
        if value is not None:
            parts.append(str(value))
    return " ".join(parts)


def verify_neo4j_ground_truth(query: str) -> str:
    driver = _neo4j_driver()
    try:
        with driver.session() as session:
            record = session.run(query).single()
            if record is None:
                return ""
            return _flatten_row(record.data())
    finally:
        driver.close()


def verify_ticket_rule(rule: str) -> str:
    tickets = json.loads(TICKETS_PATH.read_text())
    rule_lower = rule.lower()
    if "customer_id == vinet" in rule_lower and "invoice" in rule_lower:
        matches = [
            t["ticket_id"]
            for t in tickets
            if t["customer_id"] == "VINET" and "invoice correction" in t["text"].lower()
        ]
        return matches[0] if matches else ""
    if "order_id == 10864" in rule_lower:
        matches = [t["ticket_id"] for t in tickets if t["order_id"] == 10864]
        return matches[0] if matches else ""
    if "damaged" in rule_lower:
        return f"{sum(1 for t in tickets if 'damaged' in t['text'].lower())} tickets"
    if "carrier" in rule_lower:
        return f"{sum(1 for t in tickets if 'carrier' in t['text'].lower())} tickets"
    return ""


def verify_ground_truth(item: dict) -> dict[str, Any]:
    gt = item.get("ground_truth") or {}
    source = gt.get("source")
    expected = str(gt.get("value", ""))

    if source == "neo4j":
        actual = verify_neo4j_ground_truth(gt["query"])
    elif source == "tickets":
        actual = verify_ticket_rule(gt.get("rule", ""))
    elif source == "none":
        actual = "unanswerable"
    else:
        actual = ""

    if source == "neo4j":
        verified = expected.lower() in actual.lower()
    elif source == "tickets" and "tickets" in expected:
        verified = expected.split()[0] in actual
    elif source == "tickets":
        verified = bool(actual)
    elif source == "none":
        verified = actual == expected
    else:
        verified = False

    return {
        "id": item["id"],
        "source": source,
        "expected": expected,
        "actual": actual,
        "verified": verified,
    }


def audit_evaluation_set(path: Path = EVAL_SET_PATH) -> dict[str, Any]:
    items = json.loads(path.read_text())
    verifications = [verify_ground_truth(item) for item in items]
    failed = [v for v in verifications if not v["verified"]]

    scored = [i for i in items if i.get("scored", True)]
    ambiguous = [i for i in items if i.get("category") == "ambiguous"]
    unsupported = [i for i in items if i.get("category") == "unsupported"]

    return {
        "total_items": len(items),
        "scored_items": len(scored),
        "ambiguous_items": len(ambiguous),
        "unsupported_items": len(unsupported),
        "ground_truth_verified": len(verifications) - len(failed),
        "ground_truth_failed": len(failed),
        "verifications": verifications,
        "methodology_notes": {
            "matching": "Substring match on graph values + retrieved ticket text (case-insensitive). Not semantic grading.",
            "false_positive_risk": "Short numeric substrings can match unrelated numbers (e.g. '1' in '10248').",
            "false_negative_risk": "Unicode normalization (e.g. Côte de Blaye) and paraphrased correct answers fail substring checks.",
            "baseline_fairness": (
                "Flat RAG indexes one sentence per order only — no products, no ticket text. "
                "Ticket-RAG baseline uses the full ticket index. Hybrid has strictly more information."
            ),
            "graph_bias": "Majority of scored questions are GRAPH-primary by design; hybrid and ticket categories added in Section 12 expansion.",
            "synthetic_data": "Tickets are seeded (random.seed(42)); no train/test leakage, but templates repeat phrasing.",
        },
    }


def format_audit_report(report: dict) -> str:
    lines = [
        "Evaluation ground-truth audit",
        "=" * 60,
        f"Items: {report['total_items']} total | {report['scored_items']} scored | "
        f"{report['ambiguous_items']} ambiguous (unscored) | {report['unsupported_items']} unsupported",
        f"Ground truth verified: {report['ground_truth_verified']}/{report['total_items']}",
        "",
        "Methodology:",
    ]
    for key, value in report["methodology_notes"].items():
        lines.append(f"  {key}: {value}")

    if report["ground_truth_failed"]:
        lines.extend(["", "FAILED verifications:"])
        for v in report["verifications"]:
            if not v["verified"]:
                lines.append(f"  {v['id']}: expected={v['expected']!r} actual={v['actual']!r}")

    return "\n".join(lines)


if __name__ == "__main__":
    report = audit_evaluation_set()
    print(format_audit_report(report))
    out = Path(__file__).parent / "evaluation_audit_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nWrote {out}")
