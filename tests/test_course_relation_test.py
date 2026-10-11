"""Synthetic endpoint checks are not course quality evidence."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import course_weak as c
from evaluate_course_relation import candidate_rows, score_pipeline, load_inputs, run


def row():
    return {'sampleId':'synthetic','text':'BERT for tagging','entities':[
        {'start':0,'end':4,'text':'BERT','label':'METHOD'},
        {'start':9,'end':16,'text':'tagging','label':'TASK'}]}


def test_pipeline_counts_endpoint_errors_and_false_positives_in_empty_documents():
    doc=row(); pairs=candidate_rows(doc,doc['entities'])
    assert len(pairs)==1 and 'label' not in pairs[0]
    reference=[pairs[0]|{'label':'USED_FOR'}]
    predicted=[pairs[0]|{'label':'USED_FOR'}]
    assert score_pipeline([doc],reference,predicted)['positiveMicro']['f1']==1
    wrong=copy.deepcopy(predicted); wrong[0]['tail'].update(start=10,text='agging')
    metrics=score_pipeline([doc],reference,wrong)['positiveMicro']
    assert metrics['truePositive']==0 and metrics['predicted']==metrics['reference']==1
    assert score_pipeline([doc],reference,[])['positiveMicro']['recall']==0
    assert score_pipeline([doc],[],predicted)['positiveMicro']['predicted']==1
    assert score_pipeline([doc],[],[])['positiveMicro']['f1'] is None
    for bad in (predicted*2,[predicted[0]|{'label':'UNRESOLVED'}],
                [predicted[0]|{'sampleId':'unknown'}], [predicted[0]|{'text':'forged'}]):
        with pytest.raises(ValueError): score_pipeline([doc],reference,bad)
    with pytest.raises(ValueError): candidate_rows(doc,[*doc['entities'],doc['entities'][0]])


def test_final_inputs_bind_frozen_weights_data_and_inherited_entity_labels():
    root=Path(__file__).resolve().parents[1]
    data=load_inputs(root/'kg_datasets/dblp/course_v4_weak',root/'kg_datasets/dblp/course_v4_training_inputs_11',
                     root/'annotations/course_v4/re_test_selection_20261006.json')
    assert len(data['documents'])==138 and len(data['relations'])==137
    assert len(data['excluded'])==62
    assert {r['label'] for r in data['relations']}=={'USED_FOR','EVALUATED_ON','NO_RELATION'}
    assert len(data['cachedNERPredictions'])==138
    assert c.file_sha256(data['checkpoint']/'model.safetensors')==data['lock']['weightsSha256']


def test_invalid_data_seal_fails_before_inference_and_preserves_failure(tmp_path):
    import json
    root=Path(__file__).resolve().parents[1]
    seal=tmp_path/'invalid.json'; c.write_json(seal,{'snapshotManifestSha256':'0'*64})
    output=tmp_path/'failure'
    with pytest.raises(ValueError,match='sealed'):
        run(root/'kg_datasets/dblp/course_v4_weak',root/'kg_datasets/dblp/course_v4_training_inputs_11',
            root/'annotations/course_v4/re_test_selection_20261006.json',seal,output,'cpu')
    status=json.loads((output/'status.json').read_text(encoding='utf-8'))
    assert status['status']=='failed' and not status['testInferenceStarted'] and not status['trainingStarted']
    with pytest.raises(FileExistsError): run(None,None,None,None,output,'cpu')


def test_relation_test_evidence_recomputes_scope_and_rejects_resealed_coverage(tmp_path):
    import json
    import shutil
    from export_course_evidence import build_relation_test
    root=Path(__file__).resolve().parents[1]
    source=root/'kg_datasets/dblp/course_v4_runs/re_final_test_20261006_17'
    args=(root/'kg_datasets/dblp/course_v4_weak',root/'kg_datasets/dblp/course_v4_training_inputs_11')
    xml=root/'kg_datasets/dblp/course_v4_runs/tests_20261006_round16_handoff.xml'
    build_relation_test(*args,source,xml,tmp_path/'evidence')
    assert '60.07%' in (tmp_path/'evidence/08_relation_test.html').read_text(encoding='utf-8')
    clone=tmp_path/'tampered'; shutil.copytree(source,clone)
    metrics=json.loads((clone/'test_result.json').read_text(encoding='utf-8')); metrics['coverage']=1.0
    c.write_json(clone/'test_result.json',metrics)
    manifest=json.loads((clone/'manifest.json').read_text(encoding='utf-8'))
    manifest['filesSha256']['test_result.json']=c.file_sha256(clone/'test_result.json'); c.write_json(clone/'manifest.json',manifest)
    with pytest.raises(ValueError,match='coverage'):
        build_relation_test(*args,clone,xml,tmp_path/'bad_evidence')
