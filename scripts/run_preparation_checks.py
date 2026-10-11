"""Recheck generated draft packages and record real execution evidence."""
import argparse
import json
import socket
import subprocess
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from annotation_core import read_jsonl, validate_records
from prepare_ner import ROOT, digest, load_csv, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--playwright-module", help="Optional installed Playwright module path")
    args = parser.parse_args()
    directory = ROOT / "kg_datasets/dblp/ner_v1"
    destination = directory / "verification.json"
    if destination.exists():
        raise FileExistsError("Use a new verification version instead of overwriting evidence")
    tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT,
                           capture_output=True, text=True, timeout=60)
    pilot = read_jsonl(directory / "pilot_200.jsonl")
    rare = read_jsonl(directory / "rare_train_candidates/rare_candidates_train.jsonl")
    validation = validate_records(pilot, reference=pilot)
    rare_validation = validate_records(rare, reference=rare)
    gold_gate = validate_records(pilot, gold=True, reference=pilot)
    result = {"captured_at_utc": datetime.now(UTC).isoformat(),
              "unit_tests": {"passed": tests.returncode == 0, "exit_code": tests.returncode,
                             "output": tests.stdout + tests.stderr},
              "draft_validation": validation, "rare_draft_validation": rare_validation,
              "gold_gate": {"passed": not gold_gate["valid"], "draft_rejected": not gold_gate["valid"],
                            "invalid_documents": len(gold_gate["errors"])},
              "cross_package_duplicate_groups": len({r["groupId"] for r in pilot} & {r["groupId"] for r in rare}),
              "browser": {"status": "not_run"}}
    if args.playwright_module:
        browser = subprocess.run(["node", "tests/test_pilot_review.cjs", args.playwright_module], cwd=ROOT,
                                 capture_output=True, text=True, timeout=60)
        result["browser"] = {"status": "passed" if browser.returncode == 0 else "failed",
                             "exit_code": browser.returncode, "output": browser.stdout + browser.stderr}
    with socket.socket() as probe:
        probe.settimeout(1)
        result["neo4j_bolt_port_7687_reachable"] = probe.connect_ex(("127.0.0.1", 7687)) == 0
    with socket.socket() as probe:
        probe.settimeout(1)
        result["neo4j_http_port_7474_reachable"] = probe.connect_ex(("127.0.0.1", 7474)) == 0
    result["neo4j_database_state"] = "not queried; port probe is not proof of import state"
    pubs = load_csv(ROOT / "kg_datasets/dblp/processed_ai/publications.csv")
    result["corr_article_records"] = sum(r["publicationId:ID(Publication)"].startswith("journals/corr/") for r in pubs)
    edges = load_csv(ROOT / "kg_datasets/dblp/processed_ai/authored.csv")
    positions = defaultdict(list)
    for row in edges:
        positions[(row[":START_ID(Person)"], row[":END_ID(Publication)"])].append(row["position:int"])
    result["repeated_authorship_endpoint_pairs"] = [{"personId": k[0], "publicationId": k[1], "positions": v}
                                                    for k, v in positions.items() if len(v) > 1]
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    result["initial_manifest_files_unchanged"] = all(digest(directory / name) == value for name, value in manifest["output_sha256"].items())
    result["input_csvs_unchanged"] = all(digest(ROOT / "kg_datasets/dblp/processed_ai" / name) == value
                                         for name, value in manifest["input_sha256"].items())
    result["source_snapshot_match"] = json.loads((directory / "data_audit.json").read_text(encoding="utf-8"))["raw_source"]["md5"] == "41abb87b4e8b8a2e3c470efd6528ad88"
    result["current_code_sha256"] = {str(p.relative_to(ROOT)): digest(p) for folder in ("scripts", "tests", "docs")
                                     for p in sorted((ROOT / folder).iterdir()) if p.is_file()}
    result["passed"] = (tests.returncode == 0 and validation["valid"] and rare_validation["valid"]
                        and not gold_gate["valid"] and result["cross_package_duplicate_groups"] == 0
                        and result["initial_manifest_files_unchanged"] and result["input_csvs_unchanged"]
                        and result["source_snapshot_match"] and result["browser"]["status"] in {"passed", "not_run"})
    write_json(destination, result)
    print(json.dumps({k: result[k] for k in ("passed", "gold_gate", "cross_package_duplicate_groups", "corr_article_records",
                                           "initial_manifest_files_unchanged", "input_csvs_unchanged")}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
