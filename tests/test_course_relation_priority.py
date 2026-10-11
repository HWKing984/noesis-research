"""Real authored selection/labels stay train-only and preserve role contrasts."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_weak as c
from compile_course_ai import compile_decisions
from expand_course_ai_review import expand_review


def test_recorded_role_priority_is_train_pending_and_candidate_aware():
    snapshot = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_09'
    refs = {r['sampleId']: r for r in c.read_jsonl(ROOT / 'kg_datasets/dblp/course_v4_weak/references.jsonl')}
    pending = {r['sampleId']: r for r in c.read_jsonl(snapshot / 'pending_generation.jsonl')}
    folder = ROOT / 'annotations/course_v4'
    generation_path = folder / 'relation_priority002_generation_decisions.json'
    first = json.loads(generation_path.read_text(encoding='utf-8'))
    review = json.loads((folder / 'relation_priority002_review_judgments.json').read_text(encoding='utf-8'))
    expanded = expand_review(first, review, c.file_sha256(generation_path))
    selected = [refs[d['sampleId']] for d in first['decisions']]
    assert len(selected) == len({r['sampleId'] for r in selected}) == 25
    assert all(r['split'] == 'train' and c.model_payload(r) == pending[r['sampleId']] for r in selected)
    responses = compile_decisions(expanded['decisions'], selected)
    assert sum(j['verdict'] == 'revised' for j in review['judgments']) == 2
    labels = [p['label'] for r in responses if r['entityStatus'] == r['relationStatus'] == 'complete' for p in r['relations']]
    assert labels.count('NO_RELATION') >= 10 and labels.count('USED_FOR') >= 10
    assert labels.count('EVALUATED_ON') == 0  # partial QuixBugs is provenance, not a complete training row
    by_id = {r['sampleId']: r for r in responses}
    opposite = by_id['sample-f0f1cb8a7cbb36f9bfe0']
    assert [p['label'] for p in opposite['relations']] == ['NO_RELATION', 'USED_FOR']
    quix = by_id['sample-ce39355f46f7c85b80b4']
    assert quix['entityStatus'] == quix['relationStatus'] == 'unresolved'


def test_selector_rejects_nontrain_pending_and_preserves_existing_output(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('role_selector', ROOT / 'annotations/course_v4/relation_priority002_jobs.py')
    selector = importlib.util.module_from_spec(spec); spec.loader.exec_module(selector)
    monkeypatch.setattr(selector, 'ROOT', tmp_path)
    output = tmp_path / 'kg_datasets/dblp/course_v4_runs/relation_priority002_jobs'
    output.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        selector.prepare()
    output.rmdir()
    ids = ['sample-' + s for s in selector.SELECTED]
    refs = [{'sampleId': s, 'split': 'train'} for s in ids]
    refs[0]['split'] = 'dev'
    monkeypatch.setattr(selector, 'verify_files', lambda _: {})
    monkeypatch.setattr(selector, 'verify_dataset', lambda _: refs)
    monkeypatch.setattr(c, 'read_jsonl', lambda p: [{'sampleId': s} for s in ids] if p.name == 'pending_generation.jsonl' else [])
    monkeypatch.setattr(c, 'model_payload', lambda r: {'sampleId': r['sampleId']})
    with pytest.raises(ValueError, match='unannotated canonical train'):
        selector.prepare()
    assert not output.exists()
