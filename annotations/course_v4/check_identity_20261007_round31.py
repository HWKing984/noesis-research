"""Real HTTP author identity acceptance, not model accuracy evaluation."""
import json
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import course_weak as c

def main():
    output=ROOT/'kg_datasets/dblp/course_v4_runs/identity_acceptance_20261007_31.json'
    if output.exists(): raise FileExistsError('Preserve actual acceptance')
    state={'status':'running','checks':[],'modelQualityEvaluation':False}
    def get(route,**params):
        with urlopen('http://127.0.0.1:8765'+route+'?'+urlencode(params),timeout=30) as response:
            body=json.load(response)
        state['checks'].append({'route':route,'parameters':params,'response':body})
        return body['data']
    try:
        health=get('/api/health');assert health['resolution']['resolvedPersonNodes']==66091
        detail=get('/api/publication',id='conf/3dim/VavilalaVF25')
        resolved=[a for a in detail['authors'] if a['identityStatus']=='dblp_homepage_resolved']
        assert resolved and all(a['signatureName'] for a in detail['authors'])
        for a in resolved:
            for key in (a['personId'],a['dblpPid']):
                results=get('/api/publications',authorId=key,limit=50)
                assert results
                for row in results[:3]:
                    d=get('/api/publication',id=row['publicationId'])
                    assert any(person['personId']==a['personId'] for person in d['authors'])
        corrected=get('/api/publication',id='conf/wacv/AhnKKPK23')
        assert corrected['authors'][1]['signatureName']=='Hyungjun Kim'
        signatures=c.read_jsonl(ROOT/'kg_datasets/dblp/course_v4_identity_20261007_31_recovered/signatures.jsonl')
        unresolved=next(s for s in signatures if s['identity']['status']!='dblp_homepage_resolved')
        d=get('/api/publication',id=unresolved['publicationId'])
        a=next(a for a in d['authors'] if a['position']==unresolved['position'])
        assert a['personId'].startswith('unresolved-signature:')
        results=get('/api/publications',authorId=a['personId'],limit=50)
        assert [r['publicationId'] for r in results]==[unresolved['publicationId']]
        assert not get('/api/publications',authorId="x') MATCH (n) DETACH DELETE n //")
        state.update(status='completed',passed=True,graphId=health['graphId'])
    except Exception as error:
        state.update(status='failed',passed=False,error=str(error));raise
    finally:c.write_json(output,state)

if __name__=='__main__':main()
