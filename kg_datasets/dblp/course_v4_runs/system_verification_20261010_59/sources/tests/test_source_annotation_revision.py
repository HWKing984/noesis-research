"""Only explicit evidence changes; no negative filling, NER edits or historical result edits."""
import copy
import hashlib
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import revise_source_annotations as revision
from compile_abstract_annotations import annotate


@pytest.fixture
def source():
    c = revision.c; text = 'Graph method performs image classification on the Bench dataset.'
    ref = {'sampleId': 'sample-'+'0'*20, 'arxivId': 'fixture', 'split': 'dev',
           'textKind': 'abstract', 'text': text, 'textSha256': c.canonical_sha256(text)}
    ann = annotate({'mentions': {'METHOD': ['Graph method'], 'TASK': ['image classification'], 'DATASET': ['Bench']}, 'entityStatus': 'complete'}, ref)
    meta = {'provider': 'fixture', 'model': 'fixture', 'promptSha256': 'a'*64, 'sourceArtifactSha256': 'b'*64, 'createdAt': '2026-10-10T00:00:00+00:00'}
    receipt = c.make_receipt(ann, ref, meta)
    group = {'heads': ['e1'], 'tails': ['e2'], 'label': 'USED_FOR', 'supportExcerpt': text,
             'reason': 'The sentence explicitly says this method performs the task.'}
    decision = {'arxivId': 'fixture', 'textSha256': ref['textSha256'], 'upstreamReceiptSha256': receipt['contentSha256'],
                'groups': [group], 'deferred': 'No explicit evaluation on Bench is given.'}
    return ref, receipt, decision


def test_explicit_positive_preserves_ner_unknowns_and_original(source):
    ref, prior, decision = source; frozen = copy.deepcopy(prior)
    response = revision.response(prior, ref, decision, revision.read(revision.RELATION_CONTRACT))
    assert response['entities'] == prior['annotation']['entities']
    assert [p['label'] for p in response['relations']] == ['USED_FOR', 'UNRESOLVED']
    assert prior == frozen and not revision.c.validate_response(response, ref)


@pytest.mark.parametrize('field', ['textSha256', 'upstreamReceiptSha256', 'arxivId'])
def test_source_or_receipt_drift_rejected(source, field):
    ref, prior, decision = source; decision[field] = 'wrong'
    with pytest.raises(ValueError): revision.response(prior, ref, decision, revision.read(revision.RELATION_CONTRACT))


@pytest.mark.parametrize('change', ['absent_quote', 'empty_reason', 'empty_heads', 'bad_type', 'duplicate', 'no_negative_basis'])
def test_unbound_or_incompatible_evidence_rejected(source, change):
    ref, prior, decision = source; group = decision['groups'][0]
    if change == 'absent_quote': group['supportExcerpt'] = 'absent'
    if change == 'empty_reason': group['reason'] = ''
    if change == 'empty_heads': group['heads'] = []
    if change == 'bad_type': group['label'] = 'EVALUATED_ON'
    if change == 'duplicate': decision['groups'].append(copy.deepcopy(group))
    if change == 'no_negative_basis': group['label'] = 'NO_RELATION'
    with pytest.raises(ValueError): revision.response(prior, ref, decision, revision.read(revision.RELATION_CONTRACT))


def test_existing_label_not_silently_retracted(source):
    ref, prior, decision = source
    prior['annotation'] = revision.response(prior, ref, decision, revision.read(revision.RELATION_CONTRACT))
    decision['groups'][0].update(label='NO_RELATION', negativeBasis='explicit_argument_role_contrast')
    with pytest.raises(ValueError, match='retraction'):
        revision.response(prior, ref, decision, revision.read(revision.RELATION_CONTRACT))


def test_evidenced_negative_leaves_other_pairs_unknown(source):
    _, prior, _ = source
    text = 'Graph method performs image classification; Baseline method instead reconstructs tokens.'
    ref = {'sampleId': 'sample-'+'1'*20, 'arxivId': 'negative-fixture', 'split': 'dev',
           'textKind': 'abstract', 'text': text, 'textSha256': hashlib.sha256(text.encode()).hexdigest()}
    annotation = annotate({'mentions': {'METHOD': ['Graph method', 'Baseline method'],
                                        'TASK': ['reconstructs tokens']}, 'entityStatus': 'complete'}, ref)
    receipt = revision.c.make_receipt(annotation, ref, prior['generation'])
    decision = {'arxivId': ref['arxivId'], 'textSha256': ref['textSha256'],
                'upstreamReceiptSha256': receipt['contentSha256'], 'deferred': 'Other pairs are not judged.',
                'groups': [{'heads': ['e1'], 'tails': ['e3'], 'label': 'NO_RELATION',
                            'supportExcerpt': text, 'negativeBasis': 'explicit_argument_role_contrast',
                            'reason': 'The source assigns reconstruction to the baseline, not Graph method.'}]}
    response = revision.response(receipt, ref, decision, revision.read(revision.RELATION_CONTRACT))
    assert response['entities'] == annotation['entities']
    assert [p['label'] for p in response['relations']] == ['NO_RELATION', 'UNRESOLVED']
    assert response['relations'][1]['evidence'] is None
    assert not revision.c.validate_response(response, ref)


def test_output_preserves_existing_and_stays_within_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(revision.c, 'ROOT', tmp_path)
    with pytest.raises(FileExistsError): revision.checked_output(tmp_path)
    with pytest.raises(ValueError): revision.checked_output(tmp_path/'outside')
    revision.checked_output(tmp_path/'kg_datasets/dblp/new')


def test_real_cohort_and_no_reserved_test_reads():
    from unittest.mock import patch
    with patch.object(revision.c, 'read_jsonl', wraps=revision.c.read_jsonl) as reads:
        config, _, refs, receipts = revision.load_sources()
    assert len(refs) == len(receipts) == 8 and config['trainingAllowed'] is False
    assert not any('test' in call.args[0].name for call in reads.call_args_list)


@pytest.fixture
def copied_build_inputs(monkeypatch):
    config, manifest, refs, receipts = revision.load_sources()
    root = revision.c.ROOT
    with TemporaryDirectory(prefix='source_revision_test_', dir=root/'kg_datasets/dblp') as temporary:
        work = Path(temporary); copied = work/'source'
        shutil.copytree(root/config['source'], copied)
        decisions = work/'decisions.json'; reviews = work/'reviews.json'
        for path, name in ((decisions, 'supplement_relation_decisions_20261010_59.json'),
                           (reviews, 'supplement_relation_reviews_20261010_59.json')):
            shutil.copy2(root/'annotations/course_v4'/name, path)
        pinned = copy.deepcopy(config); pinned['source'] = copied.relative_to(root).as_posix()
        monkeypatch.setattr(revision, 'load_sources', lambda: (pinned, manifest, refs, receipts))
        # These tests exercise file binding, not model tokenization or inference.
        monkeypatch.setattr(revision.ner, 'encode_row', lambda _, doc, __: {
            'offsets': [(e['start'], e['end']) for e in doc['entities']],
            'features': {'labels': [revision.c.CONFIG['bioLabels'].index('B-'+e['label']) for e in doc['entities']]}})
        monkeypatch.setattr(revision.relation, 'encode_pair', lambda *_: {'features': {'input_ids': [1]}})
        yield decisions, reviews, copied, work/'output'


@pytest.mark.parametrize('changed_file', ['decisions', 'source_references'])
def test_inputs_changed_during_tokenizer_setup_rejected(copied_build_inputs, monkeypatch, changed_file):
    decisions, reviews, copied, output = copied_build_inputs
    target = decisions if changed_file == 'decisions' else copied/'references.jsonl'
    old_hash = revision.c.file_sha256(target)

    def change_after_semantic_read(_):
        target.write_bytes(target.read_bytes()+b'\n')
        return object()

    monkeypatch.setattr(revision.relation, 'prepare_tokenizer', change_after_semantic_read)
    with pytest.raises(ValueError, match='Early-pinned input drift'):
        revision.build(decisions, reviews, output)
    assert revision.c.file_sha256(target) != old_hash
    assert revision.read(output/'failure.json')['status'] == 'failed_no_fallback'
    assert not (output/'manifest.json').exists()
    assert not (output/'summary.json').exists()
