"""Ablation analysis derives from evaluation report without extra API calls."""

from eval.ablation_analysis import analyze, load_report


def test_ablation_post_fix_numbers():
    analysis = analyze(load_report())
    assert analysis["systems"]["synthesis"]["correct"] == 22
    assert analysis["systems"]["hybrid"]["correct"] == 23
    assert analysis["systems"]["graph_branch"]["correct"] == 17
    assert analysis["systems"]["flat_baseline"]["correct"] == 5
    assert analysis["systems"]["ticket_baseline"]["correct"] == 7
    assert analysis["deltas"]["evidence_vs_synthesis_gap"]["count"] == 1
