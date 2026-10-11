"""Pinned application vocabulary contracts; no training or database mutation."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import course_quality_app as app


@pytest.fixture(scope='module')
def v3():
    manifest = json.loads((app.g.ROOT/'kg_datasets/dblp/course_v4_graph_concepts_20261010_58/manifest.json').read_text(encoding='utf-8'))
    return app.load_vocabulary(manifest)


@pytest.mark.parametrize('aliases,expected', [
    (('LoRA', 'low-rank adaptation', '低秩适配'), {'lora', 'low-rank adaptation'}),
    (('RAG', 'retrieval-augmented generation', '检索增强生成'), {'rag', 'retrieval-augmented generation'}),
    (('random forest', 'random forests', '随机森林'), {'random forest', 'random forests'}),
])
def test_v3_aliases_reach_same_typed_canonical_terms(v3, aliases, expected):
    for alias in aliases:
        terms = app.search_parameters({'method': [alias]}, v3)['methodTerms']
        assert expected <= set(terms)
    # Acronyms and same-spelled words in other roles are not expanded across types.
    assert app.search_parameters({'task': [aliases[0]]}, v3)['taskTerms'] == [aliases[0].casefold()]
    assert app.search_parameters({'dataset': [aliases[0]]}, v3)['datasetTerms'] == [aliases[0].casefold()]


@pytest.mark.parametrize('value', ['QLoRA', 'AdaLoRA', 'DoRA', 'RankRAG', 'RAG-Token', 'RAG-Sequence', 'GRU', 'CRF'])
def test_v3_does_not_expand_models_variants_or_unapproved_proposals(v3, value):
    assert app.search_parameters({'method': [value]}, v3)['methodTerms'] == [value.casefold()]


def test_v3_preserves_existing_gpt_version_spelling_aliases(v3):
    gpt4 = app.search_parameters({'method': ['GPT-4']}, v3)['methodTerms']
    gpt4o = app.search_parameters({'method': ['GPT-4o']}, v3)['methodTerms']
    assert set(gpt4).isdisjoint(gpt4o) and {'gpt-4o', 'gpt4o'} <= set(gpt4o)


def test_legacy_v2_selection_and_drift_fail_closed():
    manifest = json.loads((app.g.ROOT/'kg_datasets/dblp/course_v4_graph_quality_20261009_51/manifest.json').read_text(encoding='utf-8'))
    config, _, sha = app.load_vocabulary(manifest)
    assert config['version'] == 'typed_controlled_aliases_v2' and sha == manifest['vocabularySha256']
    assert app.search_parameters({'method': ['LoRA']})['methodTerms'] == ['lora']
    with pytest.raises(ValueError, match='vocabulary'):
        app.load_vocabulary(manifest | {'vocabularySha256': '0'*64})
    with pytest.raises(ValueError, match='vocabulary'):
        app.load_vocabulary(manifest | {'vocabularyVersion': 'unreviewed'})
    with pytest.raises(ValueError, match='vocabulary'):
        app.load_vocabulary(manifest | {'vocabularyVersion': 'typed_controlled_aliases_v3'})


def test_v3_health_search_share_pinned_snapshot_without_request_hashes(v3, monkeypatch):
    class Client:
        def query(self, statement, params):
            assert params['graph'] == 'g58'
            if 'RETURN g.status' in statement: return [{'status': 'completed'}]
            if 'AS bibliographyTitles' in statement: return [{'bibliographyTitles': 20000, 'modelTitles': 19999, 'rejectedNERTitles': 1}]
            if 'AS candidateAssertions' in statement: return [{'candidateAssertions': 21497}]
            assert statement == app.SEARCH_QUERY
            assert {'lora', 'low-rank adaptation'} <= set(params['methodTerms'])
            return [{'publication': {'publicationId': 'example', 'title': 'A model', 'year': 2025}}]
    def unexpected(*args, **kwargs): raise AssertionError('Request reloaded or hashed vocabulary')
    monkeypatch.setattr(app, 'load_vocabulary', unexpected)
    monkeypatch.setattr(app, 'vocabulary', unexpected)
    monkeypatch.setattr(app.g.c, 'file_sha256', unexpected)
    for _ in range(2):
        status, body = app.api(Client(), 'g58', '/api/health', {}, v3)
        assert status == 200
        assert body['data']['conceptVocabulary']['version'] == body['data']['terminology']['version'] == 'typed_controlled_aliases_v3'
        assert body['data']['conceptVocabulary']['sha256'] == v3[2]
        assert body['data']['conceptVocabulary']['modelReliabilityPromoted'] is False
        status, body = app.api(Client(), 'g58', '/api/publications', {'method': ['低秩适配']}, v3)
        assert status == 200 and body['meta']['aliasVersion'] == 'typed_controlled_aliases_v3'
        assert body['meta']['jointPolicy'] == 'same_publication_same_method_concept_separate_candidate_assertions'
        assert body['data'][0]['publicationStatus']['verified'] is False
