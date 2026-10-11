"""Read-only round58 HTTP acceptance against the SHA-verified offline graph oracle."""
import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import course_quality_app as app


def candidate_index(graph):
    nodes = {n['id']: n for n in graph['nodes']}
    links = {kind: {e['head']: e['tail'] for e in graph['edges'] if e['kind'] == kind}
             for kind in ('SUPPORTED_BY', 'HAS_HEAD', 'HAS_TAIL', 'DENOTES')}
    candidates = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    for assertion, paper in links['SUPPORTED_BY'].items():
        method = links['DENOTES'][links['HAS_HEAD'][assertion]]
        tail = nodes[links['DENOTES'][links['HAS_TAIL'][assertion]]]['props']
        if nodes[method]['props']['entityType'] != 'METHOD': continue
        allowed = {'USED_FOR': 'TASK', 'EVALUATED_ON': 'DATASET'}.get(nodes[assertion]['props']['predicate'])
        if tail['entityType'] == allowed: candidates[paper][method][allowed].add(tail['name'].lower())
    return nodes, candidates


def oracle_ids(nodes, candidates, params):
    def matches(name, terms):
        return any(name == t if params['conceptMatch'] == 'exact' else t in name for t in terms)
    result = []
    for paper, methods in candidates.items():
        props = nodes[paper]['props']
        if app.publication_view(props)['publicationStatus']['code'] == 'retraction_signal': continue
        for method, tails in methods.items():
            if params['method'] and not matches(nodes[method]['props']['name'].lower(), params['methodTerms']): continue
            if any(params[field] and not any(matches(t, params[field+'Terms']) for t in tails[typ])
                   for field, typ in (('task', 'TASK'), ('dataset', 'DATASET'))): continue
            result.append(props); break
    result.sort(key=lambda p: (-p['year'], p['publicationId']))
    return [p['publicationId'] for p in result]


def main(port, output):
    if output.exists(): raise FileExistsError('Preserve previous acceptance')
    if not output.resolve().is_relative_to((ROOT/'kg_datasets/dblp/course_v4_runs').resolve()): raise ValueError('Output outside runs')
    state = {'startedAtUTC': datetime.now(UTC).isoformat(), 'status': 'running', 'readOnly': True,
             'checks': [], 'oracleCases': [], 'aliasGroups': [], 'modelPromoted': False}
    def request(path, expected=200, **params):
        url = f'http://127.0.0.1:{port}'+path+('?' + urlencode(params) if params else '')
        started = time.perf_counter()
        try:
            with urlopen(url, timeout=30) as response: code, body = response.status, json.load(response)
        except HTTPError as response: code, body = response.code, json.load(response)
        except URLError as error:
            state['checks'].append({'url': url, 'expectedStatus': expected, 'actualStatus': None, 'error': str(error), 'seconds': time.perf_counter()-started})
            raise
        state['checks'].append({'url': url, 'expectedStatus': expected, 'actualStatus': code, 'response': body, 'seconds': time.perf_counter()-started})
        assert code == expected, (url, code)
        return body
    try:
        config_sha = app.g.c.file_sha256(app.CONFIG)
        state.update(runtimeConfig=app.CONFIG.relative_to(ROOT).as_posix(), runtimeConfigSha256=config_sha)
        bundle = app.g.configured_bundle(app.CONFIG); graph = app.g.verify_bundle(bundle)
        aliases = app.load_vocabulary(graph['manifest']); config, _, sha = aliases
        assert config['version'] == 'typed_controlled_aliases_v3'
        state.update(graphId=graph['manifest']['graphId'], manifestSha256=app.g.c.file_sha256(bundle/'manifest.json'),
                     vocabularySha256=sha, appCodeSha256=app.APP_CODE_SHA256, checkerSha256=app.g.c.file_sha256(Path(__file__)))
        nodes, candidates = candidate_index(graph)
        health = request('/api/health')['data']
        assert health['graphId'] == state['graphId'] and health['appCodeSha256'] == app.APP_CODE_SHA256
        assert health['conceptVocabulary']['sha256'] == sha and health['conceptVocabulary']['version'] == health['terminology']['version'] == config['version']
        assert health['conceptVocabulary']['modelReliabilityPromoted'] is False
        def verify(case):
            params = app.search_parameters({k: [v] for k, v in case.items()}, aliases)
            expected = oracle_ids(nodes, candidates, params)
            body = request('/api/publications', limit=100, **case)
            assert [p['publicationId'] for p in body['data']] == expected[:100], case
            assert body['meta']['hasNext'] == (len(expected) > 100) and body['meta']['aliasVersion'] == config['version']
            state['oracleCases'].append({'query': case, 'totalOracleMatches': len(expected), 'returnedIds': expected[:100]})
            return expected
        for terms in [('LoRA', 'low-rank adaptation', '低秩适配'), ('RAG', 'retrieval-augmented generation', '检索增强生成'),
                      ('random forest', 'random forests', '随机森林'), ('CNN', 'convolutional neural network', '卷积神经网络')]:
            results = [verify({'method': term}) for term in terms]
            assert all(result == results[0] for result in results)
            state['aliasGroups'].append({'terms': terms, 'equivalent': True, 'candidatePaperSupport': len(results[0]),
                'notice': 'Zero support is a measured candidate-relation coverage gap, not successful paper discovery.' if not results[0] else 'Candidate assertions, not verified scientific facts.'})
        for term in ('GPT-4', 'GPT-4o', 'QLoRA', 'AdaLoRA', 'RankRAG', 'GRU', 'CRF'):
            verify({'method': term})
        joint = [(p, m, t) for p, methods in candidates.items() for m, t in methods.items() if t['TASK'] and t['DATASET']]
        assert joint
        for paper, method, tails in sorted(joint, key=lambda x: nodes[x[0]]['props']['publicationId'])[:3]:
            assert verify({'method': nodes[method]['props']['name'], 'task': sorted(tails['TASK'])[0], 'dataset': sorted(tails['DATASET'])[0]})
        for status, code in (('retractions', 'retraction_signal'), ('corrections', 'correction_signal')):
            expected = sorted((n['props'] for n in graph['nodes'] if n['kind'] == 'Publication' and app.publication_view(n['props'])['publicationStatus']['code'] == code), key=lambda p: (-p['year'], p['publicationId']))
            body = request('/api/publications', publicationStatus=status, limit=100)
            assert [p['publicationId'] for p in body['data']] == [p['publicationId'] for p in expected[:100]]
            assert all(p['publicationStatus']['verified'] is False for p in body['data'])
            state[status+'TitleSignals'] = len(expected)
        assert not request('/api/publications', q='RETRACTED ARTICLE')['data']
        flagged = request('/api/publications', q='RETRACTED ARTICLE', publicationStatus='all')['data']; assert flagged
        pid = flagged[0]['publicationId']
        assert request('/api/publication', id=pid)['data']['publication']['publicationStatus']['code'] == 'retraction_signal'
        assert any(n['props'].get('publicationStatus', {}).get('code') == 'retraction_signal' for n in request('/api/graph', id=pid)['data']['nodes'])
        for params in ({'conceptMatch': 'bad'}, {'publicationStatus': 'verified'}, {'graphId': 'other'}): request('/api/publications', expected=400, **params)
        assert not request('/api/publications', method="x') MATCH (n) DELETE n //")['data']
        app.g.verified_files(bundle)
        if app.g.c.file_sha256(app.CONFIG) != config_sha: raise ValueError('Runtime config changed during acceptance')
        state.update(status='passed', graphFilesUnchanged=True, runtimeConfigUnchanged=True, noNewInference=True, noTraining=True,
            notice='HTTP/oracle equivalence and query boundaries only; no independent label accuracy or global normalization claim.')
    except Exception as error:
        state.update(status='failed', errorType=type(error).__name__, error=str(error)); raise
    finally:
        state['finishedAtUTC'] = datetime.now(UTC).isoformat(); app.g.c.write_json(output, state)
    print(json.dumps({'status': state['status'], 'HTTPChecks': len(state['checks']), 'oracleCases': len(state['oracleCases']), 'aliasGroups': state['aliasGroups']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--output', type=Path, default=ROOT/'kg_datasets/dblp/course_v4_runs/concept_app_acceptance_20261010_58.json')
    args = parser.parse_args(); main(args.port, args.output)
