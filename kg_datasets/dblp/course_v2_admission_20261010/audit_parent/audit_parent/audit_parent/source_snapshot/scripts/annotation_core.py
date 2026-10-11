"""Character-span annotation contracts; no ML dependencies required."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

LABELS = ("METHOD", "TASK", "DATASET", "DOMAIN")
RELATIONS = {"USED_FOR": ("METHOD", "TASK"), "EVALUATED_ON": ("METHOD", "DATASET"),
             "APPLIED_TO": ("METHOD", "DOMAIN")}


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def validate_records(records: list[dict], *, gold: bool = False,
                     reference: list[dict] | None = None) -> dict:
    errors = []
    seen = set()
    labels = Counter()
    statuses = Counter()
    ref = {r["publicationId"]: r for r in reference} if reference is not None else None
    zero_entities = 0
    for row_number, record in enumerate(records, 1):
        if not isinstance(record, dict):
            errors.append({"row": row_number, "errors": ["record must be an object"]})
            continue
        row_errors = []
        pid, text = record.get("publicationId"), record.get("text")
        if not isinstance(pid, str) or not pid or pid in seen:
            row_errors.append("missing/duplicate publicationId")
        if isinstance(pid, str):
            seen.add(pid)
        if not isinstance(text, str) or not text:
            row_errors.append("text must be a nonempty string")
            text = ""
        if ref is not None:
            original = ref.get(pid) if isinstance(pid, str) else None
            if original is None or any(record.get(k) != original.get(k) for k in
                                       ("text", "groupId", "sourceCsvSha256", "schemaVersion")):
                row_errors.append("source text/group/hash/schema differs from pilot reference")
        status = record.get("review_status")
        if status not in {"draft", "reviewed"}:
            row_errors.append("review_status must be draft or reviewed")
        statuses[str(status)] += 1
        if gold and status != "reviewed":
            row_errors.append("gold requires actual human review, not draft rules")
        if status == "reviewed":
            if not isinstance(record.get("reviewer"), str) or not record["reviewer"].strip():
                row_errors.append("reviewed requires a named human reviewer")
            try:
                stamp = datetime.fromisoformat(record.get("reviewed_at", "").replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError):
                row_errors.append("reviewed requires an ISO timestamp with timezone")
            if record.get("annotation_source") != "human_reviewed":
                row_errors.append("reviewed requires annotation_source=human_reviewed")
        elif record.get("reviewer") or record.get("reviewed_at") or record.get("annotation_source") == "human_reviewed":
            row_errors.append("draft must not carry human-review claims")
        entities = record.get("entities", [])
        if not isinstance(entities, list):
            row_errors.append("entities must be a list")
            entities = []
        if not entities:
            zero_entities += 1
        valid_entities = {}
        spans = []
        for index, entity in enumerate(entities):
            if not isinstance(entity, dict):
                row_errors.append(f"entity {index}: expected object")
                continue
            start, end, label = entity.get("start"), entity.get("end"), entity.get("label")
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
                row_errors.append(f"entity {index}: invalid character span")
                continue
            if label not in LABELS or text[start:end] != entity.get("text"):
                row_errors.append(f"entity {index}: invalid label or text mismatch")
                continue
            spans.append((start, end))
            valid_entities[index] = entity
            labels[label] += 1
        spans.sort()
        if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
            row_errors.append("overlapping/nested entities are outside the flat schema")
        relations = record.get("relations", [])
        if not isinstance(relations, list):
            row_errors.append("relations must be a list")
            relations = []
        relation_keys = set()
        for index, relation in enumerate(relations):
            if not isinstance(relation, dict):
                row_errors.append(f"relation {index}: expected object")
                continue
            head, tail, kind = relation.get("head"), relation.get("tail"), relation.get("label")
            if type(head) is not int or type(tail) is not int or head == tail or head not in valid_entities or tail not in valid_entities:
                row_errors.append(f"relation {index}: invalid entity indices")
                continue
            pair = (valid_entities[head]["label"], valid_entities[tail]["label"])
            if not isinstance(kind, str):
                row_errors.append(f"relation {index}: label must be a string")
                continue
            if (kind == "NO_RELATION" and pair not in RELATIONS.values()) or (kind != "NO_RELATION" and RELATIONS.get(kind) != pair):
                row_errors.append(f"relation {index}: unsupported type/direction")
            key = (head, tail)
            if key in relation_keys:
                row_errors.append(f"relation {index}: duplicate relation")
            relation_keys.add(key)
            evidence = relation.get("evidence", {})
            if not isinstance(evidence, dict):
                evidence = {}
            start, end = evidence.get("start"), evidence.get("end")
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
                row_errors.append(f"relation {index}: invalid evidence span")
            elif (text[start:end] != evidence.get("text") or
                  start > min(valid_entities[head]["start"], valid_entities[tail]["start"]) or
                  end < max(valid_entities[head]["end"], valid_entities[tail]["end"])):
                row_errors.append(f"relation {index}: evidence mismatch or does not cover both entities")
        if row_errors:
            errors.append({"row": row_number, "publicationId": pid, "errors": row_errors})
    if ref is not None and seen != set(ref):
        errors.append({"errors": ["document IDs must exactly match the reference package"]})
    return {"valid": not errors, "documents": len(records), "review_status": dict(statuses),
            "entity_counts": dict(labels), "zero_entity_documents": zero_entities, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--gold", action="store_true")
    args = parser.parse_args()
    result = validate_records(read_jsonl(args.input), gold=args.gold,
                              reference=read_jsonl(args.reference) if args.reference else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
