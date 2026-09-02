"""Latency instrumentation tests."""

import json

import pytest

from agent.orchestrator import HybridOrchestrator
from eval.latency_benchmark import BENCHMARK_CASES, RUNS_PER_CASE, format_report, run_benchmark


@pytest.fixture(scope="module")
def orchestrator():
    instance = HybridOrchestrator()
    yield instance
    instance.close()


def test_latency_fields_present_on_answer(orchestrator):
    result = orchestrator.answer("How many customers are there?")
    latency = result["latency_ms"]
    assert latency["routing"] > 0
    assert latency["cypher_generation"] > 0
    assert latency["neo4j_execution"] >= 0
    assert latency["synthesis"] > 0
    assert latency["total"] > 0
    assert latency["chroma_retrieval"] is None


@pytest.mark.slow
def test_latency_benchmark_real_requests(capsys):
    report = run_benchmark(runs_per_case=RUNS_PER_CASE)
    print("\n" + format_report(report))
    assert report["wall_clock_seconds"] > 0
    if report["aborted_due_to_rate_limit"]:
        pytest.skip(f"Benchmark aborted due to rate limit: {report['abort_reason']}")
    assert len(report["cases"]) == 3
    for case in report["cases"]:
        assert case["runs_completed"] == RUNS_PER_CASE, (
            f"{case['id']}: only {case['runs_completed']}/{case['runs_requested']} completed"
        )
        total_stats = case["component_stats_ms"]["total"]
        assert total_stats["count"] == RUNS_PER_CASE
        assert total_stats["avg_ms"] > 0
        print(json.dumps(case["component_stats_ms"], indent=2))
