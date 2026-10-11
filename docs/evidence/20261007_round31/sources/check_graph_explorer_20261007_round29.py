"""Actual read-only HTTP acceptance; retain original graph responses and failures."""
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / 'scripts'))
import course_weak as c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError('Preserve actual acceptance')
    if args.port not in (8765,8766): raise ValueError('Only the scoped local demo ports')
    state = {'status':'running','createdAtUTC':datetime.now(UTC).isoformat(),'readOnly':True,'checks':[],
             'baseURL':f'http://127.0.0.1:{args.port}','modelQualityEvaluation':False}
    def check(path,expected=200,*,headers=None,method=None):
        request = Request(state['baseURL']+path,headers=headers or {},method=method)
        try:
            with urlopen(request,timeout=30) as response: status,body = response.status,response.read()
        except HTTPError as response: status,body = response.code,response.read()
        try: parsed = json.loads(body)
        except ValueError: parsed = {'bodyFormat':'non_json'}
        state['checks'].append({'path':path,'expectedStatus':expected,'actualStatus':status,'response':parsed})
        assert status == expected, path
        return parsed
    try:
        health = check('/api/health')['data']; state['graphId'] = health['graphId']
        assert health['scope']['bibliographyTitles'] == 20000
        pid = 'conf/3dim/VavilalaVF25'
        for mode in ('paper','coauthors','methods'):
            body = check('/api/graph?'+urlencode({'id':pid,'mode':mode,'limit':30}))
            nodes,edges,meta = body['data']['nodes'],body['data']['edges'],body['meta']
            ids = {n['props']['id'] for n in nodes}
            assert nodes and edges and len(ids) == len(nodes)
            assert all(n['props']['graphId'] == state['graphId'] for n in nodes)
            assert all(e['source'] in ids and e['target'] in ids for e in edges)
            assert meta['source'] == 'live_neo4j' and not meta['wholeGraph'] and meta['pathsReturned'] <= 30
            if mode == 'paper':
                assert len(nodes) == 10 and len(edges) == 11
                assert {n['kind'] for n in nodes} == {'Publication','Person','Venue','Concept','Mention','Assertion'}
            else: assert any(n['kind'] == 'Publication' and n['props']['publicationId'] != pid for n in nodes)
        limited = check('/api/graph?'+urlencode({'id':pid,'limit':1}))
        assert limited['meta']['pathsReturned'] == 1 and limited['meta']['hasMorePaths']
        check('/api/graph?'+urlencode({'id':'not-a-publication'}),404)
        check('/api/graph?'+urlencode({'id':"x') MATCH (n) DETACH DELETE n //"}),404)
        for params in ({'id':pid,'mode':'unsupported'},{'id':pid,'limit':0},{'id':pid,'limit':51},
                       {'mode':'paper'},{'id':pid,'unknown':'x'}):
            check('/api/graph?'+urlencode(params),400)
        check('/api/graph?'+urlencode({'id':pid})+'&id=another',400)
        check('/api/graph?'+urlencode({'id':pid}),501,method='POST')
        check('/api/health',403,headers={'Host':'evil.example'})
        state.update(status='completed',passed=True)
    except Exception as error:
        state.update(status='failed',passed=False,error=str(error)); raise
    finally:
        state['finishedAtUTC'] = datetime.now(UTC).isoformat()
        c.write_json(args.output,state)
    print(json.dumps({'passed':True,'HTTPChecks':len(state['checks']),'baseURL':state['baseURL']}))


if __name__ == '__main__': main()
