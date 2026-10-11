"""Regression probes use the actual sealed parent; no fake evaluation corpus."""
import copy
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import course_v2_training_roster as r
import course_v2_sampling as s
import prepare_v2_sampling as p

PARENT = p.ROOT/'kg_datasets/dblp/course_v2_admission_20261010'


@pytest.fixture
def locked(tmp_path):
    parent=tmp_path/'audit_parent'; parent.mkdir()
    for name in ('manifest.json', *r.BOUND):
        shutil.copy2(PARENT/name,parent/name)
    lock=r.expected(parent); p.write(tmp_path/'training_roster_lock.json',lock)
    return tmp_path, lock['assignments'], s.read(parent/'identity_alias_index.json')


def extra():
    return {'publicationId':'arxiv:2502.00003','arxivId':'2502.00003',
            'groupId':'arxiv-group:2502.00003','split':'train'}


def test_original_twelve_and_reordered_roster_pass(locked):
    folder,train,aliases=locked
    assert r.validate(folder,train,aliases)['trainingDocuments']==12
    assert r.validate(folder,list(reversed(train)),aliases)['trainingAuthorized'] is False


@pytest.mark.parametrize('fault',['empty','addition','replacement','deletion','duplicate','text_sha','group','publication','unknown_field','alias_context','self_resigned'])
def test_training_mutations_are_rejected(locked,fault):
    folder,original,aliases=locked; train=copy.deepcopy(original)
    if fault=='empty': train=[]
    elif fault=='addition': train.append(extra())
    elif fault=='replacement': train[0]=extra()
    elif fault=='deletion': train.pop()
    elif fault=='duplicate': train[-1]=copy.deepcopy(train[0])
    elif fault=='text_sha': train[0]['textSha256']='0'*64
    elif fault=='group': train[0]['groupId']='different-group'
    elif fault=='publication': train[0]['publicationId']='unapproved-publication'
    elif fault=='unknown_field': train[0]['trusted']=True
    elif fault=='alias_context': aliases=aliases|{'byPublication':{}}
    else:
        train.append(extra()); lock=s.read(folder/'training_roster_lock.json')
        lock.update(assignments=train,trainingDocuments=13,rosterSha256=s.admission.digest(train))
        p.write(folder/'training_roster_lock.json',lock)
    with pytest.raises(ValueError): r.validate(folder,train,aliases)


@pytest.mark.parametrize('name',['manifest.json',*r.BOUND])
def test_parent_training_bytes_cannot_be_replaced(locked,name):
    folder,train,aliases=locked
    path=folder/'audit_parent'/name; path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError): r.validate(folder,train,aliases)


def test_missing_roster_fails_closed(locked):
    folder,train,aliases=locked
    (folder/'training_roster_lock.json').unlink()
    with pytest.raises(FileNotFoundError): r.validate(folder,train,aliases)


@pytest.mark.parametrize('operation',['prelock','validate_lock','bind_content','finalize'])
def test_formal_entries_check_roster_before_sampling_or_content(locked,operation):
    folder,train,aliases=locked
    p.write(folder/'sampling_protocol.json',{'version':'course_v2_sampling_v2'})
    with pytest.raises(ValueError,match='Training roster'):
        if operation=='prelock': s.prelock(folder,[],[],aliases)
        elif operation=='validate_lock': s.validate_lock(folder,{'assignments':[]},[],aliases)
        else: getattr(s,operation)(folder,{'assignments':[]},{},[],aliases,folder)


def test_adjudicated_pair_stays_unresolved():
    row=s.read(p.ADJUDICATION)
    assert row['finalLabel']=='UNRESOLVED' and row['reviewStatus']=='adjudicated_not_admitted'
    assert row['candidateEligible'] is False and row['trainingAuthorized'] is False


def test_protocol_downgrade_cannot_bypass_formal_roster(locked):
    folder,train,aliases=locked
    p.write(folder/'sampling_protocol.json',{'version':'course_v2_sampling_v1'})
    with pytest.raises(ValueError,match='Training roster'):
        s.prelock(folder,[],[],aliases)
