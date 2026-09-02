"""Section 14 ablation analysis from a completed evaluation report."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

REPORT_PATH = Path(__file__).parent / "evaluation_report.json"
OUT_PATH = Path(__file__).parent / "ablation_report.json"

SYSTEMS = [
    ("hybrid", "hybrid_match", "Hybrid (evidence text: graph rows + ticket docs)"),
    ("synthesis", "synthesis_match", "Synthesis NL answer (what the user sees)"),
    ("graph_branch", "graph_branch_match", "Graph branch only"),
    ("ticket_branch", "ticket_branch_match", "Ticket branch only (when routed)"),
    ("flat_baseline", "flat_baseline_match", "Flat RAG (order sentences)"),
    ("ticket_baseline", "ticket_baseline_match", "Ticket RAG baseline"),
]


def load_report(path: Path = REPORT_PATH) -> dict:
    return json.loads(path.read_text())


def analyze(report: dict) -> dict:
    scored = [r for r in report["results"] if r["scored"]]
    total = len(scored)

    by_system = {}
    for key, check_key, label in SYSTEMS:
        count = sum(1 for r in scored if r["checks"][check_key])
        by_system[key] = {
            "label": label,
            "correct": count,
            "total": total,
            "accuracy": count / total if total else 0.0,
        }

    by_category: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    category_totals: dict[str, int] = defaultdict(int)
    for row in scored:
        cat = row["category"]
        category_totals[cat] += 1
        for key, check_key, _ in SYSTEMS:
            if row["checks"][check_key]:
                by_category[cat][key] += 1

    def delta_cases(winner: str, loser: str) -> list[dict]:
        w_key = next(c for k, c, _ in SYSTEMS if k == winner)
        l_key = next(c for k, c, _ in SYSTEMS if k == loser)
        out = []
        for row in scored:
            c = row["checks"]
            if c[w_key] and not c[l_key]:
                out.append(
                    {
                        "id": row["id"],
                        "category": row["category"],
                        "route": row["route"],
                        "question": row["question"],
                    }
                )
        return out

    hybrid_over_graph = delta_cases("hybrid", "graph_branch")
    graph_over_flat = delta_cases("graph_branch", "flat_baseline")
    graph_over_ticket_rag = delta_cases("graph_branch", "ticket_baseline")
    ticket_rag_over_graph = delta_cases("ticket_baseline", "graph_branch")
    synthesis_gap = [
        row
        for row in scored
        if row["checks"]["hybrid_match"] and not row["checks"]["synthesis_match"]
    ]

    return {
        "source": str(REPORT_PATH),
        "scored_items": total,
        "wall_clock_seconds": report.get("wall_clock_seconds"),
        "routing_accuracy": report.get("accuracy", {}).get("routing"),
        "systems": by_system,
        "by_category": {
            cat: {
                "total": category_totals[cat],
                **{key: by_category[cat].get(key, 0) for key, _, _ in SYSTEMS},
            }
            for cat in sorted(category_totals)
        },
        "deltas": {
            "hybrid_over_graph_branch": {
                "count": len(hybrid_over_graph),
                "cases": hybrid_over_graph,
                "interpretation": (
                    "Hybrid evidence match exceeds graph-only when ticket text (or synthesis "
                    "refusal on unsupported questions) supplies the matching substring graph "
                    "rows alone do not."
                ),
            },
            "graph_over_flat_rag": {
                "count": len(graph_over_flat),
                "cases": graph_over_flat,
                "interpretation": (
                    "Structured Cypher over Neo4j succeeds where flat order-sentence RAG lacks "
                    "products, ticket nodes, aggregations, and global counts."
                ),
            },
            "graph_over_ticket_rag": {
                "count": len(graph_over_ticket_rag),
                "cases": graph_over_ticket_rag,
                "interpretation": (
                    "Graph branch carries counting, aggregation, traversal, and catalog lookups "
                    "that ticket semantic search cannot answer from text alone."
                ),
            },
            "ticket_rag_over_graph": {
                "count": len(ticket_rag_over_graph),
                "cases": ticket_rag_over_graph,
                "interpretation": (
                    "Ticket index wins when the answer lives only in free-text ticket bodies "
                    "and graph rows do not surface the substring."
                ),
            },
            "evidence_vs_synthesis_gap": {
                "count": len(synthesis_gap),
                "cases": [
                    {
                        "id": r["id"],
                        "category": r["category"],
                        "question": r["question"],
                    }
                    for r in synthesis_gap
                ],
                "interpretation": (
                    "Evidence retrieved correctly but NL synthesis did not deliver the answer "
                    "(over-refusal / conservative synthesis)."
                ),
            },
        },
        "category_takeaways": {
            "counting": (
                "Graph 7/7 vs flat 2/7: flat RAG only indexes order sentences, so global "
                "counts (customers, products, tickets, total orders) and per-customer order "
                "counts beyond lucky substring hits require Cypher."
            ),
            "aggregation": (
                "Graph 3/3 vs flat 0/3: MAX/COUNT/GROUP BY over relationships (top customer, "
                "multi-ticket customers, most expensive product) are structurally impossible "
                "for flat order-text retrieval."
            ),
            "filtering": (
                "Graph 2/2 vs flat 2/2: country filters can accidentally match order-address "
                "text in flat RAG; graph and flat tie here — not a graph advantage category "
                "on this small set."
            ),
            "graph_traversal": (
                "Graph 1/1 vs flat 0/1: product-in-order joins (Chai order count) need the "
                "CONTAINS relationship, absent from flat index."
            ),
            "ticket_retrieval": (
                "Ticket RAG 3/3 vs graph 0/3: keyword/semantic ticket search; graph has ticket "
                "nodes but not ticket body text in returned properties for these questions."
            ),
            "hybrid": (
                "Hybrid 3/3: multi-hop Cypher plus ticket text; ticket RAG alone 2/3 (misses "
                "pure count join). Graph alone 2/3 on scored hybrid items."
            ),
            "unsupported": (
                "Refusal checks: synthesis guard + CEO-email style refusals; neither flat nor "
                "ticket RAG passes."
            ),
        },
    }


def format_report(analysis: dict) -> str:
    lines = [
        "Ablation analysis (Section 14)",
        "=" * 60,
        f"Source: {analysis['source']} | {analysis['scored_items']} scored items",
        "",
        "System accuracy (user-facing vs evidence):",
    ]
    for key in ["synthesis", "hybrid", "graph_branch", "ticket_branch", "flat_baseline", "ticket_baseline"]:
        s = analysis["systems"][key]
        lines.append(
            f"  {s['label']}: {s['correct']}/{s['total']} ({100*s['accuracy']:.1f}%)"
        )

    lines.extend(["", "Category breakdown (hybrid / graph / flat / ticket RAG):"])
    for cat, stats in analysis["by_category"].items():
        t = stats["total"]
        lines.append(
            f"  {cat}: hybrid {stats['hybrid']}/{t}, graph {stats['graph_branch']}/{t}, "
            f"flat {stats['flat_baseline']}/{t}, ticket_rag {stats['ticket_baseline']}/{t}, "
            f"synthesis {stats['synthesis']}/{t}"
        )

    lines.extend(["", "Key deltas:"])
    for name, block in analysis["deltas"].items():
        lines.append(f"  {name}: {block['count']} cases")
        lines.append(f"    {block['interpretation']}")

    lines.extend(["", "Category takeaways:"])
    for cat, text in analysis["category_takeaways"].items():
        lines.append(f"  {cat}: {text}")

    return "\n".join(lines)


def main() -> None:
    report = load_report()
    analysis = analyze(report)
    OUT_PATH.write_text(json.dumps(analysis, indent=2) + "\n")
    print(format_report(analysis))
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
