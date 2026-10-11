"""Export verified review deliverables without overwriting existing artifacts."""
import argparse
import json
import zipfile
from pathlib import Path

from prepare_ner import ROOT, digest, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = ROOT / "kg_datasets/dblp/ner_v1"
    verification = json.loads((source / "verification.json").read_text(encoding="utf-8"))
    if not verification["passed"]:
        raise ValueError("Cannot export a failed/unverified package")
    plan = output / "AI-Literature-KG-execution-plan.md"
    report = output / "AI-Literature-KG-stage1-report.md"
    if not plan.is_file() or not report.is_file():
        raise FileNotFoundError("Authored execution plan and stage report must exist before export")
    copies = {
        "AI-Literature-KG-pilot-review.html": source / "pilot_review.html",
        "AI-Literature-KG-rare-review.html": source / "rare_train_candidates/rare_candidates_review.html",
        "AI-Literature-KG-annotation-guidelines.md": source / "annotation_guidelines.md",
    }
    archive = output / "AI-Literature-KG-review-package.zip"
    export_manifest = output / "AI-Literature-KG-export-manifest.json"
    if any((output / name).exists() for name in copies) or archive.exists() or export_manifest.exists():
        raise FileExistsError("Deliverables already exist; choose a fresh export version")
    # Read before writes; identical bytes preserve source evidence and immutable text.
    contents = {name: path.read_bytes() for name, path in copies.items()}
    contents[plan.name] = plan.read_bytes()
    contents[report.name] = report.read_bytes()
    contents["README.md"] = (ROOT / "docs/review_package_readme.md").read_bytes()
    contents["validation/annotation_core.py"] = (ROOT / "scripts/annotation_core.py").read_bytes()
    for name in ("pilot_200.jsonl", "pilot_review.csv", "pilot_summary.json", "schema_v1.json",
                 "rule_review.csv", "ai_precision_review.csv"):
        contents["pilot/" + name] = (source / name).read_bytes()
    for name in ("rare_candidates_train.jsonl", "summary.json"):
        contents["rare/" + name] = (source / "rare_train_candidates" / name).read_bytes()
    for name in ("data_audit.json", "verification.json"):
        contents["evidence/" + name] = (source / name).read_bytes()
    # Compact the environment snapshot; full pip freeze stays in the workspace.
    env = json.loads((source / "environment.json").read_text(encoding="utf-8"))
    env.pop("installed_packages", None)
    contents["evidence/environment.json"] = json.dumps(env, ensure_ascii=False, indent=2).encode("utf-8")
    import hashlib
    contents["manifest.json"] = json.dumps({"status": "draft_pending_human_review",
        "files_sha256": {name: hashlib.sha256(value).hexdigest() for name, value in contents.items()}}, indent=2).encode()
    for name in copies:
        (output / name).write_bytes(contents[name])
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in sorted(contents.items()):
            bundle.writestr(name, data)
    with zipfile.ZipFile(archive) as bundle:
        if bundle.testzip() is not None or any(bundle.read(name) != value for name, value in contents.items()):
            raise ValueError("Archive verification failed")
    write_json(export_manifest, {"status": "verified_draft_package", "zip_sha256": digest(archive),
               "zip_bytes": archive.stat().st_size, "zip_files": len(contents),
               "standalone_sha256": {name: digest(output / name) for name in copies},
               "human_review_complete": False})
    print(json.dumps({"output": str(output), "zip_bytes": archive.stat().st_size, "zip_files": len(contents)}))


if __name__ == "__main__":
    main()
