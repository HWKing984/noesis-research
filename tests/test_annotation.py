import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from annotation_core import validate_records
from prepare_ner import audit_tables, draft_entities, duplicate_groups, select_pilot, ambiguity_flags


def document():
    return {"publicationId": "test/1", "text": "😀 Graph Neural Networks for Node Classification on Cora",
            "entities": draft_entities("😀 Graph Neural Networks for Node Classification on Cora"),
            "relations": [], "review_status": "draft", "annotation_source": "draft_dictionary_v1",
            "reviewer": "", "reviewed_at": "", "sourceCsvSha256": "testhash", "schemaVersion": "v1-candidate",
            "groupId": "g1"}


class AnnotationTest(unittest.TestCase):
    def test_non_object_and_invalid_id_are_errors_not_crashes(self):
        self.assertFalse(validate_records([[]])["valid"])
        row = document()
        row["publicationId"] = []
        self.assertFalse(validate_records([row], reference=[document()])["valid"])

    def test_audit_rejects_duplicate_nodes_and_dangling_edges(self):
        tables = {"persons": [{"personId:ID(Person)": "p"}],
                  "publications": [{"publicationId:ID(Publication)": "doc", "title": "t", "type": "article", "year:int": "2020", "doi": ""}],
                  "venues": [], "topics": [], "authored": [], "published_in": [], "about": []}
        self.assertTrue(audit_tables(tables)["valid"])
        tables["persons"].append(dict(tables["persons"][0]))
        self.assertFalse(audit_tables(tables)["valid"])
        tables["persons"].pop()
        tables["authored"].append({":START_ID(Person)": "missing", ":END_ID(Publication)": "doc", "position:int": "1", ":TYPE": "AUTHORED"})
        self.assertFalse(audit_tables(tables)["valid"])

    def test_dictionary_longest_span_unicode_and_boundaries(self):
        row = document()
        self.assertTrue(validate_records([row])["valid"])
        self.assertEqual([e["label"] for e in row["entities"]], ["METHOD", "TASK", "DATASET"])
        self.assertEqual(row["entities"][0]["start"], 2)  # emoji counts as one codepoint
        self.assertEqual(row["entities"][0]["text"], "Graph Neural Networks")
        self.assertEqual(draft_entities("BERTology with a new approach"), [])

    def test_draft_cannot_be_gold(self):
        row = document()
        self.assertFalse(validate_records([row], gold=True)["valid"])
        row.update(review_status="reviewed", reviewer="", annotation_source="human_reviewed")
        self.assertFalse(validate_records([row], gold=True)["valid"])
        row.update(reviewer="unit-test-fixture-not-a-real-review", reviewed_at="2026-10-05T10:00:00+08:00")
        self.assertTrue(validate_records([row], gold=True)["valid"])

    def test_wrong_spans_overlap_and_duplicates(self):
        for change in (lambda r: r["entities"][0].update(start=-1),
                       lambda r: r["entities"][0].update(text="wrong"),
                       lambda r: r["entities"].append(dict(r["entities"][0])),
                       lambda r: r["entities"][0].update(start=True)):
            row = document()
            change(row)
            self.assertFalse(validate_records([row])["valid"])
        self.assertFalse(validate_records([document(), document()])["valid"])

    def test_reference_text_hash_and_missing_record_rejected(self):
        original = document()
        self.assertTrue(validate_records([copy.deepcopy(original)], reference=[original])["valid"])
        for key in ("text", "sourceCsvSha256", "schemaVersion", "groupId"):
            edited = copy.deepcopy(original)
            edited[key] += "x"
            self.assertFalse(validate_records([edited], reference=[original])["valid"])
        self.assertFalse(validate_records([], reference=[original])["valid"])

    def test_relation_direction_and_evidence(self):
        row = document()
        row["relations"] = [{"head": 0, "tail": 1, "label": "USED_FOR", "evidence":
                              {"start": 0, "end": len(row["text"]), "text": row["text"]}}]
        self.assertTrue(validate_records([row])["valid"])
        row["relations"][0]["label"] = "EVALUATED_ON"
        self.assertFalse(validate_records([row])["valid"])
        row["relations"][0]["label"] = "USED_FOR"
        row["relations"][0]["evidence"]["text"] = "fabricated"
        self.assertFalse(validate_records([row])["valid"])

    def test_duplicate_group_transitive_links(self):
        pubs = [{"publicationId": "a", "text": "Same Title.", "doi": "1"},
                {"publicationId": "b", "text": "same title", "doi": "2"},
                {"publicationId": "c", "text": "Different Title", "doi": "2"},
                {"publicationId": "d", "text": "Other", "doi": ""}]
        groups, _ = duplicate_groups(pubs)
        self.assertEqual(groups["a"], groups["c"])
        self.assertNotEqual(groups["a"], groups["d"])

    def test_pilot_reproducible_and_group_unique(self):
        pubs = [{"publicationId": str(i), "groupId": str(i // 2), "text": "no dictionary hits",
                 "year": 2015 + i % 11, "type": "article" if i % 2 else "inproceedings",
                 "topics": ["topic-a" if i % 4 < 2 else "topic-b"]} for i in range(100)]
        first = select_pilot(pubs, 20, 42)
        self.assertEqual(first, select_pilot(list(reversed(pubs)), 20, 42))
        self.assertEqual(len({r["groupId"] for r in first}), 20)
        self.assertEqual(sum(r["samplingStratum"]["topic"] == "topic-a" for r in first), 10)
        with self.assertRaises(ValueError):
            select_pilot(pubs, 51, 42)

    def test_transformer_flag_is_not_llm_claim(self):
        self.assertIn("transformer_not_necessarily_llm_or_even_ai", ambiguity_flags({"text": "Transformer fault detection"}))
        self.assertNotIn("transformer_not_necessarily_llm_or_even_ai", ambiguity_flags({"text": "Large Language Models with Transformers"}))


if __name__ == "__main__":
    unittest.main()
