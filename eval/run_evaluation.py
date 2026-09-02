"""Run expanded evaluation with conservative API pacing."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

from agent.orchestrator import HybridOrchestrator
from eval.answer_checks import check_item
from eval.api_pacing import (
    EvaluationAbortedDueToRateLimit,
    pace_between_requests,
    run_with_pacing,
)
from eval.baseline_rag_only import build_flat_baseline_index, query_baseline
from eval.ticket_rag_baseline import query_ticket_baseline

EVAL_SET_PATH = Path(__file__).parent / "evaluation_set.json"
REPORT_PATH = Path(__file__).parent / "evaluation_report.json"


def _accuracy(correct: int, total: int) -> float:
    return correct / total if total else 0.0


def run_evaluation(verbose: bool = False, paced: bool = True) -> dict:
    wall_start = time.perf_counter()
    build_flat_baseline_index(reset=True)

    items = json.loads(EVAL_SET_PATH.read_text())
    scored_items = [i for i in items if i.get("scored", True)]

    orchestrator = HybridOrchestrator()
    retry_events: list[dict] = []
    results = []
    counters = {
        "hybrid": 0,
        "flat_baseline": 0,
        "ticket_baseline": 0,
        "graph_branch": 0,
        "ticket_branch": 0,
        "synthesis": 0,
    }
    routing_correct = 0
    routing_scored = 0
    by_category: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "hybrid": 0, "flat_baseline": 0, "ticket_baseline": 0}
    )
    aborted = False
    abort_reason: str | None = None

    try:
        for index, item in enumerate(items):
            q = item["question"]
            category = item.get("category", "uncategorized")
            is_scored = item.get("scored", True)

            if paced:
                graph_result = run_with_pacing(
                    lambda question=q: orchestrator.answer(question),
                    retry_log=retry_events,
                )
            else:
                graph_result = orchestrator.answer(q)

            flat_result = query_baseline(q)
            ticket_result = query_ticket_baseline(q)
            checks = check_item(
                graph_result,
                flat_result,
                item,
                ticket_baseline_result=ticket_result,
            )

            row = {
                "id": item["id"],
                "question": q,
                "category": category,
                "scored": is_scored,
                "route": checks["route"],
                "expected_route": item.get("primary_route"),
                "route_match": (
                    checks["route"] == item.get("primary_route")
                    if item.get("primary_route")
                    else None
                ),
                "checks": checks,
            }
            results.append(row)

            if is_scored and item.get("primary_route"):
                routing_scored += 1
                if checks["route"] == item["primary_route"]:
                    routing_correct += 1

            if is_scored:
                by_category[category]["total"] += 1
                if checks["hybrid_match"]:
                    counters["hybrid"] += 1
                    by_category[category]["hybrid"] += 1
                if checks["flat_baseline_match"]:
                    counters["flat_baseline"] += 1
                    by_category[category]["flat_baseline"] += 1
                if checks["ticket_baseline_match"]:
                    counters["ticket_baseline"] += 1
                    by_category[category]["ticket_baseline"] += 1
                if checks["graph_branch_match"]:
                    counters["graph_branch"] += 1
                if checks["ticket_branch_match"]:
                    counters["ticket_branch"] += 1
                if checks["synthesis_match"]:
                    counters["synthesis"] += 1

            if verbose:
                print(
                    f"[{category}] scored={is_scored} {q}\n"
                    f"  route={checks['route']} hybrid={checks['hybrid_match']} "
                    f"flat={checks['flat_baseline_match']} ticket_rag={checks['ticket_baseline_match']}"
                )

            if paced and index < len(items) - 1:
                pace_between_requests()
    except EvaluationAbortedDueToRateLimit as exc:
        aborted = True
        abort_reason = str(exc)
    finally:
        orchestrator.close()

    scored_total = len(scored_items)
    wall_clock_s = time.perf_counter() - wall_start

    report = {
        "disclaimer": (
            "Substring/refusal-check benchmark on a small curated set. "
            "Not semantic answer grading. API calls spaced 5s apart with 2-retry cap."
        ),
        "total_items": len(items),
        "scored_items": scored_total,
        "completed_items": len(results),
        "aborted_due_to_rate_limit": aborted,
        "abort_reason": abort_reason,
        "wall_clock_seconds": wall_clock_s,
        "retry_events": retry_events,
        "accuracy": {
            "hybrid": _accuracy(counters["hybrid"], scored_total),
            "flat_baseline": _accuracy(counters["flat_baseline"], scored_total),
            "ticket_baseline": _accuracy(counters["ticket_baseline"], scored_total),
            "graph_branch": _accuracy(counters["graph_branch"], scored_total),
            "ticket_branch": _accuracy(counters["ticket_branch"], scored_total),
            "synthesis": _accuracy(counters["synthesis"], scored_total),
            "routing": _accuracy(routing_correct, routing_scored),
        },
        "counts": {
            **counters,
            "scored_total": scored_total,
            "routing_correct": routing_correct,
            "routing_scored": routing_scored,
        },
        "by_category": dict(by_category),
        "results": results,
    }
    return report


def format_report(report: dict) -> str:
    scored = report["counts"]["scored_total"]
    lines = [
        "Evaluation report (Section 12 expanded)",
        "=" * 60,
        report["disclaimer"],
        "",
        f"Items: {report['completed_items']}/{report['total_items']} completed | "
        f"{report['scored_items']} scored",
        f"Wall-clock: {report['wall_clock_seconds']:.1f}s",
        "",
        "Accuracy (scored items only):",
        f"  Hybrid:           {report['counts']['hybrid']}/{scored} ({100*report['accuracy']['hybrid']:.1f}%)",
        f"  Flat RAG:         {report['counts']['flat_baseline']}/{scored} ({100*report['accuracy']['flat_baseline']:.1f}%)",
        f"  Ticket RAG:       {report['counts']['ticket_baseline']}/{scored} ({100*report['accuracy']['ticket_baseline']:.1f}%)",
        f"  Graph branch:     {report['counts']['graph_branch']}/{scored} ({100*report['accuracy']['graph_branch']:.1f}%)",
        f"  Ticket branch:    {report['counts']['ticket_branch']}/{scored} ({100*report['accuracy']['ticket_branch']:.1f}%)",
        f"  Synthesis:        {report['counts']['synthesis']}/{scored} ({100*report['accuracy']['synthesis']:.1f}%)",
        f"  Routing (primary): {report['counts']['routing_correct']}/{report['counts']['routing_scored']} "
        f"({100*report['accuracy']['routing']:.1f}%)",
        "",
        "By category (scored only):",
    ]
    for category, stats in sorted(report["by_category"].items()):
        t = stats["total"]
        lines.append(
            f"  {category}: hybrid {stats['hybrid']}/{t}, "
            f"flat {stats['flat_baseline']}/{t}, ticket_rag {stats['ticket_baseline']}/{t}"
        )
    if report.get("aborted_due_to_rate_limit"):
        lines.extend(["", f"ABORTED: {report.get('abort_reason')}"])
    if report.get("retry_events"):
        lines.extend(["", f"API retry events: {len(report['retry_events'])}"])
    return "\n".join(lines)


def main() -> None:
    report = run_evaluation(verbose=True)
    print(format_report(report))
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nWrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
