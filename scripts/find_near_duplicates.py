"""Suggest title-similar pairs for human review; never auto-merge publication identities."""
import argparse
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from annotation_v2 import read_jsonl
from prepare_ner import ROOT, load_csv, write_csv, write_json


def tokens(title):
    return set(re.findall(r"[a-z0-9]+", title.casefold()))


def suggest_pairs(records, *, threshold=0.82, max_anchor_frequency=60, authors=None):
    token_sets = {r["publicationId"]: tokens(r["text"]) for r in records}
    frequencies = Counter(t for terms in token_sets.values() for t in terms)
    inverted = defaultdict(list)
    for pid, terms in token_sets.items():
        for term in terms:
            if 2 <= frequencies[term] <= max_anchor_frequency:
                inverted[term].append(pid)
    candidates = set()
    for bucket in inverted.values():
        for i, left in enumerate(sorted(bucket)):
            candidates.update((left, right) for right in sorted(bucket)[i+1:])
    by_id = {r["publicationId"]: r for r in records}
    suggestions = []
    for left, right in sorted(candidates):
        a, b = by_id[left], by_id[right]
        if a["groupId"] == b["groupId"] or abs(a["year"] - b["year"]) > 3:
            continue
        terms_a, terms_b = token_sets[left], token_sets[right]
        similarity = len(terms_a & terms_b) / len(terms_a | terms_b) if terms_a | terms_b else 0
        if similarity < threshold:
            continue
        names_a, names_b = (authors or {}).get(left, set()), (authors or {}).get(right, set())
        suggestions.append({"leftId": left, "rightId": right, "leftTitle": a["text"], "rightTitle": b["text"],
                            "leftYear": a["year"], "rightYear": b["year"], "tokenJaccard": round(similarity, 4),
                            "characterSimilarity": round(SequenceMatcher(None, a["text"].casefold(), b["text"].casefold()).ratio(), 4),
                            "sharedDisplayAuthorNames": ";".join(sorted(names_a & names_b)), "decision": "", "reviewer": "", "reason": ""})
    return suggestions, {"blocked_candidate_pairs": len(candidates), "suggestions": len(suggestions),
                         "threshold": threshold, "max_anchor_document_frequency": max_anchor_frequency,
                         "year_gap_max": 3, "groups_changed": False, "human_review_complete": False,
                         "limitation": "Heuristic rare-token blocking; not exhaustive. Name overlap is not identity proof. Similar titles may be different works."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "kg_datasets/dblp/ner_v2/near_duplicate_review")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    records = read_jsonl(ROOT / "kg_datasets/dblp/ner_v1/corpus_manifest.jsonl")
    base = ROOT / "kg_datasets/dblp/processed_ai"
    names = {r["personId:ID(Person)"]: r["name"] for r in load_csv(base / "persons.csv")}
    authors = defaultdict(set)
    for row in load_csv(base / "authored.csv"):
        authors[row[":END_ID(Publication)"]].add(names[row[":START_ID(Person)"]])
    suggestions, summary = suggest_pairs(records, authors=authors)
    args.output.mkdir(parents=True)
    fields = ["leftId", "rightId", "leftTitle", "rightTitle", "leftYear", "rightYear", "tokenJaccard", "characterSimilarity", "sharedDisplayAuthorNames", "decision", "reviewer", "reason"]
    write_csv(args.output / "near_duplicate_pairs.csv", suggestions, fields)
    write_json(args.output / "summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
