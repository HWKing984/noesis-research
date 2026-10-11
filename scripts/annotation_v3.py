"""Schema-driven v3 validation: entity, relation and document-domain reviews are separate."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/annotation_v3.schema.json"
SCHEMA_BYTES = SCHEMA_PATH.read_bytes()
SCHEMA = json.loads(SCHEMA_BYTES)
Draft202012Validator.check_schema(SCHEMA)
SCHEMA_SHA256 = hashlib.sha256(SCHEMA_BYTES).hexdigest()
RULES_PATH = ROOT / "resources/boundary_rules_v3.json"
RULES_BYTES = RULES_PATH.read_bytes()
RULES = json.loads(RULES_BYTES)
RULES_SHA256 = hashlib.sha256(RULES_BYTES).hexdigest()
ANNOTATION = SCHEMA["x-annotation"]
LABELS = SCHEMA["$defs"]["entity"]["properties"]["label"]["enum"]
DOMAIN_LABELS = SCHEMA["$defs"]["domain"]["properties"]["label"]["enum"]
IMMUTABLE_FIELDS = sorted(set(SCHEMA["properties"]) - set(ANNOTATION["mutable_fields"]))
SHAPE_VALIDATOR = Draft202012Validator(SCHEMA, format_checker=Draft202012Validator.FORMAT_CHECKER)


def read_jsonl(path: Path) -> list:
    with path.open(encoding="utf-8-sig") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def new_review() -> dict:
    return {"status": "draft", "reviewer": "", "reviewed_at": "", "source": "draft"}


def candidate_pairs(entities: list[dict]) -> dict[tuple[int, int], str]:
    return {(h, t): label for h, head in enumerate(entities) for t, tail in enumerate(entities)
            for label, pair in ANNOTATION["positive_relation_pairs"].items()
            if (head["label"], tail["label"]) == tuple(pair)
            and head["mentionForm"] not in ANNOTATION["excluded_relation_mention_forms"]
            and tail["mentionForm"] not in ANNOTATION["excluded_relation_mention_forms"]}


def scope_exclusions(entities: list[dict]) -> list[dict]:
    excluded = []
    for h, head in enumerate(entities):
        for t, tail in enumerate(entities):
            compatible = any((head["label"], tail["label"]) == tuple(pair)
                             for pair in ANNOTATION["positive_relation_pairs"].values())
            if compatible and (head["mentionForm"] in ANNOTATION["excluded_relation_mention_forms"] or
                               tail["mentionForm"] in ANNOTATION["excluded_relation_mention_forms"]):
                excluded.append({"head": h, "tail": t, "reason": "COORDINATED_INDIVIDUAL_RELATIONS_EXCLUDED"})
            elif h < t and head["label"] == tail["label"] == "TASK":
                excluded.append({"head": h, "tail": t, "reason": "TASK_TO_TASK_OUT_OF_SCOPE"})
    return excluded


def span_error(span: dict, text: str) -> str | None:
    start, end = span["start"], span["end"]
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
        return "invalid Unicode character range"
    if text[start:end] != span["text"]:
        return "span text differs from source"
    return None


def review_errors(review: dict) -> list[str]:
    if review["status"] != "reviewed":
        return ["unreviewed must not carry human-review claims"] if review["reviewer"] or review["reviewed_at"] or review["source"] != "draft" else []
    errors = []
    if not review["reviewer"].strip() or review["source"] != "human_reviewed":
        errors.append("reviewed requires human reviewer and source")
    try:
        if datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00")).tzinfo is None:
            raise ValueError()
    except ValueError:
        errors.append("reviewed requires ISO timestamp with timezone")
    return errors


def validate_records(records: list, *, reference: list | None = None,
                     entity_gold: bool = False, relation_gold: bool = False, domain_gold: bool = False) -> dict:
    errors, seen = [], set()
    counts = Counter({label: 0 for label in LABELS})
    exclusions = Counter()
    statuses = {name: Counter() for name in ("entity_review", "relation_review", "domain_review")}
    ref = {}
    if reference is not None:
        for original in reference:
            if not isinstance(original, dict) or not isinstance(original.get("publicationId"), str) or original["publicationId"] in ref:
                errors.append({"errors": ["reference IDs must be unique nonempty strings"]})
                continue
            ref[original["publicationId"]] = original
            if list(SHAPE_VALIDATOR.iter_errors(original)) or original.get("schemaSha256") != SCHEMA_SHA256:
                errors.append({"publicationId": original["publicationId"], "errors": ["reference does not satisfy this schema/version"]})
    if (entity_gold or relation_gold or domain_gold) and (reference is None or not records):
        errors.append({"errors": ["gold checks require nonempty records and an independent original reference"]})
    for number, record in enumerate(records, 1):
        shape_errors = list(SHAPE_VALIDATOR.iter_errors(record))
        if shape_errors:
            errors.append({"row": number, "errors": [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in shape_errors]})
            continue
        pid, text = record["publicationId"], record["text"]
        row_errors = []
        if pid in seen:
            row_errors.append("duplicate publicationId")
        seen.add(pid)
        if record["boundaryRulesSha256"] != RULES_SHA256:
            row_errors.append("boundary rules hash differs from authoritative policy")
        provenance = record["initialDraftProvenance"]
        if (provenance["kind"] == "ai_rule_stress_test") != (provenance["aiReviewSha256"] is not None):
            row_errors.append("AI initial provenance requires explicit source hash; non-AI drafts must not carry AI source")
        if provenance["aiReviewSha256"] is not None and provenance["aiReviewSha256"] != RULES["source_review_sha256"]:
            row_errors.append("AI review source hash differs from preserved stress review")
        if any(e["origin"] == "ai_suggestion" for e in record["entities"]) and provenance["kind"] != "ai_rule_stress_test":
            row_errors.append("AI spans require declared initial AI provenance")
        if record["schemaSha256"] != SCHEMA_SHA256:
            row_errors.append("schema hash differs from authoritative contract")
        if text != record["title"] or hashlib.sha256(text.encode()).hexdigest() != record["textSource"]["textSha256"]:
            row_errors.append("title/text/hash mismatch")
        if record["textSource"]["sourceRecordId"] != pid:
            row_errors.append("sourceRecordId must identify this publication")
        if reference is not None:
            original = ref.get(pid)
            if original is None or any(record[key] != original.get(key) for key in IMMUTABLE_FIELDS):
                row_errors.append("immutable metadata differs from reference (including split/provenance)")
        for name in statuses:
            statuses[name][record[name]["status"]] += 1
            row_errors += [f"{name}: {error}" for error in review_errors(record[name])]
        entities = record["entities"]
        for index, entity in enumerate(entities):
            error = span_error(entity, text)
            if error:
                row_errors.append(f"entity {index}: {error}")
            counts[entity["label"]] += 1
        if any(left["end"] > right["start"] for left, right in zip(entities, entities[1:])):
            row_errors.append("entities must be in source order and must not overlap")
        exclusions.update(item["reason"] for item in scope_exclusions(entities))
        candidates = candidate_pairs(entities)
        annotated = {}
        for index, relation in enumerate(record["relations"]):
            if type(relation["head"]) is not int or type(relation["tail"]) is not int:
                row_errors.append(f"relation {index}: entity indices must be integers")
                continue
            pair = (relation["head"], relation["tail"])
            if pair not in candidates or pair in annotated:
                row_errors.append(f"relation {index}: invalid/duplicate directed pair")
                continue
            annotated[pair] = relation["label"]
            if relation["label"] not in {candidates[pair], ANNOTATION["negative_relation_label"], ANNOTATION["unresolved_relation_label"]}:
                row_errors.append(f"relation {index}: label incompatible with entity pair")
            evidence = relation["evidence"]
            if relation["label"] == ANNOTATION["unresolved_relation_label"]:
                if not relation["reason"].strip():
                    row_errors.append(f"relation {index}: unresolved requires reason")
            elif evidence is None:
                row_errors.append(f"relation {index}: resolved decision requires text evidence")
            if evidence is not None:
                error = span_error(evidence, text)
                if error:
                    row_errors.append(f"relation {index}: {error}")
                elif (evidence["start"] > min(entities[pair[0]]["start"], entities[pair[1]]["start"]) or
                      evidence["end"] < max(entities[pair[0]]["end"], entities[pair[1]]["end"])):
                    row_errors.append(f"relation {index}: evidence must cover both entities")
            if relation["label"] == ANNOTATION["negative_relation_label"] and not relation["reason"].strip():
                row_errors.append(f"relation {index}: explicit negative requires reason")
        if record["relation_review"]["status"] == "reviewed":
            if record["entity_review"]["status"] != "reviewed" or set(annotated) != set(candidates) or ANNOTATION["unresolved_relation_label"] in annotated.values():
                row_errors.append("relation review cannot be complete: entity review/pair coverage/resolution missing")
        domain_seen = set()
        for index, domain in enumerate(record["domains"]):
            error = span_error(domain["evidence"], text)
            if error:
                row_errors.append(f"domain {index}: {error}")
            if domain["label"] in domain_seen:
                row_errors.append("duplicate document domain label")
            domain_seen.add(domain["label"])
        for enabled, field in ((entity_gold or relation_gold, "entity_review"), (relation_gold, "relation_review"), (domain_gold, "domain_review")):
            if enabled and record[field]["status"] != "reviewed":
                row_errors.append(f"gold requires {field} reviewed")
        if row_errors:
            errors.append({"row": number, "publicationId": pid, "errors": row_errors})
    if reference is not None and seen != set(ref):
        errors.append({"errors": ["document IDs must exactly match the independent reference"]})
    return {"valid": not errors, "documents": len(records), "entity_counts": dict(counts),
            "reviews": {key: dict(value) for key, value in statuses.items()}, "errors": errors,
            "contract_sha256": SCHEMA_SHA256, "boundary_rules_sha256": RULES_SHA256,
            "scope_exclusion_counts": dict(exclusions), "schema_status": ANNOTATION["status"],
            "training_ready": not errors and entity_gold and ANNOTATION["status"] == "frozen",
            "notice": "Structural/state checks do not prove actual human review or semantic correctness"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--entity-gold", action="store_true")
    parser.add_argument("--relation-gold", action="store_true")
    parser.add_argument("--domain-gold", action="store_true")
    args = parser.parse_args()
    result = validate_records(read_jsonl(args.input), reference=read_jsonl(args.reference) if args.reference else None,
                              entity_gold=args.entity_gold, relation_gold=args.relation_gold, domain_gold=args.domain_gold)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
