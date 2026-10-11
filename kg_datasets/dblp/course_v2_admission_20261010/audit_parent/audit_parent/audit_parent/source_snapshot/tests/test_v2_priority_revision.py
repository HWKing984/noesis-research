import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import revise_v2_priority as v
import verify_v2_priority_bundle as replay


def sources():
    parent = v.c.ROOT/v.pilot.read(v.CONTRACT)['parent']
    return (v.c.read_jsonl(parent/'references.jsonl'), v.c.read_jsonl(parent/'reviewed_receipts.jsonl'),
            v.c.read_jsonl(parent/'relation_ledger.jsonl'), {d['arxivId']: d for d in v.pilot.read(v.DECISIONS)['documents']})


@pytest.mark.parametrize('index', range(12))
def test_priority_scope_preserves_entities_and_nonselected_labels(index):
    refs, old, ledger, decisions = sources(); ref, prior = refs[index], old[index]
    rows = [r for r in ledger if r['arxivId'] == ref['arxivId']]; snapshot = copy.deepcopy((prior, rows))
    annotation, after = v.revise(ref, prior, rows, decisions.get(ref['arxivId']))
    assert (prior, rows) == snapshot and annotation['entities'] == prior['annotation']['entities']
    assert len(after) == len(rows) and not v.c.validate_response(annotation, ref)
    for before, row in zip(rows, after):
        assert row['revisionPriorLabel'] == before['label'] and row['revisionPriorSupport'] == before['support']
        if row['labelChanged']:
            assert row['newCandidate'] and before['label'] == 'UNRESOLVED' and row['label'] == 'USED_FOR'
        else:
            assert row['label'] == before['label'] and row['evidence'] == before['evidence'] and row['reason'] == before['reason']
        if row['label'] == 'NO_RELATION': assert not row['candidateEligible'] and row['support'] == before['support']
        assert all(not v.c.span_errors(s, ref['text']) for s in row['support'].get('predicateSpans', []))
        assert all(not v.c.span_errors(link[k], ref['text']) for link in row['support'].get('coreferenceEvidence', []) for k in ('anaphorSpan', 'antecedentSpan'))


@pytest.mark.parametrize('fault', ['receipt', 'text', 'predicate', 'role', 'label', 'duplicate', 'old_known_target', 'augmentation_role'])
def test_source_decisions_fail_closed(fault):
    refs, old, ledger, decisions = sources(); ref = refs[0]; decision = copy.deepcopy(decisions[ref['arxivId']])
    if fault == 'receipt': decision['upstreamReceiptSha256'] = '0'*64
    elif fault == 'text': decision['textSha256'] = '0'*64
    elif fault == 'predicate': decision['groups'][0]['predicateExcerpts'] = ['Rotation and translation is used to augment training data.']
    elif fault == 'role': decision['groups'][0]['taskRole'] = 'training_augmentation'
    elif fault == 'label': decision['groups'][0]['label'] = 'NO_RELATION'
    elif fault == 'duplicate': decision['groups'].append(copy.deepcopy(decision['groups'][0]))
    elif fault == 'old_known_target': decision['groups'][0]['heads'] = ['e2']; decision['groups'][0]['tails'] = ['e1']
    elif fault == 'augmentation_role': decision['groups'][0]['taskRole'] = 'component_operation'
    with pytest.raises(ValueError): v.revise(ref, old[0], [r for r in ledger if r['arxivId'] == ref['arxivId']], decision)


@pytest.mark.parametrize('fault', ['invented_antecedent', 'duplicate_pair', 'unknown_pair', 'empty_explanation'])
def test_coreference_is_literal_and_evidence_only(fault):
    refs, old, ledger, decisions = sources(); index = next(i for i, r in enumerate(refs) if r['arxivId'] == '2107.03374')
    ref = refs[index]; decision = copy.deepcopy(decisions[ref['arxivId']])
    if fault == 'invented_antecedent': decision['coreference'][0]['links'][0]['antecedentExcerpt'] = 'invented benchmark'
    elif fault == 'duplicate_pair': decision['coreference'].append(copy.deepcopy(decision['coreference'][0]))
    elif fault == 'unknown_pair': decision['coreference'][0]['heads'] = ['e2']
    elif fault == 'empty_explanation': decision['coreference'][0]['links'][0]['explanation'] = ''
    with pytest.raises(ValueError): v.revise(ref, old[index], [r for r in ledger if r['arxivId'] == ref['arxivId']], decision)


def test_real_build_counts_snapshot_and_portable_replay(tmp_path):
    with pytest.raises(ValueError): v.build(tmp_path/'outside')
    with tempfile.TemporaryDirectory(prefix='pytest-v2-priority-', dir=v.c.ROOT/'kg_datasets/dblp') as sandbox:
        output = Path(sandbox)/'revision'; summary = v.build(output)
        assert summary['totalSourcePapersWithEligibleRE'] == summary['parentTotalSourcePapersWithEligibleRE'] == 11
        assert summary['parentLiteralPairsExact'] == 50 and summary['parentLiteralPairsCasefold'] == 49
        assert summary['literalPairsExact'] == 55 and summary['literalPairsCasefold'] == 54
        assert summary['relationSupport'] == {'EVALUATED_ON': 17, 'UNRESOLVED': 594, 'USED_FOR': 68, 'NO_RELATION': 5}
        assert summary['RECandidatePairs'] == 85 and summary['coreferenceMentionPairs'] == 3 and summary['supportGroups'] == 29
        assert not summary['trainingExecuted'] and not summary['testContentParsed']
        result = replay.verify(output)
        assert result['status'] == 'passed' and result['assertionCategories'] >= 35
        script = output/'source_snapshot/scripts/verify_v2_priority_bundle.py'
        process = subprocess.run([sys.executable, '-I', str(script), str(output)], cwd=sandbox, text=True, capture_output=True, check=True)
        assert json.loads(process.stdout) == result
        assert (output/'source_snapshot/scripts/train_course_relation.py').read_bytes() == (v.c.ROOT/'scripts/train_course_relation.py').read_bytes()
        assert 'failures="1"' in (output/'check_history/v2_entity_completion_preflight_20261010.xml').read_text(encoding='utf-8')
        # A re-signed erroneous summary still fails the semantic-independent data assertion.
        data = v.pilot.read(output/'summary.json'); data['totalSourcePapersWithEligibleRE'] = 10
        v.c.write_json(output/'summary.json', data)
        manifest = v.pilot.read(output/'manifest.json'); manifest['filesSha256']['summary.json'] = v.c.file_sha256(output/'summary.json')
        v.c.write_json(output/'manifest.json', manifest)
        with pytest.raises(ValueError, match='total_source_papers_eleven'): replay.verify(output)
        with pytest.raises(FileExistsError): v.build(output)


def test_missing_check_file_creates_no_partial_output(tmp_path):
    with tempfile.TemporaryDirectory(prefix='pytest-v2-junit-guard-', dir=v.c.ROOT/'kg_datasets/dblp') as sandbox:
        output = Path(sandbox)/'revision'
        with pytest.raises(FileNotFoundError): v.build(output, tmp_path/'not_yet_written.xml')
        assert not output.exists()


def test_new_export_metadata_does_not_enter_tokenizer_features():
    import train_course_relation as relation
    tokenizer = relation.prepare_tokenizer(v.c.ROOT/'kg_datasets/models/scibert_24f92d32')
    refs, old, ledger, decisions = sources()
    for ref, prior in zip(refs, old):
        annotation, rows = v.revise(ref, prior, [r for r in ledger if r['arxivId'] == ref['arxivId']], decisions.get(ref['arxivId']))
        changed = [r for r in rows if r['labelChanged'] or r['supportChanged']]
        for row in changed:
            candidate = {'sampleId': ref['sampleId'], 'text': ref['text'], 'head': row['head'], 'tail': row['tail'], 'label': row['label']}
            extra = candidate | row['support']
            assert relation.encode_pair(tokenizer, candidate, 512) == relation.encode_pair(tokenizer, extra, 512)
