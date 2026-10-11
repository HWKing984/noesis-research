"""Application behavior, independent of immutable training/export sources."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import course_quality_app as app


def test_search_policy_defaults_and_validation():
    p = app.search_parameters({'method': ['GPT-4'], 'task': ['classification'], 'dataset': ['MNIST']})
    assert p['conceptMatch'] == 'exact' and p['publicationStatus'] == 'exclude_retractions'
    assert 'gpt-4o' not in p['methodTerms']
    assert app.search_parameters({'conceptMatch': ['contains'], 'publicationStatus': ['all']})['conceptMatch'] == 'contains'
    for q in ({'conceptMatch':['bad']}, {'publicationStatus':['normal']}, {'conceptMatch':['exact','contains']}):
        with pytest.raises(ValueError): app.search_parameters(q)


@pytest.mark.parametrize('title,status', [
    ('RETRACTED ARTICLE: Deep learning system', 'retraction_signal'),
    ('Retraction Note: AI models', 'retraction_signal'),
    ('Retracted: A model', 'retraction_signal'),
    ('Corrigendum to: Neural networks', 'correction_signal'),
    ('Erratum to a model', 'correction_signal'),
    ('Retractions in machine learning: a survey', 'unverified'),
    ('Learning retraction operators on manifolds', 'unverified'),
    ('A neural model', 'unverified'),
])
def test_title_signals_are_not_publisher_verification(title, status):
    original = {'title':title, 'publicationId':'example'}
    annotated = app.publication_view(original)
    assert annotated['publicationStatus']['code'] == status
    assert annotated['publicationStatus']['verified'] is False
    assert annotated['publicationStatus']['source'] == 'title_prefix_rule_v1'
    assert annotated['title'] == title and 'publicationStatus' not in original


def test_fixed_query_is_used_by_api_and_scoped():
    class Client:
        def query(self, query, params):
            if 'RETURN g.status' in query: return [{'status':'completed'}]
            assert query == app.SEARCH_QUERY and params['graph'] == 'g'
            assert params['task'] and params['dataset'] and params['conceptMatch'] == 'exact'
            return [{'publication': {'title':'Corrigendum to: AI'}}]
    _, body = app.api(Client(), 'g', '/api/publications', {'task':['classification'], 'dataset':['MNIST']})
    assert body['data'][0]['publicationStatus']['code'] == 'correction_signal'
    assert body['meta']['conceptMatch'] == 'exact'
    assert 'tc.entityType' in app.SEARCH_QUERY and 'dc.entityType' in app.SEARCH_QUERY
    assert 'mh:CourseMention' in app.SEARCH_QUERY


def test_page_exposes_policy_and_keeps_warning_in_exports():
    page=(app.g.ROOT/'resources/course_literature.html').read_text(encoding='utf-8')
    assert 'name="conceptMatch"' in page and 'name="publicationStatus"' in page
    assert 'publicationStatus?.notice' in page
