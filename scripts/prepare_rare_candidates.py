"""Prepare separate training-only rare-label review candidates; never gold by default."""
import argparse
import json
import random
from collections import Counter
from pathlib import Path

from annotation_core import read_jsonl, validate_records
from prepare_ner import ROOT, draft_entities, digest, write_json, write_jsonl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, default=ROOT / "kg_datasets/dblp/ner_v1")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    output = args.pilot_dir / "rare_train_candidates"
    if output.exists():
        raise FileExistsError(output)
    pilot = read_jsonl(args.pilot_dir / "pilot_200.jsonl")
    forbidden = {r["groupId"] for r in pilot}
    candidates = []
    for row in read_jsonl(args.pilot_dir / "corpus_manifest.jsonl"):
        if row["groupId"] in forbidden:
            continue
        entities = draft_entities(row["text"])
        labels = {e["label"] for e in entities}
        if labels & {"DATASET", "DOMAIN"}:
            row.update(entities=entities, relations=[], review_status="draft", reviewer="", reviewed_at="",
                       annotation_source="draft_dictionary_v1", schemaVersion=pilot[0]["schemaVersion"],
                       sourceCsvSha256=pilot[0]["sourceCsvSha256"], intendedSplit="train", notes="",
                       samplingStratum={"selection": "rare-label dictionary hit; training only"})
            candidates.append(row)
    random.Random(args.seed).shuffle(candidates)
    # Prioritize all available DATASET hits, then DOMAIN; do not inflate the pilot.
    candidates.sort(key=lambda r: not any(e["label"] == "DATASET" for e in r["entities"]))
    selected = []
    for row in candidates:
        if row["groupId"] not in forbidden:
            selected.append(row)
            forbidden.add(row["groupId"])
            if len(selected) == args.limit:
                break
    result = validate_records(selected)
    if not result["valid"]:
        raise ValueError(result)
    output.mkdir()
    write_jsonl(output / "rare_candidates_train.jsonl", selected)
    embedded = json.dumps(selected, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = (ROOT / "docs/pilot_review_template.html").read_text(encoding="utf-8")
    (output / "rare_candidates_review.html").write_text(
        template.replace("__PILOT_JSON__", embedded).replace("200篇", f"{len(selected)}篇稀有类别候选")
        .replace("人工智能文献 · 实体试标", "稀有类别训练候选 · 独立于200篇试标")
        .replace("pilot_200_reviewed-progress.jsonl", "rare_candidates_reviewed-progress.jsonl"), encoding="utf-8")
    write_json(output / "summary.json", {**result, "candidate_pool": len(candidates), "seed": args.seed,
               "documents_with_label": dict(Counter(label for r in selected for label in {e["label"] for e in r["entities"]})),
               "purpose": "Separate training-only enrichment; excludes pilot duplicate groups. Human review required.",
               "must_not_use_for": "test set; estimates of natural entity prevalence or actual NER performance"})
    write_json(output / "manifest.json", {"status": "draft", "input_manifest_sha256": digest(args.pilot_dir / "corpus_manifest.jsonl"),
               "script_sha256": digest(Path(__file__)),
               "output_sha256": {p.name: digest(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
