"""Version-preserving v2 drafts, independent blank review pages and diversity-limited candidates."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from annotation_v2 import SCHEMA, SCHEMA_SHA256, LABELS, DOMAIN_LABELS, new_review, read_jsonl, validate_records
from prepare_ner import ROOT, digest, write_csv, write_json, write_jsonl

LEXICON_PATH = ROOT / "resources/ner_draft_lexicon_v2.json"
LEXICON = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
if set(LEXICON["entities"]) != set(LABELS) or not set(LEXICON["document_domains"]) <= set(DOMAIN_LABELS):
    raise ValueError("Lexicon labels disagree with authoritative schema")


def matches(text, phrases):
    return [match for phrase in phrases for match in re.finditer(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, re.I)]


def draft_annotations(text):
    candidates = [{"start": m.start(), "end": m.end(), "text": m.group(), "label": label, "origin": LEXICON["version"]}
                  for label, phrases in LEXICON["entities"].items() for m in matches(text, phrases)]
    entities = []
    for item in sorted(candidates, key=lambda e: (-(e["end"] - e["start"]), e["start"], e["label"])):
        if not any(item["start"] < e["end"] and e["start"] < item["end"] for e in entities):
            entities.append(item)
    domains = []
    for label, phrases in LEXICON["document_domains"].items():
        hits = matches(text, phrases)
        if hits:
            hit = min(hits, key=lambda m: (-(m.end() - m.start()), m.start()))
            domains.append({"label": label, "evidence": {"start": hit.start(), "end": hit.end(), "text": hit.group()}, "origin": LEXICON["version"]})
    return sorted(entities, key=lambda e: e["start"]), domains


def make_record(original, source_hash, sampling=None):
    entities, domains = draft_annotations(original["text"])
    text = original["text"]
    return {"publicationId": original["publicationId"], "title": text, "text": text, "textKind": "title",
            "year": original["year"], "type": original["type"], "doi": original["doi"], "topics": original["topics"],
            "groupId": original["groupId"], "sourceCsvSha256": source_hash,
            "schemaVersion": SCHEMA["properties"]["schemaVersion"]["const"], "schemaSha256": SCHEMA_SHA256,
            "intendedSplit": "train", "samplingStratum": sampling or original["samplingStratum"],
            "ambiguityFlags": original["ambiguityFlags"],
            "textSource": {"provider": "DBLP", "sourceRecordId": original["publicationId"], "snapshot": "2026-09-01",
                           "sourceUrl": "https://dblp.org/rec/" + original["publicationId"], "license": "CC0-1.0",
                           "textSha256": hashlib.sha256(text.encode()).hexdigest()},
            "entities": entities, "relations": [], "domains": domains, "entity_review": new_review(),
            "relation_review": new_review(), "domain_review": new_review(), "notes": ""}


def select_diverse(candidates, forbidden, limit=100, surface_cap=2, seed=42):
    """At most surface_cap training candidates per dataset surface; balance domain documents.

    Never fill quotas by inventing names, never pick a second known duplicate group.
    Surfaces are not canonical dataset families; family review remains necessary.
    """
    pools = defaultdict(list)
    for row in sorted(candidates, key=lambda r: r["publicationId"]):
        if row["groupId"] in forbidden:
            continue
        for entity in row["entities"]:
            if entity["label"] == "DATASET":
                pools[("dataset", entity["text"].casefold())].append(row)
        for domain in row["domains"]:
            pools[("domain", domain["label"])].append(row)
    rng = random.Random(seed)
    for key in sorted(pools):
        rng.shuffle(pools[key])
    selected, used = [], set(forbidden)
    surface_counts = Counter()
    # First broaden DATASET surfaces. Then fill by balanced document-domain strata.
    for kind in ("dataset", "domain"):
        keys = sorted(k for k in pools if k[0] == kind)
        while keys and len(selected) < limit:
            progressed = False
            for key in keys:
                while pools[key]:
                    row = pools[key].pop()
                    surfaces = {e["text"].casefold() for e in row["entities"] if e["label"] == "DATASET"}
                    if row["groupId"] in used or any(surface_counts[s] >= surface_cap for s in surfaces):
                        continue
                    row = copy.deepcopy(row)
                    row["samplingStratum"] = {"selection": "diversity-limited training candidate", "kind": kind, "surfaceOrDomain": key[1]}
                    selected.append(row)
                    used.add(row["groupId"])
                    surface_counts.update(surfaces)
                    progressed = True
                    break
                if len(selected) >= limit:
                    break
            if not progressed:
                break
    return selected


def safe_json(data):
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def render_page(records, *, title, download, blind=False):
    template = (ROOT / "docs/review_v2_template.html").read_text(encoding="utf-8")
    return (template.replace("__PILOT_JSON__", safe_json(records)).replace("__SCHEMA_JSON__", safe_json(SCHEMA))
            .replace("__PAGE_JSON__", safe_json({"title": title, "download": download, "blind": blind, "schemaSha256": SCHEMA_SHA256}))
            .replace("__REVIEW_JS__", (ROOT / "docs/review_v2.js").read_text(encoding="utf-8")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "kg_datasets/dblp/ner_v1")
    parser.add_argument("--output", type=Path, default=ROOT / "kg_datasets/dblp/ner_v2")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Preserve prior artifacts: choose a new output version")
    old_pilot = read_jsonl(args.input / "pilot_200.jsonl")
    if any(r["review_status"] != "draft" for r in old_pilot):
        raise ValueError("Do not silently migrate reviewed v1 data; explicit human migration required")
    source_hash = old_pilot[0]["sourceCsvSha256"]
    pilot = [make_record(r, source_hash) for r in old_pilot]
    corpus = read_jsonl(args.input / "corpus_manifest.jsonl")
    candidates = [make_record(r, source_hash, {"selection": "candidate pool"}) for r in corpus]
    rare = select_diverse(candidates, {r["groupId"] for r in pilot})
    blind = copy.deepcopy(random.Random(42).sample(pilot, min(50, len(pilot))))
    for row in blind:
        row["entities"] = []
        row["domains"] = []
    for rows in (pilot, rare, blind):
        if not validate_records(rows, reference=rows)["valid"]:
            raise ValueError("Invalid generated draft")
    args.output.mkdir(parents=True)
    write_jsonl(args.output / "pilot_200.jsonl", pilot)
    write_jsonl(args.output / "rare_candidates_train.jsonl", rare)
    write_jsonl(args.output / "blind_50_reference.jsonl", blind)
    for name, rows, title, download, blank in (
        ("pilot_review.html", pilot, "v2 · 200篇实体与领域试标", "pilot_v2_progress.jsonl", False),
        ("rare_review.html", rare, "v2 · 多样性受限的训练候选", "rare_v2_progress.jsonl", False),
        ("blind_50_a.html", blind, "v2 · 独立盲标 A（50篇，无预标注）", "blind_50_a_progress.jsonl", True),
        ("blind_50_b.html", blind, "v2 · 独立盲标 B（50篇，无预标注）", "blind_50_b_progress.jsonl", True)):
        (args.output / name).write_text(render_page(rows, title=title, download=download, blind=blank), encoding="utf-8")
    write_csv(args.output / "pilot_review.csv", [{"publicationId": r["publicationId"], "text": r["text"],
          "entities_json": json.dumps(r["entities"], ensure_ascii=False), "domains_json": json.dumps(r["domains"], ensure_ascii=False)} for r in pilot],
          ["publicationId", "text", "entities_json", "domains_json"])
    surfaces = Counter(e["text"].casefold() for r in rare for e in r["entities"] if e["label"] == "DATASET")
    write_json(args.output / "summary.json", {"status": "draft_pending_human_review", "schema_status": SCHEMA["x-annotation"]["status"],
        "pilot": validate_records(pilot, reference=pilot), "rare": validate_records(rare, reference=rare),
        "rare_dataset_surface_mentions": dict(surfaces), "rare_dataset_distinct_surfaces": len(surfaces),
        "rare_domain_documents": dict(Counter(d["label"] for r in rare for d in r["domains"])),
        "blind_documents": len(blind), "human_annotations_completed": 0,
        "limitations": ["Draft lexicon coverage is not actual entity prevalence", "Expanded title dictionary is not sufficient evidence of DATASET diversity",
                        "Domains are independent document labels, not NER spans", "Near-duplicate candidate review and author identities remain unresolved",
                        "Title-only candidate contract; sourced abstracts require a separately reviewed text-unit contract"]})
    write_json(args.output / "manifest.json", {"generated_at_utc": datetime.now(UTC).isoformat(), "status": "draft",
        "schema_sha256": SCHEMA_SHA256, "lexicon_sha256": digest(LEXICON_PATH),
        "input_sha256": {p.name: digest(p) for p in (args.input / "pilot_200.jsonl", args.input / "corpus_manifest.jsonl")},
        "outputs_sha256": {p.name: digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}})
    print(json.dumps({"pilot": len(pilot), "rare": len(rare), "blind": len(blind), "dataset_surfaces": dict(surfaces)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
