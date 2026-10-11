"""Small single-request arXiv metadata pilot; preserve source, hashes, title matching and policy."""
import argparse
import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from annotation_v2 import read_jsonl
from prepare_ner import ROOT, write_json, write_jsonl

POLICY_URL = "https://info.arxiv.org/help/api/tou.html"
POLICY = {"license": "CC0-1.0", "source_policy": POLICY_URL,
          "license_scope": "descriptive metadata including API title/abstract; not full-text/PDF license",
          "policy_checked_on": "2026-10-05", "redistribute_metadata": True}
NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def normalize_title(title):
    return " ".join(re.findall(r"\w+", title.casefold()))


def parse_feed(payload, requested, source_url, retrieved_at):
    if b"<!DOCTYPE" in payload or b"<!ENTITY" in payload:
        raise ValueError("Unexpected DTD/entity in API response")
    root = ET.fromstring(payload)
    if root.tag != "{" + NS["atom"] + "}feed":
        raise ValueError("Not an Atom feed")
    found = {}
    for entry in root.findall("atom:entry", NS):
        entry_id = entry.findtext("atom:id", "", NS)
        match = re.search(r"/abs/(\d{4}\.\d{4,5})(?:v\d+)?$", entry_id)
        if not match or match.group(1) not in requested:
            continue
        arxiv_id = match.group(1)
        original = requested[arxiv_id]
        title = entry.findtext("atom:title", "", NS)
        abstract = entry.findtext("atom:summary", "", NS)
        if not title.strip() or not abstract.strip() or arxiv_id in found:
            raise ValueError("Missing title/abstract or duplicate arXiv entry")
        match_ok = normalize_title(title) == normalize_title(original["title"])
        found[arxiv_id] = {"publicationId": original["publicationId"], "arxivId": arxiv_id,
           "title": title, "dblp_title": original["title"] if original.get("reference_provider", "DBLP") == "DBLP" else None,
           "reference_provider": original.get("reference_provider", "DBLP"), "reference_title": original["title"], "abstract": abstract,
           "source_url": entry_id, "request_url": source_url, "retrieved_at": retrieved_at,
           "content_hash": hashlib.sha256(abstract.encode()).hexdigest(),
           "raw_response_sha256": hashlib.sha256(payload).hexdigest(),
           "published": entry.findtext("atom:published", "", NS), "updated": entry.findtext("atom:updated", "", NS),
           "doi": entry.findtext("arxiv:doi", "", NS), "title_match": match_ok,
           "status": "source_verified_not_annotated" if match_ok else "title_mismatch_needs_review",
           "policy": POLICY, "ner_annotations": None}
    return list(found.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "kg_datasets/dblp/ner_v2")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--seeds", type=Path, help="Optional independently verified arXiv title/ID seed file")
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        parser.error("Pilot limit must be 1..20")
    output = args.output or args.data / "abstract_sources"
    if output.exists():
        raise FileExistsError("Preserve source evidence; use a new output directory")
    requested = {}
    if args.seeds:
        for seed in json.loads(args.seeds.read_text(encoding="utf-8"))["seeds"][:args.limit]:
            if not re.fullmatch(r"\d{4}\.\d{4,5}", seed["id"]):
                raise ValueError("Invalid arXiv seed identifier")
            requested[seed["id"]] = {"publicationId": "arxiv:" + seed["id"], "title": seed["title"], "reference_provider": "arXiv"}
    for row in ([] if args.seeds else read_jsonl(args.data / "rare_candidates_train.jsonl") + read_jsonl(args.data / "pilot_200.jsonl")):
        match = re.fullmatch(r"journals/corr/abs-(\d{4})-(\d{4,5})", row["publicationId"])
        if match:
            requested.setdefault(match.group(1) + "." + match.group(2), row)
            if len(requested) == args.limit:
                break
    if not requested:
        raise ValueError("No direct arXiv ID matches in the selected pilot")
    query = urllib.parse.urlencode({"id_list": ",".join(requested), "max_results": len(requested)})
    url = "https://export.arxiv.org/api/query?" + query
    output.mkdir(parents=True)
    retrieved = datetime.now(UTC).isoformat()
    write_json(output / "request.json", {"url": url, "arxiv_ids": list(requested), "requested_at_utc": retrieved,
                                        "policy": POLICY, "requests": 1, "concurrency": 1, "purpose": "small source availability/title matching pilot",
                                        "seed_file": str(args.seeds) if args.seeds else None, "intended_split": "train_candidates_only"})
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "DBLP-Course-KG/2.0 (small metadata research pilot)", "Accept": "application/atom+xml"})
        with urllib.request.urlopen(request, timeout=25) as response:
            if urllib.parse.urlsplit(response.url).hostname not in {"export.arxiv.org", "arxiv.org"}:
                raise ValueError("Unexpected source redirect")
            payload = response.read(4 * 1024 * 1024 + 1)
            if len(payload) > 4 * 1024 * 1024:
                raise ValueError("Response exceeds pilot safety limit")
        (output / "response.atom").write_bytes(payload)
        records = parse_feed(payload, requested, url, retrieved)
        write_jsonl(output / "abstracts.jsonl", records)
        write_json(output / "summary.json", {"status": "source_pilot_complete" if len(records) == len(requested) else "partial",
            "requested": len(requested), "received": len(records), "exact_normalized_title_matches": sum(r["title_match"] for r in records),
            "missing_ids": sorted(set(requested) - {r["arxivId"] for r in records}),
            "policy": POLICY, "human_annotations": 0, "merged_into_title_annotations": False})
        print(json.dumps({"received": len(records), "matched": sum(r["title_match"] for r in records)}))
    except (OSError, ValueError, ET.ParseError) as exc:
        write_json(output / "failure.json", {"status": "failed_no_synthetic_fallback", "request_url": url,
                   "error": repr(exc), "timestamp_utc": datetime.now(UTC).isoformat(), "abstracts_available": False})
        raise SystemExit(f"Abstract source pilot failed (evidence preserved): {exc}")


if __name__ == "__main__":
    main()
