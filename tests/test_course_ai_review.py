import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import course_weak as c
import expand_course_ai_review as expander
from expand_course_ai_review import expand_review
from test_course_ai_compilation import example


def inputs():
    _,decision=example()
    first={'provider':'synthetic_test','model':'not_a_real_model','round':'generation','decisions':[decision]}
    review={'provider':'synthetic_test','model':'not_a_real_model','round':'candidate_aware_ai_review',
            'generationDecisionsSha256':'a'*64,'judgments':[{'sampleId':decision['sampleId'],'verdict':'confirmed','reason':'Synthetic recheck of boundary and directed relation.'}]}
    return first,review


def test_explicit_ai_confirmation_is_preserved_not_automatically_invented():
    first,review=inputs()
    expanded=expand_review(first,review,'a'*64)
    assert expanded['decisions'][0]['entities']==first['decisions'][0]['entities']
    assert 'AI self-review' in expanded['decisions'][0]['notes']
    assert first['decisions'][0]['notes']=='Synthetic test only.'


def test_revision_preserves_first_semantic_decision():
    first,review=inputs()
    replacement=copy.deepcopy(first['decisions'][0]);replacement.update(entityStatus='unresolved',entityReason='Type ambiguous')
    review['judgments'][0].update(verdict='revised',replacement=replacement)
    expanded=expand_review(first,review,'a'*64)
    assert expanded['decisions'][0]['entityStatus']=='unresolved'
    assert first['decisions'][0]['entityStatus']=='complete'


@pytest.mark.parametrize('case',['wrong_hash','missing','duplicate','empty_reason','bad_verdict','missing_replacement','wrong_replacement_sample','unknown_field','wrong_round'])
def test_incomplete_or_forged_review_structure_fails(case):
    first,review=inputs()
    if case=='wrong_hash':review['generationDecisionsSha256']='0'*64
    elif case=='missing':review['judgments']=[]
    elif case=='duplicate':review['judgments'].append(copy.deepcopy(review['judgments'][0]))
    elif case=='empty_reason':review['judgments'][0]['reason']=''
    elif case=='bad_verdict':review['judgments'][0]['verdict']='human_reviewed'
    elif case=='missing_replacement':review['judgments'][0]['verdict']='revised'
    elif case=='wrong_replacement_sample':
        review['judgments'][0].update(verdict='revised',replacement=first['decisions'][0]|{'sampleId':'other'})
    elif case=='unknown_field':review['human_gold']=True
    elif case=='wrong_round':review['round']='blind_independent_review'
    with pytest.raises(ValueError):expand_review(first,review,'a'*64)


def test_expansion_cli_preserves_recorded_judgments(tmp_path,monkeypatch,capsys):
    first,review=inputs()
    generation=tmp_path/'generation.json';c.write_json(generation,first)
    review['generationDecisionsSha256']=c.file_sha256(generation)
    judgments=tmp_path/'judgments.json';c.write_json(judgments,review)
    output=tmp_path/'expanded'
    monkeypatch.setattr(sys,'argv',['expand_course_ai_review','--generation',str(generation),'--judgments',str(judgments),'--output',str(output)])
    expander.main()
    assert json.loads(capsys.readouterr().out)['modelCallExecutedByExpander'] is False
    manifest=json.loads((output/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['filesSha256'].items():assert c.file_sha256(output/name)==digest
    with pytest.raises(FileExistsError):expander.expand_artifact(generation,judgments,output)
