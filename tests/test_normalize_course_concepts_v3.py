import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import normalize_course_concepts_v3 as migration


def test_only_three_supported_typed_alias_groups_are_added():
    config, index = migration.vocabulary()
    assert config['version'] == 'typed_controlled_aliases_v3' and len(config['groups']) == 38
    key = lambda text, typ='METHOD': migration.canonical(text, typ, index)[0]
    for a, b in [('LoRA', 'Low-Rank Adaptation'), ('RAG', 'Retrieval-Augmented Generation'), ('Random Forests', 'Random Forest')]:
        assert key(a) == key(b)
        assert migration.canonical(a, 'METHOD', index)[1] == 'typed_controlled_aliases_v3'
    for a, b in config['noMergeExamples']:
        for typ in ('METHOD', 'TASK', 'DATASET'): assert key(a, typ) != key(b, typ)
    for a, b in [('GRU', 'gated recurrent units'), ('CRF', 'conditional random field'), ('RAG', 'RankRAG'), ('LoRA', 'AdaLoRA'), ('LoRA', 'QLoRA'), ('random forest', 'random forest classifier')]: assert key(a) != key(b)
    for typ in ('TASK', 'DATASET'):
        assert key('LoRA', typ) != key('low-rank adaptation', typ)
        assert key('RAG', typ) != key('retrieval-augmented generation', typ)


def test_frozen_normalizer_and_v2_default_remain_unchanged():
    original_path = migration.n.VOCAB
    original_version = migration.n.vocabulary()[0]['version']
    migration.vocabulary()
    assert migration.n.VOCAB == original_path
    assert migration.n.vocabulary()[0]['version'] == original_version == 'typed_controlled_aliases_v2'


@pytest.mark.parametrize('failure', ['type', 'proposal', 'duplicate', 'version', 'protected_alias'])
def test_v3_rejects_cross_type_proposals_or_unsupported_aliases(monkeypatch, failure):
    original = migration.json.loads(migration.VOCAB.read_text(encoding='utf-8'))
    config = copy.deepcopy(original)
    if failure == 'type': config['groups'][0]['type'] = 'TASK'
    if failure == 'proposal': config['groups'][0]['canonical'] = 'gated recurrent unit'
    if failure == 'duplicate': config['groups'].append(copy.deepcopy(config['groups'][0]))
    if failure == 'version': config['version'] = 'typed_controlled_aliases_v2'
    if failure == 'protected_alias': config['groups'][0]['aliases'].append('QLoRA')
    load_json = migration.json.loads
    monkeypatch.setattr(migration.json, 'loads', lambda text: config if text == migration.VOCAB.read_text(encoding='utf-8') else load_json(text))
    with pytest.raises(ValueError): migration.vocabulary()


def test_existing_output_is_not_overwritten(tmp_path):
    with pytest.raises(FileExistsError): migration.run(tmp_path)


def test_migration_cannot_write_over_sources_or_runtime():
    with pytest.raises(ValueError): migration.run(migration.g.ROOT/'resources/not_a_graph')


def small_graph_pair():
    config = migration.json.loads(migration.VOCAB.read_text(encoding='utf-8'))
    old_nodes, new_nodes, ledger = [], [], []
    for i, group in enumerate(config['groups']):
        aliases = [group['canonical']]+group['aliases']; target = f'new:Concept:{i}'
        new_nodes.append({'id': target, 'kind': 'Concept', 'props': {'id': target, 'graphId': 'new', 'entityType': 'METHOD', 'name': group['canonical'], 'aliases': aliases}})
        for j, name in enumerate(aliases):
            source = f'old:Concept:{i}-{j}'
            old_nodes.append({'id': source, 'kind': 'Concept', 'props': {'id': source, 'graphId': 'old', 'entityType': 'METHOD', 'name': name, 'aliases': [name]}})
            ledger.append({'oldConceptId': source, 'newConceptId': target, 'entityType': 'METHOD', 'oldName': name})
    for graph, nodes in [('old', old_nodes), ('new', new_nodes)]:
        nodes.append({'id': graph+':Mention:1', 'kind': 'Mention', 'props': {'id': graph+':Mention:1', 'graphId': graph, 'text': 'LoRA', 'start': 0, 'end': 4}})
        nodes.append({'id': graph+':Person:1', 'kind': 'Person', 'props': {'id': graph+':Person:1', 'graphId': graph, 'name': 'X', 'personId': 'unresolved-signature-x', 'identityStatus': 'unresolved'}})
    old_edge = {'kind': 'DENOTES', 'head': 'old:Mention:1', 'tail': 'old:Concept:0-0', 'props': {'id': 'old:Edge:1', 'graphId': 'old'}}
    new_edge = {'kind': 'DENOTES', 'head': 'new:Mention:1', 'tail': 'new:Concept:0', 'props': {'id': 'new:Edge:1', 'graphId': 'new'}}
    old = {'nodes': old_nodes, 'edges': [old_edge], 'manifest': {'graphId': 'old', 'counts': {'nodes': {'Concept': 6}}, 'modelSourceManifestSha256': 'same'}}
    new = {'nodes': new_nodes, 'edges': [new_edge], 'manifest': {'graphId': 'new', 'counts': {'nodes': {'Concept': 3}}, 'modelSourceManifestSha256': 'same'}}
    return old, new, ledger


def test_offline_parity_preserves_literals_and_author_identity():
    result = migration.parity(*small_graph_pair())
    assert result['actualAdditionalConceptReductions'] == 3
    assert result['literalAndModelPropertiesPreserved'] and result['allEdgeSignaturesAndEndpointsPreserved']
    assert not result['runtimeSwitched'] and not result['qualityPromotionPassed']


@pytest.mark.parametrize('failure', ['literal', 'type', 'edge', 'model', 'mapping'])
def test_parity_rejects_lost_evidence_cross_type_edges_models_or_mapping(failure):
    old, new, ledger = copy.deepcopy(small_graph_pair())
    if failure == 'literal': new['nodes'][-2]['props']['text'] = 'modified'
    if failure == 'type': new['nodes'][0]['props']['entityType'] = 'TASK'
    if failure == 'edge': new['edges'] = []
    if failure == 'model': new['manifest']['modelSourceManifestSha256'] = 'changed'
    if failure == 'mapping': ledger.pop()
    with pytest.raises(ValueError): migration.parity(old, new, ledger)
