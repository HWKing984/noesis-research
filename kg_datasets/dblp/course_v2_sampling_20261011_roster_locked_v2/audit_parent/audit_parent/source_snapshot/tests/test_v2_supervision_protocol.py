import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import finalize_v2_supervision as v


def sources():
    parent = v.ROOT/v.read(v.CONTRACT)['parent']
    return (v.rows(parent/'references.jsonl'), v.rows(parent/'reviewed_receipts.jsonl'), v.rows(parent/'relation_ledger.jsonl'),
            {d['arxivId']: d for d in v.read(v.DECISIONS)['documents']})


@pytest.mark.parametrize('index', range(12))
def test_review_preserves_all_but_five_negatives_and_three_evidence_pairs(index):
    refs, receipts, ledger, decisions = sources(); ref, prior = refs[index], receipts[index]
    before = [r for r in ledger if r['arxivId'] == ref['arxivId']]; snapshot = copy.deepcopy((prior, before))
    annotation, after = v.revise(ref, prior, before, decisions.get(ref['arxivId']))
    assert (prior, before) == snapshot and annotation['entities'] == prior['annotation']['entities']
    for old, row in zip(before, after):
        assert row['protocolPriorLabel'] == old['label'] and row['protocolPriorEvidence'] == old['evidence']
        if v.key(row) in v.NEGATIVES:
            assert row['label'] == 'UNRESOLVED' and row['evidence'] is None and not row['candidateEligible']
        else: assert all(row[k] == old[k] for k in ('label', 'evidence', 'reason'))
        if v.key(row) in v.COREFERENCE:
            assert row['support']['relationEvidenceLevel'] == 'discourse_inferred'
            for link in row['support']['coreferenceEvidence']:
                span = link['triggerSpan']; assert ref['text'][span['start']:span['end']] == span['text']
                assert len(span['text']) <= 12 and link['resolvedEntityId'] in link['referentAliasIds']


@pytest.mark.parametrize('fault', ['hash', 'receipt', 'positive_withdrawal', 'duplicate_withdrawal', 'invented_trigger', 'unknown_referent', 'wrong_referent', 'oracle_direct', 'alias_outside_context', 'cross_sentence_direct'])
def test_decisions_fail_closed(fault):
    refs, receipts, ledger, decisions = sources()
    arxiv = '1903.10404' if fault in ('hash', 'receipt', 'positive_withdrawal', 'duplicate_withdrawal') else '2107.03374'
    index = next(i for i, r in enumerate(refs) if r['arxivId'] == arxiv); decision = copy.deepcopy(decisions[arxiv])
    if fault == 'hash': decision['textSha256'] = '0'*64
    elif fault == 'receipt': decision['upstreamReceiptSha256'] = '0'*64
    elif fault == 'positive_withdrawal': decision['withdrawNegativePairs'] = [['e2', 'e4']]
    elif fault == 'duplicate_withdrawal': decision['withdrawNegativePairs'].append(decision['withdrawNegativePairs'][0])
    elif fault == 'invented_trigger': decision['coreference'][0]['links'][0]['trigger'] = 'this invented method'
    elif fault == 'unknown_referent': decision['coreference'][0]['links'][0]['resolvedEntityId'] = 'e999'
    elif fault == 'wrong_referent': decision['coreference'][0]['links'][0]['resolvedEntityId'] = 'e1'
    elif fault == 'oracle_direct': decision['coreference'][0]['relationEvidenceLevel'] = 'direct'
    elif fault == 'alias_outside_context': decision['coreference'][0]['links'][0]['referentAliasIds'] += ['e1']
    elif fault == 'cross_sentence_direct': decision['coreference'][0]['links'][0]['evidenceLevel'] = 'direct'
    with pytest.raises(ValueError): v.revise(refs[index], receipts[index], [r for r in ledger if r['arxivId'] == arxiv], decision)


@pytest.mark.parametrize('conflict', ['group', 'publication', 'version', 'text_hash', 'exposed', 'test_body', 'missing', 'unknown_split'])
def test_metadata_partition_guard(conflict):
    a = {'publicationId': 'paper:a', 'groupId': 'group:a', 'arxivId': '2601.00001v1', 'textSha256': 'a'*64, 'split': 'train'}
    b = {'publicationId': 'paper:b', 'groupId': 'group:b', 'arxivId': '2601.00002', 'textSha256': 'b'*64, 'split': 'test'}
    excluded = []
    if conflict == 'group': b['groupId'] = a['groupId']
    elif conflict == 'publication': b['publicationId'] = a['publicationId']
    elif conflict == 'version': b['arxivId'] = '2601.00001v2'
    elif conflict == 'text_hash': b['textSha256'] = a['textSha256']
    elif conflict == 'exposed': excluded = [b]
    elif conflict == 'test_body': b['text'] = 'sealed text'
    elif conflict == 'missing': del b['groupId']
    elif conflict == 'unknown_split': b['split'] = 'validation-ish'
    with pytest.raises(ValueError): v.validate_partition([a, b], excluded)


def test_fresh_metadata_only_partitions_and_train_exposure_are_allowed():
    a = {'publicationId': 'paper:a', 'groupId': 'group:a', 'split': 'train'}
    b = {'publicationId': 'paper:b', 'groupId': 'group:b', 'split': 'dev'}
    c = {'publicationId': 'paper:c', 'groupId': 'group:c', 'split': 'challenge'}
    assert v.validate_partition([a, b, c], [a]) == {'train': 1, 'dev': 1, 'challenge': 1}


def test_real_build_and_isolated_portable_replay():
    with tempfile.TemporaryDirectory(prefix='pytest-v2-protocol-', dir=v.ROOT/'kg_datasets/dblp') as sandbox:
        output = Path(sandbox)/'bundle'; summary = v.build(output)
        assert summary['relationSupport'] == {'USED_FOR': 68, 'EVALUATED_ON': 17, 'NO_RELATION': 0, 'UNRESOLVED': 599}
        assert summary['RECandidatePairs'] == 85 and summary['fineCoreferencePairs'] == 3 and summary['fineCoreferenceFactChains'] == 2
        assert not summary['evaluationInventoryLocked'] and not summary['trainingExecuted']
        result = v.verify(output); assert result['status'] == 'passed'
        process = subprocess.run([sys.executable, '-I', str(output/'source_snapshot/scripts/finalize_v2_supervision.py'), '--verify', str(output)],
            cwd=sandbox, text=True, capture_output=True, check=True)
        assert json.loads(process.stdout) == result
        with pytest.raises(FileExistsError): v.build(output)
        data = v.read(output/'summary.json'); data['acceptedNegativePairs'] = 5
        import revise_v2_priority as parent
        parent.c.write_json(output/'summary.json', data)
        manifest = v.read(output/'manifest.json'); manifest['filesSha256']['summary.json'] = v.sha(output/'summary.json')
        parent.c.write_json(output/'manifest.json', manifest)
        with pytest.raises(ValueError, match='protocol_summary_counts'): v.verify(output)


def test_missing_junit_does_not_create_partial_output(tmp_path):
    with tempfile.TemporaryDirectory(prefix='pytest-v2-protocol-junit-', dir=v.ROOT/'kg_datasets/dblp') as sandbox:
        output = Path(sandbox)/'bundle'
        with pytest.raises(FileNotFoundError): v.build(output, tmp_path/'missing.xml')
        assert not output.exists()


def test_fine_audit_metadata_never_enters_scibert_features():
    import train_course_relation as relation
    tokenizer = relation.prepare_tokenizer(v.ROOT/'kg_datasets/models/scibert_24f92d32')
    refs, receipts, ledger, decisions = sources()
    for ref, prior in zip(refs, receipts):
        _, revised = v.revise(ref, prior, [r for r in ledger if r['arxivId'] == ref['arxivId']], decisions.get(ref['arxivId']))
        for row in revised:
            if v.key(row) not in v.COREFERENCE: continue
            base = {'sampleId': ref['sampleId'], 'text': ref['text'], 'head': row['head'], 'tail': row['tail'], 'label': row['label']}
            assert relation.encode_pair(tokenizer, base, 512) == relation.encode_pair(tokenizer, base | row['support'], 512)
