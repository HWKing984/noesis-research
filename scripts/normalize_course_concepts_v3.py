"""Offline v3 alias extension using the immutable normalizer; no runtime/database switch."""
import argparse
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from unittest.mock import patch

import normalize_course_concepts as n

g, c = n.g, n.g.c
VOCAB = g.ROOT/'resources/course_concept_v3.json'
BASE = g.ROOT/'kg_datasets/dblp/course_v4_graph_quality_20261009_51'
IDENTITIES = g.ROOT/'kg_datasets/dblp/course_v4_identity_crosswalk_20261009_51'
ORIGINAL_VOCABULARY, ORIGINAL_CANONICAL = n.vocabulary, n.canonical


def vocabulary():
    extension = json.loads(VOCAB.read_text(encoding='utf-8'))
    if extension['version'] != 'typed_controlled_aliases_v3' or not extension['offlineOnly'] or extension['runtimeSwitchAllowed'] or extension['trainingAllowed']: raise ValueError('V3 migration scope changed')
    if any(c.file_sha256(g.ROOT/p) != sha for p, sha in extension['sourceBindings'].items()): raise ValueError('V3 source binding drift')
    base, index = ORIGINAL_VOCABULARY(g.ROOT/extension['baseVocabulary']); index = index.copy()
    evidence = g.ROOT/extension['candidateEvidence']; g.verified_files(evidence)
    supported = {x['canonical']: x for x in c.read_jsonl(evidence/'groups.jsonl') if x['status'] in ('candidate_local_definition', 'candidate_spelling_only')}
    groups = extension['groups']
    if len(groups) != 3 or {x['canonical'] for x in groups} != set(supported): raise ValueError('Only three supported candidates allowed')
    for group in groups:
        names = [group['canonical']]+group['aliases']; source = supported[group['canonical']]
        if group['type'] != 'METHOD' or not group['evidence'] or not group['zh'] or set(map(n.spelling, names)) != set(source['members']): raise ValueError('Unsupported typed alias')
        for name in names:
            key = group['type'], n.spelling(name)
            if key in index: raise ValueError('Typed alias collision')
            index[key] = group
    return base | {'version': extension['version'], 'groups': base['groups']+groups,
        'noMergeExamples': base['noMergeExamples']+extension['noMergeExamples'], 'reviewSource': extension['reviewSource']}, index


def canonical(name, entity_type, index):
    key, policy, group = ORIGINAL_CANONICAL(name, entity_type, index)
    return key, 'typed_controlled_aliases_v3' if group else policy, group


def parity(old, new, ledger):
    stripped = lambda props: {k: v for k, v in props.items() if k not in ('id', 'graphId')}
    before = {n['id']: n for n in old['nodes']}; after = {n['id']: n for n in new['nodes']}
    mapped = {key: new['manifest']['graphId']+key[len(old['manifest']['graphId']):] for key, node in before.items() if node['kind'] != 'Concept'}
    if len(ledger) != old['manifest']['counts']['nodes']['Concept'] or len({r['oldConceptId'] for r in ledger}) != len(ledger): raise ValueError('Incomplete concept mapping')
    mapped.update({r['oldConceptId']: r['newConceptId'] for r in ledger})
    if set(mapped) != set(before): raise ValueError('Lost original node identity')
    for node_id, node in before.items():
        target = after[mapped[node_id]]
        if node['kind'] != target['kind'] or (node['kind'] != 'Concept' and stripped(node['props']) != stripped(target['props'])): raise ValueError('Literal/model/person property lost')
        if node['kind'] == 'Concept' and (node['props']['entityType'] != target['props']['entityType'] or not set([node['props']['name']]+node['props'].get('aliases', [])) <= set(target['props']['aliases'])): raise ValueError('Typed concept aliases lost')
    old_edges = Counter(c.canonical_sha256([e['kind'], mapped[e['head']], mapped[e['tail']], stripped(e['props'])]) for e in old['edges'])
    new_edges = Counter(c.canonical_sha256([e['kind'], e['head'], e['tail'], stripped(e['props'])]) for e in new['edges'])
    if old_edges != new_edges: raise ValueError('Edge signatures, evidence or connectivity changed')
    members = defaultdict(set)
    for row in ledger: members[row['newConceptId']].add((row['entityType'], n.spelling(row['oldName'])))
    actual = {frozenset(values) for values in members.values() if len(values) > 1}
    config = json.loads(VOCAB.read_text(encoding='utf-8'))
    expected = {frozenset(('METHOD', n.spelling(name)) for name in [x['canonical']]+x['aliases']) for x in config['groups']}
    if actual != expected or len(new['nodes']) != len(old['nodes'])-3: raise ValueError('Unexpected concept or version merge')
    if old['manifest']['modelSourceManifestSha256'] != new['manifest']['modelSourceManifestSha256']: raise ValueError('Model version drift')
    return {'status': 'completed', 'literalAndModelPropertiesPreserved': True, 'personPropertiesPreserved': True,
        'allEdgeSignaturesAndEndpointsPreserved': True, 'sourceConceptAliasesPreserved': True, 'onlyThreeApprovedMethodGroupsMerged': True,
        'actualAdditionalConceptReductions': 3, 'counts': new['manifest']['counts'], 'modelSourceUnchanged': True,
        'graphId': new['manifest']['graphId'], 'liveDatabaseImported': False, 'runtimeSwitched': False, 'trainingExecuted': False,
        'qualityPromotionPassed': False, 'notice': 'Offline structural/evidence parity, not semantic accuracy, online retrieval acceptance or global concept resolution.'}


def run(output):
    output = output.resolve()
    if output.exists(): raise FileExistsError('Preserve graph candidate')
    if not output.is_relative_to((g.ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Output outside datasets')
    config, index = vocabulary(); hashes = json.loads(VOCAB.read_text(encoding='utf-8'))['sourceBindings'] | {'resources/course_concept_v3.json': c.file_sha256(VOCAB)}
    required = sum((BASE/name).stat().st_size for name in ('nodes.jsonl', 'edges.jsonl', 'concept_mapping.jsonl'))+1_000_000_000+50_000_000
    if shutil.disk_usage(output.parent).free < required: raise ValueError('Insufficient graph disk budget; preserve1GB reserve')
    try:
        with patch.multiple(n, VOCAB=VOCAB, vocabulary=lambda: (config, index), canonical=canonical): n.run(BASE, IDENTITIES, output)
        old, new = g.verify_bundle(BASE), g.verify_bundle(output)
        verification = parity(old, new, c.read_jsonl(output/'concept_mapping.jsonl'))
        if any(c.file_sha256(g.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Migration sources changed')
        c.write_json(output/'migration_verification.json', verification)
        manifest = new['manifest'] | {'candidateStatus': 'offline_parity_passed_not_live', 'vocabularyVersion': config['version'],
            'migrationInputSha256': hashes, 'migrationEntryPointSha256': c.file_sha256(Path(__file__)),
            'filesSha256': {p.name: c.file_sha256(p) for p in output.iterdir() if p.is_file() and p.name != 'manifest.json'}}
        c.write_json(output/'manifest.json', manifest); g.verified_files(output)
        print(json.dumps(verification), flush=True)
    except Exception as error:
        if output.exists(): c.write_json(output/'migration_status.json', {'status': 'failed_not_promoted', 'error': str(error)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True); run(parser.parse_args().output)
