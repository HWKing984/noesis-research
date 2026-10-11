import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import course_v2_sampling as s
import prepare_v2_sampling as p


def page(ids, total=None):
    # Synthetic metadata only, not real paper identities or evaluation references.
    total=len(ids) if total is None else total
    html='<p>Total of '+str(total)+' entries</p><dl>'
    for value in ids:html+='<dt><a href="/abs/'+value+'">id</a></dt><dd><div class="list-title"><span>Title:</span> Synthetic title '+value+'</div></dd>'
    return (html+'</dl>').encode()


@pytest.fixture
def protocol():
    return {'sourceURL':'https://arxiv.org/list/cs.AI/2025-02','pageSize':2000,'seed':20261011,
        'samplingMethod':s.METHOD,'devSize':2,'testSize':2,'challengeSize':0}


def test_listing_parses_only_metadata():
    count,rows=s.parse_listing(page(['2502.00001','2502.00002']))
    assert count==2 and set(rows[0])==s.META and rows[0]['title']=='Synthetic title 2502.00001'


@pytest.mark.parametrize('fault',['abstract','duplicate','missing_title','missing_total'])
def test_listing_rejects_wrong_source_content(fault):
    payload=page(['2502.00001'])
    if fault=='abstract':payload+=b'<blockquote class="abstract">Never parse a reserved body.</blockquote>'
    elif fault=='duplicate':payload=page(['2502.00001','2502.00001'])
    elif fault=='missing_title':payload=payload.replace(b'list-title',b'other')
    else:payload=payload.replace(b'Total of',b'Count')
    with pytest.raises(ValueError):s.parse_listing(payload)


def test_complete_population_excludes_exposed_versions(protocol):
    ids=['2502.0000'+str(n) for n in range(1,6)]
    pages=[{'sourceURL':protocol['sourceURL']+'?skip=0&show=2000','payload':page(ids)}]
    aliases={'byPublication':{},'blockedPublications':{}}
    eligible,rejected,total=s.population(pages,protocol,[{'arxivId':'ARXIV:2502.00001v3','origin':'train'}],aliases)
    assert total==5 and len(eligible)==4 and rejected[0]['arxivId']=='2502.00001'
    chosen=s.draw(eligible,protocol)
    assert len(chosen)==4 and [r['split'] for r in chosen]==['dev','dev','test','test']
    assert s.draw(eligible,protocol)==chosen


@pytest.mark.parametrize('fault',['wrong_url','wrong_page','truncated','repeat_page'])
def test_population_requires_full_bound_listing(protocol,fault):
    pages=[{'sourceURL':protocol['sourceURL']+'?skip=0&show=2000','payload':page(['2502.00001'])}]
    if fault=='wrong_url':pages[0]['sourceURL']=pages[0]['sourceURL'].replace('arxiv.org','example.org')
    elif fault=='wrong_page':pages[0]['sourceURL']=pages[0]['sourceURL'].replace('skip=0','skip=1')
    elif fault=='truncated':pages[0]['payload']=page(['2502.00001'],2)
    else:pages.append(copy.deepcopy(pages[0]))
    with pytest.raises(ValueError):s.population(pages,protocol,[],{'byPublication':{},'blockedPublications':{}})


def test_draw_cannot_silently_shrink_or_use_purposive_challenge(protocol):
    rows=[{'arxivId':'2502.00001','sourceURL':'https://arxiv.org/abs/2502.00001','title':'synthetic'}]
    with pytest.raises(ValueError):s.draw(rows,protocol)
    with pytest.raises(ValueError):s.draw(rows,protocol|{'challengeSize':1})


def test_boolean_alone_is_not_verified_frame(tmp_path):
    with pytest.raises(FileNotFoundError):s.validate_frame(tmp_path,[],{'byPublication':{},'blockedPublications':{}})


def frame_fixture(tmp_path, protocol):
    protocol=protocol|{'version':'course_v2_sampling_v1','population':s.admission.FRAME['population'],
        'category':'cs.AI','listingMonth':'2025-02','scope':'Synthetic metadata fixture only, not an actual evaluation cohort.'}
    payload=page(['2502.0000'+str(n) for n in range(1,6)])
    source=tmp_path/'source.html';source.write_bytes(payload)
    aliases={'byPublication':{},'blockedPublications':{}}
    url=protocol['sourceURL']+'?skip=0&show=2000'
    eligible,rejected,total=s.population([{'sourceURL':url,'payload':payload}],protocol,[],aliases)
    selected=s.draw(eligible,protocol)
    for name,value in [('sampling_protocol',protocol),('selected_members',selected)]:p.write(tmp_path/(name+'.json'),value)
    p.jsonl(tmp_path/'population.jsonl',eligible);p.jsonl(tmp_path/'excluded_population.jsonl',rejected)
    receipt={'protocolSha256':s.admission.digest(protocol),'exclusionsSha256':s.admission.digest([]),'aliasIndexSha256':s.admission.digest(aliases),
        'sourcePages':[{'sourceURL':url,'file':source.name,'sha256':p.sha(source)}], 'sourceListingCount':total,'eligiblePopulationCount':5,
        'excludedPopulationCount':0,'populationSha256':s.admission.digest(eligible),'selectedMembersSha256':s.admission.digest(selected),
        'selectionCounts':{'dev':2,'test':2,'challenge':0},'inclusionProbabilities':{'dev':0.4,'test':0.4},'seed':protocol['seed'],
        'samplingMethod':protocol['samplingMethod'],'samplingFrameLocked':True,'fullDBLPRepresentative':False,
        'contentBindingCompleted':False,'evaluationAuthorized':False}
    p.write(tmp_path/'sampling_frame.json',receipt)
    return aliases,receipt,selected


def test_frame_replays_real_bound_files_and_never_authorizes(tmp_path,protocol):
    aliases,receipt,selected=frame_fixture(tmp_path,protocol)
    assert s.validate_frame(tmp_path,[],aliases)==(selected,receipt)
    lock=s.prelock(tmp_path,[],[],aliases)
    assert lock['counts']=={'dev':2,'test':2} and lock['status']=='pending_content_binding' and lock['evaluationAuthorized'] is False
    with pytest.raises(ValueError):s.finalize(tmp_path,lock,{},[],aliases,tmp_path)


@pytest.mark.parametrize('fault',['source_changed','seed','probability','population_count','exposure_context','selected_member','locked_boolean','authorization'])
def test_frame_rejects_unbound_or_modified_sampling_records(tmp_path,protocol,fault):
    aliases,receipt,selected=frame_fixture(tmp_path,protocol)
    if fault=='source_changed':(tmp_path/'source.html').write_bytes(b'changed metadata')
    elif fault=='seed':receipt['seed']+=1
    elif fault=='probability':receipt['inclusionProbabilities']['dev']=1.0
    elif fault=='population_count':receipt['eligiblePopulationCount']+=1
    elif fault=='exposure_context':receipt['exclusionsSha256']='0'*64
    elif fault=='selected_member':selected[0]['split']='test';p.write(tmp_path/'selected_members.json',selected)
    elif fault=='locked_boolean':receipt['samplingFrameLocked']=False
    else:receipt['evaluationAuthorized']=True
    p.write(tmp_path/'sampling_frame.json',receipt)
    with pytest.raises(ValueError):s.validate_frame(tmp_path,[],aliases)


def test_train_screening_cannot_authorize_or_rewrite_negatives():
    old=p.ROOT/'kg_datasets/dblp/course_v2_admission_20261010'; decisions=s.read(p.DECISIONS)
    reviews,candidate=p.negatives(old,decisions)
    assert len(reviews)==12 and candidate['priorLabel']=='UNRESOLVED' and candidate['proposedLabel']=='NO_RELATION'
    assert candidate['trainingAuthorized'] is False and candidate['candidateEligible'] is False
    assert candidate['head']['text']=='pooling' and candidate['tail']['text']=='MNIST'
    changed=copy.deepcopy(decisions);changed['candidate']['trainingAuthorized']=True
    with pytest.raises(ValueError):p.negatives(old,changed)


def test_existing_output_is_preserved(tmp_path):
    with pytest.raises(FileExistsError):p.prepare(tmp_path)
