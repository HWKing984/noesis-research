"""Sealed model candidates -> isolated Neo4j graph -> loopback read-only search.

No fitting, final-test inference, label editing, database reset or local-data fallback.
"""
from __future__ import annotations

import argparse
import base64
import csv
import getpass
import hashlib
import json
import math
import os
import re
from collections import Counter
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlsplit
from urllib.request import Request, urlopen

import course_weak as c

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'kg_datasets/dblp/course_v4_runs/re_final_test_20261006_17'
BUNDLE = ROOT / 'kg_datasets/dblp/course_v4_graph_20261007_18_final'
RUN_SHA = 'ce9697e286c4532d9e6b18b114b7d96eae65432e5b4f3cadfbc4629b0d4191af'
KINDS = ('Publication', 'Person', 'Venue', 'Concept', 'Mention', 'Assertion')
EDGE_KINDS = ('AUTHORED', 'PUBLISHED_IN', 'MENTIONS', 'DENOTES', 'SUPPORTED_BY', 'HAS_HEAD', 'HAS_TAIL')

# Query/display vocabulary only: never rewrite evidence or graph identities.
# ponytail: exact aliases, not sentence translation; expand only with reviewed terminology.
TERMINOLOGY = {
    'version': 'zh_alias_v1',
    'nodeLabels': dict(zip(KINDS, ('论文/文献', '作者', '会议/期刊', '概念', '实体提及', '候选断言'))),
    'entityLabels': {'METHOD': '方法', 'TASK': '任务', 'DATASET': '数据集'},
    'relationshipLabels': dict(zip(EDGE_KINDS, ('署名', '发表于', '提及', '指向概念', '题名证据来自', '头实体', '尾实体'))) |
                          {'USED_FOR': '用于（候选）', 'EVALUATED_ON': '在数据集上评估（候选）'},
    'publicationTypes': {'inproceedings': '会议论文', 'article': '期刊文章', 'proceedings': '会议论文集',
                         'book': '图书', 'incollection': '书中章节', 'phdthesis': '博士论文', 'mastersthesis': '硕士论文'},
    'aliases': [
        {'zh': zh, 'fields': ['q', field], 'terms': terms}
        for field, zh, terms in (
            ('method', '扩散模型', ['diffusion model', 'diffusion models']),
            ('method', '知识图谱', ['knowledge graph', 'knowledge graphs']),
            ('method', '图神经网络', ['graph neural network', 'graph neural networks']),
            ('method', '卷积神经网络', ['convolutional neural network', 'convolutional neural networks']),
            ('method', '神经网络', ['neural network', 'neural networks']),
            ('method', '机器学习', ['machine learning']),
            ('method', '深度学习', ['deep learning']),
            ('method', '强化学习', ['reinforcement learning']),
            ('method', '大语言模型', ['large language model', 'large language models']),
            ('method', '大型语言模型', ['large language model', 'large language models']),
            ('method', '对比学习', ['contrastive learning']),
            ('method', '迁移学习', ['transfer learning']),
            ('method', '联邦学习', ['federated learning']),
            ('method', '自监督学习', ['self-supervised learning']),
            ('task', '命名实体识别', ['named entity recognition']),
            ('task', '关系抽取', ['relation extraction']),
            ('task', '机器翻译', ['machine translation']),
            ('task', '目标检测', ['object detection']),
            ('task', '图像分类', ['image classification']),
            ('task', '语义分割', ['semantic segmentation']),
            ('task', '推荐系统', ['recommender system', 'recommender systems', 'recommendation system', 'recommendation systems']),
        )
    ] + [{'zh': 'AAAI会议', 'fields': ['venue'], 'terms': ['aaai']}],
}


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def identifier(graph, kind, key):
    return graph + ':' + kind + ':' + digest(json.dumps(key, ensure_ascii=False, sort_keys=True))


def verified_files(folder, expected=None):
    if expected and c.file_sha256(folder / 'manifest.json') != expected:
        raise ValueError('Sealed source manifest changed')
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    for name, sha in manifest['filesSha256'].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or c.file_sha256(path) != sha:
            raise ValueError('Artifact missing, unsafe or changed: ' + name)
    return manifest


def candidate_graph(graph, docs, cache, predictions, publications, models, *, source_run_sha=RUN_SHA):
    documents = {d['sampleId']: d for d in docs}
    if len(documents) != len(docs) or len(cache) != len(docs): raise ValueError('Duplicate or missing documents')
    nodes = {}; edges = []
    def node(kind, key, props):
        nid = identifier(graph, kind, key)
        nodes[nid] = {'kind': kind, 'id': nid, 'props': props | {'id': nid, 'graphId': graph}}
        return nid
    def edge(kind, head, tail):
        edges.append({'kind': kind, 'head': head, 'tail': tail, 'props': {'graphId': graph}})
    mentions = {}; seen_cache = set()
    for row in cache:
        sid = row['sampleId']
        if sid not in documents or sid in seen_cache: raise ValueError('Unknown or duplicate NER cache document')
        seen_cache.add(sid); doc = documents[sid]; text = doc['text']; end = 0
        if digest(text) != doc['textSha256']: raise ValueError('Title hash changed')
        for e in row['predictedEntities']:
            if (type(e['start']) is not int or type(e['end']) is not int or
                not end <= e['start'] < e['end'] <= len(text) or text[e['start']:e['end']] != e['text'] or
                e['label'] not in ('METHOD', 'TASK', 'DATASET')): raise ValueError('Invalid predicted mention')
            end = e['end']
            concept = node('Concept', [e['label'], e['text'].casefold()],
                           {'name': e['text'], 'entityType': e['label'], 'normalization': 'casefold_only_no_alias_resolution'})
            mid = node('Mention', [sid, e['start'], e['end'], e['label']], e | {
                'sampleId': sid, 'source': 'model_prediction', 'status': 'candidate',
                'textSha256': doc['textSha256'], 'NERWeightsSha256': models.get('NERWeightsSha256', ''),
                'offsetUnit': 'Unicode_code_points', 'evidence': text, 'sourceRunManifestSha256': source_run_sha})
            mentions[sid, e['start'], e['end'], e['label']] = (mid, e)
            edge('MENTIONS', publications[sid], mid); edge('DENOTES', mid, concept)
    seen_pairs = set()
    for p in predictions:
        sid = p['sampleId']
        if sid not in documents or p['text'] != documents[sid]['text'] or p['textSha256'] != documents[sid]['textSha256']:
            raise ValueError('Prediction title binding changed')
        ends = []
        for key in ('head', 'tail'):
            e = p[key]; item = mentions.get((sid, e['start'], e['end'], e['label']))
            if item is None or item[1] != e: raise ValueError('Relation endpoint not a predicted mention')
            ends.append(item[0])
        pair = (sid, *ends)
        if pair in seen_pairs: raise ValueError('Duplicate relation pair')
        seen_pairs.add(pair)
        positive = {'TASK': 'USED_FOR', 'DATASET': 'EVALUATED_ON'}.get(p['tail']['label'])
        probabilities = p['probabilities']
        if (p['head']['label'] != 'METHOD' or positive is None or p['label'] not in (positive, 'NO_RELATION') or
            set(probabilities) != {'USED_FOR', 'EVALUATED_ON', 'NO_RELATION'} or
            any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in probabilities.values()) or
            abs(sum(probabilities.values()) - 1) > 1e-5 or max(probabilities, key=probabilities.get) != p['label']):
            raise ValueError('Illegal relation or probabilities')
        if p['label'] == 'NO_RELATION': continue
        aid = node('Assertion', pair, {'sampleId': sid, 'pairId': p['pairId'], 'predicate': p['label'],
            'source': 'model_prediction', 'entitySource': 'frozen_NER_prediction', 'status': 'candidate',
            'confidence': probabilities[p['label']], 'confidenceCalibrated': False,
            'probabilitiesJson': json.dumps(probabilities, sort_keys=True), 'evidence': p['text'],
            'textSha256': p['textSha256'], 'NERWeightsSha256': models['NERWeightsSha256'],
            'REWeightsSha256': models['REWeightsSha256'], 'sourceRunManifestSha256': source_run_sha})
        edge('SUPPORTED_BY', aid, publications[sid]); edge('HAS_HEAD', aid, ends[0]); edge('HAS_TAIL', aid, ends[1])
    return list(nodes.values()), edges


def export_graph(output, *, production=None):
    if output.exists(): raise FileExistsError('Preserve existing graph bundle')
    source_run = RUN if production is None else production.resolve()
    run_sha = RUN_SHA if production is None else c.file_sha256(source_run / 'manifest.json')
    sealed = verified_files(source_run, run_sha)
    result = json.loads((source_run / ('test_result.json' if production is None else 'summary.json')).read_text(encoding='utf-8'))
    if production is not None:
        state = json.loads((source_run / 'status.json').read_text(encoding='utf-8'))
        if (sealed.get('kind') != 'frozen_title_only_corpus_inference' or sealed['status'] != 'completed'
                or state['status'] != 'completed' or state['processed'] != state['documentsRequested']
                or sealed['evaluationExecuted'] or sealed['trainingExecuted']):
            raise ValueError('Production run incomplete or not frozen inference')
        for p, sha in sealed['inputSha256'].items():
            original = (ROOT / p).resolve()
            # Executed source is archived in the sealed run; later source edits do not rewrite its provenance.
            path = source_run / Path(p).name if p.startswith('scripts/') else original
            if not original.is_relative_to(ROOT) or c.file_sha256(path) != sha:
                raise ValueError('Production source drift or unsafe path')
    source = ROOT / 'kg_datasets/dblp/processed_ai'
    weak = ROOT / 'kg_datasets/dblp/course_v4_weak'
    weak_key = str((weak / 'manifest.json').resolve()) if production is None else (weak / 'manifest.json').relative_to(ROOT).as_posix()
    if c.file_sha256(weak / 'manifest.json') != sealed['inputSha256'][weak_key]:
        raise ValueError('Canonical references manifest differs from frozen run')
    weak_manifest = verified_files(weak)
    if c.file_sha256(source / 'publications.csv') != weak_manifest['inputSha256']['kg_datasets/dblp/processed_ai/publications.csv']:
        raise ValueError('Bookkeeping source differs from sealed corpus')
    source_paths = [source / (name + '.csv') for name in ('publications', 'persons', 'venues', 'authored', 'published_in')]
    inputs = {str(p.relative_to(ROOT)): c.file_sha256(p) for p in source_paths + [source_run / 'manifest.json', weak / 'manifest.json']}
    graph = 'ai-literature-' + c.canonical_sha256({'inputs': inputs, 'graphSchema': 2})[:20]
    nodes = []; edges = []; maps = {}
    for kind, file, key in (('Publication', 'publications', 'publicationId:ID(Publication)'),
                            ('Person', 'persons', 'personId:ID(Person)'), ('Venue', 'venues', 'venueId:ID(Venue)')):
        maps[kind] = {}
        with (source / (file + '.csv')).open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                pid = row[key]
                if not pid or pid in maps[kind]: raise ValueError('Duplicate or blank source node')
                nid = identifier(graph, kind, pid); maps[kind][pid] = nid
                props = {k.split(':')[0]: v.split(';') if ':string[]' in k and v else v for k, v in row.items() if not k.startswith(':')}
                props.update(id=nid, graphId=graph, source='dblp_structured_xml', sourceFileSha256=inputs[str((source / (file + '.csv')).relative_to(ROOT))])
                if kind == 'Publication': props['year'] = int(props['year']); props['dblpUrl'] = 'https://dblp.org/rec/' + quote(pid, safe='/')
                if kind == 'Person': props['identityStatus'] = 'normalized_name_not_disambiguated'
                nodes.append({'kind': kind, 'id': nid, 'props': props})
    for file, kind, head, tail in (('authored', 'AUTHORED', 'Person', 'Publication'), ('published_in', 'PUBLISHED_IN', 'Publication', 'Venue')):
        with (source / (file + '.csv')).open(encoding='utf-8-sig', newline='') as stream:
            for row in csv.DictReader(stream):
                try: a = maps[head][row[f':START_ID({head})']]; b = maps[tail][row[f':END_ID({tail})']]
                except KeyError: raise ValueError('Dangling source edge') from None
                props = {'graphId': graph, 'source': 'dblp_structured_xml'}
                if kind == 'AUTHORED': props['position'] = int(row['position:int'])
                edges.append({'kind': kind, 'head': a, 'tail': b, 'props': props})
    all_docs = c.read_jsonl(source_run / ('test_documents.jsonl' if production is None else 'documents.jsonl'))
    refs = {r['sampleId']: r for r in c.read_jsonl(weak / 'references.jsonl')} if production is None else {d['sampleId']: d for d in all_docs}
    cache = c.read_jsonl(source_run / ('cached_ner_predictions.jsonl' if production is None else 'ner_predictions.jsonl'))
    predictions = c.read_jsonl(source_run / ('pipeline_predictions.jsonl' if production is None else 'relation_predictions.jsonl'))
    if production is not None:
        if [r['sampleId'] for r in cache] != [d['sampleId'] for d in all_docs]: raise ValueError('Production NER coverage differs')
        by_id = {r['sampleId']: r for r in cache}
        docs = [d for d in all_docs if by_id[d['sampleId']]['status'] != 'rejected']
        cache = [r for r in cache if r['status'] != 'rejected']
    else: docs = all_docs
    pubs = {}
    paper_nodes = {n['props']['publicationId']: n for n in nodes if n['kind'] == 'Publication'}
    if production is not None:
        for d in all_docs:
            r = by_id[d['sampleId']]
            pid = d['publicationId']
            if paper_nodes[pid]['props']['title'] != d['text']: raise ValueError('Production title differs from bibliography')
            paper_nodes[pid]['props'].update(modelApplicationStatus=r['status'], modelRunManifestSha256=run_sha)
            if r['status']=='rejected':
                paper_nodes[pid]['props'].update(modelApplied=False, modelSampleId=d['sampleId'], modelApplicationReason=r['reason'])
    for d in docs:
        ref = refs[d['sampleId']]; pid = ref['publicationId']
        if ref['text'] != d['text'] or paper_nodes[pid]['props']['title'] != d['text']: raise ValueError('Model title does not match bibliography')
        paper_nodes[pid]['props'].update(modelApplied=True, modelSampleId=d['sampleId'], modelRunManifestSha256=run_sha)
        pubs[d['sampleId']] = maps['Publication'][pid]
    candidates, candidate_edges = candidate_graph(graph, docs, cache, predictions, pubs, result, source_run_sha=run_sha)
    nodes.extend(candidates); edges.extend(candidate_edges)
    for e in edges:
        e['id'] = identifier(graph, 'Edge', [e['kind'], e['head'], e['tail'], e['props'].get('position')])
        e['props']['id'] = e['id']
    if any(c.file_sha256(ROOT / p) != sha for p, sha in inputs.items()): raise ValueError('Inputs changed during export')
    output.mkdir(parents=True, exist_ok=False)
    c.write_jsonl(output / 'nodes.jsonl', nodes); c.write_jsonl(output / 'edges.jsonl', edges)
    manifest = {'graphId': graph, 'createdAtUTC': datetime.now(UTC).isoformat(), 'inputSha256': inputs,
        'scope': {'bibliographyTitles': len(maps['Publication']), 'modelTitles': len(docs), 'pipelinePairs': len(predictions),
                  'negativeDecisionsExcluded': sum(p['label']=='NO_RELATION' for p in predictions),
                  'modelAppliedToFullCorpus': len(docs)==len(maps['Publication']),
                  'testQueueCoverage': result.get('coverage'),
                  'production': production is not None, 'rejectedRelationPairs': result.get('rejectedPairs',0),
                  'processedModelTitles': len(all_docs), 'rejectedNERTitles': len(all_docs)-len(docs)},
        'counts': {'nodes': dict(Counter(n['kind'] for n in nodes)), 'edges': dict(Counter(e['kind'] for e in edges))},
        'liveDatabaseImported': False, 'modelSourceManifestSha256': run_sha,
        'exporterCodeSha256': c.file_sha256(Path(__file__)),
        'notice': 'Predictions are candidate assertions, not DBLP facts. No CITES, no human gold, no calibrated confidence. Topic-rule edges intentionally not mixed into this bundle.',
        'filesSha256': {name: c.file_sha256(output / name) for name in ('nodes.jsonl', 'edges.jsonl')}}
    c.write_json(output / 'manifest.json', manifest)
    verify_bundle(output)
    return manifest


def verify_bundle(bundle):
    manifest = verified_files(bundle); nodes = c.read_jsonl(bundle / 'nodes.jsonl'); edges = c.read_jsonl(bundle / 'edges.jsonl')
    ids = {n['id'] for n in nodes}; seen = set(); graph = manifest['graphId']
    if len(ids) != len(nodes): raise ValueError('Duplicate graph node')
    for n in nodes:
        if n['kind'] not in KINDS or n['props'].get('id') != n['id'] or n['props'].get('graphId') != graph:
            raise ValueError('Invalid scoped graph node')
    for e in edges:
        key = e['id']
        if e['kind'] not in EDGE_KINDS or e['head'] not in ids or e['tail'] not in ids or key in seen or e['props'].get('graphId') != graph or e['props'].get('id') != key:
            raise ValueError('Invalid or duplicate graph edge')
        seen.add(key)
    actual = {'nodes': dict(Counter(n['kind'] for n in nodes)), 'edges': dict(Counter(e['kind'] for e in edges))}
    if actual != manifest['counts']: raise ValueError('Bundle counts differ')
    return {'manifest': manifest, 'nodes': nodes, 'edges': edges}


class DatabaseUnavailable(RuntimeError): pass


class Neo4j:
    def __init__(self, url, database, user, password):
        parsed = urlsplit(url)
        if (parsed.scheme not in ('http', 'https') or parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or
            parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/') or
            not re.fullmatch(r'[A-Za-z0-9_.-]+', database)):
            raise ValueError('Course client requires a credential-free loopback URL and valid database name')
        self.endpoint = url.rstrip('/') + '/db/' + quote(database, safe='') + '/query/v2'
        self.authorization = 'Basic ' + base64.b64encode((user + ':' + password).encode()).decode()

    def query(self, statement, parameters):
        request = Request(self.endpoint, data=json.dumps({'statement': statement, 'parameters': parameters}, allow_nan=False).encode(),
                          headers={'Authorization': self.authorization, 'Content-Type': 'application/json', 'Accept': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=20) as response: body = json.loads(response.read())
        except HTTPError as error:
            raise DatabaseUnavailable('Neo4j HTTP ' + str(error.code)) from None
        except (URLError, TimeoutError, OSError, ValueError): raise DatabaseUnavailable('Neo4j connection or response unavailable') from None
        if body.get('errors'): raise DatabaseUnavailable('Neo4j rejected query')
        data = body.get('data', {})
        if not isinstance(data, dict) or not isinstance(data.get('fields'), list) or not isinstance(data.get('values'), list):
            raise DatabaseUnavailable('Neo4j result missing')
        if any(not isinstance(row, list) or len(row) != len(data['fields']) for row in data['values']): raise DatabaseUnavailable('Neo4j result malformed')
        return [dict(zip(data['fields'], row)) for row in data['values']]


def import_graph(client, bundle, receipt):
    if receipt.exists(): raise FileExistsError('Preserve import receipt; use a new path to retry')
    data = verify_bundle(bundle); manifest = data['manifest']; graph = manifest['graphId']
    state = {'status': 'running', 'graphId': graph, 'bundleManifestSha256': c.file_sha256(bundle / 'manifest.json'),
             'startedAtUTC': datetime.now(UTC).isoformat(), 'batchesCommitted': 0, 'databaseReset': False}
    receipt.parent.mkdir(parents=True, exist_ok=True); c.write_json(receipt, state)
    try:
        client.query('RETURN 1 AS connected', {})
        client.query('CREATE CONSTRAINT course_node_id IF NOT EXISTS FOR (n:CourseNode) REQUIRE n.id IS UNIQUE', {})
        client.query('CREATE CONSTRAINT course_graph_id IF NOT EXISTS FOR (g:CourseGraph) REQUIRE g.id IS UNIQUE', {})
        existing = client.query('MATCH (g:CourseGraph {id:$graph}) RETURN g.status AS status', {'graph': graph})
        if existing and existing[0]['status'] == 'completed':
            state['alreadyImported'] = True
        else:
            client.query('MERGE (g:CourseGraph {id:$graph}) SET g.status="importing", g.manifestSha256=$sha',
                         {'graph': graph, 'sha': state['bundleManifestSha256']})
            # ponytail: sequential 500-row batches; add concurrent imports only for measured throughput needs.
            for kind in KINDS:
                rows = [n for n in data['nodes'] if n['kind'] == kind]
                query = f'UNWIND $rows AS row MERGE (n:CourseNode:Course{kind}:{kind} {{id:row.id}}) ON CREATE SET n += row.props RETURN count(n) AS count'
                for start in range(0, len(rows), 500):
                    batch = rows[start:start + 500]
                    if client.query(query, {'rows': batch})[0]['count'] != len(batch): raise ValueError('Node batch count differs')
                    state['batchesCommitted'] += 1; c.write_json(receipt, state)
            for kind in EDGE_KINDS:
                rows = [e for e in data['edges'] if e['kind'] == kind]
                query = f'UNWIND $rows AS row MATCH (a:CourseNode {{id:row.head}}), (b:CourseNode {{id:row.tail}}) MERGE (a)-[r:{kind} {{id:row.id}}]->(b) ON CREATE SET r += row.props RETURN count(r) AS count'
                for start in range(0, len(rows), 500):
                    batch = rows[start:start + 500]
                    if client.query(query, {'rows': batch})[0]['count'] != len(batch): raise ValueError('Edge endpoints missing')
                    state['batchesCommitted'] += 1; c.write_json(receipt, state)
        actual = {'nodes': {}, 'edges': {}}
        for kind in KINDS:
            count = client.query(f'MATCH (n:Course{kind} {{graphId:$graph}}) RETURN count(n) AS count', {'graph': graph})[0]['count']
            if count: actual['nodes'][kind] = count
        for kind in EDGE_KINDS:
            count = client.query(f'MATCH (a:CourseNode {{graphId:$graph}})-[r:{kind}]->(b:CourseNode {{graphId:$graph}}) RETURN count(r) AS count', {'graph': graph})[0]['count']
            if count: actual['edges'][kind] = count
        if actual != manifest['counts']: raise ValueError('Database counts differ; graph remains unavailable')
        client.query('MATCH (g:CourseGraph {id:$graph}) SET g.status="completed" RETURN g.id AS id', {'graph': graph})
        state.update(status='completed', actualCounts=actual, liveDatabaseImported=True)
    except Exception as error:
        state.update(status='failed', error=str(error), liveDatabaseImported=False)
        raise
    finally:
        state['finishedAtUTC'] = datetime.now(UTC).isoformat(); c.write_json(receipt, state)
    return state


SEARCH_QUERY = '''MATCH (p:CoursePublication {graphId:$graph})
WHERE ($q='' OR any(term IN $qTerms WHERE toLower(p.title) CONTAINS term)) AND ($year IS NULL OR p.year=$year)
AND ($author='' OR EXISTS { MATCH (a:CoursePerson)-[:AUTHORED]->(p) WHERE toLower(a.name) CONTAINS $author })
AND ($venue='' OR EXISTS { MATCH (p)-[:PUBLISHED_IN]->(v:CourseVenue) WHERE any(term IN $venueTerms WHERE toLower(v.name) CONTAINS term) })
AND (($method='' AND $task='' AND $dataset='') OR EXISTS {
 MATCH (a:CourseAssertion)-[:SUPPORTED_BY]->(p), (a)-[:HAS_HEAD]->(:CourseMention)-[:DENOTES]->(m:CourseConcept),
       (a)-[:HAS_TAIL]->(:CourseMention)-[:DENOTES]->(t:CourseConcept)
 WHERE ($method='' OR any(term IN $methodTerms WHERE toLower(m.name) CONTAINS term))
 AND ($task='' OR (t.entityType='TASK' AND any(term IN $taskTerms WHERE toLower(t.name) CONTAINS term)))
 AND ($dataset='' OR (t.entityType='DATASET' AND any(term IN $datasetTerms WHERE toLower(t.name) CONTAINS term))) })
RETURN properties(p) AS publication ORDER BY p.year DESC, p.publicationId SKIP $offset LIMIT $limit'''


def search_parameters(query):
    allowed = {'q', 'author', 'venue', 'method', 'task', 'dataset', 'year', 'limit', 'offset'}
    if set(query) - allowed or any(len(values) != 1 for values in query.values()): raise ValueError('Unknown or repeated parameter')
    result = {k: query.get(k, [''])[0].strip().lower() for k in ('q', 'author', 'venue', 'method', 'task', 'dataset')}
    if any(len(v) > 200 for v in result.values()): raise ValueError('Search terms must be at most 200 characters')
    try:
        result['year'] = int(query['year'][0]) if query.get('year', [''])[0] else None
        result['limit'] = int(query.get('limit', ['20'])[0]); result['offset'] = int(query.get('offset', ['0'])[0])
    except (ValueError, TypeError): raise ValueError('Year and pagination must be integers') from None
    if not 1 <= result['limit'] <= 100 or not 0 <= result['offset'] <= 20000 or (result['year'] is not None and not 2015 <= result['year'] <= 2025):
        raise ValueError('Year or pagination out of range')
    for field in ('q', 'venue', 'method', 'task', 'dataset'):
        terms = [result[field]] if result[field] else []
        for alias in TERMINOLOGY['aliases']:
            if field in alias['fields'] and result[field] == alias['zh'].lower(): terms.extend(alias['terms'])
        result[field + 'Terms'] = list(dict.fromkeys(terms))
    return result


GRAPH_PATTERNS = {
    'paper': '''CALL () {
      MATCH path=(a:CoursePerson)-[:AUTHORED]->(p:CoursePublication {graphId:$graph,publicationId:$id}) RETURN path
      UNION ALL MATCH path=(p:CoursePublication {graphId:$graph,publicationId:$id})-[:PUBLISHED_IN]->(:CourseVenue) RETURN path
      UNION ALL MATCH path=(p:CoursePublication {graphId:$graph,publicationId:$id})-[:MENTIONS]->(:CourseMention)-[:DENOTES]->(:CourseConcept) RETURN path
      UNION ALL MATCH path=(p:CoursePublication {graphId:$graph,publicationId:$id})<-[:SUPPORTED_BY]-(:CourseAssertion)-[:HAS_HEAD|HAS_TAIL]->(:CourseMention) RETURN path
    }''',
    'coauthors': '''MATCH path=(p:CoursePublication {graphId:$graph,publicationId:$id})<-[:AUTHORED]-(:CoursePerson)-[:AUTHORED]->(other:CoursePublication)
      WHERE p<>other''',
    'methods': '''MATCH path=(p:CoursePublication {graphId:$graph,publicationId:$id})-[:MENTIONS]->(:CourseMention)-[:DENOTES]->(c:CourseConcept)<-[:DENOTES]-(:CourseMention)<-[:MENTIONS]-(other:CoursePublication)
      WHERE p<>other AND c.entityType='METHOD' ''',
}
GRAPH_RETURN = '''WITH path WHERE all(n IN nodes(path) WHERE n.graphId=$graph) AND all(r IN relationships(path) WHERE r.graphId=$graph)
RETURN [n IN nodes(path) | {kind:[tag IN labels(n) WHERE tag IN $kinds][0],props:properties(n)}] AS nodes,
       [r IN relationships(path) | {id:r.id,kind:type(r),source:startNode(r).id,target:endNode(r).id}] AS edges LIMIT $limit'''


def graph_parameters(query):
    if set(query)-{'id','mode','limit'} or any(len(v)!=1 for v in query.values()): raise ValueError('Unknown or repeated graph parameter')
    pid = query.get('id',[''])[0]; mode = query.get('mode',['paper'])[0]
    try: limit = int(query.get('limit',['30'])[0])
    except (ValueError,TypeError): raise ValueError('Invalid graph limit') from None
    if not 1 <= len(pid) <= 300 or mode not in GRAPH_PATTERNS or not 1 <= limit <= 50: raise ValueError('Graph parameters out of range')
    return {'id':pid,'mode':mode,'limit':limit}


def graph_response(publication, rows, graph, params):
    nodes, edges = {}, {}
    def add_node(node):
        if (node.get('kind') not in KINDS or not isinstance(node.get('props'),dict) or
            node['props'].get('graphId') != graph or not isinstance(node['props'].get('id'),str)):
            raise DatabaseUnavailable('Malformed graph node')
        nid = node['props']['id']
        if nid in nodes and nodes[nid] != node: raise DatabaseUnavailable('Conflicting graph node')
        nodes[nid] = node
    add_node({'kind':'Publication','props':publication})
    if len(rows) > params['limit']+1: raise DatabaseUnavailable('Graph response over limit')
    for row in rows[:params['limit']]:
        if not isinstance(row.get('nodes'),list) or not isinstance(row.get('edges'),list) or len(row['nodes']) > 5 or len(row['edges']) > 4:
            raise DatabaseUnavailable('Malformed bounded path')
        for node in row['nodes']: add_node(node)
        for edge in row['edges']:
            if (edge.get('kind') not in EDGE_KINDS or not isinstance(edge.get('id'),str) or
                edge.get('source') not in nodes or edge.get('target') not in nodes): raise DatabaseUnavailable('Malformed graph edge')
            if edge['id'] in edges and edges[edge['id']] != edge: raise DatabaseUnavailable('Conflicting graph edge')
            edges[edge['id']] = edge
    return {'data':{'nodes':list(nodes.values()),'edges':list(edges.values()),'rootId':publication['id']},
        'meta':{'source':'live_neo4j','graphId':graph,'mode':params['mode'],'pathsReturned':min(len(rows),params['limit']),
            'hasMorePaths':len(rows)>params['limit'],'pathLimit':params['limit'],'wholeGraph':False,
            'notice':'局部有界路径；共享作者姓名未消歧，同方法仅表示模型提及，不是引用或已验证语义相似。'}}


def api(client, graph, path, query):
    if path not in ('/api/health', '/api/publications', '/api/publication','/api/graph'): return 404, {'error': {'code': 'not_found', 'message': '接口不存在'}}
    params = search_parameters(query) if path == '/api/publications' else None
    graph_params = graph_parameters(query) if path == '/api/graph' else None
    if path == '/api/publication' and (set(query) != {'id'} or len(query['id']) != 1 or not 1 <= len(query['id'][0]) <= 300):
        raise ValueError('Exactly one publication id required')
    if path == '/api/health' and query: raise ValueError('Health takes no parameters')
    ready = client.query('MATCH (g:CourseGraph {id:$graph}) RETURN g.status AS status', {'graph': graph})
    if not ready or ready[0]['status'] != 'completed': raise DatabaseUnavailable('Course graph not completely imported')
    if path == '/api/health':
        publications = client.query('MATCH (p:CoursePublication {graphId:$graph}) RETURN count(p) AS bibliographyTitles, count(CASE WHEN p.modelApplied THEN 1 END) AS modelTitles, count(CASE WHEN p.modelApplicationStatus="rejected" THEN 1 END) AS rejectedNERTitles', {'graph': graph})
        assertions = client.query('MATCH (a:CourseAssertion {graphId:$graph}) RETURN count(a) AS candidateAssertions', {'graph': graph})
        if len(publications) != 1 or len(assertions) != 1: raise DatabaseUnavailable('Graph scope missing')
        scope = publications[0] | assertions[0]
        if set(scope) != {'bibliographyTitles', 'modelTitles', 'rejectedNERTitles', 'candidateAssertions'} or any(type(n) is not int or n < 0 for n in scope.values()):
            raise DatabaseUnavailable('Graph scope malformed')
        return 200, {'data': {'status': 'ready', 'graphId': graph, 'source': 'live_neo4j', 'scope': scope,
                             'terminology': TERMINOLOGY}}
    if params is not None:
        rows = client.query(SEARCH_QUERY, params | {'graph': graph, 'limit': params['limit'] + 1})
        return 200, {'data': [r['publication'] for r in rows[:params['limit']]],
                     'meta': {'offset': params['offset'], 'limit': params['limit'], 'hasNext': len(rows) > params['limit'], 'source': 'live_neo4j',
                              'aliasVersion': TERMINOLOGY['version'],
                              'expandedTerms': {field: params[field + 'Terms'] for field in ('q', 'venue', 'method', 'task', 'dataset')
                                                if len(params[field + 'Terms']) > 1}}}
    pid = query['id'][0]; p = {'graph': graph, 'id': pid}
    publications = client.query('MATCH (p:CoursePublication {graphId:$graph, publicationId:$id}) RETURN properties(p) AS publication', p)
    if not publications: return 404, {'error': {'code': 'not_found', 'message': '文献不存在'}}
    if graph_params is not None:
        rows = client.query(GRAPH_PATTERNS[graph_params['mode']] + '\n' + GRAPH_RETURN,
            p | {'kinds':list(KINDS),'limit':graph_params['limit']+1})
        return 200, graph_response(publications[0]['publication'],rows,graph,graph_params)
    authors = client.query('MATCH (a:CoursePerson)-[r:AUTHORED]->(p:CoursePublication {graphId:$graph,publicationId:$id}) RETURN a.name AS name, r.position AS position, a.identityStatus AS identityStatus ORDER BY position', p)
    venues = client.query('MATCH (p:CoursePublication {graphId:$graph,publicationId:$id})-[:PUBLISHED_IN]->(v:CourseVenue) RETURN v.name AS name, v.venueType AS type', p)
    mentions = client.query('MATCH (p:CoursePublication {graphId:$graph,publicationId:$id})-[:MENTIONS]->(m:CourseMention) RETURN properties(m) AS mention ORDER BY m.start', p)
    assertions = client.query('MATCH (a:CourseAssertion)-[:SUPPORTED_BY]->(p:CoursePublication {graphId:$graph,publicationId:$id}), (a)-[:HAS_HEAD]->(h:CourseMention), (a)-[:HAS_TAIL]->(t:CourseMention) RETURN properties(a) AS assertion, properties(h) AS head, properties(t) AS tail ORDER BY h.start,t.start', p)
    publication = publications[0]['publication']
    citation = '; '.join(a['name'] for a in authors) + '. ' + publication['title'] + ' ' + '; '.join(v['name'] for v in venues) + ', ' + str(publication['year']) + '. DOI: ' + (publication.get('doi') or '缺失')
    return 200, {'data': {'publication': publication, 'authors': authors, 'venues': venues,
        'mentions': [m['mention'] for m in mentions], 'assertions': assertions, 'citationDraft': citation,
        'notice': '候选参考文献；引用前阅读原文并核验书目信息。模型分数未校准，题名证据不等于全文结论。'}}


def server(client, graph, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args): pass  # no query terms or credentials in request logs
        def do_GET(self):
            parsed = urlsplit(self.path)
            if self.headers.get('Host') not in (f'127.0.0.1:{port}', f'localhost:{port}'):
                self.send_error(403); return
            try:
                if parsed.path == '/':
                    status = 200; payload = (ROOT / 'resources/course_literature.html').read_bytes(); content_type = 'text/html; charset=utf-8'
                elif parsed.path == '/favicon.ico': status = 204; payload = b''; content_type = 'image/x-icon'
                else:
                    status, body = api(client, graph, parsed.path, parse_qs(parsed.query, keep_blank_values=True, max_num_fields=20))
                    payload = json.dumps(body, ensure_ascii=False, allow_nan=False).encode(); content_type = 'application/json; charset=utf-8'
            except ValueError:
                status = 400; payload = json.dumps({'error': {'code': 'invalid_request', 'message': '查询参数无效'}}, ensure_ascii=False).encode(); content_type = 'application/json; charset=utf-8'
            except DatabaseUnavailable:
                status = 503; payload = json.dumps({'error': {'code': 'neo4j_unavailable', 'message': 'Neo4j连接、认证或课程图谱未就绪；未使用离线替代数据。'}}, ensure_ascii=False).encode(); content_type = 'application/json; charset=utf-8'
            except Exception:
                status = 500; payload = b'{"error":{"code":"internal_error","message":"Request failed"}}'; content_type = 'application/json'
            self.send_response(status); self.send_header('Content-Type', content_type); self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers(); self.wfile.write(payload)
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('action', choices=('export', 'verify', 'import', 'serve', 'check'))
    parser.add_argument('--bundle', type=Path, default=BUNDLE); parser.add_argument('--output', type=Path)
    parser.add_argument('--production', type=Path, help='Sealed production inference run; export only')
    parser.add_argument('--url', default='http://127.0.0.1:7474'); parser.add_argument('--database', default='neo4j')
    parser.add_argument('--user', default='neo4j'); parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if args.production is not None and args.action != 'export': parser.error('--production is export-only')
    if args.action == 'export': print(json.dumps(export_graph(args.bundle, production=args.production), ensure_ascii=False, indent=2)); return
    if args.action == 'verify': print(json.dumps(verify_bundle(args.bundle)['manifest'], ensure_ascii=False, indent=2)); return
    password = os.environ.get('NEO4J_PASSWORD') or getpass.getpass('Neo4j password (not saved): ')
    client = Neo4j(args.url, args.database, args.user, password)
    if args.action == 'check': print(json.dumps(client.query('RETURN 1 AS connected', {}))); return
    if args.action == 'import':
        if args.output is None: parser.error('import requires --output for a new receipt')
        print(json.dumps(import_graph(client, args.bundle, args.output), ensure_ascii=False, indent=2)); return
    manifest = verified_files(args.bundle)
    if not 1024 <= args.port <= 65535: parser.error('port must be 1024..65535')
    print(f'Loopback read-only demo: http://127.0.0.1:{args.port}', flush=True)
    server(client, manifest['graphId'], args.port).serve_forever()


if __name__ == '__main__': main()
