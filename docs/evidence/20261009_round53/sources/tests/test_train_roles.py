"""One source-bound role check: no absence negatives, entity mutation or test reads."""
import copy
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import enrich_train_roles as role


def test_role_revision_binds_training_evidence_and_keeps_unknowns():
    with patch.object(role.c, 'read_jsonl', wraps=role.c.read_jsonl) as reads:
        config, parent, refs, receipts = role.load_sources()
    assert len(refs) == 70 and len(config['revisionCohort']) == 11
    assert not any('test' in call.args[0].name or 'dev' in call.args[0].name for call in reads.call_args_list)
    decisions = role.read(role.c.ROOT/'annotations/course_v4/abstract_role_decisions_20261009_53.json')['documents']
    lookup = {ref['arxivId']: (ref, prior) for ref, prior in zip(refs, receipts)}
    for decision in decisions:
        ref, prior = lookup[decision['arxivId']]; revised = role.response(prior, ref, decision, parent)
        assert all(revised[k] == prior['annotation'][k] for k in role.NER_FIELDS)
        assert len(revised['relations']) == len(prior['annotation']['relations'])
    ref, prior = lookup['1903.10404']; decision = decisions[0]
    revised = role.response(prior, ref, decision, parent)
    assert next(p['label'] for p in revised['relations'] if p['head'] == 'e10') == 'UNRESOLVED'
    assert sum(p['label'] == 'NO_RELATION' for p in revised['relations']) == 3
    bad = copy.deepcopy(decision); bad['groups'][1].pop('negativeBasis')
    with pytest.raises(ValueError): role.response(prior, ref, bad, parent)
    bad = copy.deepcopy(decision); bad['groups'][0]['supportExcerpt'] = 'invented source quote'
    with pytest.raises(ValueError): role.response(prior, ref, bad, parent)
    for field in ('textSha256', 'upstreamReceiptSha256'):
        bad = copy.deepcopy(decision); bad[field] = '0'*64
        with pytest.raises(ValueError): role.response(prior, ref, bad, parent)
    bad = copy.deepcopy(prior); next(p for p in bad['annotation']['relations'] if p['head'] == 'e1')['label'] = 'USED_FOR'
    with pytest.raises(ValueError): role.response(bad, ref, decision, parent)
    with pytest.raises(FileExistsError): role.build(Path('unused'), Path('unused'), Path(__file__).parent.resolve())
