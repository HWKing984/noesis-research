"""Current pinned graph acceptance: real reads only; no model test or data writes."""
import getpass
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'scripts'))
import course_graph as g


def main():
    output=ROOT/'kg_datasets/dblp/course_v4_runs/application_acceptance_20261009_50_final.json'
    if output.exists(): raise FileExistsError('Preserve actual acceptance')
    bundle=g.configured_bundle(); manifest=g.verified_files(bundle)
    state={'startedAtUTC':datetime.now(UTC).isoformat(),'readOnly':True,'graphId':manifest['graphId'],'modelQualityEvaluation':False,'modelPromoted':False,'sourceSha256':g.c.file_sha256(Path(__file__)),'HTTPChecks':[],'databaseChecks':[]}
    def request(path,expected=200,**params):
        route=path+('?' + urlencode(params) if params else '')
        try:
            with urlopen('http://127.0.0.1:8765'+route,timeout=30) as response: status,body=response.status,json.load(response)
        except HTTPError as response: status,body=response.code,json.load(response)
        state['HTTPChecks'].append({'route':route,'expectedStatus':expected,'actualStatus':status,'response':body})
        assert status==expected,(route,status)
        return body
    try:
        health=request('/api/health')['data']
        assert health['status']=='ready' and health['source']=='live_neo4j' and health['graphId']==manifest['graphId']
        assert health['scope']=={'bibliographyTitles':20000,'modelTitles':19999,'rejectedNERTitles':1,'candidateAssertions':21497}
        assert health['resolution']['resolvedPersonNodes']==66091 and health['terminology']==g.TERMINOLOGY
        pid='conf/3dim/VavilalaVF25'; detail=request('/api/publication',id=pid)['data']; paper=detail['publication']
        assert paper['graphId']==manifest['graphId'] and paper['publicationId']==pid and len(detail['authors'])==3 and detail['venues'][0]['name']=='3DV'
        assert len(detail['mentions'])==2 and len(detail['assertions'])==1 and paper['doi'] in detail['citationDraft']
        for mention in detail['mentions']:
            assert paper['title'][mention['start']:mention['end']]==mention['text'] and mention['textSha256']==hashlib.sha256(paper['title'].encode()).hexdigest()
        for relation in detail['assertions']:
            assert relation['assertion']['status']=='candidate' and relation['assertion']['confidenceCalibrated'] is False and relation['assertion']['sourceRunManifestSha256']==manifest['modelSourceManifestSha256']
        comparisons=[]
        for field,zh,en in [('q','知识图谱','knowledge graph'),('q','大语言模型','large language model'),('method','扩散模型','diffusion model'),('task','机器翻译','machine translation'),('venue','AAAI会议','aaai')]:
            chinese=request('/api/publications',**{field:zh,'limit':100}); english=request('/api/publications',**{field:en,'limit':100})
            assert chinese['meta']['source']=='live_neo4j' and chinese['data'] and chinese['data']==english['data'] and chinese['meta']['expandedTerms'][field][0]==zh.lower()
            comparisons.append({'field':field,'zh':zh,'en':en,'orderedFirstPageEqual':True,'pageSize':len(chinese['data']),'allPagesCompared':False})
        state['chineseComparisons']=comparisons
        found=request('/api/publications',method='扩散模型',q='Denoising Monte Carlo Renders')['data']
        assert len(found)==1 and found[0]['publicationId']==pid
        author=next(a for a in detail['authors'] if a['identityStatus']=='dblp_homepage_resolved')
        for identity in (author['personId'],author['dblpPid']):
            papers=request('/api/publications',authorId=identity,limit=50)['data']; assert papers
            for row in papers[:3]:
                d=request('/api/publication',id=row['publicationId'])['data']; assert any(a['personId']==author['personId'] for a in d['authors'])
        signatures=g.c.read_jsonl(ROOT/'kg_datasets/dblp/course_v4_identity_20261007_31_recovered/signatures.jsonl')
        unresolved=next(s for s in signatures if s['identity']['status']!='dblp_homepage_resolved')
        d=request('/api/publication',id=unresolved['publicationId'])['data']; a=next(a for a in d['authors'] if a['position']==unresolved['position'])
        assert a['personId'].startswith('unresolved-signature:') and [p['publicationId'] for p in request('/api/publications',authorId=a['personId'],limit=50)['data']]==[unresolved['publicationId']]
        assert request('/api/publication',id='conf/wacv/AhnKKPK23')['data']['authors'][1]['signatureName']=='Hyungjun Kim'
        pages=[request('/api/publications',limit=1,offset=n) for n in (0,1)]
        assert all(len(p['data'])==1 and p['meta']['hasNext'] for p in pages) and pages[0]['data'][0]['publicationId']!=pages[1]['data'][0]['publicationId']
        assert not request('/api/publications',q='course_round50_missing_8091')['data']
        assert not request('/api/publications',authorId="x') MATCH (n) DETACH DELETE n //")['data']
        rejected=request('/api/publication',id='journals/idt/Tsihrintzis25a')['data']
        assert not rejected['publication']['modelApplied'] and rejected['publication']['modelApplicationStatus']=='rejected' and not rejected['mentions'] and not rejected['assertions']
        for path,expected in [('/api/publications?limit=0',400),('/api/publications?year=2010',400),('/api/publications?q=a&q=b',400),('/api/publications?qTerms=forged',400),('/api/health?unexpected=1',400),('/api/publication?id=round50_missing',404),('/round50_unknown',404)]: request(path,expected)
        client=g.Neo4j('http://127.0.0.1:7474','neo4j','neo4j',getpass.getpass('Neo4j password (not saved): ')); parameters={'graph':manifest['graphId']}
        def query(name,statement):
            rows=client.query(statement,parameters); state['databaseChecks'].append({'name':name,'cypher':statement,'rows':rows}); return rows
        nodes={kind:query('count_'+kind,f'MATCH (n:Course{kind} {{graphId:$graph}}) RETURN count(n) AS count')[0]['count'] for kind in g.KINDS}
        edges={r['kind']:r['count'] for r in query('edge_counts','MATCH (a:CourseNode {graphId:$graph})-[r]->(b:CourseNode {graphId:$graph}) WHERE r.graphId=$graph RETURN type(r) AS kind,count(r) AS count')}
        assert {'nodes':nodes,'edges':edges}==manifest['counts'] and sum(nodes.values())==194639 and sum(edges.values())==263059
        assert query('cross_scope_edges','MATCH (a:CourseNode {graphId:$graph})-[r]->(b) WHERE coalesce(r.graphId,"")<>$graph OR coalesce(b.graphId,"")<>$graph RETURN count(r) AS count')[0]['count']==0
        state.update(status='completed',passed=True,nodeCount=sum(nodes.values()),edgeCount=sum(edges.values()),bundleManifestSha256=g.c.file_sha256(bundle/'manifest.json'),sourceSha256=g.c.file_sha256(Path(__file__)))
    except Exception as error:
        state.update(status='failed',passed=False,errorType=type(error).__name__,error=str(error)); raise
    finally:
        state['finishedAtUTC']=datetime.now(UTC).isoformat(); g.c.write_json(output,state)
    print(json.dumps({'passed':True,'HTTPChecks':len(state['HTTPChecks']),'databaseChecks':len(state['databaseChecks']),'nodes':state['nodeCount'],'edges':state['edgeCount']}))


if __name__=='__main__': main()
