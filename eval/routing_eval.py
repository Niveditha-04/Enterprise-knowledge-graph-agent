"""Routing evaluation: compare predicted routes against independently-labeled expectations."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROUTES = ("GRAPH", "TICKETS", "BOTH")
CASES_PATH = Path(__file__).parent / "routing_cases.json"


def load_routing_cases(path: Path | None = None) -> list[dict[str, Any]]:
    return json.loads((path or CASES_PATH).read_text())


def clear_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in cases if c.get("clear", True)]


def ambiguous_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in cases if not c.get("clear", True)]


def _predict_route(classify_fn, question: str) -> str:
    """Normalize classifier output (str or (route, usage, ms) tuple)."""
    result = classify_fn(question)
    if isinstance(result, tuple):
        result = result[0]
    return result.strip().upper()


def evaluate_routing(
    classify_fn,
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cases = cases or load_routing_cases()
    results: list[dict[str, Any]] = []

    for case in cases:
        predicted = _predict_route(classify_fn, case["question"])
        if predicted not in ROUTES:
            for route in ROUTES:
                if route in predicted:
                    predicted = route
                    break
        entry = {
            "id": case["id"],
            "question": case["question"],
            "clear": case.get("clear", True),
            "adversarial": case.get("adversarial", False),
            "expected_route": case.get("expected_route"),
            "predicted_route": predicted,
            "defensible_routes": case.get("defensible_routes"),
            "rationale": case.get("rationale", ""),
        }
        if case.get("clear", True):
            entry["correct"] = predicted == case["expected_route"]
        else:
            entry["correct"] = None
        results.append(entry)

    clear = [r for r in results if r["clear"]]
    correct_count = sum(1 for r in clear if r["correct"])
    total_clear = len(clear)

    per_class: dict[str, dict[str, int]] = {
        route: {"total": 0, "correct": 0} for route in ROUTES
    }
    for r in clear:
        expected = r["expected_route"]
        per_class[expected]["total"] += 1
        if r["correct"]:
            per_class[expected]["correct"] += 1

    confusion: dict[str, dict[str, int]] = {
        expected: {predicted: 0 for predicted in ROUTES} for expected in ROUTES
    }
    for r in clear:
        confusion[r["expected_route"]][r["predicted_route"]] += 1

    return {
        "results": results,
        "total_clear": total_clear,
        "correct_clear": correct_count,
        "overall_accuracy": correct_count / total_clear if total_clear else 0.0,
        "per_class": per_class,
        "confusion_matrix": confusion,
        "ambiguous_results": [r for r in results if not r["clear"]],
    }


def format_confusion_matrix(confusion: dict[str, dict[str, int]]) -> str:
    col_width = 8
    header = f"{'':12}" + "".join(f"{r:>{col_width}}" for r in ROUTES)
    lines = [header, "-" * len(header)]
    for expected in ROUTES:
        row = f"{expected:12}" + "".join(
            f"{confusion[expected][predicted]:>{col_width}}" for predicted in ROUTES
        )
        lines.append(row)
    lines.append("")
    lines.append("Rows = expected route, Columns = predicted route")
    return "\n".join(lines)


def format_report(report: dict[str, Any]) -> str:
    lines = [
        "Routing evaluation report",
        "=" * 60,
        f"Clear-cut questions: {report['correct_clear']}/{report['total_clear']} "
        f"({100 * report['overall_accuracy']:.1f}% accuracy)",
        "",
        "Per-class accuracy (clear-cut only):",
    ]
    for route in ROUTES:
        stats = report["per_class"][route]
        if stats["total"]:
            acc = 100 * stats["correct"] / stats["total"]
            lines.append(f"  {route:8} {stats['correct']}/{stats['total']} ({acc:.1f}%)")
        else:
            lines.append(f"  {route:8} (no cases)")

    lines.extend(["", "Confusion matrix:", format_confusion_matrix(report["confusion_matrix"])])

    lines.extend(["", "Per-case results (clear-cut):"])
    for r in report["results"]:
        if not r["clear"]:
            continue
        status = "PASS" if r["correct"] else "FAIL"
        adv = " [adversarial]" if r.get("adversarial") else ""
        lines.append(
            f"  [{status}]{adv} {r['id']}: expected={r['expected_route']} "
            f"predicted={r['predicted_route']}"
        )

    if report["ambiguous_results"]:
        lines.extend(["", "Ambiguous / multi-intent (not scored):"])
        for r in report["ambiguous_results"]:
            defensible = ", ".join(r["defensible_routes"] or [])
            in_defensible = r["predicted_route"] in (r["defensible_routes"] or [])
            note = "within defensible set" if in_defensible else "outside defensible set"
            lines.append(
                f"  [{r['id']}] predicted={r['predicted_route']} "
                f"(defensible: {defensible}; {note})"
            )
            lines.append(f"    Q: {r['question']}")

    return "\n".join(lines)
