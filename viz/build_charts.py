"""Build static charts from existing project data (Approach A — read-only, no API changes).

Reads Northwind CSVs and eval JSON reports only. Does not call the orchestrator,
LLM, Neo4j, or Chroma.

Usage (from repo root):
    pip install -r requirements-viz.txt
    python viz/build_charts.py

Outputs PNG files and a simple index.html under viz/output/.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(__file__).resolve().parent / "output"

THEME_PATTERNS: list[tuple[str, str]] = [
    ("Delay / carrier", r"\bdelay\b|\bcarrier\b"),
    ("Damaged product", r"\bdamaged\b|\breplacement\b"),
    ("Invoice / pricing", r"\binvoice\b|\bpricing\b|\bdiscrepancy\b"),
    ("Billing / payment", r"\bbilling\b|\bpayment\b|\bcharge\b"),
    ("Other", r".*"),
]


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
    ax.set_xlim(0, 105)
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


def chart_customers_by_country(out: Path, top_n: int = 12) -> Path:
    df = pd.read_csv(ROOT / "data" / "customers.csv")
    counts = df["country"].value_counts().head(top_n)

    fig, ax = plt.subplots(figsize=(9, 5))
    counts.plot(kind="barh", ax=ax, color="#3498db")
    ax.set_xlabel("Number of customers")
    ax.set_title(f"Customers by country (top {top_n})")
    ax.invert_yaxis()
    fig.tight_layout()
    path = out / "customers_by_country.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _classify_ticket(text: str) -> str:
    lower = text.lower()
    for label, pattern in THEME_PATTERNS[:-1]:
        if re.search(pattern, lower):
            return label
    return "Other"


def _ticket_theme_counts() -> tuple[Counter[str], Counter[str], int, int]:
    """Classify all tickets; optionally drop small 'Other' bucket from chart only."""
    tickets = json.loads((ROOT / "data" / "support_tickets.json").read_text(encoding="utf-8"))
    full = Counter(_classify_ticket(t["text"]) for t in tickets)
    total = len(tickets)
    displayed = full.copy()
    dropped_other = 0
    if displayed["Other"] < total * 0.05:
        dropped_other = displayed["Other"]
        del displayed["Other"]
    return full, displayed, dropped_other, total


def chart_ticket_themes(out: Path) -> tuple[Path, Counter[str], int, int]:
    full, displayed, dropped_other, total = _ticket_theme_counts()

    labels = list(displayed.keys())
    values = [displayed[k] for k in labels]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(labels, values, color="#9b59b6")
    ax.set_ylabel("Ticket count")
    ax.set_title("Support ticket themes (keyword rules on ticket text)")
    plt.xticks(rotation=25, ha="right")
    fig.text(
        0.5,
        -0.02,
        "Themes are mutually exclusive by first-match keyword order "
        "(e.g. delay + billing → Delay / carrier only). Not multi-label.",
        ha="center",
        fontsize=8,
        color="#555",
        wrap=True,
    )
    fig.tight_layout()
    path = out / "ticket_themes.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path, full, dropped_other, total


def write_index_html(out: Path, images: list[Path]) -> Path:
    rel = [img.name for img in images]
    sections = []
    for name in rel:
        title = name.replace("_", " ").replace(".png", "").title()
        extra = ""
        if name == "ticket_themes.png":
            extra = (
                '<p class="note">Ticket themes are mutually exclusive by first-match keyword order '
                "(a ticket mentioning both &ldquo;delay&rdquo; and &ldquo;billing&rdquo; is "
                "bucketed only under whichever pattern is checked first). Not multi-label categorization.</p>"
            )
        sections.append(
            f'  <section><h2>{title}</h2>{extra}'
            f'<img src="{name}" alt="{name}" width="900"/></section>'
        )
    body = "\n".join(sections)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Enterprise KG Agent — static charts</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 960px; margin: 2rem auto; padding: 0 1rem; }}
    h1 {{ font-size: 1.25rem; }}
    section {{ margin-bottom: 2.5rem; }}
    img {{ max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; }}
    p.note {{ color: #555; font-size: 0.9rem; }}
  </style>
</head>
<body>
  <h1>Enterprise Knowledge Graph Agent — read-only charts</h1>
  <p class="note">Generated by <code>viz/build_charts.py</code>. Data from eval JSON and Northwind CSVs only — no LLM or live DB calls.</p>
{body}
</body>
</html>
"""
    path = out / "index.html"
    path.write_text(html, encoding="utf-8")
    return path


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    benchmark = chart_benchmark_accuracy(OUTPUT)
    customers = chart_customers_by_country(OUTPUT)
    tickets, full_themes, dropped_other, ticket_total = chart_ticket_themes(OUTPUT)

    displayed_sum = sum(
        c for label, c in full_themes.items() if not (label == "Other" and dropped_other)
    )
    print(
        f"Ticket themes: displayed_sum={displayed_sum}, "
        f"dropped_Other={dropped_other}, total={displayed_sum + dropped_other} "
        f"(expected {ticket_total})"
    )
    if displayed_sum + dropped_other != ticket_total:
        raise SystemExit(
            f"Ticket theme counts do not sum to {ticket_total}: "
            f"{displayed_sum} + {dropped_other} = {displayed_sum + dropped_other}"
        )

    images = [benchmark, customers, tickets]
    index = write_index_html(OUTPUT, images)
    print("Wrote charts:")
    for img in images:
        print(f"  {img}")
    print(f"  {index}")
    print(f"\nOpen: file://{index.resolve()}")


if __name__ == "__main__":
    main()
