"""Read-only quality graph app; reuse the existing UI/API and expand typed aliases."""
import argparse
import getpass
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import course_graph as g
from normalize_course_concepts import VOCAB, spelling, vocabulary

CONFIG = g.ROOT/'resources/course_graph_quality_runtime.json'
APP_CODE_SHA256 = g.c.file_sha256(Path(__file__))


def search_parameters(query):
    params = g.search_parameters(query); config, index = vocabulary()
    for field, typ in (('method', 'METHOD'), ('task', 'TASK'), ('dataset', 'DATASET')):
        group = index.get((typ, spelling(params[field]))) if params[field] else None
        if group is None: group = next((v for v in config['groups'] if v['type'] == typ and params[field] == v['zh'].casefold()), None)
        if group:
            params[field+'Terms'] = list(dict.fromkeys(params[field+'Terms']+[spelling(n) for n in [group['canonical']]+group['aliases']]))
    return params


def api(client, graph, path, query):
    if path != '/api/publications':
        status, body = g.api(client, graph, path, query)
        if path == '/api/health' and status == 200:
            body['data']['conceptVocabulary'] = {'version': 'typed_controlled_aliases_v2', 'sha256': g.c.file_sha256(VOCAB),
                'aliasesAreCuratedNotFacts': True, 'modelReliabilityPromoted': False}
            body['data']['appCodeSha256'] = APP_CODE_SHA256
            body['data']['liveImportCompleted'] = True
            config, _ = vocabulary()
            body['data']['terminology'] = g.TERMINOLOGY | {'version': config['version'], 'aliases': g.TERMINOLOGY['aliases']+[
                {'zh': v['zh'], 'fields': [{'METHOD': 'method', 'TASK': 'task', 'DATASET': 'dataset'}[v['type']]],
                 'terms': [spelling(n) for n in [v['canonical']]+v['aliases']]} for v in config['groups']]}
        if path == '/api/publication' and status == 200:
            evidence = client.query('MATCH (a:CoursePerson {graphId:$graph})-[r:AUTHORED {graphId:$graph}]->(:CoursePublication {graphId:$graph,publicationId:$id}) RETURN a.personId AS personId,r.position AS position,a.identityEvidence AS identityEvidence,a.identityEvidenceMethods AS identityEvidenceMethods,a.independentlyVerified AS independentlyVerified,a.orcidSourceValues AS orcidSourceValues', {'graph': graph, 'id': query['id'][0]})
            by_signature = {(a['personId'], a['position']): a for a in evidence}
            if len(by_signature) != len(evidence) or set(by_signature) != {(a['personId'], a['position']) for a in body['data']['authors']}: raise g.DatabaseUnavailable('Author evidence coverage mismatch')
            body['data']['authors'] = [a | by_signature[(a['personId'], a['position'])] for a in body['data']['authors']]
        return status, body
    params = search_parameters(query)
    ready = client.query('MATCH (g:CourseGraph {id:$graph}) RETURN g.status AS status', {'graph': graph})
    if not ready or ready[0]['status'] != 'completed': raise g.DatabaseUnavailable('Quality graph not ready')
    rows = client.query(g.SEARCH_QUERY, params | {'graph': graph, 'limit': params['limit']+1})
    return 200, {'data': [r['publication'] for r in rows[:params['limit']]], 'meta': {
        'offset': params['offset'], 'limit': params['limit'], 'hasNext': len(rows) > params['limit'], 'source': 'live_neo4j',
        'aliasVersion': 'typed_controlled_aliases_v2', 'expandedTerms': {
            field: params[field+'Terms'] for field in ('q', 'venue', 'method', 'task', 'dataset') if len(params[field+'Terms']) > 1}}}


def server(client, graph, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args): pass
        def do_GET(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{port}', f'localhost:{port}'):
                self.send_error(403); return
            parsed = urlsplit(self.path); content_type = 'application/json; charset=utf-8'
            try:
                if parsed.path == '/':
                    status = 200; payload = (g.ROOT/'resources/course_literature.html').read_bytes(); content_type = 'text/html; charset=utf-8'
                elif parsed.path == '/favicon.ico': status = 204; payload = b''; content_type = 'image/x-icon'
                else:
                    status, body = api(client, graph, parsed.path, parse_qs(parsed.query, keep_blank_values=True, max_num_fields=20))
                    payload = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            except ValueError:
                status = 400; payload = json.dumps({'error': {'code': 'invalid_request', 'message': '查询参数无效'}}, ensure_ascii=False).encode()
            except g.DatabaseUnavailable:
                status = 503; payload = json.dumps({'error': {'code': 'neo4j_unavailable', 'message': '图谱或数据库未就绪；没有离线替代数据。'}}, ensure_ascii=False).encode()
            except Exception:
                status = 500; payload = b'{"error":{"code":"internal_error","message":"Request failed"}}'
            self.send_response(status); self.send_header('Content-Type', content_type); self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers(); self.wfile.write(payload)
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False); parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535: parser.error('port must be 1024..65535')
    bundle = g.configured_bundle(CONFIG); manifest = g.verified_files(bundle)
    if manifest['vocabularySha256'] != g.c.file_sha256(VOCAB): raise ValueError('Pinned graph vocabulary drift')
    client = g.Neo4j('http://127.0.0.1:7474', 'neo4j', 'neo4j', getpass.getpass('Neo4j password (not saved): '))
    print(f'Quality candidate graph: http://127.0.0.1:{args.port}/', flush=True)
    server(client, manifest['graphId'], args.port).serve_forever()
