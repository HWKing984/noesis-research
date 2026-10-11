"""One check for abstention, exact training references and held-out boundaries."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import evaluate_abstract_abstention as evaluation
from course_bio_abstention import decode_with_abstention


def test_conservative_bio_abstention_preserves_valid_spans():
    r=decode_with_abstention([3,2],[(0,9),(10,19)],'detecting malicious')
    assert r['entities']==[] and r['abstainedEntities'][0]['text']=='detecting'
    assert r['abstainedEntities'][0]['abstentionReasons']==['conflicting_I_continuation_after_closed_prefix']
    r=decode_with_abstention([1,0],[(0,3),(3,6)],'abcdef')
    assert not r['entities'] and r['abstainedEntities'][0]['abstentionReasons']==['boundary_inside_word']
    r=decode_with_abstention([1,2],[(0,3),(3,6)],'abcdef')
    assert r['entities']==[{'start':0,'end':6,'text':'abcdef','label':'METHOD'}] and not r['abstainedEntities']
    assert len(evaluation.load_inputs()[3]['train']['ner'])==58
    with pytest.raises(FileExistsError):evaluation.run(Path(__file__).parent.resolve())
