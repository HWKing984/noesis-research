"""Verify active v2 revision and export a source-complete review package, preserving v1."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from annotation_v2 import ROOT, SCHEMA_SHA256, read_jsonl, validate_records
from prepare_ner import digest, write_json


def check_source_pool(directory):
    raw = (directory / "response.atom").read_bytes()
    rows = read_jsonl(directory / "abstracts.jsonl")
    request = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    scope_path = directory / "scope_policy.json"
    scope = json.loads(scope_path.read_text(encoding="utf-8")) if scope_path.exists() else {}
    bound = scope.get("bound_files_sha256", {})
    scope_bound = bool(bound) and all(digest(directory / name) == value for name, value in bound.items())
    split = request.get("intended_split", scope.get("intended_split") if scope_bound else None)
    scope_source = "request.json" if "intended_split" in request else "scope_policy.json" if scope_bound else "missing"
    raw_hash = hashlib.sha256(raw).hexdigest()
    return {"records": len(rows), "title_matches": sum(r["title_match"] for r in rows),
            "reference_providers": sorted({r.get("reference_provider", scope.get("reference_provider", "unknown") if scope_bound else "unknown") for r in rows}),
            "hashes_verified": bool(rows) and all(hashlib.sha256(r["abstract"].encode()).hexdigest() == r["content_hash"]
                                                 and raw_hash == r["raw_response_sha256"] for r in rows),
            "candidate_boundary_verified": split == "train_candidates_only"
                and all(r["ner_annotations"] is None and r["policy"]["license"] == "CC0-1.0" for r in rows),
            "scope_source": scope_source,
            "merged_into_ner": False, "human_annotations": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "kg_datasets/dblp/ner_v2_1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--playwright-module", required=True)
    args = parser.parse_args()
    data, output = args.data.resolve(), args.output.resolve()
    if (data / "verification.json").exists():
        raise FileExistsError("Verification already recorded; choose a new revision")
    report, plan = output / "AI-Literature-KG-v2-revision-report.md", output / "AI-Literature-KG-v2-plan.md"
    if not report.is_file() or not plan.is_file():
        raise FileNotFoundError("Author report and plan before sealing the package")
    names = {"pilot_review.html": "AI-Literature-KG-v2-pilot-review.html",
             "rare_review.html": "AI-Literature-KG-v2-rare-review.html",
             "blind_50_a.html": "AI-Literature-KG-v2-blind-50-A.html",
             "blind_50_b.html": "AI-Literature-KG-v2-blind-50-B.html"}
    archive = output / "AI-Literature-KG-v2-review-package.zip"
    exterior_manifest = output / "AI-Literature-KG-v2-export-manifest.json"
    if archive.exists() or exterior_manifest.exists() or any((output / name).exists() for name in names.values()):
        raise FileExistsError("Export artifacts exist; no overwriting")
    for directory in ("near_duplicate_review", "abstract_sources", "benchmark_abstract_sources"):
        shutil.copytree(ROOT / "kg_datasets/dblp/ner_v2" / directory, data / directory)
    manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
    outputs_intact = all(digest(data / name) == value for name, value in manifest["outputs_sha256"].items())
    v1 = ROOT / "kg_datasets/dblp/ner_v1"
    v1_manifest = json.loads((v1 / "manifest.json").read_text(encoding="utf-8"))
    v1_intact = all(digest(v1 / name) == value for name, value in v1_manifest["output_sha256"].items())
    csv_intact = all(digest(ROOT / "kg_datasets/dblp/processed_ai" / name) == value for name, value in v1_manifest["input_sha256"].items())
    raw_source = json.loads((v1 / "data_audit.json").read_text(encoding="utf-8"))["raw_source"]
    raw_path = ROOT / "kg_datasets/dblp/dblp.xml.gz"
    raw_intact = raw_path.stat().st_size == raw_source["bytes"] and digest(raw_path, "md5") == raw_source["md5"]
    python_command = [sys.executable, "-m", "pytest", "tests", "-q", "--cov=annotation_v2", "--cov=prepare_revision_v2", "--cov-branch",
                      "--cov-report=term-missing", "--cov-report=json:" + str(data / "coverage.json")]
    tests = subprocess.run(python_command, cwd=ROOT, capture_output=True, text=True, timeout=60)
    browser_command = ["node", "tests/test_review_v2.cjs", args.playwright_module, str(data)]
    browser = subprocess.run(browser_command, cwd=ROOT, capture_output=True, text=True, timeout=60)
    pilot = read_jsonl(data / "pilot_200.jsonl")
    rare = read_jsonl(data / "rare_candidates_train.jsonl")
    blind = read_jsonl(data / "blind_50_reference.jsonl")
    validation = validate_records(pilot, reference=pilot)
    rare_validation = validate_records(rare, reference=rare)
    draft_gold_rejected = all(not validate_records(pilot, reference=pilot, **{scope: True})["valid"] for scope in ("entity_gold", "relation_gold", "domain_gold"))
    overlap = len({r["groupId"] for r in pilot} & {r["groupId"] for r in rare})
    blank = all(not r["entities"] and not r["domains"] and not r["relations"] for r in blind)
    source_pools = {directory: check_source_pool(data / directory)
                    for directory in ("abstract_sources", "benchmark_abstract_sources")}
    source_checks = all(pool["hashes_verified"] and pool["candidate_boundary_verified"] for pool in source_pools.values())
    freeze = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True, timeout=30)
    code_hashes = {p.relative_to(ROOT).as_posix(): digest(p) for folder in ("scripts", "tests", "docs", "schemas", "resources")
                   for p in sorted((ROOT / folder).iterdir()) if p.is_file()}
    verification = {"captured_at_utc": datetime.now(UTC).isoformat(), "schema_sha256": SCHEMA_SHA256,
        "python": sys.version, "executable": sys.executable, "installed_packages": freeze.splitlines(),
        "playwright_version": json.loads((Path(args.playwright_module) / "package.json").read_text(encoding="utf-8"))["version"],
        "tests": {"command": python_command, "exit_code": tests.returncode, "output": tests.stdout + tests.stderr},
        "browser": {"command": browser_command, "exit_code": browser.returncode, "output": browser.stdout + browser.stderr},
        "coverage": json.loads((data / "coverage.json").read_text(encoding="utf-8"))["totals"],
        "pilot_validation": validation, "rare_validation": rare_validation, "draft_gold_all_scopes_rejected": draft_gold_rejected,
        "cross_package_duplicate_groups": overlap, "blind_pages_original_data_empty": blank,
        "source_abstracts": source_pools,
        "initial_generated_files_unchanged": outputs_intact, "v1_files_unchanged": v1_intact, "source_csvs_unchanged": csv_intact,
        "raw_dblp_source_unchanged": raw_intact,
        "code_sha256": code_hashes, "human_gold_complete": False, "schema_frozen": False, "training_started": False}
    verification["passed"] = (tests.returncode == browser.returncode == 0 and validation["valid"] and rare_validation["valid"] and
                              draft_gold_rejected and overlap == 0 and blank and source_checks and outputs_intact and v1_intact and csv_intact and raw_intact)
    write_json(data / "verification.json", verification)
    if not verification["passed"]:
        raise ValueError("Verification failed; report retained, export refused")
    contents = {"README.md": (ROOT / "docs/review_package_v2_readme.md").read_bytes(),
                report.name: report.read_bytes(), plan.name: plan.read_bytes(), "requirements-validation.txt": (ROOT / "requirements-validation.txt").read_bytes(),
                "requirements-validation.lock.txt": freeze.encode("utf-8")}
    for folder in ("scripts", "tests", "docs", "schemas", "resources"):
        for path in sorted((ROOT / folder).iterdir()):
            if path.is_file():
                contents[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for path in sorted(data.rglob("*")):
        if path.is_file():
            contents["kg_datasets/dblp/ner_v2/" + path.relative_to(data).as_posix()] = path.read_bytes()
    # Retain legacy UI inputs solely for the included legacy browser regression.
    for relative in ("pilot_review.html", "rare_train_candidates/rare_candidates_review.html"):
        contents["kg_datasets/dblp/ner_v1/" + relative] = (v1 / relative).read_bytes()
    for name in ("data_audit.json", "environment.json"):
        contents["evidence/v1-" + name] = (v1 / name).read_bytes()
    contents["evidence/verification.json"] = (data / "verification.json").read_bytes()
    contents["manifest.json"] = json.dumps({"status": "candidate_pending_human_pilot", "schema_sha256": SCHEMA_SHA256,
        "files_sha256": {name: hashlib.sha256(value).hexdigest() for name, value in contents.items()}}, indent=2).encode()
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, payload in sorted(contents.items()):
            bundle.writestr(name, payload)
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None or any(bundle.read(name) != payload for name, payload in contents.items()):
            raise ValueError("Archive content verification failed")
    for source_name, target_name in names.items():
        (output / target_name).write_bytes((data / source_name).read_bytes())
    (output / "AI-Literature-KG-v2-guidelines.md").write_bytes((ROOT / "docs/annotation_guidelines_v2.md").read_bytes())
    write_json(exterior_manifest, {"status": "verified_candidate_package", "zip_sha256": digest(archive), "zip_bytes": archive.stat().st_size,
        "zip_entries": len(contents), "code_sha256": code_hashes, "schema_sha256": SCHEMA_SHA256,
        "standalone_sha256": {name: digest(output / name) for name in names.values()}, "human_gold_complete": False})
    print(json.dumps({"passed": True, "zip_bytes": archive.stat().st_size, "files": len(contents), "output": str(output)}))


if __name__ == "__main__":
    main()
