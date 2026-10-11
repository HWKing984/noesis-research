"""Relation training contracts; synthetic examples are not coursework labels."""
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import course_weak as c
import train_course_relation as r


def example(text='😀 BERT for tagging'):
    return {'sampleId':'synthetic_test', 'text':text,
            'head':{'start':2,'end':6,'text':'BERT','label':'METHOD'},
            'tail':{'start':11,'end':18,'text':'tagging','label':'TASK'}, 'label':'USED_FOR'}


def test_markers_preserve_direction_unicode_and_original_spans():
    row = example()
    marked = r.mark_pair(row)
    assert marked == '😀  [unused0] BERT [unused1]  for  [unused2] tagging [unused4] '
    reverse = {'sampleId':'synthetic_reverse', 'text':'MNIST with BERT',
               'head':{'start':11,'end':15,'text':'BERT','label':'METHOD'},
               'tail':{'start':0,'end':5,'text':'MNIST','label':'DATASET'}, 'label':'EVALUATED_ON'}
    assert r.mark_pair(reverse).index('[unused3]') < r.mark_pair(reverse).index('[unused0]')
    for bad in (row | {'text':'😀 XERT for tagging'}, row | {'tail':row['head']},
                row | {'head':row['head'] | {'label':'TASK'}}, row | {'text':row['text']+' [unused0]'}):
        with pytest.raises(ValueError):
            r.mark_pair(bad)


def test_metrics_exclude_negative_class_from_positive_f1_and_disclose_support():
    rows = [example(), example() | {'sampleId':'negative', 'label':'NO_RELATION'}]
    metrics = r.score_relations(rows, ['USED_FOR','USED_FOR'])
    assert metrics['accuracy'] == 0.5 and metrics['positiveMicro']['truePositive'] == 1
    assert metrics['positiveMicro']['f1'] == pytest.approx(2/3)
    assert metrics['perClass']['EVALUATED_ON']['reference'] == 0
    assert metrics['perClass']['EVALUATED_ON']['f1'] is None
    assert metrics['supportedPositiveClasses'] == ['USED_FOR']
    assert metrics['confusionMatrix'] == [[1,0,0],[0,0,0],[1,0,0]]
    for bad_rows, predictions in [(rows,[]), (rows,['UNRESOLVED','USED_FOR']),
                                  (rows,['EVALUATED_ON','USED_FOR']), ([rows[0],rows[0]],['USED_FOR']*2)]:
        with pytest.raises(ValueError):
            r.score_relations(bad_rows, predictions)


def test_majority_baseline_uses_train_labels_by_tail_type_only():
    rows = [example(), example() | {'sampleId':'negative', 'label':'NO_RELATION'}]
    baseline = r.type_majority(rows)
    assert baseline['TASK'] == 'USED_FOR'
    assert r.allowed_labels('TASK') == ['USED_FOR','NO_RELATION']
    assert r.allowed_labels('DATASET') == ['EVALUATED_ON','NO_RELATION']
    with pytest.raises(ValueError):
        r.allowed_labels('METHOD')


def test_actual_relation_inputs_bound_to_receipts_not_resealed_exports(tmp_path):
    root = Path(__file__).resolve().parents[1]
    dataset = root / 'kg_datasets/dblp/course_v4_weak'
    snapshot = root / 'kg_datasets/dblp/course_v4_training_inputs_09'
    rows, summary = r.load_relation_snapshot(dataset, snapshot)
    assert {s:len(v) for s,v in rows.items()} == {'train':315,'dev':162}
    assert not summary['relationTrainingReady']
    clone = tmp_path / 'tampered'
    shutil.copytree(snapshot,clone)
    inputs = c.read_jsonl(clone / 'relation_inputs_train.jsonl')
    inputs[0]['reason'] = 'fabricated replacement'
    c.write_jsonl(clone / 'relation_inputs_train.jsonl', inputs)
    manifest = json.loads((clone / 'manifest.json').read_text())
    manifest['filesSha256']['relation_inputs_train.jsonl'] = c.file_sha256(clone / 'relation_inputs_train.jsonl')
    c.write_json(clone / 'manifest.json',manifest)
    with pytest.raises(ValueError,match='reviewed receipts'):
        r.load_relation_snapshot(dataset,clone)


def test_failed_run_is_explicit_and_existing_artifacts_preserved(tmp_path):
    output = tmp_path / 'failed'
    with pytest.raises(FileNotFoundError):
        r.run(tmp_path,tmp_path,tmp_path,output,r.RelationConfig())
    state = json.loads((output / 'status.json').read_text())
    assert state['status']=='failed' and not state['trainingStarted'] and not state['testEvaluated']
    before = c.file_sha256(output / 'status.json')
    with pytest.raises(FileExistsError):
        r.run(tmp_path,tmp_path,tmp_path,output,r.RelationConfig())
    assert c.file_sha256(output / 'status.json') == before


def test_invalid_config_rejected_before_writing(tmp_path):
    for config in (r.RelationConfig(epochs=0),r.RelationConfig(epochs=True),r.RelationConfig(batch_size=0),
                   r.RelationConfig(learning_rate=float('nan')),r.RelationConfig(max_length=1)):
        with pytest.raises(ValueError):
            r.run(tmp_path,tmp_path,tmp_path,tmp_path/'never',config)
        assert not (tmp_path/'never').exists()


def test_entity_representation_config_is_explicit_and_fail_closed(tmp_path):
    assert r.RelationConfig().representation == 'cls'
    assert r.RelationConfig(representation='entity_markers').representation == 'entity_markers'
    with pytest.raises(ValueError, match='configuration'):
        r.run(tmp_path,tmp_path,tmp_path,tmp_path/'never',r.RelationConfig(representation='automatic'))
    assert not (tmp_path/'never').exists()


def test_pair_encoding_has_no_reason_evidence_or_metadata_features_and_never_truncates():
    class LiteralTokenizer:
        def convert_tokens_to_ids(self, token):
            return list(r.MARKERS.values()).index(token)+1

        def __call__(self, text, return_offsets_mapping=False, truncation=False):
            assert truncation is False
            tokens = list(re.finditer(r'\[unused\d+\]|\w+|[^\s]',text))
            result = {'input_ids':[101]+[self.convert_tokens_to_ids(m.group()) if m.group() in r.MARKERS.values() else 100 for m in tokens]+[102],
                      'attention_mask':[1]*(len(tokens)+2)}
            if return_offsets_mapping:
                result['offset_mapping'] = [(0,0)]+[(m.start(),m.end()) for m in tokens]+[(0,0)]
            return result
    tokenizer, row = LiteralTokenizer(), example()
    encoded = r.encode_pair(tokenizer,row,128)
    assert encoded == r.encode_pair(tokenizer,row|{'reason':'secret answer','evidence':{'text':'answer'},'topics':['answer'],'split':'test'},128)
    assert set(encoded['features']) == {'input_ids','attention_mask','labels'}
    unlabeled = {key:value for key,value in row.items() if key!='label'}
    inference = r.encode_pair(tokenizer,unlabeled,128)
    assert 'labels' not in inference['features']
    assert inference['features'] == {key:value for key,value in encoded['features'].items() if key!='labels'}
    with pytest.raises(ValueError,match='truncation forbidden'):
        r.encode_pair(tokenizer,row,2)
    with pytest.raises(ValueError,match='boundary'):
        r.encode_pair(tokenizer,row|{'tail':row['tail']|{'end':15,'text':'tagg'}},128)
    with pytest.raises(ValueError,match='target'):
        r.encode_pair(tokenizer,row|{'label':'UNRESOLVED'},128)


def test_balanced_weights_use_only_train_counts_and_missing_class_fails():
    rows = [example(), example()|{'sampleId':'negative','label':'NO_RELATION'},
            example()|{'sampleId':'dataset','label':'EVALUATED_ON','tail':{'label':'DATASET'}}]
    assert r.class_weights(rows,False) == [1.0,1.0,1.0]
    assert r.class_weights(rows,True) == [1.0,1.0,1.0]
    assert r.class_weights(rows+[example()|{'sampleId':'second'}],True) == pytest.approx([2/3,4/3,4/3])
    with pytest.raises(ValueError,match='class support'):
        r.class_weights(rows[:1],True)


def test_all_class_selection_includes_negative_and_rejects_zero_support():
    majority = {'positiveMacroF1':0.99, 'perClass':{
        'USED_FOR':{'reference':155,'f1':0.98}, 'EVALUATED_ON':{'reference':2,'f1':1.0},
        'NO_RELATION':{'reference':5,'f1':0.0}}}
    role = {'positiveMacroF1':0.98, 'perClass':{
        'USED_FOR':{'reference':155,'f1':0.96}, 'EVALUATED_ON':{'reference':2,'f1':1.0},
        'NO_RELATION':{'reference':5,'f1':0.3}}}
    assert r.selection_score(majority,'positive_macro') > r.selection_score(role,'positive_macro')
    assert r.selection_score(majority,'all_class_macro') < r.selection_score(role,'all_class_macro')
    assert r.selection_score(role,'all_class_macro') == pytest.approx((0.96+1.0+0.3)/3)
    role['perClass']['NO_RELATION']['reference'] = 0
    with pytest.raises(ValueError,match='support'):
        r.selection_score(role,'all_class_macro')
    with pytest.raises(ValueError,match='selection'):
        r.selection_score(majority,'invented')
    with pytest.raises(ValueError):
        r.run(Path('.'),Path('.'),Path('.'),Path('must_never_write_invalid_selection'),r.RelationConfig(selection_metric='invented'))
