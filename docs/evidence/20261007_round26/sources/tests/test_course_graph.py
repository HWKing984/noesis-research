"""Graph engineering checks; synthetic cases are not model accuracy evidence."""
import json
import sys
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import course_graph as g


def test_candidates_use_predictions_and_preserve_literal_evidence():
    doc = {'sampleId': 's', 'text': 'BERT for tagging', 'textSha256': g.digest('BERT for tagging')}
    entities = [{'start': 0, 'end': 4, 'text': 'BERT', 'label': 'METHOD'},
                {'start': 9, 'end': 16, 'text': 'tagging', 'label': 'TASK'}]
    pair = doc | {'head': entities[0], 'tail': entities[1], 'label': 'USED_FOR',
                  'probabilities': {'USED_FOR': .8, 'EVALUATED_ON': 0., 'NO_RELATION': .2}, 'pairId': 'p'}
    nodes, edges = g.candidate_graph('test', [doc], [{'sampleId': 's', 'predictedEntities': entities}],
                                     [pair], {'s': 'paper'}, {'NERWeightsSha256': 'n', 'REWeightsSha256': 'r'})
    assertion = next(n for n in nodes if n['kind'] == 'Assertion')['props']
    assert assertion['source'] == 'model_prediction' and assertion['status'] == 'candidate'
    assert assertion['evidence'] == doc['text'] and assertion['confidenceCalibrated'] is False
    production_nodes, _ = g.candidate_graph('prod', [doc], [{'sampleId':'s','predictedEntities':entities}],
        [pair], {'s':'paper'}, {'NERWeightsSha256':'n','REWeightsSha256':'r'}, source_run_sha='new-production-source')
    assert all(n['props']['sourceRunManifestSha256']=='new-production-source' for n in production_nodes if n['kind'] in ('Mention','Assertion'))
    assert len([e for e in edges if e['kind'] == 'HAS_HEAD']) == 1
    negative = pair | {'label': 'NO_RELATION', 'probabilities': {'USED_FOR': .2, 'EVALUATED_ON': 0., 'NO_RELATION': .8}}
    assert not any(n['kind'] == 'Assertion' for n in g.candidate_graph('t', [doc], [{'sampleId': 's', 'predictedEntities': entities}], [negative], {'s': 'paper'}, {})[0])
    for bad in (pair | {'label': 'EVALUATED_ON'}, pair | {'text': 'forged'}, pair | {'probabilities': {}},
                pair | {'tail': entities[1] | {'start': 10}}, pair | {'sampleId': 'other'}):
        with pytest.raises(ValueError):
            g.candidate_graph('t', [doc], [{'sampleId': 's', 'predictedEntities': entities}], [bad], {'s': 'paper'}, {})


def test_parameters_are_bounded_and_never_interpolated():
    value = "x') MATCH (n) DETACH DELETE n //"
    p = g.search_parameters({'q': [value], 'limit': ['20'], 'year': ['2024']})
    assert p['q'] == value.lower() and p['year'] == 2024
    assert value not in g.SEARCH_QUERY
    for query in ({'limit': ['0']}, {'limit': ['101']}, {'year': ['abc']}, {'offset': ['-1']},
                  {'q': ['x', 'y']}, {'unknown': ['x']}, {'q': ['x' * 201]}):
        with pytest.raises(ValueError): g.search_parameters(query)


def test_production_export_resolves_relative_cli_path(tmp_path, monkeypatch):
    seen=[]
    def stop_before_read(folder, expected=None):
        seen.append(folder)
        raise RuntimeError('path-check-only')
    monkeypatch.setattr(g,'verified_files',stop_before_read)
    source=Path('kg_datasets/dblp/course_v4_runs/corpus_pilot_20261007_25')
    # Manifest hash is read before verification; the real sealed pilot is preserved.
    monkeypatch.setattr(g.c,'file_sha256',lambda path:'synthetic-sha')
    with pytest.raises(RuntimeError,match='path-check-only'):
        g.export_graph(tmp_path/'new',production=source)
    assert seen==[source.resolve()]


def test_neo4j_errors_never_masquerade_as_success(monkeypatch):
    gclient = g.Neo4j('http://127.0.0.1:7474', 'neo4j', 'neo4j', 'synthetic-secret')
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"errors":[{"code":"Neo.ClientError.Statement.SyntaxError","message":"private detail"}]}'
    monkeypatch.setattr(g, 'urlopen', lambda *a, **k: Response())
    with pytest.raises(g.DatabaseUnavailable) as exc: gclient.query('RETURN 1', {})
    assert 'private detail' not in str(exc.value) and 'synthetic-secret' not in str(exc.value)
    for url in ('http://evil.example:7474', 'http://user:secret@localhost:7474', 'ftp://localhost'):
        with pytest.raises(ValueError): g.Neo4j(url, 'neo4j', 'neo4j', 'secret')
    for body in (b'{}', b'{"data":{"fields":["a"],"values":[[]]}}', b'invalid'):
        monkeypatch.setattr(Response, 'read', lambda self, b=body: b)
        with pytest.raises(g.DatabaseUnavailable): gclient.query('RETURN 1', {})
    monkeypatch.setattr(Response, 'read', lambda self: b'{"data":{"fields":["connected"],"values":[[1]]}}')
    assert gclient.query('RETURN 1', {}) == [{'connected': 1}]
    def unauthorized(*args, **kwargs): raise HTTPError('url', 401, 'secret', None, None)
    monkeypatch.setattr(g, 'urlopen', unauthorized)
    with pytest.raises(g.DatabaseUnavailable, match='401'): gclient.query('RETURN 1', {})


def test_real_export_and_tamper_detection(tmp_path):
    bundle = tmp_path / 'graph'
    manifest = g.export_graph(bundle)
    assert manifest['counts']['nodes']['Publication'] == 20000
    assert manifest['counts']['nodes']['Assertion'] == 140
    assert manifest['scope']['modelTitles'] == 138 and manifest['scope']['pipelinePairs'] == 148
    assert manifest['liveDatabaseImported'] is False
    data = g.verify_bundle(bundle)
    assert len(data['nodes']) == sum(manifest['counts']['nodes'].values())
    with pytest.raises(FileExistsError): g.export_graph(bundle)
    with (bundle / 'nodes.jsonl').open('a', encoding='utf-8') as stream: stream.write('{}\n')
    with pytest.raises(ValueError): g.verify_bundle(bundle)


def test_scoped_idempotent_import_and_failure_receipt(tmp_path, monkeypatch):
    node = {'kind': 'Publication', 'id': 'n', 'props': {'graphId': 'test', 'id': 'n'}}
    counts = {'nodes': {'Publication': 1}, 'edges': {}}
    bundle = tmp_path / 'bundle'; bundle.mkdir(); c = g.c
    c.write_json(bundle / 'manifest.json', {})
    monkeypatch.setattr(g, 'verify_bundle', lambda b: {'manifest': {'graphId': 'test', 'counts': counts}, 'nodes': [node], 'edges': []})
    class Client:
        queries = []
        def query(self, statement, parameters):
            self.queries.append(statement)
            if 'RETURN g.status' in statement: return []
            if 'UNWIND' in statement: return [{'count': len(parameters['rows'])}]
            if 'RETURN count(n)' in statement: return [{'count': int('CoursePublication' in statement)}]
            if 'RETURN count(r)' in statement: return [{'count': 0}]
            return [{'id': 'test'}]
    client = Client(); receipt = tmp_path / 'ok.json'
    assert g.import_graph(client, bundle, receipt)['actualCounts'] == counts
    assert all('DELETE' not in q and 'DROP' not in q for q in client.queries)
    assert any('MERGE (n:CourseNode:CoursePublication:Publication' in q for q in client.queries)
    with pytest.raises(FileExistsError): g.import_graph(client, bundle, receipt)
    class Failed:
        def query(self, *args): raise g.DatabaseUnavailable('Neo4j HTTP 401')
    failed = tmp_path / 'failed.json'
    with pytest.raises(g.DatabaseUnavailable): g.import_graph(Failed(), bundle, failed)
    status = json.loads(failed.read_text())
    assert status['status'] == 'failed' and status['batchesCommitted'] == 0 and not status['liveDatabaseImported']
    class Incomplete(Client):
        def query(self, statement, parameters):
            if 'RETURN count(n)' in statement and 'UNWIND' not in statement: return [{'count': 0}]
            return super().query(statement, parameters)
    with pytest.raises(ValueError, match='counts differ'): g.import_graph(Incomplete(), bundle, tmp_path / 'incomplete.json')


def test_live_http_validation_outage_and_read_only_contract():
    class Failed:
        def query(self, *args): raise g.DatabaseUnavailable('synthetic private secret')
    app = g.server(Failed(), 'synthetic', 0)
    # The production Host check uses the bound port; test uses a deterministic configured port.
    app.server_close()
    import socket
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    app = g.server(Failed(), 'synthetic', port)
    worker = threading.Thread(target=app.serve_forever, daemon=True); worker.start()
    try:
        base = f'http://127.0.0.1:{port}'
        with urlopen(base + '/') as response:
            assert response.status == 200 and b'AI-Literature-KG' in response.read()
            assert response.headers['X-Content-Type-Options'] == 'nosniff'
        for path, status in (('/api/health', 503), ('/api/publications?limit=0', 400), ('/missing', 404),
                             ('/api/publication?id=a&id=b', 400), ('/api/health?x=1', 400)):
            with pytest.raises(HTTPError) as error: urlopen(base + path)
            assert error.value.code == status
            assert b'synthetic private secret' not in error.value.read()
        with pytest.raises(HTTPError) as error: urlopen(Request(base + '/', data=b'{}', method='POST'))
        assert error.value.code == 501
        with pytest.raises(HTTPError) as error: urlopen(Request(base + '/', headers={'Host': 'evil.example'}))
        assert error.value.code == 403
    finally:
        app.shutdown(); app.server_close(); worker.join(3)


def test_search_detail_and_incomplete_graph_do_not_use_local_fallback():
    class Client:
        def query(self, statement, params):
            if 'RETURN g.status' in statement: return [{'status': 'completed'}]
            if 'AS bibliographyTitles' in statement: return [{'bibliographyTitles': 20000, 'modelTitles': 19999, 'rejectedNERTitles': 1}]
            if 'AS candidateAssertions' in statement: return [{'candidateAssertions': 21497}]
            if statement == g.SEARCH_QUERY: return [{'publication': {'title': 'synthetic'}}] * 2
            if 'RETURN properties(p)' in statement: return [{'publication': {'title': 'Synthetic title', 'year': 2024}}]
            if 'RETURN a.name' in statement: return [{'name': 'Synthetic author', 'position': 1}]
            if 'RETURN v.name' in statement: return [{'name': 'Synthetic venue', 'type': 'conference'}]
            return []
    client = Client()
    assert g.api(client, 't', '/api/health', {})[1]['data']['status'] == 'ready'
    assert g.api(client, 't', '/api/health', {})[1]['data']['scope'] == {'bibliographyTitles': 20000, 'modelTitles': 19999, 'rejectedNERTitles': 1, 'candidateAssertions': 21497}
    result = g.api(client, 't', '/api/publications', {'limit': ['1']})[1]
    assert len(result['data']) == 1 and result['meta']['hasNext']
    detail = g.api(client, 't', '/api/publication', {'id': ['test']})[1]['data']
    assert 'Synthetic author' in detail['citationDraft'] and not detail['assertions']
    class Empty:
        def query(self, *args): return []
    with pytest.raises(g.DatabaseUnavailable): g.api(Empty(), 't', '/api/health', {})
    class Missing(Client):
        def query(self, statement, params):
            if 'RETURN properties(p)' in statement: return []
            return super().query(statement, params)
    assert g.api(Missing(), 't', '/api/publication', {'id': ['missing']})[0] == 404
    class BadScope(Client):
        def query(self, statement, params):
            if 'AS bibliographyTitles' in statement: return [{'bibliographyTitles': '20000'}]
            return super().query(statement, params)
    with pytest.raises(g.DatabaseUnavailable, match='scope malformed'):
        g.api(BadScope(), 't', '/api/health', {})
    page = (g.ROOT / 'resources/course_literature.html').read_text(encoding='utf-8')
    assert '138篇' not in page and 'modelApplicationStatus' in page and 'r.data.scope' in page
