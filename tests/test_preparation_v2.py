import sys
import json
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_revision_v2 import draft_annotations, select_diverse
import prepare_revision_v2 as prepare


def test_medical_task_and_document_domain_no_entity_conflict():
    text = "A Vision Transformer for Medical Image Segmentation"
    entities, domains = draft_annotations(text)
    assert [e["text"] for e in entities] == ["Vision Transformer", "Medical Image Segmentation"]
    assert domains[0]["label"] == "healthcare"
    assert domains[0]["evidence"]["start"] >= entities[1]["start"]
    assert all(e["label"] != "DOMAIN" for e in entities)


def test_modifiers_and_missing_task_dictionary_regressions():
    entities, _ = draft_annotations("Novel Siamese Neural Networks for Fraud Detection with Deep Convolutional Neural Networks")
    assert [e["text"] for e in entities] == ["Siamese Neural Networks", "Fraud Detection", "Deep Convolutional Neural Networks"]


def test_diversity_cap_and_group_isolation():
    candidates = [{"publicationId": str(i), "groupId": str(i // 2),
                   "entities": [{"label": "DATASET", "text": "MNIST" if i < 10 else "SQuAD"}],
                   "domains": [{"label": "healthcare"}]} for i in range(20)]
    chosen = select_diverse(candidates, {"0"}, limit=100, surface_cap=2)
    assert len(chosen) == 4
    assert len({r["groupId"] for r in chosen}) == 4
    assert not any(r["groupId"] == "0" for r in chosen)
    assert chosen == select_diverse(list(reversed(candidates)), {"0"}, limit=100, surface_cap=2)
    assert len(select_diverse(candidates, set(), limit=1)) == 1


def test_prepare_main_version_protection_and_blank_material(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in ("review_v2_template.html", "review_v2.js"):
        shutil.copy2(prepare.ROOT / "docs" / name, docs / name)
    source = tmp_path / "v1"
    source.mkdir()
    base = {"publicationId": "test/1", "text": "Vision Transformer for Medical Image Segmentation", "year": 2020,
            "type": "article", "doi": "", "topics": ["computer-vision"], "groupId": "g1",
            "ambiguityFlags": [], "samplingStratum": {"topic": "computer-vision"},
            "sourceCsvSha256": "a" * 64, "review_status": "draft"}
    rare = dict(base, publicationId="test/2", text="Neural Networks on MNIST", groupId="g2")
    (source / "pilot_200.jsonl").write_text(json.dumps(base) + '\n', encoding='utf-8')
    (source / "corpus_manifest.jsonl").write_text(json.dumps(base) + '\n' + json.dumps(rare) + '\n', encoding='utf-8')
    destination = tmp_path / "v2"
    monkeypatch.setattr(prepare, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["prepare_revision_v2.py", "--input", str(source), "--output", str(destination)])
    prepare.main()
    blind = prepare.read_jsonl(destination / "blind_50_reference.jsonl")
    assert not blind[0]["entities"] and not blind[0]["domains"]
    assert prepare.validate_records(prepare.read_jsonl(destination / "pilot_200.jsonl"))["valid"]
    with pytest.raises(FileExistsError):
        prepare.main()
    monkeypatch.setattr(sys, "argv", ["prepare_revision_v2.py", "--input", str(source), "--output", str(tmp_path / 'v3')])
    base["review_status"] = "reviewed"
    (source / "pilot_200.jsonl").write_text(json.dumps(base) + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match="silently migrate"):
        prepare.main()
    base["review_status"] = "draft"
    base["year"] = 1900
    (source / "pilot_200.jsonl").write_text(json.dumps(base) + '\n', encoding='utf-8')
    with pytest.raises(ValueError, match="Invalid generated"):
        prepare.main()


def test_entrypoint_and_lexicon_schema_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['prepare_revision_v2.py', '--output', str(tmp_path)])
    with pytest.raises(FileExistsError):
        __import__('runpy').run_path(str(prepare.ROOT / 'scripts/prepare_revision_v2.py'), run_name='__main__')
    original = Path.read_text
    def bad_lexicon(path, *args, **kwargs):
        if path == prepare.LEXICON_PATH:
            value = json.loads(original(path, *args, **kwargs))
            value['entities']['UNKNOWN'] = []
            return json.dumps(value)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', bad_lexicon)
    with pytest.raises(ValueError, match='Lexicon labels'):
        __import__('runpy').run_path(str(prepare.ROOT / 'scripts/prepare_revision_v2.py'))
