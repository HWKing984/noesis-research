"""Read-only live application acceptance; no passwords, training or database writes."""
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_graph as g


def main():
    output = ROOT / 'kg_datasets/dblp/course_v4_runs/application_acceptance_20261007_26.json'
    if output.exists(): raise FileExistsError('Preserve actual acceptance; choose a new output path')
    bundle = ROOT / 'kg_datasets/dblp/course_v4_graph_production_20261007_25'
    manifest = g.verified_files(bundle)
    state = {'status': 'running', 'startedAtUTC': datetime.now(UTC).isoformat(),
             'graphId': manifest['graphId'], 'kind': 'live_http_application_acceptance',
             'readOnly': True, 'modelQualityEvaluation': False, 'checks': []}

    def request(path, expected=200):
        try:
            with urlopen('http://127.0.0.1:8765' + path, timeout=30) as response:
                status, raw = response.status, response.read()
        except HTTPError as error:
            status, raw = error.code, error.read()
        body = json.loads(raw)
        state['checks'].append({'path': path, 'httpStatus': status, 'body': body})
        assert status == expected, (path, status)
        return body

    try:
        health = request('/api/health')['data']
        assert health['status'] == 'ready' and health['graphId'] == manifest['graphId']
        assert health['source'] == 'live_neo4j'
        assert health['scope'] == {'bibliographyTitles': 20000, 'modelTitles': 19999,
                                   'rejectedNERTitles': 1, 'candidateAssertions': 21497}
        pid = 'conf/3dim/VavilalaVF25'
        detail = request('/api/publication?' + urlencode({'id': pid}))['data']
        paper = detail['publication']; title = paper['title']
        assert paper['publicationId'] == pid and paper['graphId'] == manifest['graphId']
        assert paper['modelApplied'] and len(detail['authors']) == 3 and detail['venues'][0]['name'] == '3DV'
        assert len(detail['mentions']) == 2 and len(detail['assertions']) == 1
        assert detail['authors'][0]['name'] in detail['citationDraft'] and paper['doi'] in detail['citationDraft']
        for mention in detail['mentions']:
            assert title[mention['start']:mention['end']] == mention['text']
            assert mention['textSha256'] == hashlib.sha256(title.encode()).hexdigest()
        assertion = detail['assertions'][0]['assertion']
        assert assertion['status'] == 'candidate' and assertion['confidenceCalibrated'] is False
        assert assertion['sourceRunManifestSha256'] == manifest['modelSourceManifestSha256']
        cases = [{'q': 'Denoising Monte Carlo Renders'}, {'author': 'Vaibhav Vavilala', 'year': 2025},
                 {'venue': '3DV', 'q': 'Denoising Monte Carlo'},
                 {'method': 'Diffusion Models', 'task': 'Denoising Monte Carlo Renders'}]
        for params in cases:
            result = request('/api/publications?' + urlencode(params | {'limit': 100}))
            assert result['meta']['source'] == 'live_neo4j'
            assert any(p['publicationId'] == pid for p in result['data']), params
        dataset = request('/api/publications?' + urlencode({'dataset': 'wisconsin', 'limit': 100}))
        assert dataset['data'], 'Known dataset candidate search returned no result'
        for params in ({'limit': 1}, {'limit': 1, 'offset': 1}):
            page = request('/api/publications?' + urlencode(params))
            assert len(page['data']) == 1 and page['meta']['hasNext']
        assert state['checks'][-1]['body']['data'][0]['publicationId'] != state['checks'][-2]['body']['data'][0]['publicationId']
        assert request('/api/publications?q=course26_no_such_literature_92837')['data'] == []
        rejected = request('/api/publication?' + urlencode({'id': 'journals/idt/Tsihrintzis25a'}))['data']
        assert not rejected['publication']['modelApplied']
        assert rejected['publication']['modelApplicationStatus'] == 'rejected'
        assert rejected['publication']['modelApplicationReason'] and not rejected['mentions'] and not rejected['assertions']
        request('/api/publication?id=course26_missing_publication', 404)
        for path in ('/api/publications?limit=0', '/api/publications?year=2010',
                     '/api/publication?id=a&id=b', '/api/health?unexpected=1'):
            request(path, 400)
        request('/course26_unknown_endpoint', 404)
        state.update(status='completed', passed=True, checkedRequests=len(state['checks']))
    except Exception as error:
        state.update(status='failed', passed=False, error=str(error))
        raise
    finally:
        state['finishedAtUTC'] = datetime.now(UTC).isoformat()
        g.c.write_json(output, state)
    print(json.dumps({k: state[k] for k in ('status', 'passed', 'checkedRequests', 'graphId')}))


if __name__ == '__main__': main()
