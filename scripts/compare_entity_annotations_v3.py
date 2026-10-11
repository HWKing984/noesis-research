"""Compare two real independent entity annotations; no invented agreement scores."""
import argparse
import json
from pathlib import Path

from annotation_v3 import read_jsonl, validate_records


def compare(left, right, reference):
    for records in (left, right):
        result = validate_records(records, reference=reference, entity_gold=True)
        if not result["valid"]:
            raise ValueError("Both annotation sets must pass entity review and reference checks")
    a = {r["publicationId"]: r for r in left}
    b = {r["publicationId"]: r for r in right}
    exact, left_total, right_total, boundary, label_confusion = 0, 0, 0, [], []
    for pid in sorted(a):
        spans_a = {(e["start"], e["end"], e["label"]) for e in a[pid]["entities"]}
        spans_b = {(e["start"], e["end"], e["label"]) for e in b[pid]["entities"]}
        exact += len(spans_a & spans_b)
        left_total += len(spans_a)
        right_total += len(spans_b)
        for start, end, label in sorted(spans_a - spans_b):
            for bs, be, bl in sorted(spans_b - spans_a):
                if (start, end) == (bs, be) and label != bl:
                    label_confusion.append({"publicationId": pid, "span": [start, end], "left": label, "right": bl})
                elif label == bl and start < be and bs < end:
                    boundary.append({"publicationId": pid, "label": label, "left": [start, end], "right": [bs, be]})
    denominator = left_total + right_total
    return {"documents": len(left), "left_entities": left_total, "right_entities": right_total,
            "exact_matches": exact, "strict_entity_agreement_f1": 2 * exact / denominator if denominator else None,
            "boundary_disagreements": boundary, "label_confusion": label_confusion,
            "all_empty": denominator == 0, "adjudication_completed": False,
            "notice": "Pairwise span candidates can be many-to-many; counts are diagnostic, not a complete error partition"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(read_jsonl(args.left), read_jsonl(args.right), read_jsonl(args.reference)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
