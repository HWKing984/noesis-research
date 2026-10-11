"""Replay from verified extracted ZIP sources, without falling back to host project code."""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def verify_archive(archive):
    def check_name(name):
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or name.endswith("/"):
            raise ValueError(f"Unsafe archive path: {name}")

    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len({name.casefold() for name in names}):
            raise ValueError("Duplicate ZIP entries")
        for name in names:
            check_name(name)
        manifest = json.loads(bundle.read("manifest.json"))
        hashes = manifest["files_sha256"]
        for name in hashes:
            check_name(name)
        if set(names) != set(hashes) | {"manifest.json"}:
            raise ValueError("Archive entries differ from manifest")
        if bundle.testzip() is not None:
            raise ValueError("ZIP CRC check failed")
        for name, expected in hashes.items():
            if hashlib.sha256(bundle.read(name)).hexdigest() != expected:
                raise ValueError(f"File hash mismatch: {name}")
    return {"files_checked": len(hashes), "zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--export-manifest", required=True, type=Path)
    parser.add_argument("--playwright-module", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError("Replay evidence exists; choose a new report")
    integrity = verify_archive(args.archive)
    exterior = json.loads(args.export_manifest.read_text(encoding="utf-8"))
    if integrity["zip_sha256"] != exterior["zip_sha256"]:
        raise ValueError("External ZIP hash mismatch")
    replay = Path(tempfile.mkdtemp(prefix=".review-replay-", dir=ROOT)).resolve()
    with zipfile.ZipFile(args.archive) as bundle:
        for name in bundle.namelist():
            if not (replay / name).resolve().is_relative_to(replay):
                raise ValueError("Extraction path escaped replay directory")
        bundle.extractall(replay)
    proof = "import sys,json;from pathlib import Path;sys.path.insert(0,str(Path.cwd()/'scripts'));import annotation_v2,prepare_revision_v2;mods=[annotation_v2,prepare_revision_v2];assert all(Path(m.__file__).resolve().is_relative_to(Path.cwd()) for m in mods);print(json.dumps([m.__file__ for m in mods]))"
    commands = {
        "module_sources": [sys.executable, "-c", proof],
        "pytest": [sys.executable, "-m", "pytest", "tests", "-q"],
        "browser_v2": ["node", "tests/test_review_v2.cjs", args.playwright_module],
        "browser_v1_regression": ["node", "tests/test_pilot_review.cjs", args.playwright_module]}
    results = {}
    for name, command in commands.items():
        result = subprocess.run(command, cwd=replay, capture_output=True, text=True, timeout=60)
        results[name] = {"command": command, "exit_code": result.returncode, "output": result.stdout + result.stderr}
    report = {"captured_at_utc": datetime.now(UTC).isoformat(), "integrity": integrity,
              "extracted_root": str(replay), "python": sys.executable,
              "dependency_reuse": "Host isolated validation interpreter and existing Playwright/Chromium only; no host project source fallback",
              "checks": results, "passed": all(result["exit_code"] == 0 for result in results.values()),
              "human_gold_complete": False, "training_started": False,
              "retained_for_inspection": True}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "files_checked": integrity["files_checked"], "extracted_root": str(replay)}))
    if not report["passed"]:
        raise SystemExit("Replay failed; evidence and extracted sources retained")


if __name__ == "__main__":
    main()
