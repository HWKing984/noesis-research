#!/usr/bin/env python3
"""Run every test suite in this repository.

Standard library only — no third-party test runner, no install step. That is a
deliberate property of this repository today: everything under
``integrations/`` and ``packages/`` imports with the stdlib alone, so CI can be
a bare Python interpreter plus this script.

Suites that need a live service skip themselves (see
``tests/integration/test_kg_live.py``), so this exits 0 with or without Neo4j.

Usage:
    python scripts/run_all_tests.py [--verbose]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SUITES: tuple[tuple[str, Path], ...] = (
    ("offline / knowledge-graph adapter", ROOT / "integrations" / "knowledge-graph"),
    ("offline / evidence contract", ROOT / "packages" / "contracts"),
    ("live / knowledge graph (self-skips when unreachable)", ROOT / "tests" / "integration"),
)


def _run(name: str, directory: Path, *, verbose: bool) -> int:
    command = [
        sys.executable,
        "-m",
        "unittest",
        "discover",
        "-s",
        str(directory),
        "-t",
        str(directory),
    ]
    if verbose:
        command.append("-v")
    print(f"=== {name} ===", flush=True)
    result = subprocess.run(command, cwd=str(ROOT))
    print(f"--- {name}: exit {result.returncode}", flush=True)
    return result.returncode


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv or "-v" in argv
    failures: list[str] = []
    for name, directory in SUITES:
        if not directory.is_dir():
            print(f"!!! suite directory missing: {directory}", flush=True)
            failures.append(name)
            continue
        if _run(name, directory, verbose=verbose) != 0:
            failures.append(name)

    print()
    if failures:
        print(f"FAILED suites ({len(failures)}): {', '.join(failures)}")
        return 1
    print(f"all {len(SUITES)} suites passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
