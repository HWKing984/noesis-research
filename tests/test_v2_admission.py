import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import course_v2_admission as a
import run_v2_admission_checks as checks
import harden_v2_identity as parent

ALIASES = {'byPublication': {}, 'blockedPublications': {}}
ROW = {'publicationId': 'synthetic:a', 'groupId': 'synthetic-group:a', 'arxivId': '2610.88888', 'split': 'test'}


def junit_xml(cases, declared=None, **attrs):
    import xml.etree.ElementTree as E
    root=E.Element('testsuites'); suite=E.SubElement(root,'testsuite', {'tests':str(len(cases) if declared is None else declared),
        'failures':'0','errors':'0','skipped':'0','hostname':'synthetic-fixture','timestamp':'2026-10-10T00:00:00+00:00','time':'0.1'} | attrs)
    for classname,name in cases:E.SubElement(suite,'testcase', {'classname':classname,'name':name,'time':'0.01'})
    return io.StringIO(E.tostring(root,encoding='unicode'))


EXPECTED=[('tests.test_v2_admission','case:a'), ('tests.test_v2_admission','case:b')]


@pytest.mark.parametrize('fault',['fake_one','wrong_count','missing','duplicate','unknown','failure','error','skipped','missing_metadata','nan_time'])
def test_junit_identity_and_runtime_gate_rejects_incomplete_evidence(fault):
    cases=EXPECTED.copy(); declared=None; attrs={}
    if fault=='fake_one':cases=[('tests.test_v2_identity_guard','fabricated_pass')];declared=205
    elif fault=='wrong_count':declared=205
    elif fault=='missing':cases.pop()
    elif fault=='duplicate':cases=[EXPECTED[0],EXPECTED[0]]
    elif fault=='unknown':cases[0]=('tests.test_v2_admission','unknown')
    elif fault in ('failure','error','skipped'):attrs[{'failure':'failures','error':'errors','skipped':'skipped'}[fault]]='1'
    elif fault=='missing_metadata':attrs['hostname']=''
    elif fault=='nan_time':attrs['time']='nan'
    with pytest.raises(ValueError):checks.junit(junit_xml(cases,declared,**attrs),EXPECTED)


def test_complete_junit_and_old_fabricated_gate_difference():
    assert checks.junit(junit_xml(EXPECTED),EXPECTED)==2
    assert parent.passing_junit(junit_xml([('tests.test_v2_identity_guard','fabricated_pass')],205))==1


def synthetic_binding(tmp_path):
    # Synthetic fixture only; neither the ID nor these texts certify a real paper.
    content=tmp_path/'abstract.txt';content.write_text('Synthetic evidence for admission tests only.',encoding='utf-8')
    evidence=tmp_path/'review.txt';evidence.write_text('Synthetic source and duplicate review fixture; not independent semantic evidence.',encoding='utf-8')
    binding={'content':{'file':content.name,'sha256':parent.sha(content)}}
    frame=a.FRAME | {'samplingFrameLocked':True, 'syntheticFixtureOnly':True}
    lock=a.prelock([ROW],[],ALIASES,frame)
    lock,context=a.bind_content(lock,{ROW['publicationId']:binding},[],ALIASES,tmp_path)
    for field,kind in [('sourceReview','source_origin'),('nearDuplicateReview','near_duplicate')]:
        binding[field]={'kind':kind,'status':'cleared','canonicalPaperId':'arxiv:2610.88888','textSha256':parent.sha(content),
            'contextSha256':context,'reviewer':'synthetic-fixture-only','reviewedAtUTC':'2026-10-10T00:00:00+00:00',
            'reason':'Synthetic control, no real semantic certification','evidenceArtifacts':[{'file':evidence.name,'sha256':parent.sha(evidence)}]}
    binding['sourceReview']['sourceURL']='https://arxiv.org/abs/2610.88888'
    return lock,{ROW['publicationId']:binding}


def test_metadata_without_sha_is_pending_never_final(tmp_path):
    lock=a.prelock([ROW],[],ALIASES,a.FRAME)
    assert lock['status']=='pending_content_binding' and lock['evaluationAuthorized'] is False
    with pytest.raises(ValueError):a.finalize(lock,{},[],ALIASES,tmp_path)
    exposed=[{'arxivId':'2107.03374','origin':'train'}]
    with pytest.raises(ValueError):a.prelock([ROW | {'arxivId':'arXiv:2107.03374V3'}],exposed,ALIASES,a.FRAME)
    with pytest.raises(ValueError):a.prelock([ROW | {'text':'sealed body'}],[],ALIASES,a.FRAME)


@pytest.mark.parametrize('fault',['missing_sha','missing_review','bare_pass','wrong_source','bare_id_source','wrong_context',
    'content_changed','review_evidence_changed','missing_evidence','escaped_path','changed_member','history_changed','frame_unlocked','hash_changed','unknown_binding'])
def test_final_admission_requires_actual_bound_bytes_and_reviews(tmp_path,fault):
    lock,bindings=synthetic_binding(tmp_path);bound=bindings[ROW['publicationId']]
    if fault=='missing_sha':
        row=dict(lock['assignments'][0]);row.pop('textSha256');lock=a.prelock([row],[],ALIASES,lock['samplingFrame'])
    elif fault=='missing_review':bound['nearDuplicateReview']['status']='pending'
    elif fault=='bare_pass':bound['sourceReview']={'passed':True}
    elif fault=='wrong_source':bound['sourceReview']['sourceURL']='https://example.org/abs/2610.88888'
    elif fault=='bare_id_source':bound['sourceReview']['sourceURL']='arxiv:2610.88888'
    elif fault=='wrong_context':bound['nearDuplicateReview']['contextSha256']='0'*64
    elif fault=='content_changed':(tmp_path/'abstract.txt').write_text('changed',encoding='utf-8')
    elif fault=='review_evidence_changed':(tmp_path/'review.txt').write_text('changed',encoding='utf-8')
    elif fault=='missing_evidence':bound['sourceReview']['evidenceArtifacts']=[]
    elif fault=='escaped_path':bound['content']['file']='../escaped.txt'
    elif fault=='changed_member':lock['assignments'][0]['groupId']='another-group'
    elif fault=='history_changed':lock['exclusionsSha256']='0'*64
    elif fault=='frame_unlocked':
        lock=a.prelock(lock['assignments'],[],ALIASES,a.FRAME)
    elif fault=='hash_changed':bound['content']['sha256']='0'*64
    elif fault=='unknown_binding':bindings['unknown']=bound
    with pytest.raises((ValueError,KeyError)):a.finalize(lock,bindings,[],ALIASES,tmp_path)


def test_synthetic_content_success_is_not_evaluation_or_training_authority(tmp_path):
    lock,bindings=synthetic_binding(tmp_path)
    result=a.finalize(lock,bindings,[],ALIASES,tmp_path)
    assert result['status']=='content_binding_checks_passed' and result['evaluationAuthorized'] is False
    assert a.FRAME['samplingFrameLocked'] is False and a.FRAME['fullDBLPRepresentative'] is False


def test_bound_content_hash_still_blocks_historical_exposure_and_cross_split(tmp_path):
    lock,bindings=synthetic_binding(tmp_path);r=lock['assignments'][0]
    history=[{'publicationId':'historical:other','groupId':'history:other','textSha256':r['textSha256'],'origin':'train'}]
    with pytest.raises(ValueError):a.prelock([r],history,ALIASES,lock['samplingFrame'])
    train=ROW | {'publicationId':'train:other','groupId':'train:other','arxivId':'2610.88889','split':'train','textSha256':r['textSha256']}
    with pytest.raises(ValueError):a.prelock([train,r],[],ALIASES,lock['samplingFrame'])
    empty=a.prelock([],[],ALIASES,a.FRAME)
    with pytest.raises(ValueError,match='Empty evaluation'):a.finalize(empty,{},[],ALIASES,tmp_path)


def test_restricted_sampling_scope_cannot_claim_full_dblp():
    with pytest.raises(ValueError):a.prelock([ROW],[],ALIASES,a.FRAME | {'fullDBLPRepresentative':True})


def test_runner_does_not_accept_external_xml_argument():
    process=subprocess.run([sys.executable,str(Path(checks.__file__)),'--output','unused','--test-evidence','fake.xml'],capture_output=True,text=True)
    assert process.returncode==2 and 'unrecognized arguments' in process.stderr


def test_actual_controlled_runner_and_receipt_rejects_resigned_xml(tmp_path,monkeypatch):
    import shutil
    source=tmp_path/'tests/test_smoke.py';source.parent.mkdir()
    shutil.copy2(Path(__file__).parent/'fixtures/v2_execution_smoke.py',source)
    frozen={'testFiles':['tests/test_smoke.py'],'nodeIds':['tests/test_smoke.py::test_smoke'],
        'sourceSha256':{'tests/test_smoke.py':parent.sha(source)}}
    inventory=tmp_path/'inventory.json';inventory.write_text(json.dumps(frozen),encoding='utf-8')
    monkeypatch.setattr(checks,'ROOT',tmp_path);monkeypatch.setattr(checks,'INVENTORY',inventory);monkeypatch.setattr(checks,'TESTS',tuple(frozen['testFiles']))
    output=tmp_path/'execution';receipt=checks.run(output)
    assert receipt['status']=='passed' and receipt['actualTests']==1
    assert checks.verify(output,frozen,tmp_path)==1
    with pytest.raises(FileExistsError):checks.run(output)
    (output/'checks.xml').write_text(junit_xml([('tests.test_v2_identity_guard','fabricated_pass')],205).getvalue(),encoding='utf-8')
    receipt['junitSha256']=parent.sha(output/'checks.xml');(output/'run_receipt.json').write_text(json.dumps(receipt),encoding='utf-8')
    with pytest.raises(ValueError):checks.verify(output,frozen,tmp_path)


def test_actual_collection_and_source_are_required_before_run(tmp_path,monkeypatch):
    inventory=tmp_path/'inventory.json'
    inventory.write_text(json.dumps({'testFiles':list(checks.TESTS),'nodeIds':['fabricated'],
        'sourceSha256':{'missing.py':'0'*64}}),encoding='utf-8')
    monkeypatch.setattr(checks,'ROOT',tmp_path);monkeypatch.setattr(checks,'INVENTORY',inventory)
    with pytest.raises(FileNotFoundError):checks.run(tmp_path/'execution')
    assert not (tmp_path/'execution').exists()


def test_build_cli_rejects_external_pass_xml_and_preserves_existing_output(tmp_path):
    import finalize_v2_admission as final
    with pytest.raises(FileExistsError):final.build(tmp_path)
    process=subprocess.run([sys.executable,str(Path(final.__file__)),'--test-evidence','fake.xml'],capture_output=True,text=True)
    assert process.returncode==2 and 'unrecognized arguments' in process.stderr
