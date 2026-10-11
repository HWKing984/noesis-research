"""Verify expanded development and live scoped graph; no test inference or DB writes."""
import csv
import getpass
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_graph as g


def main():
    output = ROOT / 'kg_datasets/dblp/course_v4_runs/delivery_checks_20261007_28'
    if output.exists(): raise FileExistsError('Preserve actual delivery checks')
    output.mkdir()
    state = {'status': 'running', 'createdAtUTC': datetime.now(UTC).isoformat(), 'readOnlyDatabase': True,
             'modelTestRepeated': False, 'modelPromoted': False, 'checks': []}
    try:
        runs = ROOT / 'kg_datasets/dblp/course_v4_runs'
        old = json.loads((runs / 'verification_20261007_round27.json').read_text(encoding='utf-8'))
        assert all(g.c.file_sha256(ROOT / p) == sha for p, sha in old['immutableSourceSha256'].items())
        lock = json.loads((runs / 'refresh_lock_20261007_28.json').read_text(encoding='utf-8'))
        assert len(lock['holdout']) == len({r['groupId'] for r in lock['holdout']}) == 200
        refs = g.c.read_jsonl(ROOT / 'kg_datasets/dblp/course_v4_weak/references.jsonl')
        assert not {r['groupId'] for r in refs} & {r['groupId'] for r in lock['holdout']}
        candidates = {}
        for name in ('ner_expanded_development_20261007_28', 're_expanded_development_20261007_28'):
            folder = runs / name
            manifest = g.verified_files(folder)
            result = json.loads((folder / 'development_result.json').read_text(encoding='utf-8'))
            status = json.loads((folder / 'status.json').read_text(encoding='utf-8'))
            assert status['status'] == 'completed' and status['trainingStarted']
            assert datetime.fromisoformat(status['createdAt']) > datetime.fromisoformat(lock['createdAtUTC'])
            assert result['passed'] and result['classifierChanged'] and result['encoderChanged'] and result['reloadPredictionsIdentical']
            assert not result['testEvaluated'] and not result['testTokenized'] and not result['devUsedForGradient']
            selected = folder / result['bestCheckpoint'] / 'model.safetensors'
            candidates[name] = {'result': result, 'config': manifest['config'], 'weightsSha256': g.c.file_sha256(selected),
                                'elapsedSeconds': status['elapsedSeconds']}
        state['candidateDevelopment'] = candidates
        snapshots = ROOT / 'kg_datasets/dblp'
        def ner_signature(row): return (row['sampleId'], row['text'], row['entities'])
        def re_signature(row): return (row['sampleId'], row['text'], row['head'], row['tail'], row['label'])
        for filename, old_snapshot, signature in [('ner_inputs_dev.jsonl', 'course_v4_training_inputs_08', ner_signature),
                                                  ('relation_inputs_dev.jsonl', 'course_v4_training_inputs_10', re_signature)]:
            prior = g.c.read_jsonl(snapshots / old_snapshot / filename)
            current = g.c.read_jsonl(snapshots / 'course_v4_training_inputs_17' / filename)
            assert list(map(signature, prior)) == list(map(signature, current)), filename
        state['sameDevContent'] = True
        with (snapshots / 'processed_ai/publications.csv').open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        markers = re.compile(r'\b(book review|retraction note|erratum|corrigendum|editorial|call for papers|table of contents)\b', re.I)
        flagged = [{'publicationId': r['publicationId:ID(Publication)'], 'title': r['title'],
                    'marker': m.group().lower(), 'status': 'needs_review_not_automatically_excluded'}
                   for r in rows if (m := markers.search(r['title']))]
        g.c.write_jsonl(output / 'quality_marker_review.jsonl', flagged)
        state['qualityTriage'] = {'markerMatches': len(flagged), 'markerCounts': dict(Counter(r['marker'] for r in flagged)),
                                  'dataModified': False, 'notVerifiedNonResearchLabels': True}
        with urlopen('http://127.0.0.1:8765/api/health', timeout=30) as response:
            health = json.loads(response.read())['data']
        assert health['source'] == 'live_neo4j' and health['scope']['bibliographyTitles'] == 20000
        graph = health['graphId']; state['graphId'] = graph
        client = g.Neo4j('http://127.0.0.1:7474', 'neo4j', 'neo4j', getpass.getpass('Neo4j password (not saved): '))
        queries = {
            'content_counts': 'MATCH (n:CourseNode {graphId:$graph}) RETURN count(n) AS count',
            'edge_counts': 'MATCH (a:CourseNode {graphId:$graph})-[r]->(b:CourseNode {graphId:$graph}) WHERE r.graphId=$graph RETURN type(r) AS kind,count(r) AS count ORDER BY kind',
            'coauthors_2hop': 'MATCH (a:CoursePerson {graphId:$graph,name:$author})-[:AUTHORED]->(p:CoursePublication)<-[:AUTHORED]-(b:CoursePerson) WHERE a<>b AND p.graphId=$graph AND b.graphId=$graph RETURN p.publicationId AS paper,b.name AS coauthor ORDER BY paper,coauthor LIMIT 30',
            'methods_3hop': 'MATCH (a:CoursePerson {graphId:$graph,name:$author})-[:AUTHORED]->(p:CoursePublication)-[:MENTIONS]->(m:CourseMention)-[:DENOTES]->(c:CourseConcept) WHERE p.graphId=$graph AND m.graphId=$graph AND c.graphId=$graph AND c.entityType="METHOD" RETURN p.publicationId AS paper,c.name AS method ORDER BY paper,method LIMIT 30',
        }
        for name, query in queries.items():
            result = client.query(query, {'graph': graph, 'author': 'Vaibhav Vavilala'})
            state['checks'].append({'name': name, 'cypher': query, 'result': result})
            assert result, name
        assert state['checks'][0]['result'][0]['count'] == 192185
        assert sum(r['count'] for r in state['checks'][1]['result']) == 263059
        assert any(r['paper'] == 'conf/3dim/VavilalaVF25' and r['method'] == 'Diffusion Models' for r in state['checks'][3]['result'])
        state['health'] = health
        state.update(status='completed', passed=True, qualityPromotionPassed=False)
    except Exception as error:
        state.update(status='failed', passed=False, error=str(error)); raise
    finally:
        state['finishedAtUTC'] = datetime.now(UTC).isoformat()
        g.c.write_json(output / 'result.json', state)
    print(json.dumps({'status': state['status'], 'readOnlyQueries': len(state['checks']), 'qualityTriage': state['qualityTriage']}, ensure_ascii=False))


if __name__ == '__main__': main()
