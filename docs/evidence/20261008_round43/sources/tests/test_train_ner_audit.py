from pathlib import Path
import sys
from unittest.mock import patch
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import audit_abstract_ner_training as audit
import revise_train_task_boundary as boundary
import copy


def test_train_only_diagnostics():
    with patch.object(audit.c, 'read_jsonl', wraps=audit.c.read_jsonl) as reads:
        config, rows, refs, review = audit.load_inputs()
    assert {call.args[0].name for call in reads.call_args_list} == {'train_references.jsonl', 'train_reviewed_receipts.jsonl', 'ner_train.jsonl'}
    assert len(rows) == 50 and all(r['split'] == 'train' for r in refs)
    assert len(review['documents']) == 16 and not review['independent']
    stats = audit.inventory(rows)
    assert stats['entitySupport'] == {'METHOD': 378, 'TASK': 189, 'DATASET': 44}
    assert stats['datasetDocuments'][0]['mentions'] == 14
    row = {'sampleId': 'synthetic', 'textSha256': 'unused', 'text': 'abc def ghi jkl', 'entities': [
        {'start': 0, 'end': 3, 'text': 'abc', 'label': 'TASK'}, {'start': 4, 'end': 7, 'text': 'def', 'label': 'METHOD'}, {'start': 8, 'end': 11, 'text': 'ghi', 'label': 'DATASET'}]}
    pred = [{'start': 0, 'end': 3, 'text': 'abc', 'label': 'METHOD'}, {'start': 4, 'end': 6, 'text': 'de', 'label': 'METHOD'}, {'start': 12, 'end': 15, 'text': 'jkl', 'label': 'TASK'}]
    errors = audit.errors_for(row, pred)
    assert sorted(e['cause'] for e in errors) == ['boundary', 'boundary', 'extra', 'missing', 'type', 'type']
    assert not audit.errors_for(row, row['entities'])
    with pytest.raises(ValueError, match='Duplicate'): audit.errors_for(row, pred+pred[:1])
    assert audit.revised.dev_scope({'micro': {'evaluationTarget': 'held_out'}}, config['evaluationTarget'])['micro']['evaluationTarget'] == config['evaluationTarget']
    with pytest.raises(FileExistsError): audit.run(Path(__file__).parent.resolve())
    proposal = audit.read(boundary.CONTRACT)
    original_receipts = audit.c.read_jsonl(audit.c.ROOT/config['snapshot']/'train_reviewed_receipts.jsonl')
    ref, prior = next((r, a) for r, a in zip(refs, original_receipts) if r['arxivId'] == proposal['arxivId'])
    response = boundary.amend(proposal, ref, prior)
    assert response['entities'][2] == proposal['after'] and prior['annotation']['entities'][2] == proposal['before']
    assert response['relations'] == prior['annotation']['relations']
    wrong = copy.deepcopy(prior)
    changed_pair = next(p for p in wrong['annotation']['relations'] if p['tail'] == 'e3')
    changed_pair['label'] = 'NO_RELATION'
    with patch.object(boundary.c, 'validate_receipt', return_value=[]):
        with pytest.raises(ValueError, match='resolved relation'): boundary.amend(proposal, ref, wrong)
    with pytest.raises(FileExistsError): boundary.build(Path(__file__).parent.resolve())
