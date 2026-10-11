"""Read-only live Cypher acceptance against the pinned graph's independent file oracle."""
import json
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import course_quality_app as app


def main():
    output = ROOT/'kg_datasets/dblp/course_v4_runs/search_repair_acceptance_20261009_final.json'
    if output.exists(): raise FileExistsError('Preserve previous acceptance')
    state = {'startedAtUTC':datetime.now(UTC).isoformat(), 'readOnly':True, 'checks':[], 'status':'running'}
    def request(path, expected=200, port=8766, **params):
        url = f'http://127.0.0.1:{port}'+path+('?' + urlencode(params) if params else '')
        started=time.perf_counter()
        try:
            with urlopen(url, timeout=30) as response: code, body = response.status, json.load(response)
        except HTTPError as response: code, body = response.code, json.load(response)
        state['checks'].append({'url':url, 'expectedStatus':expected, 'actualStatus':code, 'response':body, 'seconds':time.perf_counter()-started})
        assert code == expected, (url, code)
        return body
    try:
        bundle = app.g.configured_bundle(app.CONFIG); graph = app.g.verify_bundle(bundle)
        nodes = {n['id']:n for n in graph['nodes']}; edges = graph['edges']
        pubs = {i:n['props'] for i,n in nodes.items() if n['kind']=='Publication'}
        links = {kind:{e['head']:e['tail'] for e in edges if e['kind']==kind} for kind in ('SUPPORTED_BY','HAS_HEAD','HAS_TAIL','DENOTES')}
        candidates = defaultdict(lambda:defaultdict(lambda:defaultdict(set)))
        for a,p in links['SUPPORTED_BY'].items():
            m = links['DENOTES'][links['HAS_HEAD'][a]]; t = nodes[links['DENOTES'][links['HAS_TAIL'][a]]]['props']
            candidates[p][m][t['entityType']].add(t['name'].lower())
        health = request('/api/health')['data']
        assert health['graphId']==graph['manifest']['graphId'] and health['appCodeSha256']==app.APP_CODE_SHA256
        assert request('/api/health',port=8765)['data']['appCodeSha256']==app.APP_CODE_SHA256
        for status, expected in [('retractions',14),('corrections',9)]:
            data=request('/api/publications',publicationStatus=status,limit=100)['data']
            assert len(data)==expected and all(p['publicationStatus']['verified'] is False for p in data)
        assert not request('/api/publications',q='RETRACTED ARTICLE')['data']
        flagged=request('/api/publications',q='RETRACTED ARTICLE',publicationStatus='all')['data']; assert flagged
        pid=flagged[0]['publicationId']
        assert request('/api/publication',id=pid)['data']['publication']['publicationStatus']['code']=='retraction_signal'
        assert any(n['props'].get('publicationStatus',{}).get('code')=='retraction_signal' for n in request('/api/graph',id=pid)['data']['nodes'])

        cases=[{'method':'GPT-4'}, {'method':'GPT-4','conceptMatch':'contains'}, {'method':'CNN'}, {'method':'卷积神经网络'}]
        joint=[(p,m,t) for p,methods in candidates.items() for m,t in methods.items() if t['TASK'] and t['DATASET']]
        assert joint
        for p,m,t in sorted(joint,key=lambda row:pubs[row[0]]['publicationId'])[:3]:
            cases.append({'method':nodes[m]['props']['name'], 'task':sorted(t['TASK'])[0], 'dataset':sorted(t['DATASET'])[0]})
        def matches(name,terms,mode): return not terms or any(name==term if mode=='exact' else term in name for term in terms)
        for case in cases:
            params=app.search_parameters({k:[v] for k,v in case.items()}); expected=[]
            for p,methods in candidates.items():
                if app.publication_view(pubs[p])['publicationStatus']['code']=='retraction_signal': continue
                for m,t in methods.items():
                    if not matches(nodes[m]['props']['name'].lower(),params['methodTerms'],params['conceptMatch']): continue
                    if params['task'] and not any(matches(name,params['taskTerms'],params['conceptMatch']) for name in t['TASK']): continue
                    if params['dataset'] and not any(matches(name,params['datasetTerms'],params['conceptMatch']) for name in t['DATASET']): continue
                    expected.append(pubs[p]); break
            expected.sort(key=lambda p:(-p['year'],p['publicationId']))
            actual=request('/api/publications',limit=100,**case)
            assert [p['publicationId'] for p in actual['data']]==[p['publicationId'] for p in expected[:100]],case
            assert actual['meta']['hasNext']==(len(expected)>100)
            assert expected,case
        request('/api/publications',expected=400,conceptMatch='bad')
        request('/api/publications',expected=400,publicationStatus='verified')
        request('/api/publications',expected=400,graphId='other')
        assert not request('/api/publications',method="x') MATCH (n) DELETE n //")['data']
        state.update(status='passed', oracleCases=len(cases), graphId=health['graphId'], graphFilesUnchanged=True,
            appCodeSha256=app.APP_CODE_SHA256, titleStatusCounts={'retractionSignals':14,'correctionSignals':9}, modelPromoted=False)
        app.g.verified_files(bundle)
    except Exception as error:
        state.update(status='failed',errorType=type(error).__name__,error=str(error)); raise
    finally:
        state['finishedAtUTC']=datetime.now(UTC).isoformat(); app.g.c.write_json(output,state)
    print(json.dumps({'status':state['status'],'HTTPChecks':len(state['checks']),'oracleCases':state['oracleCases']}))


if __name__=='__main__': main()
