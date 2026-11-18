"""RAG retrieval evaluation: Recall@K, Precision@K, and MRR.

Ground-truth ticket IDs in eval/rag_retrieval_cases.json were derived from
ticket metadata and text rules applied to data/support_tickets.json — not from
retriever output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

CASES_PATH = Path(__file__).parent / "rag_retrieval_cases.json"
DEFAULT_K_VALUES = (3, 5, 10)


def load_retrieval_cases(path: Path | None = None) -> list[dict[str, Any]]:
    return json.loads((path or CASES_PATH).read_text())


def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    hits = sum(1 for doc_id in retrieved[:k] if doc_id in relevant)
    return hits / len(relevant)


def precision_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if k == 0:
        return 0.0
    hits = sum(1 for doc_id in retrieved[:k] if doc_id in relevant)
    return hits / k


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


def _macro_for_cases(cases: list[dict[str, Any]], k_values: tuple[int, ...]) -> dict[str, Any]:
    if not cases:
        return {
            "count": 0,
            "recall": {k: 0.0 for k in k_values},
            "precision": {k: 0.0 for k in k_values},
            "mrr": 0.0,
        }
    n = len(cases)
    return {
        "count": n,
        "recall": {k: sum(c["recall"][k] for c in cases) / n for k in k_values},
        "precision": {k: sum(c["precision"][k] for c in cases) / n for k in k_values},
        "mrr": sum(c["rr"] for c in cases) / n,
    }


def evaluate_retrieval(
    retrieve_fn: Callable[[str, int], list[str]],
    cases: list[dict[str, Any]] | None = None,
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
) -> dict[str, Any]:
    cases = cases or load_retrieval_cases()
    max_k = max(k_values)
    per_case: list[dict[str, Any]] = []

    for case in cases:
        relevant = set(case["ground_truth_ticket_ids"])
        retrieved = retrieve_fn(case["query"], max_k)
        entry = {
            "id": case["id"],
            "query": case["query"],
            "query_type": case.get("query_type", "theme"),
            "ground_truth_rule": case.get("ground_truth_rule", ""),
            "relevant_count": len(relevant),
            "retrieved": retrieved,
            "relevant_ids": sorted(relevant),
            "recall": {k: recall_at_k(retrieved, relevant, k) for k in k_values},
            "precision": {k: precision_at_k(retrieved, relevant, k) for k in k_values},
            "rr": reciprocal_rank(retrieved, relevant),
        }
        per_case.append(entry)

    n = len(per_case)
    macro_all = _macro_for_cases(per_case, k_values)
    narrow_cases = [c for c in per_case if c["query_type"] == "narrow"]
    theme_cases = [c for c in per_case if c["query_type"] == "theme"]

    return {
        "per_case": per_case,
        "macro": macro_all,
        "macro_by_query_type": {
            "narrow": _macro_for_cases(narrow_cases, k_values),
            "theme": _macro_for_cases(theme_cases, k_values),
        },
        "k_values": k_values,
        "case_count": n,
    }


def chroma_retrieve_ids(query: str, n_results: int) -> list[str]:
    from rag.query_index import query_tickets

    results = query_tickets(query, n_results=n_results)
    return list(results.get("ids", [[]])[0])


def format_report(report: dict[str, Any]) -> str:
    k_values = report["k_values"]
    macro = report["macro"]
    by_type = report.get("macro_by_query_type", {})
    lines = [
        "RAG retrieval evaluation report",
        "=" * 60,
        f"Cases: {report['case_count']}",
        "",
        "Blended macro (all cases — do not quote without narrow/theme split):",
        f"  MRR: {macro['mrr']:.3f}",
    ]
    for k in k_values:
        lines.append(
            f"  Recall@{k}: {macro['recall'][k]:.3f}   Precision@{k}: {macro['precision'][k]:.3f}"
        )

    for query_type in ("narrow", "theme"):
        stats = by_type.get(query_type, {})
        if not stats.get("count"):
            continue
        lines.extend(
            [
                "",
                f"{query_type.capitalize()} queries (n={stats['count']}):",
                f"  MRR: {stats['mrr']:.3f}",
            ]
        )
        for k in k_values:
            lines.append(
                f"  Recall@{k}: {stats['recall'][k]:.3f}   Precision@{k}: {stats['precision'][k]:.3f}"
            )
        if query_type == "theme":
            lines.append(
                "  (Theme recall ceiling is low at small K because each query has 31-45 relevant tickets.)"
            )

    lines.extend(["", "Per-case results:"])
    for case in report["per_case"]:
        hits_at_3 = [tid for tid in case["retrieved"][:3] if tid in set(case["relevant_ids"])]
        lines.append(
            f"  [{case['id']}] relevant={case['relevant_count']} "
            f"RR={case['rr']:.3f} hits@3={hits_at_3}"
        )
        lines.append(f"    query: {case['query']}")
        lines.append(f"    rule: {case['ground_truth_rule']}")
        lines.append(f"    retrieved@{max(k_values)}: {case['retrieved']}")
        for k in k_values:
            lines.append(
                f"    R@{k}={case['recall'][k]:.3f} P@{k}={case['precision'][k]:.3f}"
            )

    return "\n".join(lines)
