"""Full regression runner (Section 26).

Runs the audit test suite in tiers and writes eval/regression_report.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TIERS = [
    {
        "name": "tier1_offline",
        "description": "No live API / Neo4j required",
        "files": [
            "test_cypher_safety.py",
            "test_ontology_manifest.py",
            "test_chroma_behavior.py",
            "test_ablation_analysis.py",
            "test_evaluation_audit.py",
            "test_graph_scale_analysis.py",
            "test_data_validation.py",
        ],
    },
    {
        "name": "tier2_infra",
        "description": "Neo4j + Chroma + local services",
        "files": [
            "test_phase0.py",
            "test_phase3.py",
            "test_phase5.py",
        ],
    },
    {
        "name": "tier3_api_security",
        "description": "FastAPI security + error boundaries (mocked Anthropic where needed)",
        "files": [
            "test_api_security.py",
            "test_error_boundaries.py",
        ],
    },
    {
        "name": "tier4_llm_integration",
        "description": "Live Anthropic API — skipped if ANTHROPIC_API_KEY unset",
        "files": [
            "test_nl_to_cypher_repair.py",
            "test_latency_instrumentation.py",
            "test_token_usage.py",
        ],
        "requires_api_key": True,
    },
    {
        "name": "tier5_full_llm_eval",
        "description": "Long-running live LLM + Neo4j suites",
        "files": [
            "test_nl_to_cypher_semantic.py",
            "test_routing_eval.py",
            "test_synthesis_hallucination.py",
            "test_synthesis_prompt_injection.py",
            "test_synthesis_unpopulated_label.py",
            "test_rag_retrieval_eval.py",
            "test_adversarial_unknown_entities.py",
        ],
        "requires_api_key": True,
    },
]


def run_pytest(files: list[str]) -> dict:
    paths = [str(ROOT / f) for f in files]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q", "--tb=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**dict(**__import__("os").environ)},
    )
    # Parse last line like "8 passed, 1 failed in 49.39s"
    summary = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    return {
        "exit_code": proc.returncode,
        "passed": proc.returncode == 0,
        "summary": summary,
        "stderr_tail": proc.stderr.strip().splitlines()[-5:] if proc.stderr else [],
    }


def build_report() -> dict:
    import os

    has_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    tier_results = []
    for tier in TIERS:
        if tier.get("requires_api_key") and not has_key:
            tier_results.append(
                {
                    "tier": tier["name"],
                    "description": tier["description"],
                    "skipped": True,
                    "reason": "ANTHROPIC_API_KEY not set",
                }
            )
            continue
        result = run_pytest(tier["files"])
        tier_results.append(
            {
                "tier": tier["name"],
                "description": tier["description"],
                "files": tier["files"],
                "skipped": False,
                **result,
            }
        )

    ran = [t for t in tier_results if not t.get("skipped")]
    return {
        "section": 26,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "anthropic_api_key_present": has_key,
        "all_passed": all(t.get("passed", False) for t in ran),
        "tiers": tier_results,
    }


def main() -> int:
    report = build_report()
    out = ROOT / "eval" / "regression_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWrote {out}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
