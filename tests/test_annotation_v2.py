import copy
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import annotation_v2 as contract


@pytest.fixture
def row():
    text = "😀 Graph Neural Networks for Node Classification on Cora"
    return {
        "publicationId": "test/1", "title": text, "text": text, "textKind": "title", "year": 2020,
        "type": "article", "doi": "10.1000/test", "topics": ["graph-neural-network"], "groupId": "g1",
        "sourceCsvSha256": "a" * 64, "schemaVersion": contract.SCHEMA["properties"]["schemaVersion"]["const"],
        "schemaSha256": contract.SCHEMA_SHA256, "intendedSplit": "train", "samplingStratum": {"topic": "graph-neural-network"},
        "ambiguityFlags": [], "textSource": {"provider": "DBLP", "sourceRecordId": "test/1", "snapshot": "2026-09-01",
          "sourceUrl": "https://dblp.org/rec/test/1", "license": "CC0-1.0", "textSha256": hashlib.sha256(text.encode()).hexdigest()},
        "entities": [{"start": 2, "end": 23, "text": "Graph Neural Networks", "label": "METHOD", "origin": "human"},
                     {"start": 28, "end": 47, "text": "Node Classification", "label": "TASK", "origin": "human"},
                     {"start": 51, "end": 55, "text": "Cora", "label": "DATASET", "origin": "human"}],
        "relations": [], "domains": [], "entity_review": contract.new_review(), "relation_review": contract.new_review(),
        "domain_review": contract.new_review(), "notes": ""
    }


def reviewed():
    return {"status": "reviewed", "reviewer": "SYNTHETIC-UNIT-TEST", "reviewed_at": "2026-10-05T10:00:00+08:00", "source": "human_reviewed"}


def test_valid_draft_and_explicit_gold_scope(row):
    assert contract.validate_records([row], reference=[row])["valid"]
    assert not contract.validate_records([row], reference=[row], entity_gold=True)["valid"]
    row["entity_review"] = reviewed()
    result = contract.validate_records([row], reference=[row], entity_gold=True)
    assert result["valid"] and not result["training_ready"]
    assert not contract.validate_records([row], reference=[row], relation_gold=True)["valid"]


@pytest.mark.parametrize("key,value", [
    ("year", 2021), ("type", "inproceedings"), ("doi", "10.1000/tampered"), ("topics", ["tampered"]),
    ("intendedSplit", "test"), ("samplingStratum", {"topic": "tampered"}), ("ambiguityFlags", ["tampered"]),
    ("title", "changed"), ("groupId", "changed"), ("sourceCsvSha256", "b" * 64)])
def test_all_metadata_locked(row, key, value):
    changed = copy.deepcopy(row)
    changed[key] = value
    assert not contract.validate_records([changed], reference=[row])["valid"]


def test_nested_provenance_and_schema_hash_locked(row):
    changed = copy.deepcopy(row)
    changed["textSource"]["sourceUrl"] += "tampered"
    assert not contract.validate_records([changed], reference=[row])["valid"]
    row["schemaSha256"] = "0" * 64
    assert not contract.validate_records([row])["valid"]


def test_relation_gold_requires_all_pairs_and_resolved_labels(row):
    row["entity_review"] = reviewed()
    row["relation_review"] = reviewed()
    evidence = {"start": 0, "end": len(row["text"]), "text": row["text"]}
    row["relations"] = [{"head": 0, "tail": 1, "label": "USED_FOR", "evidence": evidence, "reason": "explicit for phrase"}]
    assert not contract.validate_records([row], reference=[row], relation_gold=True)["valid"]
    row["relations"].append({"head": 0, "tail": 2, "label": "UNRESOLVED", "evidence": None, "reason": "title insufficient"})
    assert not contract.validate_records([row], reference=[row], relation_gold=True)["valid"]
    row["relations"][1].update(label="NO_RELATION", evidence=evidence, reason="no evaluation assertion in title")
    assert contract.validate_records([row], reference=[row], relation_gold=True)["valid"]


def test_separate_domain_evidence_can_overlap_task(row):
    row["domains"] = [{"label": "education", "evidence": {"start": 28, "end": 47, "text": "Node Classification"}, "origin": "human"}]
    # Structural fixture only, not a claim this title really concerns education.
    row["domain_review"] = reviewed()
    assert contract.validate_records([row], reference=[row], domain_gold=True)["valid"]
    row["entities"][1]["label"] = "DOMAIN"
    assert not contract.validate_records([row])["valid"]


@pytest.mark.parametrize("value", [None, [], "bad", 123])
def test_bad_record_fails_without_crashing(value):
    assert not contract.validate_records([value])["valid"]


def test_empty_gold_and_missing_reference_rejected(row):
    assert not contract.validate_records([], reference=[], entity_gold=True)["valid"]
    row["entity_review"] = reviewed()
    assert not contract.validate_records([row], entity_gold=True)["valid"]


@pytest.mark.parametrize("review", [
    {"status": "reviewed", "reviewer": " ", "reviewed_at": "2026-10-05T10:00:00+08:00", "source": "human_reviewed"},
    {"status": "reviewed", "reviewer": "tester", "reviewed_at": "2026-10-05T10:00:00", "source": "human_reviewed"},
    {"status": "draft", "reviewer": "tester", "reviewed_at": "", "source": "draft"}])
def test_review_claim_consistency(row, review):
    row["entity_review"] = review
    assert not contract.validate_records([row])["valid"]


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(title="wrong title"),
    lambda r: r["textSource"].update(textSha256="0" * 64),
    lambda r: r["textSource"].update(sourceRecordId="wrong"),
    lambda r: r["entities"][0].update(end=2000),
    lambda r: r["entities"][0].update(text="wrong span"),
    lambda r: r["entities"].append(copy.deepcopy(r["entities"][0])),
    lambda r: r["entity_review"].update(status="reviewed", reviewer="tester", reviewed_at="bad", source="draft"),
    lambda r: r.update(unexpected="field")])
def test_semantic_and_shape_failures(row, mutation):
    mutation(row)
    assert not contract.validate_records([row])["valid"]


def test_duplicate_and_invalid_reference_rows(row):
    assert not contract.validate_records([row, row])["valid"]
    assert not contract.validate_records([row], reference=[row, row, None])["valid"]
    original = copy.deepcopy(row)
    original["year"] = 1900
    assert not contract.validate_records([row], reference=[original])["valid"]


@pytest.mark.parametrize("mutation", [
    lambda r: r["relations"][0].update(head=0.0),
    lambda r: r["relations"][0].update(head=2, tail=0),
    lambda r: r["relations"].append(copy.deepcopy(r["relations"][0])),
    lambda r: r["relations"][0].update(label="EVALUATED_ON"),
    lambda r: r["relations"][0].update(label="UNRESOLVED", evidence=None, reason=""),
    lambda r: r["relations"][0].update(evidence=None),
    lambda r: r["relations"][0]["evidence"].update(text="fabricated"),
    lambda r: r["relations"][0].update(evidence={"start": 2, "end": 23, "text": "Graph Neural Networks"}),
    lambda r: r["relations"][0].update(label="NO_RELATION", reason="")])
def test_relation_failure_cases(row, mutation):
    row["relations"] = [{"head": 0, "tail": 1, "label": "USED_FOR",
        "evidence": {"start": 0, "end": len(row["text"]), "text": row["text"]}, "reason": "for phrase"}]
    mutation(row)
    assert not contract.validate_records([row])["valid"]


def test_domain_failures_and_empty_document_gold(row):
    domain = {"label": "healthcare", "evidence": {"start": 0, "end": 1, "text": "wrong"}, "origin": "human"}
    row["domains"] = [domain, copy.deepcopy(domain)]
    assert not contract.validate_records([row], reference=[row], domain_gold=True)["valid"]
    row["domains"] = []
    row["entities"] = []
    row["entity_review"] = reviewed()
    row["relation_review"] = reviewed()
    assert contract.validate_records([row], reference=[row], relation_gold=True)["valid"]


def test_span_strict_integer_and_empty_end(row):
    assert contract.span_error({"start": True, "end": 2, "text": " "}, row["text"])
    assert contract.span_error({"start": 2, "end": 2, "text": ""}, row["text"])


def test_cli_scopes_and_exit_codes(row, tmp_path, monkeypatch, capsys):
    source = tmp_path / "reference.jsonl"
    source.write_text(__import__('json').dumps(row) + '\n', encoding='utf-8')
    for flag, expected in (([], 0), (["--entity-gold"], 1), (["--relation-gold"], 1), (["--domain-gold"], 1)):
        monkeypatch.setattr(sys, "argv", ["annotation_v2.py", str(source), "--reference", str(source), *flag])
        with pytest.raises(SystemExit) as exit_result:
            contract.main()
        assert exit_result.value.code == expected
    monkeypatch.setattr(sys, "argv", ["annotation_v2.py", str(source), "--gold"])
    with pytest.raises(SystemExit) as exit_result:
        contract.main()
    assert exit_result.value.code == 2
    monkeypatch.setattr(sys, "argv", ["annotation_v2.py", str(source)])
    with pytest.raises(SystemExit) as exit_result:
        __import__('runpy').run_path(str(contract.ROOT / 'scripts/annotation_v2.py'), run_name='__main__')
    assert exit_result.value.code == 0


def test_agreement_requires_actual_review_declarations(row):
    from compare_entity_annotations import compare
    with pytest.raises(ValueError):
        compare([row], [row], [row])
    row["entity_review"] = reviewed()
    other = copy.deepcopy(row)
    other["entities"][0].update(start=8, text="Neural Networks")
    other["entities"][1]["label"] = "METHOD"
    result = compare([row], [other], [row])
    assert result["boundary_disagreements"] and result["label_confusion"]
    assert result["strict_entity_agreement_f1"] < 1
    row["entities"] = []
    assert compare([row], [row], [row])["strict_entity_agreement_f1"] is None
