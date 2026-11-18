"""Latency benchmark: repeated real requests with per-component timing."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from pathlib import Path

from anthropic import APIStatusError

from agent.latency import summarize_component_runs
from agent.orchestrator import HybridOrchestrator

RUNS_PER_CASE = 3
MAX_RETRY_ATTEMPTS = 2
INTER_RUN_DELAY_S = 5
MAX_RETRY_WAIT_S = 15
RATE_LIMIT_CODES = {429, 529}

BENCHMARK_CASES = [
    {
        "id": "graph_count_customers",
        "expected_route": "GRAPH",
        "question": "How many customers are there?",
    },
    {
        "id": "tickets_damaged_products",
        "expected_route": "TICKETS",
        "question": "Which support tickets mention that products arrived damaged?",
    },
    {
        "id": "both_chai_damaged_customers",
        "expected_route": "BOTH",
        "question": "Which customers who ordered Chai also filed support tickets about damaged products?",
    },
]

COMPONENTS = [
    "routing",
    "cypher_generation",
    "cypher_repair",
    "neo4j_execution",
    "chroma_retrieval",
    "synthesis",
    "total",
]


class BenchmarkAbortedDueToRateLimit(Exception):
    """Raised when benchmark should stop after sustained API throttling."""


def detect_environment() -> dict[str, str]:
    env = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "neo4j": "Neo4j 5.24 Community in Docker (local container kg-agent-neo4j)",
        "chroma": "ChromaDB persistent local index at ./chroma_db",
        "anthropic_api": "Claude Sonnet 4.5 via Anthropic API (network latency included)",
        "load_model": "Single sequential requests, no concurrency",
    }
    try:
        env["cpu"] = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip()
    except Exception:
        env["cpu"] = platform.processor() or platform.machine()
    try:
        mem_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip())
        env["memory_gb"] = f"{mem_bytes / (1024 ** 3):.0f} GB"
    except Exception:
        env["memory_gb"] = "unknown"
    return env


def run_with_retries(
    orchestrator: HybridOrchestrator,
    question: str,
    retry_log: list[dict],
    max_attempts: int = MAX_RETRY_ATTEMPTS,
) -> tuple[dict, float]:
    """Return (result, api_throttling_overhead_ms)."""
    throttle_ms = 0.0
    for attempt in range(1, max_attempts + 1):
        try:
            return orchestrator.answer(question), throttle_ms
        except APIStatusError as exc:
            wait_s = min(MAX_RETRY_WAIT_S, 2 ** attempt)
            throttle_ms += wait_s * 1000
            retry_log.append(
                {
                    "question": question,
                    "attempt": attempt,
                    "status_code": exc.status_code,
                    "wait_s": wait_s,
                    "message": str(exc),
                }
            )
            if attempt >= max_attempts:
                if exc.status_code in RATE_LIMIT_CODES:
                    raise BenchmarkAbortedDueToRateLimit(
                        f"Anthropic API server-side capacity error (HTTP 529 overloaded) "
                        f"persisted after {max_attempts} retries"
                    ) from exc
                raise
            print(
                f"  API error ({exc.status_code}), retrying in {wait_s}s "
                f"(attempt {attempt}/{max_attempts})",
                flush=True,
            )
            time.sleep(wait_s)


def run_benchmark(runs_per_case: int = RUNS_PER_CASE) -> dict:
    wall_start = time.perf_counter()
    orchestrator = HybridOrchestrator()
    environment = detect_environment()
    cases_out = []
    retry_events: list[dict] = []
    failed_runs: list[dict] = []
    aborted = False
    abort_reason: str | None = None
    total_throttling_overhead_ms = 0.0
    total_request_latency_ms = 0.0

    try:
        for case in BENCHMARK_CASES:
            case_runs = []
            print(f"\nRunning {case['id']} ({case['expected_route']})...")
            for i in range(runs_per_case):
                print(f"  run {i + 1}/{runs_per_case}", flush=True)
                try:
                    result, throttle_ms = run_with_retries(
                        orchestrator, case["question"], retry_events
                    )
                    total_throttling_overhead_ms += throttle_ms
                    request_latency = float(result["latency_ms"]["total"])
                    total_request_latency_ms += request_latency
                    case_runs.append(
                        {
                            "run": i + 1,
                            "route": result["route"],
                            "latency_ms": result["latency_ms"],
                            "api_throttling_overhead_ms": throttle_ms,
                        }
                    )
                except BenchmarkAbortedDueToRateLimit as exc:
                    aborted = True
                    abort_reason = str(exc)
                    failed_runs.append(
                        {
                            "case_id": case["id"],
                            "run": i + 1,
                            "status": "aborted_benchmark",
                            "error": str(exc),
                        }
                    )
                    print(f"  STOPPING BENCHMARK: {exc}", flush=True)
                    break
                except APIStatusError as exc:
                    failed_runs.append(
                        {
                            "case_id": case["id"],
                            "run": i + 1,
                            "status_code": exc.status_code,
                            "error": str(exc),
                        }
                    )
                    print(f"  FAILED after retries: {exc.status_code}", flush=True)
                if aborted:
                    break
                if i < runs_per_case - 1:
                    time.sleep(INTER_RUN_DELAY_S)
            component_stats = {
                component: summarize_component_runs(case_runs, component)
                for component in COMPONENTS
            }
            throttle_values = [r["api_throttling_overhead_ms"] for r in case_runs]
            cases_out.append(
                {
                    "id": case["id"],
                    "expected_route": case["expected_route"],
                    "question": case["question"],
                    "runs_requested": runs_per_case,
                    "runs_completed": len(case_runs),
                    "runs_failed": runs_per_case - len(case_runs) if not aborted else runs_per_case - len(case_runs),
                    "routes_observed": [r["route"] for r in case_runs],
                    "component_stats_ms": component_stats,
                    "api_throttling_overhead_ms": {
                        "per_run": throttle_values,
                        "total": sum(throttle_values),
                    },
                }
            )
            if aborted:
                break
    finally:
        orchestrator.close()

    wall_clock_s = time.perf_counter() - wall_start

    return {
        "environment": environment,
        "disclaimer": (
            "Local single-machine latency with sequential requests and no concurrent load. "
            "Not production latency. Includes network round-trips to Anthropic API."
        ),
        "runs_per_case": runs_per_case,
        "inter_run_delay_s": INTER_RUN_DELAY_S,
        "max_retry_attempts": MAX_RETRY_ATTEMPTS,
        "wall_clock_seconds": wall_clock_s,
        "aggregate": {
            "completed_requests": sum(c["runs_completed"] for c in cases_out),
            "failed_or_skipped_requests": len(failed_runs),
            "total_request_latency_ms": total_request_latency_ms,
            "total_api_throttling_overhead_ms": total_throttling_overhead_ms,
        },
        "retry_events": retry_events,
        "failed_runs": failed_runs,
        "aborted_due_to_rate_limit": aborted,
        "abort_reason": abort_reason,
        "cases": cases_out,
    }


def format_report(report: dict) -> str:
    lines = [
        "Latency benchmark report",
        "=" * 72,
        report["disclaimer"],
        "",
        f"Wall-clock time: {report['wall_clock_seconds']:.1f}s",
        f"Inter-run delay: {report['inter_run_delay_s']}s | Max retries: {report['max_retry_attempts']}",
        "",
        "Aggregate (completed requests only):",
        f"  Actual request/response latency (sum): {report['aggregate']['total_request_latency_ms']:.1f} ms",
        f"  API throttling overhead (sum): {report['aggregate']['total_api_throttling_overhead_ms']:.1f} ms",
        f"    (throttling overhead is NOT system latency)",
        "",
        "Environment:",
    ]
    for key, value in report["environment"].items():
        lines.append(f"  {key}: {value}")

    if report.get("aborted_due_to_rate_limit"):
        lines.extend(["", f"ABORTED: {report.get('abort_reason')}"])

    for case in report["cases"]:
        lines.extend(
            [
                "",
                f"Case: {case['id']} ({case['expected_route']})",
                f"Question: {case['question']}",
                f"Runs: {case['runs_completed']}/{case['runs_requested']} completed | routes: {case['routes_observed']}",
                f"API throttling overhead (this case): {case['api_throttling_overhead_ms']['total']:.1f} ms",
                "",
                "Actual request/response latency by component (ms):",
                f"{'component':<20} {'avg':>10} {'median':>10} {'p95':>10} {'n':>5}",
                "-" * 58,
            ]
        )
        for component in COMPONENTS:
            stats = case["component_stats_ms"][component]
            if stats["count"] == 0:
                lines.append(f"{component:<20} {'—':>10} {'—':>10} {'—':>10} {'0':>5}")
                continue
            lines.append(
                f"{component:<20} "
                f"{stats['avg_ms']:>10.1f} "
                f"{stats['median_ms']:>10.1f} "
                f"{stats['p95_ms']:>10.1f} "
                f"{stats['count']:>5.0f}"
            )

    if report.get("retry_events"):
        lines.extend(["", "Retry events:", json.dumps(report["retry_events"], indent=2)])
    if report.get("failed_runs"):
        lines.extend(["", "Failed/skipped runs:", json.dumps(report["failed_runs"], indent=2)])

    return "\n".join(lines)


def main() -> None:
    report = run_benchmark()
    output = format_report(report)
    print(output)
    out_path = Path(__file__).parent / "latency_benchmark_report.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
