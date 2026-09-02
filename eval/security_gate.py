"""Final security gate (Section 25).

Runs automated checks before release / audit sign-off. No new features — verification only.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Application code that may execute Cypher at runtime (must go through cypher_safety).
RUNTIME_CYPHER_FILES = [
    ROOT / "agent" / "nl_to_cypher.py",
]

# Offline loaders — not in the /ask path; documented separately.
OFFLINE_CYPHER_FILES = [
    ROOT / "graph" / "load_graph.py",
    ROOT / "eval" / "evaluation_audit.py",
]

DIRECT_DRIVER_PATTERN = re.compile(
    r"session\.run\s*\(|GraphDatabase\.driver\s*\(",
)


def run_secret_scan() -> dict:
    script = ROOT / "scripts" / "check_secrets.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return {
        "check": "secret_scan",
        "passed": proc.returncode == 0,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def audit_neo4j_call_paths() -> dict:
    """Document where Neo4j is called and whether cypher_safety applies."""
    runtime_hits: list[dict] = []
    for path in RUNTIME_CYPHER_FILES:
        text = path.read_text(encoding="utf-8")
        uses_validation = "validate_read_only_cypher" in text
        has_session_run = "session.run" in text
        runtime_hits.append(
            {
                "file": str(path.relative_to(ROOT)),
                "session_run": has_session_run,
                "uses_cypher_safety": uses_validation,
                "in_ask_path": True,
            }
        )

    offline = [str(p.relative_to(ROOT)) for p in OFFLINE_CYPHER_FILES]

    bypass_risk = (
        "A write bypass would be: (1) a bug in cypher_safety.py that fails to reject "
        "a mutation, (2) new code calling GraphDatabase.driver().session().run() without "
        "validate_read_only_cypher — e.g. a shortcut in orchestrator or a new API route — "
        "or (3) using the Neo4j credentials directly outside this app (credentials are "
        "full-write on Community Edition; see Section 2 / Section 23)."
    )

    return {
        "check": "neo4j_call_path_audit",
        "passed": all(h["uses_cypher_safety"] for h in runtime_hits if h["session_run"]),
        "runtime_paths": runtime_hits,
        "offline_loaders": offline,
        "bypass_risk_note": bypass_risk,
    }


def check_gitignore_sensitive() -> dict:
    gitignore = ROOT / ".gitignore"
    required = {".env", "chroma_db", "venv"}
    present = set()
    if gitignore.exists():
        text = gitignore.read_text(encoding="utf-8")
        for item in required:
            if item in text:
                present.add(item)
    return {
        "check": "gitignore_sensitive_paths",
        "passed": required <= present,
        "required": sorted(required),
        "found": sorted(present),
    }


def build_report() -> dict:
    checks = [
        run_secret_scan(),
        audit_neo4j_call_paths(),
        check_gitignore_sensitive(),
    ]
    return {
        "section": 25,
        "all_passed": all(c["passed"] for c in checks),
        "checks": checks,
        "manual_security_tests": [
            "pytest test_cypher_safety.py test_api_security.py test_synthesis_prompt_injection.py -v",
            "pytest test_error_boundaries.py -v",
        ],
        "known_limitations": [
            "Neo4j Community Edition — no read-only DB role (Section 2)",
            "No API authentication (Section 9)",
            "Cypher validation is application-layer only",
        ],
    }


def main() -> int:
    report = build_report()
    out = ROOT / "eval" / "security_gate_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nWrote {out}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
