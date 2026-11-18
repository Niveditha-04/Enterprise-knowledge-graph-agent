"""Build static charts from existing project data (read-only, no API calls).

Reads eval JSON reports only. Does not call the orchestrator, LLM, Neo4j, or Chroma.

Usage (from repo root):
    pip install -r requirements.txt
    python viz/build_charts.py

Outputs PNG files under viz/output/.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(__file__).resolve().parent / "output"


def _load_eval_counts() -> list[tuple[str, int, int]]:
    report = json.loads((ROOT / "eval" / "evaluation_report.json").read_text(encoding="utf-8"))
    total = report["counts"]["scored_total"]
    rows = [
        ("Synthesis (NL answer)", report["counts"]["synthesis"], total),
        ("Hybrid (evidence)", report["counts"]["hybrid"], total),
        ("Graph branch", report["counts"]["graph_branch"], total),
        ("Flat RAG baseline", report["counts"]["flat_baseline"], total),
        ("Ticket RAG baseline", report["counts"]["ticket_baseline"], total),
    ]
    return rows


def chart_benchmark_accuracy(out: Path) -> Path:
    rows = _load_eval_counts()
    labels = [r[0] for r in rows]
    correct = [r[1] for r in rows]
    totals = [r[2] for r in rows]
    pcts = [100 * c / t for c, t in zip(correct, totals)]

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = ["#2ecc71" if "Synthesis" in lbl or "Hybrid" in lbl else "#95a5a6" for lbl in labels]
    bars = ax.barh(labels, pcts, color=colors)
    ax.set_xlim(0, 112)
    ax.set_xlabel("Accuracy (%)")
    ax.set_title("Evaluation benchmark (23 scored questions)")
    ax.invert_yaxis()

    for bar, c, t in zip(bars, correct, totals):
        ax.text(
            bar.get_width() + 1,
            bar.get_y() + bar.get_height() / 2,
            f"{c}/{t}",
            va="center",
            fontsize=9,
        )

    fig.tight_layout()
    path = out / "benchmark_accuracy.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    benchmark = chart_benchmark_accuracy(OUTPUT)
    print("Wrote charts:")
    print(f"  {benchmark}")


if __name__ == "__main__":
    main()
