"""Verify preserved graph semantics, actual alias search and identity evidence; no fitting."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT/'scripts'))
import course_graph as g
from normalize_course_concepts import vocabulary, canonical


def run():
    output = ROOT/'kg_datasets/dblp/course_v4_runs/quality_acceptance_20261009_51.json'
    if output.exists(): raise FileExistsError('Preserve actual quality acceptance')
    state = {'status': 'running', 'checks': [], 'passed': False, 'qualityPromotionPassed': False}
    def check(name, condition):
        state['checks'].append({'name': name, 'passed': bool(condition)})
        if not condition: raise AssertionError(name)
    def get(path, **params):
        with urlopen('http://127.0.0.1:8766'+path+('?' + urlencode(params) if params else ''), timeout=30) as response: body = json.load(response)
        state.setdefault('responses', []).append({'path': path, 'parameters': params, 'response': body}); return body
    try:
        old = g.verify_bundle(ROOT/'kg_datasets/dblp/course_v4_graph_resolved_20261007_31_ready')
        folder = g.configured_bundle(ROOT/'resources/course_graph_quality_runtime.json'); new = g.verify_bundle(folder)
        stripped = lambda p: {k: v for k, v in p.items() if k not in ('id', 'graphId')}
        for kind in ('Publication', 'Venue', 'Mention', 'Assertion'):
            before = Counter(json.dumps(stripped(n['props']), ensure_ascii=False, sort_keys=True) for n in old['nodes'] if n['kind'] == kind)
            after = Counter(json.dumps(stripped(n['props']), ensure_ascii=False, sort_keys=True) for n in new['nodes'] if n['kind'] == kind)
            check(kind+'_literal_and_model_evidence_preserved', before == after)
        def signatures(bundle):
            nodes = {n['id']: n for n in bundle['nodes']}
            return Counter((nodes[e['tail']]['props']['publicationId'], e['props']['position'], e['props']['signatureName'], e['props']['legacyName'], e['props']['orcidSourceValue']) for e in bundle['edges'] if e['kind'] == 'AUTHORED')
        check('all_88762_literal_signatures_preserved', signatures(old) == signatures(new))
        check('all_edge_kind_counts_preserved', old['manifest']['counts']['edges'] == new['manifest']['counts']['edges'])
        mapping = g.c.read_jsonl(folder/'concept_mapping.jsonl'); check('every_29878_old_concept_mapped_once', len(mapping) == 29878 and len({r['oldConceptId'] for r in mapping}) == 29878)
        check('exactly_39_concepts_grouped', len({r['newConceptId'] for r in mapping}) == 29839)
        health = get('/api/health')['data']
        check('actual_live_graph_identity', health['source'] == 'live_neo4j' and health['graphId'] == new['manifest']['graphId'])
        check('actual_live_app_source_binding', health['appCodeSha256'] == g.c.file_sha256(ROOT/'scripts/course_quality_app.py'))
        check('actual_live_author_counts', health['resolution']['resolvedPersonNodes'] == 66093 and health['resolution']['unresolvedSignatureNodes'] == 9062)
        check('live_vocabulary_version', health['conceptVocabulary']['sha256'] == new['manifest']['vocabularySha256'] and health['terminology']['version'] == 'typed_controlled_aliases_v2')
        for terms in [('LLM', 'Large Language Models', '大语言模型'), ('CNN', 'convolutional neural network', '卷积神经网络'), ('GNN', 'graph neural network', '图神经网络'), ('ViT', 'vision transformer', '视觉Transformer')]:
            result = [[r['publicationId'] for r in get('/api/publications', method=term, limit=20)['data']] for term in terms]
            check('live_alias_equivalence_'+terms[0], bool(result[0]) and all(r == result[0] for r in result))
        authors = ROOT/'kg_datasets/dblp/course_v4_identity_crosswalk_20261009_51'
        g.verified_files(authors); recovered = [r for r in g.c.read_jsonl(authors/'recovery_ledger.jsonl') if r['newIdentity']]
        check('two_source_supported_recoveries', len(recovered) == 2)
        for r in recovered:
            a = next(a for a in get('/api/publication', id=r['publicationId'])['data']['authors'] if a['position'] == r['position'])
            check('live_recovered_'+r['name'], a['personId'] == r['newIdentity']['key'] and a['signatureName'] == r['name'] and not a['independentlyVerified'] and a['identityEvidenceMethods'] == ['source_orcid_unique_dblp_alias_crosswalk'])
            hits = get('/api/publications', authorId=a['personId'], limit=100)['data']; check('exact_author_search_'+r['name'], r['publicationId'] in {p['publicationId'] for p in hits})
        unresolved = next(s for s in g.c.read_jsonl(authors/'signatures.jsonl') if s['identity']['status'] != 'dblp_homepage_resolved')
        detail = get('/api/publication', id=unresolved['publicationId'])['data']
        a = next(a for a in detail['authors'] if a['position'] == unresolved['position'])
        hits = get('/api/publications', authorId=a['personId'], limit=100)['data']
        check('unresolved_signature_stays_single_paper', [p['publicationId'] for p in hits] == [unresolved['publicationId']])
        for mode in ('paper', 'coauthors', 'methods'):
            body = get('/api/graph', id='conf/3dim/VavilalaVF25', mode=mode, limit=30)
            check('scoped_live_multihop_'+mode, body['meta']['source'] == 'live_neo4j' and all(n['props']['graphId'] == health['graphId'] for n in body['data']['nodes']))
        for path, code, headers, method in [('/api/publications?method=x&method=y', 400, {}, 'GET'), ('/api/publications?graphId=old', 400, {}, 'GET'), ('/api/health', 403, {'Host': 'evil.invalid'}, 'GET'), ('/api/health', 501, {}, 'POST')]:
            request = Request('http://127.0.0.1:8766'+path, headers=headers, method=method)
            try:
                urlopen(request, timeout=30); actual = 200
            except HTTPError as error: actual = error.code
            check('reject_'+path+'_'+method+'_'+str(code), actual == code)
        config, index = vocabulary()
        check('protected_versions_and_subtypes', all(canonical(a, typ, index)[0] != canonical(b, typ, index)[0] for a, b in config['noMergeExamples'] for typ in ('METHOD', 'TASK', 'DATASET')))
        raw = json.loads((ROOT/'kg_datasets/dblp/course_v4_runs/relation_evidence_development_20261009_51/development_result.json').read_text(encoding='utf-8'))
        # Attribution correction only: frozen helper inherited a held_out target string on exposed dev.
        def attribution(value):
            if isinstance(value, list): return [attribution(v) for v in value]
            if isinstance(value, dict): return {k: 'development_AI_reference_agreement_not_final_test_or_human_gold' if k == 'evaluationTarget' else attribution(v) for k, v in value.items()}
            return value
        state['modelDiagnostic'] = attribution(raw)
        state['evaluationAttributionCorrection'] = 'Legacy helper target names corrected in this presentation copy only; raw sealed metrics/counts unchanged. Historical exposed7-doc dev and partial supplementary dev are neither final tests nor independent gold.'
        check('failed_model_experiment_not_promoted', not raw['qualityPromotionPassed'] and not raw['modelPromoted'] and not raw['trainingExecuted'] and not raw['testEvaluated'])
        receipt = json.loads((ROOT/'kg_datasets/dblp/course_v4_runs/import_quality_20261009_51.json').read_text(encoding='utf-8'))
        check('real_neo4j_import_count_parity', receipt['status'] == 'completed' and receipt['actualCounts'] == new['manifest']['counts'] and not receipt['databaseReset'])
        state.update(status='completed', passed=True, graphId=health['graphId'], graphCounts=new['manifest']['counts'],
            authorFullyDisambiguated=False, conceptsGloballyCanonicalized=False, modelReliabilityResolved=False,
            screenshotAttempts={'legacy_capture_1': 'timeout_no_screenshot', 'legacy_capture_2': 'timeout_no_screenshot', 'no_failed_screenshots_claimed': True})
    except Exception as error:
        state.update(status='failed', errorType=type(error).__name__, error=str(error)); raise
    finally: g.c.write_json(output, state)
    print(json.dumps({'passed': state['passed'], 'checks': len(state['checks']), 'graphId': state['graphId'], 'qualityPromotionPassed': False}))


if __name__ == '__main__': run()
