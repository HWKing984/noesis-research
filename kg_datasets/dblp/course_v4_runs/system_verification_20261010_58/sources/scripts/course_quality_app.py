"""Read-only quality graph app; reuse the existing UI/API and expand typed aliases."""
import argparse
import getpass
import json
import re
from functools import cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import course_graph as g
from normalize_course_concepts import VOCAB, spelling, vocabulary

# Historical training snapshots bind the v2 config; the v3 app has its own pin.
CONFIG = g.ROOT/'resources/course_graph_quality_v3_runtime.json'
APP_CODE_SHA256 = g.c.file_sha256(Path(__file__))


def load_vocabulary(manifest=None):
    """Validate a small typed vocabulary once, independently of graph file hashing."""
    version = (manifest or {}).get('vocabularyVersion', 'typed_controlled_aliases_v2')
    if version == 'typed_controlled_aliases_v2': path, loader = VOCAB, vocabulary
    elif version == 'typed_controlled_aliases_v3':
        import normalize_course_concepts_v3 as v3
        path, loader = v3.VOCAB, v3.vocabulary
    else: raise ValueError('Unsupported graph vocabulary version')
    config, index = loader(); sha = g.c.file_sha256(path)
    if config['version'] != version or (manifest is not None and manifest.get('vocabularySha256') != sha):
        raise ValueError('Pinned graph vocabulary drift')
    return config, index, sha


@cache
def default_vocabulary():
    # Legacy direct callers retain v2; a running server receives its explicit snapshot.
    return load_vocabulary()

# The old exporter is hash-bound to training runs; application queries evolve here.
RETRACTION_PATTERN = r'(?is)^\s*(?:retracted(?:\s+article)?\s*:|retraction(?:\s+(?:note|notice))?\s*:).*'
CORRECTION_PATTERN = r'(?is)^\s*(?:corrigendum|erratum)(?:\s|:).*'
SEARCH_QUERY = '''MATCH (p:CoursePublication {graphId:$graph})
WHERE ($q='' OR any(term IN $qTerms WHERE toLower(p.title) CONTAINS term)) AND ($year IS NULL OR p.year=$year)
AND ($publicationStatus='all'
 OR ($publicationStatus='exclude_retractions' AND NOT p.title =~ $retractionPattern)
 OR ($publicationStatus='retractions' AND p.title =~ $retractionPattern)
 OR ($publicationStatus='corrections' AND p.title =~ $correctionPattern))
AND (($author='' AND $authorId='') OR EXISTS { MATCH (a:CoursePerson {graphId:$graph})-[:AUTHORED {graphId:$graph}]->(p)
 WHERE ($authorId='' OR a.personId=$authorId) AND ($author='' OR toLower(a.name) CONTAINS $author
 OR any(alias IN CASE WHEN a.aliases='' THEN [] ELSE coalesce(a.aliases,[]) END WHERE toLower(alias) CONTAINS $author)) })
AND ($venue='' OR EXISTS { MATCH (p)-[:PUBLISHED_IN]->(v:CourseVenue {graphId:$graph}) WHERE any(term IN $venueTerms WHERE toLower(v.name) CONTAINS term) })
AND (($method='' AND $task='' AND $dataset='') OR EXISTS {
 MATCH (a:CourseAssertion {graphId:$graph})-[:SUPPORTED_BY]->(p),
       (a)-[:HAS_HEAD]->(mh:CourseMention {graphId:$graph})-[:DENOTES]->(m:CourseConcept {graphId:$graph}),
       (a)-[:HAS_TAIL]->(:CourseMention {graphId:$graph})-[:DENOTES]->(t:CourseConcept {graphId:$graph})
 WHERE m.entityType='METHOD' AND ($method='' OR any(term IN $methodTerms WHERE
   ($conceptMatch='exact' AND toLower(m.name)=term) OR ($conceptMatch='contains' AND toLower(m.name) CONTAINS term)))
 AND ((a.predicate='USED_FOR' AND t.entityType='TASK') OR (a.predicate='EVALUATED_ON' AND t.entityType='DATASET'))
 WITH m, collect(DISTINCT t) AS tails
 WHERE ($task='' OR any(tc IN tails WHERE tc.entityType='TASK' AND any(term IN $taskTerms WHERE
     ($conceptMatch='exact' AND toLower(tc.name)=term) OR ($conceptMatch='contains' AND toLower(tc.name) CONTAINS term))))
 AND ($dataset='' OR any(dc IN tails WHERE dc.entityType='DATASET' AND any(term IN $datasetTerms WHERE
     ($conceptMatch='exact' AND toLower(dc.name)=term) OR ($conceptMatch='contains' AND toLower(dc.name) CONTAINS term)))) })
RETURN properties(p) AS publication ORDER BY p.year DESC, p.publicationId SKIP $offset LIMIT $limit'''


def publication_view(publication):
    # shortcut: title signals only, upgrade with publisher evidence before asserting actual status.
    title = publication.get('title', '')
    code, notice = 'unverified', '未检出撤稿/更正题名前缀信号；出版状态未经独立核验。'
    if re.fullmatch(RETRACTION_PATTERN, title):
        code, notice = 'retraction_signal', '题名含撤稿或撤稿通知信号：不应作为正常研究结论引用，请核验出版商记录。'
    elif re.fullmatch(CORRECTION_PATTERN, title):
        code, notice = 'correction_signal', '题名含勘误/更正信号：请同时核对原文与更正内容，不代表原论文已撤稿。'
    return publication | {'publicationStatus': {'code': code, 'notice': notice,
        'source': 'title_prefix_rule_v1', 'verified': False, 'evidence': title if code != 'unverified' else None}}


def search_parameters(query, aliases=None):
    extra = {'conceptMatch': ('exact', 'contains'), 'publicationStatus': ('exclude_retractions', 'all', 'retractions', 'corrections')}
    choices = {}
    for key, allowed in extra.items():
        values = query.get(key, [allowed[0]])
        if len(values) != 1 or values[0] not in allowed: raise ValueError('Invalid search policy')
        choices[key] = values[0]
    params = g.search_parameters({k: v for k, v in query.items() if k not in extra}) | choices
    params.update(retractionPattern=RETRACTION_PATTERN, correctionPattern=CORRECTION_PATTERN)
    config, index, _ = aliases if aliases is not None else default_vocabulary()
    for field, typ in (('method', 'METHOD'), ('task', 'TASK'), ('dataset', 'DATASET')):
        group = index.get((typ, spelling(params[field]))) if params[field] else None
        if group is None: group = next((v for v in config['groups'] if v['type'] == typ and params[field] == v['zh'].casefold()), None)
        if group:
            params[field+'Terms'] = list(dict.fromkeys(params[field+'Terms']+[spelling(n) for n in [group['canonical']]+group['aliases']]))
    return params


def api(client, graph, path, query, aliases=None):
    aliases = aliases if aliases is not None else default_vocabulary()
    config, _, sha = aliases
    if path != '/api/publications':
        status, body = g.api(client, graph, path, query)
        if path == '/api/health' and status == 200:
            body['data']['conceptVocabulary'] = {'version': config['version'], 'sha256': sha,
                'aliasesAreCuratedNotFacts': True, 'modelReliabilityPromoted': False}
            body['data']['appCodeSha256'] = APP_CODE_SHA256
            body['data']['liveImportCompleted'] = True
            body['data']['terminology'] = g.TERMINOLOGY | {'version': config['version'], 'aliases': g.TERMINOLOGY['aliases']+[
                {'zh': v['zh'], 'fields': [{'METHOD': 'method', 'TASK': 'task', 'DATASET': 'dataset'}[v['type']]],
                 'terms': [spelling(n) for n in [v['canonical']]+v['aliases']]} for v in config['groups']]}
        if path == '/api/publication' and status == 200:
            body['data']['publication'] = publication_view(body['data']['publication'])
            evidence = client.query('MATCH (a:CoursePerson {graphId:$graph})-[r:AUTHORED {graphId:$graph}]->(:CoursePublication {graphId:$graph,publicationId:$id}) RETURN a.personId AS personId,r.position AS position,a.identityEvidence AS identityEvidence,a.identityEvidenceMethods AS identityEvidenceMethods,a.independentlyVerified AS independentlyVerified,a.orcidSourceValues AS orcidSourceValues', {'graph': graph, 'id': query['id'][0]})
            by_signature = {(a['personId'], a['position']): a for a in evidence}
            if len(by_signature) != len(evidence) or set(by_signature) != {(a['personId'], a['position']) for a in body['data']['authors']}: raise g.DatabaseUnavailable('Author evidence coverage mismatch')
            body['data']['authors'] = [a | by_signature[(a['personId'], a['position'])] for a in body['data']['authors']]
        if path == '/api/graph' and status == 200:
            for node in body['data']['nodes']:
                if node['kind'] == 'Publication': node['props'] = publication_view(node['props'])
        return status, body
    params = search_parameters(query, aliases)
    ready = client.query('MATCH (g:CourseGraph {id:$graph}) RETURN g.status AS status', {'graph': graph})
    if not ready or ready[0]['status'] != 'completed': raise g.DatabaseUnavailable('Quality graph not ready')
    rows = client.query(SEARCH_QUERY, params | {'graph': graph, 'limit': params['limit']+1})
    return 200, {'data': [publication_view(r['publication']) for r in rows[:params['limit']]], 'meta': {
        'offset': params['offset'], 'limit': params['limit'], 'hasNext': len(rows) > params['limit'], 'source': 'live_neo4j',
        'conceptMatch': params['conceptMatch'], 'publicationStatus': params['publicationStatus'],
        'jointPolicy': 'same_publication_same_method_concept_separate_candidate_assertions',
        'aliasVersion': config['version'], 'expandedTerms': {
            field: params[field+'Terms'] for field in ('q', 'venue', 'method', 'task', 'dataset') if len(params[field+'Terms']) > 1}}}


def server(client, graph, port, aliases=None):
    aliases = aliases if aliases is not None else default_vocabulary()
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
                    status, body = api(client, graph, parsed.path, parse_qs(parsed.query, keep_blank_values=True, max_num_fields=20), aliases)
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
    aliases = load_vocabulary(manifest)
    client = g.Neo4j('http://127.0.0.1:7474', 'neo4j', 'neo4j', getpass.getpass('Neo4j password (not saved): '))
    print(f'Quality candidate graph: http://127.0.0.1:{args.port}/', flush=True)
    server(client, manifest['graphId'], args.port, aliases).serve_forever()
