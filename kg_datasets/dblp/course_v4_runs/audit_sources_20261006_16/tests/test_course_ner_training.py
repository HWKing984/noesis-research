"""Offline contract tests; not model training/evaluation evidence."""
import sys
import json
import shutil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import course_weak as c
import train_course_ner as ner


def entity(text, literal, label='METHOD'):
    start = text.index(literal)
    return {'start': start, 'end': start + len(literal), 'text': literal, 'label': label}


def test_unicode_bio_decode_and_special_tokens():
    text = '😀 BERT for NER'
    result = ner.decode_bio([0, 1, 2, 0, 3, 0], [(0, 0), (2, 4), (4, 6), (7, 10), (11, 14), (0, 0)], text)
    assert result['entities'] == [entity(text, 'BERT'), entity(text, 'NER', 'TASK')]
    assert result['invalidTransitions'] == 0


@pytest.mark.parametrize('labels,expected,bad', [
    ([2], [], 1), ([1], ['BERT'], 0), ([0], [], 0),
])
def test_orphan_inside_is_not_silently_promoted(labels, expected, bad):
    result = ner.decode_bio(labels, [(0, 4)], 'BERT')
    assert [e['text'] for e in result['entities']] == expected
    assert result['invalidTransitions'] == bad


def test_type_switch_discards_orphan_inside():
    result = ner.decode_bio([1, 4], [(0, 4), (5, 8)], 'BERT NER')
    assert result['entities'] == [entity('BERT NER', 'BERT')]
    assert result['invalidTransitions'] == 1


@pytest.mark.parametrize('labels,offsets', [([1], []), ([7], [(0, 1)]), ([0], [(1, 3)]), ([0], [(0, 2)])])
def test_invalid_decode_rejected(labels, offsets):
    with pytest.raises(ValueError):
        ner.decode_bio(labels, offsets, 'x')


def test_non_whitespace_gap_cannot_be_joined_as_entity():
    result = ner.decode_bio([1, 2], [(0, 1), (3, 4)], 'aXXb')
    assert [e['text'] for e in result['entities']] == ['a']
    assert result['invalidTransitions'] == 1


def test_dictionary_uses_only_supplied_train_spans_and_longest_match():
    text = 'Graph Neural Network'
    rows = [{'text': text, 'entities': [entity(text, text)]},
            {'text': 'Neural Network', 'entities': [entity('Neural Network', 'Neural Network')]}]
    lexicon = ner.make_dictionary(rows)
    assert ner.dictionary_predict(text, lexicon) == [entity(text, text)]
    assert ner.dictionary_predict('unseen DATASET', lexicon) == []
    assert ner.dictionary_predict('XGraph Neural NetworkX', lexicon) == []


def test_dictionary_ambiguous_types_are_not_assigned_arbitrarily():
    rows = [{'text': 'Foo', 'entities': [entity('Foo', 'Foo')]},
            {'text': 'Foo', 'entities': [entity('Foo', 'Foo', 'DATASET')]}]
    assert ner.make_dictionary(rows) == []


def test_smoke_selection_is_train_only_deterministic_with_class_coverage():
    rows = [{'sampleId': str(i), 'text': name, 'entities': [entity(name, name, label)]}
            for i, (name, label) in enumerate([('BERT', 'METHOD'), ('NER', 'TASK'), ('IMDb', 'DATASET')])]
    selected = ner.select_smoke(rows, 3, 7)
    assert selected == ner.select_smoke(rows, 3, 7)
    assert {e['label'] for row in selected for e in row['entities']} == set(c.CONFIG['entityLabels'])
    assert ner.select_smoke(rows[:1], 1, 7)[0]['sampleId'] == '0'
    with pytest.raises(ValueError):
        ner.select_smoke(rows, 4, 7)


def test_model_manifest_rejects_unsafe_paths_and_changed_bytes(tmp_path):
    c.write_json(tmp_path / 'manifest.json', {'filesSha256': {'../outside': '0' * 64}})
    with pytest.raises(ValueError, match='Unsafe'):
        ner.verify_files(tmp_path)
    (tmp_path / 'weights').write_bytes(b'original')
    c.write_json(tmp_path / 'manifest.json', {'filesSha256': {'weights': c.file_sha256(tmp_path / 'weights')}})
    assert ner.verify_files(tmp_path)['filesSha256']['weights'] == c.file_sha256(tmp_path / 'weights')
    (tmp_path / 'weights').write_bytes(b'changed')
    with pytest.raises(ValueError, match='changed'):
        ner.verify_files(tmp_path)


def test_empty_predictions_do_not_fabricate_perfect_scores():
    scores = ner.score_rows([{'sampleId': 'x', 'text':'', 'entities': []}], [[]])
    assert scores['micro']['f1'] is None
    assert scores['perClass']['DATASET']['reference'] == 0


def test_train_smoke_scores_are_never_labelled_held_out():
    scores = ner.score_rows([{'sampleId': 'x', 'text':'', 'entities': []}], [[]],
                            evaluation_target='in_sample_ai_reference_agreement_not_generalization')
    for result in [scores['micro'], *scores['perClass'].values()]:
        assert result['evaluationTarget'] == 'in_sample_ai_reference_agreement_not_generalization'


def test_scores_bind_document_identity_and_type():
    rows = [{'sampleId': 'a', 'text':'BERT', 'entities': [entity('BERT', 'BERT')]},
            {'sampleId': 'b', 'text':'BERT', 'entities': [entity('BERT', 'BERT')]}]
    scores = ner.score_rows(rows, [[entity('BERT', 'BERT')], []])
    assert scores['micro']['recall'] == 0.5
    assert scores['micro']['f1'] == pytest.approx(2 / 3)
    with pytest.raises(ValueError):
        ner.score_rows(rows, [[]])


def test_scores_reject_duplicate_documents_invalid_or_duplicate_spans():
    item = entity('BERT','BERT')
    row = {'sampleId':'unique','text':'BERT','entities':[item]}
    for rows, predictions in ([row,row],[[item],[item]]), ([row],[[item,item]]), ([row],[[item|{'label':'UNKNOWN'}]]), ([row],[[item|{'text':'wrong'}]]), ([row],[[item|{'end':99}]]):
        with pytest.raises(ValueError):
            ner.score_rows(rows,predictions)


def test_smoke_gates_require_real_change_reload_and_learning():
    assert ner.smoke_passed(2.0, 0.1, 0.95, True, True)
    assert not ner.smoke_passed(2.0, 1.8, 0.95, True, True)
    assert not ner.smoke_passed(2.0, 0.1, 0.6, True, True)
    assert not ner.smoke_passed(2.0, 0.1, 0.95, False, True)
    assert not ner.smoke_passed(2.0, 0.1, 0.95, True, False)


def test_tokenizer_must_preserve_entity_boundaries_without_truncation():
    row = {'sampleId': 'x', 'text': 'BERT', 'entities': [entity('BERT', 'BERT')]}

    def tokenizer(text, **options):
        assert options == {'return_offsets_mapping': True, 'truncation': False}
        return {'input_ids': [101, 10, 11, 102], 'attention_mask': [1] * 4,
                'offset_mapping': [(0, 0), (0, 2), (2, 4), (0, 0)]}

    encoded = ner.encode_row(tokenizer, row, 4)
    assert encoded['features']['labels'] == [-100, 1, 2, -100]
    with pytest.raises(ValueError, match='truncation forbidden'):
        ner.encode_row(tokenizer, row, 3)
    row['entities'] = [entity('BERT', 'BER')]
    with pytest.raises(ValueError):
        ner.encode_row(tokenizer, row, 4)


def test_actual_snapshot_receipts_are_bound_not_just_hash_valid(tmp_path):
    root = Path(__file__).resolve().parents[1]
    dataset = root / 'kg_datasets/dblp/course_v4_weak'
    snapshot = root / 'kg_datasets/dblp/course_v4_training_inputs_06'
    if not snapshot.exists():
        pytest.skip('Local sealed coursework fixture not distributed with source-only checkout')
    splits, summary = ner.load_snapshot(dataset, snapshot)
    assert {key: len(rows) for key, rows in splits.items()} == {'train': 338, 'dev': 167}
    assert not summary['nerTrainingReady']
    clone = tmp_path / 'snapshot'
    shutil.copytree(snapshot, clone)
    rows = c.read_jsonl(clone / 'ner_inputs_train.jsonl')
    rows[0]['annotationSha256'] = '0' * 64
    c.write_jsonl(clone / 'ner_inputs_train.jsonl', rows)
    manifest = json.loads((clone / 'manifest.json').read_text(encoding='utf-8'))
    manifest['filesSha256']['ner_inputs_train.jsonl'] = c.file_sha256(clone / 'ner_inputs_train.jsonl')
    c.write_json(clone / 'manifest.json', manifest)
    with pytest.raises(ValueError, match='differs from reviewed receipt'):
        ner.load_snapshot(dataset, clone)


def test_failed_run_records_failure_and_cannot_overwrite(tmp_path):
    output = tmp_path / 'failed'
    with pytest.raises(FileNotFoundError):
        ner.run(tmp_path / 'missing', tmp_path / 'missing', tmp_path / 'missing', output,
                'preflight', ner.TrainingConfig())
    state = json.loads((output / 'status.json').read_text(encoding='utf-8'))
    assert state['status'] == 'failed' and not state['trainingStarted'] and not state['testEvaluated']
    before = c.file_sha256(output / 'status.json')
    with pytest.raises(FileExistsError):
        ner.run(tmp_path, tmp_path, tmp_path, output, 'preflight', ner.TrainingConfig())
    assert c.file_sha256(output / 'status.json') == before


def test_dev_checkpoint_selection_requires_finite_strict_f1_and_earliest_tie():
    assert ner.dev_checkpoint_improved(0.5, None)
    assert ner.dev_checkpoint_improved(0.6, 0.5)
    assert not ner.dev_checkpoint_improved(0.5, 0.5)
    assert not ner.dev_checkpoint_improved(0.4, 0.5)
    for score in (None, float('nan'), float('inf'), -0.1, 1.1):
        with pytest.raises(ValueError):
            ner.dev_checkpoint_improved(score, None)


def test_development_fit_rejects_invalid_epochs_before_writing(tmp_path):
    for epochs in (0, -1, True, 1.5):
        output = tmp_path / str(epochs)
        with pytest.raises(ValueError, match='configuration'):
            ner.run(tmp_path, tmp_path, tmp_path, output, 'fit-dev', ner.TrainingConfig(epochs=epochs))
        assert not output.exists()


def test_final_test_refuses_partial_queue_without_changing_exports():
    root = Path(__file__).resolve().parents[1]
    dataset = root / 'kg_datasets/dblp/course_v4_weak'
    snapshot = root / 'kg_datasets/dblp/course_v4_training_inputs_08'
    before = c.file_sha256(snapshot / 'manifest.json')
    with pytest.raises(ValueError, match='entire test queue'):
        ner.load_snapshot(dataset, snapshot, include_test=True)
    assert c.file_sha256(snapshot / 'manifest.json') == before


def test_locked_checkpoint_is_bound_to_selection_not_latest_or_last_epoch(tmp_path):
    root = Path(__file__).resolve().parents[1]
    run = root / 'kg_datasets/dblp/course_v4_runs/ner_development_20261006_08'
    lock = root / 'annotations/course_v4/ner_test_selection_20261006.json'
    checkpoint, manifest = ner.load_test_checkpoint(run, lock)
    assert checkpoint.name == 'checkpoint_epoch_04'
    assert manifest['filesSha256']['checkpoint_epoch_04/model.safetensors'] == '968a594de551a1ab77a263a725fcdf487b8c559539f7452e2edeb8cf62c8d996'
    changed = json.loads(lock.read_text())
    for key, value in [('weightsSha256','0'*64), ('checkpoint','../outside'), ('developmentManifestSha256','0'*64)]:
        mutated = tmp_path / (key + '.json')
        c.write_json(mutated, changed | {key:value})
        with pytest.raises(ValueError):
            ner.load_test_checkpoint(run, mutated)


def test_final_inputs_preserve_training_and_bind_full_reviewed_queue():
    root = Path(__file__).resolve().parents[1]
    checkpoint, _, splits, summary, lock = ner.load_final_inputs(
        root / 'kg_datasets/dblp/course_v4_weak', root / 'kg_datasets/dblp/course_v4_training_inputs_09',
        root / 'kg_datasets/dblp/course_v4_runs/ner_development_20261006_08',
        root / 'annotations/course_v4/ner_test_selection_20261006.json')
    assert checkpoint.name == 'checkpoint_epoch_04' and lock['testQueueDocuments'] == 200
    assert {s: len(r) for s, r in splits.items()} == {'train': 397, 'dev': 167, 'test': 144}
    assert summary['entitySupport']['test'] == {'METHOD':192, 'TASK':118, 'DATASET':2}
    assert summary['nerTrainingReady'] and not summary['relationTrainingReady']


def test_test_failure_is_explicit_and_existing_artifacts_never_overwritten(tmp_path):
    output = tmp_path / 'failed_test'
    with pytest.raises(FileNotFoundError):
        ner.evaluate_test(tmp_path, tmp_path, tmp_path, tmp_path / 'absent.json', output)
    state = json.loads((output / 'status.json').read_text())
    assert state['status'] == 'failed' and not state['testEvaluated'] and not state['trainingStarted']
    before = c.file_sha256(output / 'status.json')
    with pytest.raises(FileExistsError):
        ner.evaluate_test(tmp_path, tmp_path, tmp_path, tmp_path, output)
    assert c.file_sha256(output / 'status.json') == before


@pytest.mark.parametrize('option',['--seed=123','--learning-rate=0.1'])
def test_final_test_cli_rejects_equals_form_tuning_before_evaluation(monkeypatch,option):
    monkeypatch.setattr(sys,'argv',['train_course_ner.py','evaluate-test','--dataset','unused',
                        '--snapshot','unused','--model','unused','--output','unused','--selection','unused',option])
    monkeypatch.setattr(ner,'evaluate_test',lambda *args:pytest.fail('Test tuning option reached evaluation'))
    with pytest.raises(SystemExit) as error:
        ner.main()
    assert error.value.code==2
