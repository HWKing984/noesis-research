import copy
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import complete_v2_evidence_pilot as v


def sources():
    folder = v.c.ROOT/v.pilot.read(v.CONTRACT)['parent']
    return (v.c.read_jsonl(folder/'references.jsonl'), v.c.read_jsonl(folder/'reviewed_receipts.jsonl'),
            v.c.read_jsonl(folder/'change_ledger.jsonl'), {d['arxivId']: d for d in v.pilot.read(v.DECISIONS)['documents']})


@pytest.mark.parametrize('index', range(12))
def test_rebuild_preserves_all_judgments_by_literal_spans(index):
    refs, old, ledger, decisions = sources(); ref, prior = refs[index], old[index]; snapshot = copy.deepcopy(prior)
    annotation, rows, mapping = v.complete(ref, prior, [r for r in ledger if r['arxivId'] == ref['arxivId']], decisions.get(ref['arxivId']))
    assert prior == snapshot and not v.c.validate_response(annotation, ref)
    assert set((r['head'], r['tail']) for r in annotation['relations']) == set(v.c.candidate_pairs(annotation['entities']))
    assert all(r['label'] == 'UNRESOLVED' and not r['candidateEligible'] for r in rows if r['newCandidate'])
    new = {e['entityId']: e for e in annotation['entities']}
    remap = {m['oldId']: m['newId'] for m in mapping}
    for entity in prior['annotation']['entities']: assert v.anchor(entity) == v.anchor(new[remap[entity['entityId']]])
    inherited = {(r['priorHeadId'], r['priorTailId']): r for r in rows if not r['newCandidate']}
    for pair in prior['annotation']['relations']:
        row = inherited[pair['head'], pair['tail']]
        assert row['label'] == pair['label'] and row['evidence'] == pair['evidence']
    if ref['arxivId'] in decisions:
        assert len(rows) > len(prior['annotation']['relations']) and any(m['oldId'] != m['newId'] for m in mapping)
        assert len(annotation['entities']) == len(prior['annotation']['entities'])+len(decisions[ref['arxivId']]['additions'])


@pytest.mark.parametrize('fault', ['hash', 'receipt', 'unknown_occurrence', 'negative_occurrence', 'overlap', 'label', 'missing_document', 'ledger', 'predicate', 'role'])
def test_source_and_export_fail_closed(fault):
    refs, old, ledger, decisions = sources(); ref, prior = refs[0], old[0]
    decision = copy.deepcopy(decisions[ref['arxivId']]); rows = copy.deepcopy([r for r in ledger if r['arxivId'] == ref['arxivId']])
    if fault == 'hash': decision['textSha256'] = '0'*64
    elif fault == 'receipt': decision['upstreamReceiptSha256'] = '0'*64
    elif fault == 'unknown_occurrence': decision['additions'][0]['occurrence'] = 999
    elif fault == 'negative_occurrence': decision['additions'][0]['occurrence'] = -1
    elif fault == 'overlap': decision['additions'].append(copy.deepcopy(decision['additions'][0]))
    elif fault == 'label': decision['additions'][0]['label'] = 'METRIC'
    elif fault == 'missing_document': decision = None
    elif fault == 'ledger': rows[0]['reviewedReceiptSha256'] = '0'*64
    elif fault == 'predicate': rows[0]['support']['predicateSpans'][0]['text'] = 'invented'
    elif fault == 'role': rows[0]['support']['taskRole'] = 'training_proxy'
    with pytest.raises(ValueError): v.complete(ref, prior, rows, decision)


def reviewed(ref, annotation):
    metadata = {'provider': 'test', 'model': 'test', 'promptSha256': 'a'*64, 'sourceArtifactSha256': 'b'*64, 'createdAt': '2026-10-10T00:00:00+00:00'}
    initial = v.c.make_receipt(annotation, ref, metadata)
    annotation = copy.deepcopy(annotation); annotation['reviewOfSha256'] = initial['contentSha256']
    return v.c.make_receipt(annotation, ref, metadata, previous=initial)


@pytest.mark.parametrize('fault', [None, 'negative_admission', 'silent_omission', 'support', 'duplicate', 'missing', 'fake_span', 'role'])
def test_export_preserves_roles_and_never_accepts_scoped_negatives(fault):
    refs, old, ledger, _ = sources(); ref, prior = refs[6], old[6]
    annotation, rows, _ = v.complete(ref, prior, [r for r in ledger if r['arxivId'] == ref['arxivId']], None)
    receipt = reviewed(ref, annotation)
    for row in rows: row['sourceReceiptSha256'] = receipt['contentSha256']
    if fault == 'negative_admission': next(r for r in rows if r['label'] == 'NO_RELATION')['candidateEligible'] = True
    elif fault == 'silent_omission': next(r for r in rows if r['candidateEligible'])['candidateEligible'] = False
    elif fault == 'support': next(r for r in rows if r['candidateEligible'])['support'].pop('supportGroup')
    elif fault == 'duplicate': rows.append(copy.deepcopy(rows[0]))
    elif fault == 'missing': rows.pop()
    elif fault == 'fake_span': next(r for r in rows if r['candidateEligible'])['support']['predicateSpans'][0]['text'] = 'fake'
    elif fault == 'role': next(r for r in rows if r['candidateEligible'])['support']['taskRole'] = 'not_applicable'
    if fault:
        with pytest.raises(ValueError): v.candidate_rows(ref, receipt, rows)
    else:
        ner, pairs = v.candidate_rows(ref, receipt, rows)
        assert len(pairs) == 22 and all(r['label'] == 'USED_FOR' and r['trainingAuthorized'] is False for r in pairs)
        assert {'component_operation', 'downstream_application'} == {r['taskRole'] for r in pairs}
        assert all(r['supportGroup'] and r['attribution'] and r['predicateSpans'] for r in pairs)


def test_actual_bundle_counts_package_and_read_scope(tmp_path):
    with pytest.raises(ValueError): v.build(tmp_path/'outside')
    with tempfile.TemporaryDirectory(prefix='pytest-v2-completion-', dir=v.c.ROOT/'kg_datasets/dblp') as sandbox:
        output = Path(sandbox)/'completion'
        with patch.object(v.c, 'read_jsonl', wraps=v.c.read_jsonl) as reads:
            summary = v.build(output)
        parent = v.c.ROOT/v.pilot.read(v.CONTRACT)['parent']; config = v.pilot.read(v.pilot.CONTRACT)
        assert {call.args[0] for call in reads.call_args_list} == {
            parent/'references.jsonl', parent/'reviewed_receipts.jsonl', parent/'change_ledger.jsonl',
            parent/'source_provenance_sidecars.jsonl', v.c.ROOT/config['splitMetadata']}
        assert summary['NERCandidateDocuments'] == 12 and summary['addedEntityMentions'] == 26
        assert summary['entityMentions'] == 177 and summary['candidatePairs'] > 499
        assert summary['RECandidateSupport'] == {'EVALUATED_ON': 17, 'USED_FOR': 63}
        assert summary['quarantinedNegativePairs'] == 5 and summary['relationSupport']['NO_RELATION'] == 5
        assert summary['sourcePapersByCandidateClass']['EVALUATED_ON'] == 5
        assert not summary['trainingExecuted'] and not summary['testContentParsed']
        assert len(list((output/'audit_sources').glob('*.html'))) == 2
        v.g.verified_files(output)
        for ref, receipt in zip(v.c.read_jsonl(output/'references.jsonl'), v.c.read_jsonl(output/'reviewed_receipts.jsonl')):
            assert not v.c.validate_receipt(receipt, ref)
        with pytest.raises(FileExistsError): v.build(output)


def test_real_tokenization_roundtrip_and_evidence_not_features():
    import train_course_ner as ner
    import train_course_relation as relation
    tokenizer = relation.prepare_tokenizer(v.c.ROOT/'kg_datasets/models/scibert_24f92d32')
    refs, old, ledger, decisions = sources()
    for ref, prior in zip(refs, old):
        annotation, rows, _ = v.complete(ref, prior, [r for r in ledger if r['arxivId'] == ref['arxivId']], decisions.get(ref['arxivId']))
        receipt = reviewed(ref, annotation)
        for row in rows: row['sourceReceiptSha256'] = receipt['contentSha256']
        nr, pairs = v.candidate_rows(ref, receipt, rows)
        encoded = ner.encode_row(tokenizer, nr, 512)
        decoded = ner.decode_bio([0 if label == -100 else label for label in encoded['features']['labels']], encoded['offsets'], ref['text'])
        assert {v.anchor(e) for e in decoded['entities']} == {v.anchor(e) for e in annotation['entities']}
        for row in pairs:
            record = relation.encode_pair(tokenizer, row, 512)
            assert not {'taskRole', 'supportGroup', 'predicateSpans', 'attribution'} & record['features'].keys()
            without = {k: value for k, value in row.items() if k not in ('taskRole', 'supportGroup', 'predicateSpans', 'attribution', 'negativeBasis')}
            assert relation.encode_pair(tokenizer, without, 512) == record
