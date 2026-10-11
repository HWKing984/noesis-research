"""Typed aliases with immutable mentions and version-preserving graph migration."""
import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import course_graph as g
from course_resolution import concept_key

VOCAB = g.ROOT/'resources/course_concept_v2.json'


def spelling(name):
    if not isinstance(name, str) or not name.strip(): raise ValueError('Empty concept')
    return ' '.join(unicodedata.normalize('NFC', name).split()).casefold().replace('\u2011', '-')


def vocabulary(path=VOCAB):
    value = json.loads(path.read_text(encoding='utf-8')); index = {}
    if value['version'] != 'typed_controlled_aliases_v2': raise ValueError('Vocabulary drift')
    for group in value['groups']:
        if group['type'] not in ('METHOD', 'TASK', 'DATASET') or not group['evidence'] or not group['zh']: raise ValueError('Invalid typed alias')
        for name in [group['canonical']]+group['aliases']:
            key = group['type'], spelling(name)
            if key in index and index[key]['canonical'] != group['canonical']: raise ValueError('Ambiguous typed alias')
            if name in value['excludedAmbiguousAliases']: raise ValueError('Ambiguous acronym used globally')
            index[key] = group
    return value, index


def canonical(name, entity_type, index):
    if entity_type not in ('METHOD', 'TASK', 'DATASET'): raise ValueError('Invalid concept type')
    literal = spelling(name); group = index.get((entity_type, literal))
    if group: return group['canonical'], 'typed_controlled_aliases_v2', group
    key, policy = concept_key(literal, entity_type)
    return key, policy, None


def family(key, entity_type):
    if entity_type != 'METHOD': return None
    for pattern, group in ((r'gpt[- ]?\d', 'gpt'), (r'yolo[- ]?v?\d', 'yolo'), (r'bert[- ](?:base|large)', 'bert'), (r'llama[- ]?\d', 'llama')):
        if re.match(pattern, key): return group
    return None


def run(base, identities, output):
    if output.exists(): raise FileExistsError('Preserve graph; use a new output')
    source = g.verify_bundle(base); g.verified_files(identities); config, index = vocabulary()
    paths = [base/'manifest.json', identities/'manifest.json', VOCAB, Path(__file__), g.ROOT/'tests/test_normalize_course_concepts.py']
    hashes = {p.relative_to(g.ROOT).as_posix(): g.c.file_sha256(p) for p in paths}
    graph = 'ai-literature-'+g.c.canonical_sha256({'inputs': hashes, 'schema': 'concept_v2'})[:20]
    mapping = {}; nodes = {}; groups = defaultdict(list); ledger = []; old_graph = source['manifest']['graphId']
    methods = defaultdict(set)
    for s in g.c.read_jsonl(identities/'signatures.jsonl'):
        if s['identity']['status'] == 'dblp_homepage_resolved': methods[s['identity']['key']].add(s['identity'].get('method', 'dblp_exact_case_sensitive_homepage_alias'))
    for n in source['nodes']:
        props = n['props']
        if n['kind'] == 'Concept':
            key, policy, group = canonical(props['name'], props['entityType'], index)
            nid = g.identifier(graph, 'Concept', [props['entityType'], key]); groups[nid].append(n)
            row = {'name': key, 'entityType': props['entityType'], 'canonicalKey': key, 'normalization': policy,
                'normalizationSource': 'AI_curated_typed_vocabulary_not_dblp_fact', 'vocabularySha256': g.c.file_sha256(VOCAB)}
            if group: row.update(displayNameZh=group['zh'], normalizationEvidence=group['evidence'])
            parent = family(key, props['entityType'])
            if parent: row.update(familyCanonicalKey=parent, familyRelation='VARIANT_OF_not_equivalence')
            ledger.append({'oldConceptId': n['id'], 'oldName': props['name'], 'entityType': props['entityType'], 'newConceptId': nid, 'canonicalKey': key, 'policy': policy})
        else:
            if not n['id'].startswith(old_graph+':'): raise ValueError('Unexpected graph identity')
            nid = graph+n['id'][len(old_graph):]; row = props.copy()
            if n['kind'] == 'Person' and props['personId'] in methods:
                row['identityEvidenceMethods'] = sorted(methods[props['personId']])
                row['identityEvidence'] = '+'.join(row['identityEvidenceMethods'])
        mapping[n['id']] = nid
        nodes[nid] = {'kind': n['kind'], 'id': nid, 'props': row | {'id': nid, 'graphId': graph}}
    for nid, members in groups.items():
        aliases = {alias for n in members for alias in [n['props']['name']]+n['props'].get('aliases', [])}
        key = nodes[nid]['props']['canonicalKey']; group = index.get((nodes[nid]['props']['entityType'], key))
        if group: aliases.update([group['canonical']]+group['aliases'])
        nodes[nid]['props'].update(aliases=sorted(aliases), legacyConceptIds=sorted(n['id'] for n in members))
    edges = []
    for edge in source['edges']:
        head, tail = mapping[edge['head']], mapping[edge['tail']]
        eid = g.identifier(graph, 'Edge', [edge['kind'], head, tail, edge['props'].get('position')])
        edges.append(edge | {'id': eid, 'head': head, 'tail': tail, 'props': edge['props'] | {'id': eid, 'graphId': graph}})
    if len({e['id'] for e in edges}) != len(edges): raise ValueError('Edge collision after merge')
    if any(g.c.file_sha256(g.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Normalization input drift')
    summary = {'oldConceptNodes': len(ledger), 'newConceptNodes': len(groups), 'sourceConceptsGrouped': len(ledger)-len(groups),
        'controlledConceptNodes': sum(n['props'].get('normalization') == config['version'] for n in nodes.values()),
        'controlledAliasGroups': len(config['groups']), 'variantConceptNodes': sum('familyCanonicalKey' in n['props'] for n in nodes.values()),
        'literalMentionsUnchanged': True, 'candidateAssertionCountUnchanged': True, 'authorSignaturesUnchanged': True,
        'modelReliabilityPromoted': False, 'liveDatabaseImported': False}
    output.mkdir(parents=True); g.c.write_jsonl(output/'nodes.jsonl', list(nodes.values())); g.c.write_jsonl(output/'edges.jsonl', edges)
    g.c.write_jsonl(output/'concept_mapping.jsonl', ledger); g.c.write_json(output/'resolution_summary.json', source['manifest'].get('resolution', {}) | summary)
    manifest = source['manifest'] | {'graphId': graph, 'createdAtUTC': datetime.now(UTC).isoformat(), 'inputSha256': hashes,
        'baseGraphId': old_graph, 'liveDatabaseImported': False, 'resolution': source['manifest'].get('resolution', {}) | summary,
        'exporterCodeSha256': g.c.file_sha256(Path(__file__)), 'vocabularySha256': g.c.file_sha256(VOCAB),
        'counts': {'nodes': dict(Counter(n['kind'] for n in nodes.values())), 'edges': dict(Counter(e['kind'] for e in edges))},
        'notice': 'Typed controlled aliases; variants not equivalence. Original model candidates and evidence preserved, not verified facts.',
        'filesSha256': {p.name: g.c.file_sha256(p) for p in output.iterdir() if p.is_file()}}
    g.c.write_json(output/'manifest.json', manifest); g.verify_bundle(output); print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--identities', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); run(args.base.resolve(), args.identities.resolve(), args.output.resolve())
