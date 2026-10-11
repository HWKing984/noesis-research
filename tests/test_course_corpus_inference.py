"""Input isolation and source binding, not semantic accuracy tests."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
import infer_course_corpus as production


def test_production_tokenization_never_receives_labels_or_truncates():
    class Tokenizer:
        def __call__(self,text,**options):
            assert options=={'return_offsets_mapping':True,'truncation':False}
            return {'input_ids':[1,2,3],'attention_mask':[1,1,1],'offset_mapping':[(0,0),(0,4),(0,0)]}
    d={'sampleId':'s','text':'BERT','textSha256':'h'}
    encoded,length=production.encode_title(Tokenizer(),d,3)
    assert length==3 and 'labels' not in encoded['features']
    assert production.encode_title(Tokenizer(),d,2)==(None,3)
    for bad in (d|{'entities':[]},d|{'label':'USED_FOR'},d|{'referenceEntities':[]},d|{'split':'test'}):
        with pytest.raises(ValueError,match='anonymous title'): production.encode_title(Tokenizer(),bad,3)


def test_locked_corpus_and_cached_prediction_coverage():
    docs,locks,nr,rr,bindings=production.load_sources()
    assert len(docs)==20000 and len(nr)==144 and len(rr)==148
    assert len({d['sampleId'] for d in docs})==20000
    assert locks['ner']['weightsSha256']==locks['re']['pipelineNERWeightsSha256']
    assert not any('training_inputs' in p or 'receipts' in p for p in bindings)
    assert 'scripts/infer_course_corpus.py' in bindings


def test_production_refuses_overwrite_and_invalid_limits(tmp_path):
    with pytest.raises(FileExistsError): production.run(tmp_path)
    for count in (0,20001,True):
        with pytest.raises(ValueError): production.run(tmp_path/'new',count)


def test_changed_annotation_contract_is_rejected_before_inference(tmp_path, monkeypatch):
    changed=tmp_path/'changed_config.json'
    changed.write_text('{}',encoding='utf-8')
    monkeypatch.setattr(production.c,'CONFIG_PATH',changed)
    with pytest.raises(ValueError,match='annotation contract changed'):
        production.load_sources()
