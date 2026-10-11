import copy
import csv
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import review_v2_evidence_pilot as v


def sources():
    config = v.pilot.read(v.CONTRACT); folder = v.c.ROOT/config['pilot']
    return (v.c.read_jsonl(folder/'references.jsonl'), v.c.read_jsonl(folder/'inherited_receipts.jsonl'),
            v.pilot.read(v.DECISIONS)['documents'])


@pytest.mark.parametrize('index', range(12))
def test_each_source_decision_is_bound_and_preserves_literal_inventory(index):
    refs, old, decisions = sources(); before = copy.deepcopy(old[index])
    annotation, supports = v.revise(refs[index], old[index], decisions[index])
    assert old[index] == before and annotation['entities'] == before['annotation']['entities']
    assert not v.c.validate_response(annotation, refs[index])
    assert len(annotation['relations']) == len(before['annotation']['relations'])
    assert all(not v.c.span_errors(s, refs[index]['text']) for group in supports.values() for s in group['predicateSpans'])


@pytest.mark.parametrize('fault', ['hash', 'receipt', 'excerpt', 'negative_basis', 'coverage', 'duplicate', 'type', 'indirect_role'])
def test_decisions_fail_closed(fault):
    refs, old, decisions = sources(); ref, prior, decision = refs[6], old[6], copy.deepcopy(decisions[6])
    if fault == 'hash': decision['textSha256'] = '0'*64
    elif fault == 'receipt': decision['upstreamReceiptSha256'] = '0'*64
    elif fault == 'excerpt': decision['groups'][0]['predicateExcerpts'] = ['fabricated source predicate']
    elif fault == 'negative_basis': decision['groups'][3].pop('negativeBasis')
    elif fault == 'coverage': decision['groups'].pop(0)
    elif fault == 'duplicate': decision['groups'].append(copy.deepcopy(decision['groups'][0]))
    elif fault == 'type': decision['groups'][0]['label'] = 'EVALUATED_ON'
    elif fault == 'indirect_role': decision['groups'][3]['taskRole'] = 'downstream_application'
    with pytest.raises(ValueError): v.revise(ref, prior, decision)


def test_role_attribution_regressions_and_conservation():
    refs, old, decisions = sources(); after = {}
    for ref, prior, decision in zip(refs, old, decisions):
        annotation, support = v.revise(ref, prior, decision)
        for p in annotation['relations']: after[(ref['arxivId'], p['head'], p['tail'])] = p['label']
    assert after['2107.03374', 'e4', 'e3'] == 'UNRESOLVED'  # Distinct production actor.
    assert after['2107.03374', 'e2', 'e3'] == 'UNRESOLVED'
    assert after['2107.03374', 'e9', 'e5'] == 'EVALUATED_ON'  # Separately reported strategy result.
    assert after['1910.12770', 'e3', 'e5'] == after['1910.12770', 'e3', 'e8'] == 'UNRESOLVED'
    assert after['2503.01309', 'e2', 'e10'] == after['2503.01309', 'e9', 'e13'] == 'UNRESOLVED'
    assert after['2503.03790', 'e11', 'e14'] == 'NO_RELATION'
    assert after['2312.03556', 'e6', 'e8'] == after['2010.01057', 'e5', 'e10'] == 'UNRESOLVED'
    assert len(after) == 499 and sum(label != 'UNRESOLVED' for label in after.values()) == 85


def test_raw_sources_supply_provenance_without_guessing_missing_fields():
    refs, _, _ = sources(); config = v.pilot.read(v.CONTRACT)
    for arxiv, repair in config['sourceRepairs'].items():
        ref = next(r for r in refs if r['arxivId'] == arxiv); original = copy.deepcopy(ref)
        sidecar = v.provenance(ref, repair)
        assert ref == original and sidecar['rawSourceVerified']
        assert all(value is None for value in sidecar['originalFieldsNotBackfilled'].values())
        bad = copy.deepcopy(ref); bad['text'] += ' fabricated'
        with pytest.raises(ValueError): v.provenance(bad, repair)


def test_real_build_guarded_read_scope_receipts_and_audit_exports(tmp_path):
    with pytest.raises(ValueError): v.build(tmp_path/'outside')
    with tempfile.TemporaryDirectory(prefix='pytest-v2-semantic-', dir=v.c.ROOT/'kg_datasets/dblp') as sandbox:
        output = Path(sandbox)/'revision'
        with patch.object(v.c, 'read_jsonl', wraps=v.c.read_jsonl) as reads:
            summary = v.build(output)
        config = v.pilot.read(v.CONTRACT); pilot_config = v.pilot.read(v.pilot.CONTRACT)
        assert {call.args[0] for call in reads.call_args_list} == {
            v.c.ROOT/config['pilot']/'references.jsonl', v.c.ROOT/config['pilot']/'inherited_receipts.jsonl',
            v.c.ROOT/pilot_config['splitMetadata']}
        assert summary['revisedSupport'] == {'EVALUATED_ON': 17, 'UNRESOLVED': 414, 'USED_FOR': 63, 'NO_RELATION': 5}
        assert summary['withdrawnToUnresolved'] == 19 and summary['newlyResolvedPairs'] == 2
        assert summary['NEREligibleDocuments'] == 8 and summary['candidateEligibleRelationPairs'] == 57
        assert not summary['trainingExecuted'] and not summary['testContentParsed']
        assert summary['priorityQueueAdjudicated'] == 12
        assert all(not v.c.validate_receipt(r, r['reference']) for r in v.c.read_jsonl(output/'reviewed_receipts.jsonl'))
        assert all(not r['candidateEligible'] for r in v.c.read_jsonl(output/'change_ledger.jsonl') if r['newLabel'] == 'UNRESOLVED')
        with (output/'priority_adjudications.csv').open(encoding='utf-8-sig', newline='') as stream:
            queue = list(csv.DictReader(stream))
        ranking = next(q for q in queue if q['arxiv_id'] == '1910.12770' and q['tail_entity_id'] == 'e4')
        assert ranking['headText'] == 'self-supervised representation learning' and ranking['taskRole'] == 'training_proxy'
        manifest = v.g.verified_files(output)
        assert manifest['kind'] == 'real_artifact_visualization_not_original_console_ui'
        with pytest.raises(FileExistsError): v.build(output)
