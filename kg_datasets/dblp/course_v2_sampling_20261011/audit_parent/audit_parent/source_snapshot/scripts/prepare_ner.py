"""Audit existing DBLP CSVs and prepare a reproducible, explicitly draft NER pilot."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import random
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from annotation_core import LABELS, RELATIONS, validate_records
from process_dblp_ai import extract_doi

ROOT = Path(__file__).resolve().parents[1]
# Small, inspectable draft dictionary. It is NOT a coverage-complete gold standard.
LEXICON = {
    "METHOD": ["large language model", "large language models", "LLM", "LLMs", "BERT", "GPT",
               "graph neural network", "graph neural networks", "graph convolutional network",
               "graph convolutional networks", "convolutional neural network", "convolutional neural networks",
               "neural network", "neural networks", "deep neural network", "deep neural networks",
               "reinforcement learning", "deep reinforcement learning", "machine learning", "deep learning",
               "federated learning", "transfer learning", "contrastive learning", "representation learning",
               "transformer", "transformers", "diffusion model", "diffusion models", "support vector machine",
               "random forest", "decision tree", "autoencoder", "generative adversarial network"],
    "TASK": ["named entity recognition", "relation extraction", "entity linking", "question answering",
             "visual question answering", "machine translation", "text classification", "object detection",
             "image segmentation", "semantic segmentation", "image recognition", "image generation",
             "link prediction", "node classification", "knowledge graph completion", "sentiment analysis",
             "anomaly detection", "time series forecasting", "recommendation", "text summarization"],
    "DATASET": ["ImageNet", "CIFAR-10", "CIFAR-100", "MNIST", "COCO", "SQuAD", "GLUE",
                "SuperGLUE", "WikiText-103", "Cora", "Citeseer", "FB15k-237", "WN18RR", "Human3.6M"],
    "DOMAIN": ["healthcare", "medical imaging", "autonomous driving", "remote sensing",
               "drug discovery", "bioinformatics", "cybersecurity", "precision agriculture", "smart grid"],
}


def digest(path: Path, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError(f"Malformed CSV: {path}")
    return rows


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def audit_tables(tables: dict[str, list[dict]]) -> dict:
    node_specs = {"persons": "personId:ID(Person)", "publications": "publicationId:ID(Publication)",
                  "venues": "venueId:ID(Venue)", "topics": "topicId:ID(Topic)"}
    errors, nodes, edges, id_sets = [], {}, {}, {}
    for table, key in node_specs.items():
        ids = [r[key] for r in tables[table]]
        id_sets[table] = set(ids)
        nodes[table] = {"rows": len(ids), "unique_ids": len(set(ids)), "empty_ids": ids.count("")}
        if "" in ids or len(ids) != len(set(ids)):
            errors.append(f"{table}: missing/duplicate IDs")
    edge_specs = {"authored": ("persons", "publications", ":START_ID(Person)", ":END_ID(Publication)", "AUTHORED"),
                  "published_in": ("publications", "venues", ":START_ID(Publication)", ":END_ID(Venue)", "PUBLISHED_IN"),
                  "about": ("publications", "topics", ":START_ID(Publication)", ":END_ID(Topic)", "ABOUT")}
    for table, (src, dst, skey, dkey, kind) in edge_specs.items():
        rows = tables[table]
        dangling = sum(r[skey] not in id_sets[src] or r[dkey] not in id_sets[dst] for r in rows)
        duplicates = len(rows) - len({tuple(sorted(r.items())) for r in rows})
        pairs = len(rows) - len({(r[skey], r[dkey]) for r in rows})
        wrong_types = sum(r[":TYPE"] != kind for r in rows)
        edges[table] = {"rows": len(rows), "dangling_edges": dangling, "duplicate_rows": duplicates,
                        "repeated_endpoint_pairs": pairs, "wrong_types": wrong_types}
        if dangling or duplicates or wrong_types:
            errors.append(f"{table}: invalid endpoints/duplicates/types")
    pubs = tables["publications"]
    invalid = sum(not r["title"].strip() or r["type"] not in {"article", "inproceedings"}
                  or not r["year:int"].isdigit() or not 2015 <= int(r["year:int"]) <= 2025 for r in pubs)
    if invalid:
        errors.append("publications: invalid title/type/year")
    authored_ids = {r[":END_ID(Publication)"] for r in tables["authored"]}
    venue_ids = {r[":START_ID(Publication)"] for r in tables["published_in"]}
    return {"valid": not errors, "nodes": nodes, "edges": edges, "errors": errors,
            "missing_authors": len(id_sets["publications"] - authored_ids),
            "missing_venues": len(id_sets["publications"] - venue_ids),
            "missing_doi": sum(not r["doi"] for r in pubs),
            "year_distribution": dict(sorted(Counter(r["year:int"] for r in pubs).items())),
            "type_distribution": dict(Counter(r["type"] for r in pubs)),
            "array_format": "semicolon-delimited inherited v1; literal semicolons may be ambiguous; pilot uses titles only"}


def duplicate_groups(pubs: list[dict]) -> tuple[dict[str, str], list[dict]]:
    parent = {r["publicationId"]: r["publicationId"] for r in pubs}

    def find(pid):
        while pid != parent[pid]:
            parent[pid] = parent[parent[pid]]
            pid = parent[pid]
        return pid

    keys = {}
    reasons = []
    for row in sorted(pubs, key=lambda r: r["publicationId"]):
        title = " ".join(unicodedata.normalize("NFKC", row["text"]).casefold().split()).rstrip(".")
        for kind, value in (("title", title), ("doi", row["doi"])):
            if not value:
                continue
            key = (kind, value)
            if key in keys:
                left, right = find(row["publicationId"]), find(keys[key])
                parent[max(left, right)] = min(left, right)
                reasons.append({"publicationId": row["publicationId"], "matchedId": keys[key], "reason": kind, "value": value})
            else:
                keys[key] = row["publicationId"]
    return {pid: "group-" + hashlib.sha256(find(pid).encode()).hexdigest()[:16] for pid in parent}, reasons


def draft_entities(text: str) -> list[dict]:
    candidates = []
    for label, phrases in LEXICON.items():
        for phrase in phrases:
            for match in re.finditer(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, re.I):
                candidates.append({"start": match.start(), "end": match.end(), "label": label,
                                   "text": match.group(), "method": "draft_dictionary_v1"})
    selected = []
    for item in sorted(candidates, key=lambda r: (-(r["end"] - r["start"]), r["start"], r["label"])):
        if not any(item["start"] < s["end"] and s["start"] < item["end"] for s in selected):
            selected.append(item)
    return sorted(selected, key=lambda r: r["start"])


def ambiguity_flags(row: dict) -> list[str]:
    text = row["text"].casefold()
    flags = []
    if re.search(r"\btransformers?\b", text) and not re.search(r"\b(?:large language models?|llms?)\b", text):
        flags.append("transformer_not_necessarily_llm_or_even_ai")
    if re.search(r"\bdiffusion models?\b", text):
        flags.append("diffusion_requires_context")
    if re.search(r"\bontolog(?:y|ies)\b", text):
        flags.append("ontology_scope_review")
    return flags


def select_pilot(pubs: list[dict], count: int, seed: int) -> list[dict]:
    """Least-populated-topic assignment + equal topic quota + year/type round-robin.

    This is a purposeful pilot, not a probability sample for domain-wide estimates.
    Selection never depends on dictionary entity hits, including zero-hit titles.
    """
    frequencies = Counter(t for row in pubs for t in row["topics"])
    bins = defaultdict(list)
    for row in sorted(pubs, key=lambda r: r["publicationId"]):
        topic = min(row["topics"], key=lambda t: (frequencies[t], t))
        bins[(topic, row["year"], row["type"])].append(row)
    rng = random.Random(seed)
    for key in sorted(bins):
        rng.shuffle(bins[key])
    topics = sorted(frequencies)
    keys_by_topic = {t: [k for k in sorted(bins) if k[0] == t] for t in topics}
    for keys in keys_by_topic.values():
        rng.shuffle(keys)
    chosen, groups, cursors = [], set(), Counter()
    while len(chosen) < count:
        progressed = False
        for topic in topics:
            keys = keys_by_topic[topic]
            for _ in range(len(keys)):
                key = keys[cursors[topic] % len(keys)]
                cursors[topic] += 1
                while bins[key] and bins[key][-1]["groupId"] in groups:
                    bins[key].pop()
                if bins[key]:
                    row = dict(bins[key].pop())
                    row["samplingStratum"] = {"topic": topic, "year": row["year"], "type": row["type"]}
                    chosen.append(row)
                    groups.add(row["groupId"])
                    progressed = True
                    break
            if len(chosen) == count:
                break
        if not progressed:
            raise ValueError("Insufficient distinct paper groups for pilot")
    return chosen


def environment() -> dict:
    result = {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
              "disk_free_bytes": shutil.disk_usage(ROOT).free, "packages": {},
              "captured_at_utc": datetime.now(UTC).isoformat()}
    for package in ("lxml", "torch", "transformers", "datasets"):
        try:
            result["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result["packages"][package] = None
    try:
        import torch
        result["cuda_available"] = torch.cuda.is_available()
        result["torch_cuda_version"] = torch.version.cuda
        if result["cuda_available"]:
            result["gpu_name"] = torch.cuda.get_device_name(0)
            value = (torch.ones((16, 16), device="cuda") @ torch.ones((16, 16), device="cuda"))[0, 0].item()
            result["cuda_matmul_smoke"] = {"passed": value == 16.0, "value": value}
    except Exception as exc:
        result["torch_error"] = repr(exc)
    try:
        result["installed_packages"] = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True, timeout=30).splitlines()
    except (OSError, subprocess.SubprocessError) as exc:
        result["pip_freeze_error"] = repr(exc)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "kg_datasets/dblp/processed_ai")
    parser.add_argument("--output", type=Path, default=ROOT / "kg_datasets/dblp/ner_v1")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be positive")
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"Output already exists; use a new version directory: {output}")
    tables = {name: load_csv(args.input / f"{name}.csv") for name in
              ("persons", "publications", "venues", "topics", "authored", "published_in", "about")}
    audit = audit_tables(tables)
    if not audit["valid"]:
        raise ValueError(json.dumps(audit, ensure_ascii=False))
    input_hashes = {p.name: digest(p) for p in sorted(args.input.glob("*.csv"))}
    topics = defaultdict(list)
    for row in tables["about"]:
        topics[row[":START_ID(Publication)"]].append(row[":END_ID(Topic)"])
    pubs, doi_changes = [], []
    for row in tables["publications"]:
        pid = row["publicationId:ID(Publication)"]
        # Typed CSV v1 arrays can contain URL semicolons; direct resolver regex keeps
        # DOI path punctuation and stops before the next URL where possible.
        urls = re.split(r";(?=https?://)", row["urls:string[]"])
        recovered = extract_doi(tuple(urls))
        if recovered and recovered != row["doi"]:
            doi_changes.append({"publicationId": pid, "oldDoi": row["doi"], "urlDoi": recovered})
        pubs.append({"publicationId": pid, "text": row["title"], "year": int(row["year:int"]), "type": row["type"],
                     "doi": recovered or row["doi"], "topics": sorted(set(topics[pid]))})
    if any(not row["topics"] for row in pubs):
        raise ValueError("Every pilot candidate must have a known topic stratum")
    groups, reasons = duplicate_groups(pubs)
    for row in pubs:
        row["groupId"] = groups[row["publicationId"]]
        row["ambiguityFlags"] = ambiguity_flags(row)
    pilot = select_pilot(pubs, args.count, args.seed)
    for row in pilot:
        row.update({"entities": draft_entities(row["text"]), "relations": [], "review_status": "draft",
                    "reviewer": "", "reviewed_at": "", "annotation_source": "draft_dictionary_v1",
                    "schemaVersion": "v1-candidate", "sourceCsvSha256": input_hashes["publications.csv"],
                    "intendedSplit": "train", "notes": ""})
    validation = validate_records(pilot)
    if not validation["valid"]:
        raise ValueError(json.dumps(validation))
    output.mkdir(parents=True)
    try:
        write_json(output / "environment.json", environment())
        raw = ROOT / "kg_datasets/dblp/dblp.xml.gz"
        audit["raw_source"] = {"path": str(raw), "bytes": raw.stat().st_size, "md5": digest(raw, "md5")}
        audit["source_csv_sha256"] = input_hashes
        audit["script_sha256"] = {p.name: digest(p) for p in sorted((ROOT / "scripts").glob("*.py"))}
        audit["doi_recovery_changes"] = doi_changes
        write_json(output / "data_audit.json", audit)
        write_jsonl(output / "corpus_manifest.jsonl", pubs)
        write_jsonl(output / "duplicate_matches.jsonl", reasons)
        write_jsonl(output / "pilot_200.jsonl", pilot)
        write_csv(output / "pilot_review.csv", [
            {"publicationId": r["publicationId"], "year": r["year"], "type": r["type"], "text": r["text"],
             "topics": ";".join(r["topics"]), "entities_json": json.dumps(r["entities"], ensure_ascii=False),
             "review_status": "draft", "notes": ""} for r in pilot],
            ["publicationId", "year", "type", "text", "topics", "entities_json", "review_status", "notes"])
        flagged = [r for r in pubs if r["ambiguityFlags"]]
        rng = random.Random(args.seed)
        rng.shuffle(flagged)
        write_csv(output / "rule_review.csv", [
            {"publicationId": r["publicationId"], "text": r["text"], "flags": ";".join(r["ambiguityFlags"]),
             "is_ai": "", "llm_topic_correct": "", "reviewer": "", "notes": ""} for r in flagged[:100]],
            ["publicationId", "text", "flags", "is_ai", "llm_topic_correct", "reviewer", "notes"])
        uniform_candidates = random.Random(args.seed).sample(sorted(pubs, key=lambda r: r["publicationId"]), min(100, len(pubs)))
        write_csv(output / "ai_precision_review.csv", [
            {"publicationId": r["publicationId"], "text": r["text"], "is_ai": "", "reviewer": "", "notes": ""}
            for r in uniform_candidates], ["publicationId", "text", "is_ai", "reviewer", "notes"])
        group_sizes = Counter(groups.values())
        summary = {**validation, "seed": args.seed, "duplicate_group_count": len(group_sizes),
                   "non_singleton_groups": sum(n > 1 for n in group_sizes.values()),
                   "corpus_ambiguity_flags": dict(Counter(f for r in pubs for f in r["ambiguityFlags"])),
                   "topic_quota": dict(Counter(r["samplingStratum"]["topic"] for r in pilot)),
                   "years": dict(sorted(Counter(str(r["year"]) for r in pilot).items())),
                   "types": dict(Counter(r["type"] for r in pilot)), "relations_auto_created": 0,
                   "sampling": "purposeful equal-topic round robin over year/type; one paper per known duplicate group; not a probability sample",
                   "limitations": ["Exact normalized title/DOI grouping only; near duplicates require further review",
                                   "All annotations are draft; zero dictionary hits do not imply no entity",
                                   "Schema remains candidate pending human pilot review",
                                   "Existing CSVs and topic assignments were not modified; AI precision/recall not yet measured"]}
        write_json(output / "pilot_summary.json", summary)
        write_json(output / "schema_v1.json", {"version": "v1-candidate", "status": "pending_human_pilot",
                   "entity_labels": LABELS, "offsets": "Unicode codepoints, [start,end), unchanged CSV title",
                   "flat_non_overlapping": True, "relation_pairs": RELATIONS, "negative_label": "NO_RELATION"})
        template = (ROOT / "docs/pilot_review_template.html").read_text(encoding="utf-8")
        embedded = json.dumps(pilot, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        (output / "pilot_review.html").write_text(template.replace("__PILOT_JSON__", embedded), encoding="utf-8")
        shutil.copy2(ROOT / "docs/annotation_guidelines.md", output / "annotation_guidelines.md")
        write_json(output / "manifest.json", {"status": "draft_package_ready", "human_review_complete": False,
                   "generated_at_utc": datetime.now(UTC).isoformat(), "command": [sys.executable, *sys.argv],
                   "input_sha256": input_hashes, "output_sha256": {p.name: digest(p) for p in sorted(output.iterdir()) if p.is_file()}})
    except Exception as exc:
        write_json(output / "FAILED.json", {"error": repr(exc), "status": "incomplete_do_not_use"})
        raise
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
