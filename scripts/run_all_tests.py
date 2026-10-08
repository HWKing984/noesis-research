#!/usr/bin/env python3
"""Run every test suite in this repository and report what really happened.

Zero third-party requirements for the core suites — ``integrations/`` and
``packages/`` import with the standard library alone, on purpose, because they
are the seam the agent tools sit on. The API suite needs FastAPI and skips
itself when it is missing, so this script is safe to run with any interpreter.

The two flags exist to close the "green because nothing ran" hole:

``--require key[,key]``      listed suites must run and must not skip
``--expect-skip key[,key]``  listed suites must skip (proves the skip is a
                             dependency skip, not a silently broken import)

Usage:
    python scripts/run_all_tests.py [--verbose] [--require api] [--expect-skip live]
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SUITES: tuple[tuple[str, str, Path], ...] = (
    ("adapter", "offline / knowledge-graph adapter", ROOT / "integrations" / "knowledge-graph"),
    ("contracts", "offline / evidence contract", ROOT / "packages" / "contracts"),
    ("api", "http / research API (requires fastapi)", ROOT / "apps" / "api"),
    ("agent", "agent / research tools (requires deepagents)", ROOT / "services" / "research-agent"),
    ("live", "live / knowledge graph + API (self-skips)", ROOT / "tests" / "integration"),
)

_RAN = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)
_SKIPPED = re.compile(r"skipped=(\d+)")


@dataclass
class SuiteResult:
    key: str
    label: str
    exit_code: int
    ran: int
    skipped: int

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and self.ran > 0


def _run(key: str, label: str, directory: Path, *, verbose: bool) -> SuiteResult:
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
    print(f"=== {key}: {label} ===", flush=True)
    completed = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, errors="replace")
    output = (completed.stdout or "") + (completed.stderr or "")
    print(output.rstrip(), flush=True)

    ran_match = _RAN.search(output)
    skip_match = _SKIPPED.search(output)
    return SuiteResult(
        key=key,
        label=label,
        exit_code=completed.returncode,
        ran=int(ran_match.group(1)) if ran_match else 0,
        skipped=int(skip_match.group(1)) if skip_match else 0,
    )


def _parse_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _flag_value(argv: list[str], flag: str) -> str | None:
    if flag in argv:
        index = argv.index(flag)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv or "-v" in argv
    required = _parse_list(_flag_value(argv, "--require"))
    expect_skip = _parse_list(_flag_value(argv, "--expect-skip"))
    known = {key for key, _, _ in SUITES}

    unknown = [key for key in required + expect_skip if key not in known]
    if unknown:
        print(f"unknown suite key(s): {', '.join(unknown)}; known: {', '.join(sorted(known))}")
        return 2

    results: list[SuiteResult] = []
    for key, label, directory in SUITES:
        if not directory.is_dir():
            print(f"!!! suite directory missing: {directory}")
            results.append(SuiteResult(key=key, label=label, exit_code=1, ran=0, skipped=0))
            continue
        results.append(_run(key, label, directory, verbose=verbose))

    by_key = {result.key: result for result in results}
    problems: list[str] = []
    for result in results:
        if result.exit_code != 0:
            problems.append(f"{result.key}: exit {result.exit_code}")
    for key in required:
        result = by_key.get(key)
        if result is None or not result.passed:
            problems.append(f"{key}: required to run, but ran={result.ran if result else 0} exit={result.exit_code if result else 'n/a'}")
        elif result.skipped:
            problems.append(f"{key}: required to run, but {result.skipped} test(s) skipped")
    for key in expect_skip:
        result = by_key.get(key)
        if result is None or result.exit_code != 0:
            problems.append(f"{key}: expected to skip cleanly, but exit={result.exit_code if result else 'n/a'}")
        elif not result.skipped:
            problems.append(f"{key}: expected a dependency skip, but nothing skipped (ran={result.ran})")

    print()
    print("suite      ran  skipped  exit")
    for result in results:
        print(f"{result.key:<10} {result.ran:>3}  {result.skipped:>7}  {result.exit_code:>4}")

    if problems:
        print()
        print("FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    total_ran = sum(result.ran - result.skipped for result in results)
    print()
    print(f"all {len(results)} suites ok ({total_ran} tests executed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
