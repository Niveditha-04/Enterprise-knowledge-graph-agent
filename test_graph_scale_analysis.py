"""Tests for graph scale analysis report structure (no scale benchmarks)."""

from eval.graph_scale_analysis import (
    AVG_LINES_PER_ORDER,
    CURRENT_COUNTS,
    build_report,
    project_counts,
    scale_assessment,
)


def test_current_demo_ratio_sane():
    assert CURRENT_COUNTS["Order"] == 830
    assert AVG_LINES_PER_ORDER > 2


def test_project_counts_scales_orders():
    p = project_counts(100_000)
    assert p["Order"] == 100_000
    assert p["CONTAINS"] == int(round(100_000 * AVG_LINES_PER_ORDER))


def test_scale_assessment_tiers():
    assert scale_assessment(50_000)["tier"] == "100K"
    assert scale_assessment(500_000)["tier"] == "1M"
    assert scale_assessment(5_000_000)["tier"] == "10M"


def test_build_report_has_operational_indexes():
    report = build_report()
    assert report["current_counts"]["Order"] > 0
    assert len(report["operational_indexes"]) == 4
    assert "100_000_orders" in report["scale_projections"]
