import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from course_identity import resolve_signature


def test_only_exact_unambiguous_dblp_profile_resolves():
    profiles={'homepages/a/1':{'disambiguation':False},'homepages/a/2':{'disambiguation':False},'homepages/d':{'disambiguation':True}}
    aliases={'Li Wei 0001':{'homepages/a/1'},'Li Wei 0002':{'homepages/a/2'},'LI Wei':{'homepages/a/1'},
        'conflict':{'homepages/a/1','homepages/a/2'},'ambiguous':{'homepages/d'},'redirect':{'homepages/old'}}
    resolve=lambda name,redirects={}:resolve_signature({'name':name},aliases,profiles,redirects)
    assert resolve('Li Wei 0001')['key']!=resolve('Li Wei 0002')['key']
    assert resolve('LI Wei')['key']==resolve('Li Wei 0001')['key']
    assert resolve('li wei 0001')['status']=='unresolved_no_profile'
    assert resolve('conflict')['status']=='unresolved_ambiguous_alias'
    assert resolve('ambiguous')['status']=='unresolved_profile'
    assert resolve('redirect',{'homepages/old':'homepages/a/1'})['key']=='homepages/a/1'
    assert resolve('redirect',{'homepages/old':'homepages/old'})['status']=='unresolved_redirect_cycle'
