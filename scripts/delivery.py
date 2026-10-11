"""Frozen V1 entry and small delivery checks; never train or promote V2."""
import argparse
import getpass
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

import course_quality_app as app

ROOT = app.g.ROOT
GRAPH = 'ai-literature-63686318d85cccb07afb'


def client():
    return app.g.Neo4j('http://127.0.0.1:7474', 'neo4j', 'neo4j',
                       os.environ.get('NEO4J_PASSWORD') or getpass.getpass('Neo4j password (not saved): '))


def verify_files():
    manifest = json.loads((ROOT/'docs/delivery/manifest.json').read_text(encoding='utf-8'))
    for name, sha in manifest['filesSha256'].items():
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or app.g.c.file_sha256(path) != sha:
            raise ValueError('Missing or changed delivery file: '+name)
    if manifest['productionReplacementAllowed'] or manifest['test20BodyIncluded']:
        raise ValueError('Delivery freeze boundary violated')
    print('Delivery file hashes verified:', len(manifest['filesSha256']), flush=True)
    return manifest


def verify_live(port):
    checks = []
    def request(path, status=200, **query):
        route = path+('?' + urlencode(query) if query else '')
        try:
            with urlopen(f'http://127.0.0.1:{port}'+route, timeout=30) as response:
                code, body = response.status, json.load(response)
        except HTTPError as response:
            code, body = response.code, json.load(response)
        if code != status:
            raise RuntimeError(f'{route}: HTTP {code}, expected {status}')
        checks.append({'route': route, 'status': code})
        return body
    health = request('/api/health')['data']
    if health['status'] != 'ready' or health['graphId'] != GRAPH or health['source'] != 'live_neo4j':
        raise RuntimeError('Not the ready frozen V1 graph')
    rows = request('/api/publications', method='卷积神经网络', limit=5)['data']
    if not rows:
        raise RuntimeError('Chinese search returned no papers')
    pid = 'conf/seeda/VonitsanosESKM25'
    detail = request('/api/publication', id=pid)['data']
    if not detail['authors'] or not detail['mentions'] or not detail['assertions']:
        raise RuntimeError('Demo paper missing authors/entities/relations')
    graph_views = {}
    for view in ('paper', 'coauthors', 'methods'):
        data = request('/api/graph', id=pid, mode=view)['data']
        if not data['nodes'] or not data['edges']:
            raise RuntimeError('Empty graph: '+view)
        graph_views[view] = {'nodes': len(data['nodes']), 'edges': len(data['edges'])}
    request('/api/publications', 400, limit=0)
    request('/api/publication', 404, id='delivery-missing-paper')
    request('/api/health', 400, unexpected=1)
    return {'status': 'passed', 'liveHealth': health, 'HTTPChecks': checks, 'graphViews': graph_views,
            'modelQualityReevaluated': False, 'test20Read': False}


def infer_demo(output):
    """Actual title inference on five existing bibliography records, not an evaluation."""
    import torch
    import train_course_ner as ner
    import train_course_relation as re_model
    from evaluate_course_relation import candidate_rows, predict
    from transformers import AutoModelForTokenClassification, AutoTokenizer, DataCollatorWithPadding
    inventory = json.loads((ROOT/'docs/delivery/models.json').read_text(encoding='utf-8'))
    paths = {r['name']: ROOT/r['path'] for r in inventory['models']}
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    torch.set_num_threads(4)
    nt = AutoTokenizer.from_pretrained(paths['V1_NER'], local_files_only=True, use_fast=True)
    nm, info = AutoModelForTokenClassification.from_pretrained(paths['V1_NER'], local_files_only=True,
                                                               output_loading_info=True)
    if any(info[k] for k in ('missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs')):
        raise RuntimeError('Incomplete V1 NER weight loading')
    nm.to(device).eval().requires_grad_(False)
    rt = re_model.prepare_tokenizer(paths['V1_RE'])
    rm = re_model.load_relation_model(paths['V1_RE'], rt).to(device).eval().requires_grad_(False)
    rows = json.loads((ROOT/'docs/delivery/v1_demo_papers.json').read_text(encoding='utf-8'))
    records = []
    for row in rows:
        doc = {k: row[k] for k in ('sampleId', 'text', 'textSha256')}
        encoded = nt(doc['text'], return_offsets_mapping=True, return_tensors='pt', truncation=False)
        offsets = encoded.pop('offset_mapping')[0].tolist()
        if encoded['input_ids'].shape[1] > 128:
            raise ValueError('Demo title exceeds frozen limit; no truncation')
        with torch.inference_mode():
            labels = nm(**{k:v.to(device) for k,v in encoded.items()}).logits.argmax(-1)[0].cpu().tolist()
        decoded = ner.decode_bio(labels, offsets, doc['text'])
        pairs = candidate_rows(doc, decoded['entities'])
        predictions = predict(rm, rt, pairs, 128, DataCollatorWithPadding(rt), device, 8)
        records.append(row | {'entities': decoded['entities'], 'invalidTransitions': decoded['invalidTransitions'],
                               'relations': predictions})
    if output.exists():
        raise FileExistsError('Preserve the existing inference receipt')
    app.g.c.write_json(output, {'status': 'passed', 'actualWeightLoading': True, 'device': str(device),
                               'trainingExecuted': False, 'evaluationExecuted': False, 'papers': records})
    print('Actual frozen V1 inference completed:', len(records), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('action', choices=('serve', 'verify', 'infer-demo'))
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--files', action='store_true')
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    if not 1024 <= args.port <= 65535:
        p.error('port must be 1024..65535')
    if args.action == 'infer-demo':
        if args.output is None:
            p.error('infer-demo requires a new --output receipt')
        infer_demo(args.output); return
    if args.action == 'verify':
        if args.files:
            verify_files()
        result = verify_live(args.port)
        if args.output:
            if args.output.exists():
                raise FileExistsError('Preserve verification receipt')
            app.g.c.write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2)); return
    bundle = app.g.configured_bundle(app.CONFIG)
    manifest = app.g.verified_files(bundle)
    if manifest['graphId'] != GRAPH:
        raise RuntimeError('Production graph pin changed')
    db = client()
    found = db.query('MATCH (g:CourseGraph {id:$graph}) RETURN g.status AS status', {'graph': GRAPH})
    if not found or found[0]['status'] != 'completed':
        # Initial import uses the existing graph-scoped, non-deleting importer.
        from datetime import datetime
        receipt = ROOT/'outputs'/('delivery_import_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.json')
        app.g.import_graph(db, bundle, receipt)
    aliases = app.load_vocabulary(manifest)
    status, body = app.api(db, GRAPH, '/api/health', {}, aliases)
    if status != 200 or body['data']['status'] != 'ready':
        raise RuntimeError('V1 graph unavailable; no offline fallback')
    server = app.server(db, GRAPH, args.port, aliases)
    original = server.RequestHandlerClass
    class DeliveryHandler(original):
        def do_GET(self):
            static = {'/delivery-demo': 'demo.html', '/delivery-report': 'report.html'}
            if self.path not in static:
                return super().do_GET()
            if self.headers.get('Host') not in (f'127.0.0.1:{args.port}', f'localhost:{args.port}'):
                self.send_error(403); return
            payload = (ROOT/'docs/delivery'/static[self.path]).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers(); self.wfile.write(payload)
    server.RequestHandlerClass = DeliveryHandler
    print(f'V1 ready: http://127.0.0.1:{args.port}/ | experimental evidence: /delivery-demo', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
