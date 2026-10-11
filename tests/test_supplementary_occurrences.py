"""One source-occurrence check: a task modifier cannot become a nested flat entity."""
import hashlib
import runpy
from pathlib import Path


def test_supplementary_occurrence_adapter():
    response=runpy.run_path(str(Path(__file__).resolve().parents[1]/'annotations/course_v4/annotate_supplement_20261009_round49.py'))['response']
    text='Alpha translation model supports translation.'
    ref={'sampleId':'sample-'+'b'*20,'arxivId':'9999.54321','text':text,'textSha256':hashlib.sha256(text.encode()).hexdigest()}
    decision={'arxivId':ref['arxivId'],'textSha256':ref['textSha256'],'notes':'Explicit source occurrences, no discarded task or fabricated method.','groups':[],
              'occurrenceMentions':[{'text':'Alpha translation model','occurrences':[{'occurrence':1,'label':'METHOD','reason':'Whole architecture name.'}]},
                                    {'text':'translation','occurrences':[{'occurrence':1,'label':'WITHIN_ENTITY','container':{'text':'Alpha translation model','occurrence':1},'reason':'Modifier inside the flat method entity.'},{'occurrence':2,'label':'TASK','reason':'Explicit output task.'}]}]}
    actual=response(decision,ref)
    assert [e['text'] for e in actual['entities']]==['Alpha translation model','translation']
    assert actual['relationStatus']=='unresolved' and actual['relations'][0]['label']=='UNRESOLVED'
