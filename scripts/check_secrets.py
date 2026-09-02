#!/usr/bin/env python3
"""Scan tracked project files for likely secrets before commit."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

IGNORE_DIRS = {
    "venv",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "chroma_db",
    "chroma_db_baseline",
    ".git",
}

PATTERNS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "Anthropic API key"),
    (re.compile(r"NEO4J_PASSWORD\s*=\s*[^\s#]+"), "Neo4j password assignment"),
    (re.compile(r"ANTHROPIC_API_KEY\s*=\s*sk-"), "Anthropic API key assignment"),
]

BLOCKED_TRACKED = {".env", "chroma_db", "chroma_db_baseline", "venv"}

# Deliberate fake credentials in leak-prevention tests (not real secrets).
ALLOWLIST_PATHS = {
    "test_api_security.py",
    "eval/capture_exception_leak_transcripts.py",
}


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def git_tracked_files() -> set[str]:
    try:
        out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return set()
    return set(out.splitlines())


def main() -> int:
    failures: list[str] = []

    tracked = git_tracked_files()
    for blocked in BLOCKED_TRACKED:
        if blocked in tracked:
            failures.append(f"Tracked file should not be committed: {blocked}")

    if (ROOT / ".env").exists() and ".env" in tracked:
        failures.append(".env is tracked by git")

    for path in iter_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWLIST_PATHS:
            continue
        if rel in {".env.example"}:
            continue
        if rel == ".env":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern, label in PATTERNS:
            if pattern.search(text):
                failures.append(f"{label} pattern found in {rel}")

    if failures:
        print("SECRET / SAFETY CHECK FAILED:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("Secret scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
