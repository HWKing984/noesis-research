"""New TRAIN judgments conserve sealed references and reject invented evidence."""
import copy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import revise_diverse_train_roles as diverse


def inputs():
    config, parent, refs, old = diverse.load_sources()
    decisions = diverse.read(diverse.c.ROOT/'annotations/course_v4/diverse_train_role_decisions_20261010_56.json')['documents']
    lookup = {ref['arxivId']: (ref, prior) for ref, prior in zip(refs, old)}
    return parent, decisions, lookup


def test_train_only_cohort_and_pair_conservation():
    with patch.object(diverse.c, 'read_jsonl', wraps=diverse.c.read_jsonl) as reads:
        parent, decisions, lookup = inputs()
    assert not any('dev' in call.args[0].name or 'test' in call.args[0].name for call in reads.call_args_list)
    added = []
    for decision in decisions:
        ref, prior = lookup[decision['arxivId']]; new = diverse.revision(prior, ref, decision, parent)
        assert all(new[k] == prior['annotation'][k] for k in diverse.role.NER_FIELDS)
        assert len(new['relations']) == len(prior['annotation']['relations'])
        assert all(p['label'] == 'UNRESOLVED' for p in prior['annotation']['relations'])
        added.extend(p['label'] for p in new['relations'] if p['label'] != 'UNRESOLVED')
    assert diverse.Counter(added) == {'USED_FOR': 19, 'NO_RELATION': 3}
    ref, prior = lookup['2312.03556']; decision = next(d for d in decisions if d['arxivId'] == ref['arxivId'])
    assert all(p['label'] == 'UNRESOLVED' for p in diverse.revision(prior, ref, decision, parent)['relations'] if p['tail'] == 'e8')
    ref, prior = lookup['2503.00416']; new = diverse.revision(prior, ref, decisions[-1], parent)
    assert all(p['label'] == 'UNRESOLVED' for p in new['relations'] if p['head'] in ('e4', 'e5') and p['tail'] == 'e11')


@pytest.mark.parametrize('fault', ['source_hash', 'receipt_hash', 'invented_quote', 'missing_negative_basis', 'resolved_pair', 'duplicate_pair'])
def test_invalid_or_previously_known_judgments_fail(fault):
    parent, decisions, lookup = inputs(); decision = copy.deepcopy(decisions[-1]); ref, prior = lookup[decision['arxivId']]; prior = copy.deepcopy(prior)
    if fault == 'source_hash': decision['textSha256'] = '0'*64
    elif fault == 'receipt_hash': decision['upstreamReceiptSha256'] = '0'*64
    elif fault == 'invented_quote': decision['groups'][0]['supportExcerpt'] = 'fabricated evidence'
    elif fault == 'missing_negative_basis': decision['groups'][-1].pop('negativeBasis')
    elif fault == 'resolved_pair': next(p for p in prior['annotation']['relations'] if p['head'] == 'e1' and p['tail'] == 'e3')['label'] = 'USED_FOR'
    else: decision['groups'].append(copy.deepcopy(decision['groups'][0]))
    with pytest.raises(ValueError): diverse.revision(prior, ref, decision, parent)


def test_no_overwrite_or_out_of_dataset_write(tmp_path):
    with pytest.raises(FileExistsError): diverse.build(Path('unused'), Path('unused'), tmp_path)
    with patch.object(diverse.c, 'ROOT', tmp_path/'separate_workspace'):
        with pytest.raises(ValueError, match='outside datasets'): diverse.build(Path('unused'), Path('unused'), tmp_path/'new')
    assert list(tmp_path.iterdir()) == []
