import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import course_quality_app as app
import course_graph as g


def test_alias_search_expands_acronym_and_chinese_without_merging_versions():
    for value in ('LLM', 'LLMs', '大语言模型'):
        p = app.search_parameters({'method': [value]})
        assert 'large language model' in p['methodTerms'] and 'llm' in p['methodTerms']
    assert 'gpt-4o' not in app.search_parameters({'method': ['GPT-4']})['methodTerms']
    assert app.search_parameters({'method': ['RL']})['methodTerms'] == ['rl']
    with pytest.raises(ValueError): app.search_parameters({'method': ['x', 'y']})
    with pytest.raises(ValueError): app.search_parameters({'graphId': ['other']})


def test_quality_api_uses_live_scoped_graph_and_fails_closed():
    class Client:
        def __init__(self, status): self.status = status; self.calls = []
        def query(self, statement, params):
            self.calls.append((statement, params))
            return [{'status': self.status}] if len(self.calls) == 1 else [{'publication': {'publicationId': 'p1'}}]
    client = Client('completed'); status, body = app.api(client, 'g1', '/api/publications', {'method': ['CNN']})
    assert status == 200 and body['meta']['aliasVersion'] == 'typed_controlled_aliases_v2'
    assert client.calls[-1][1]['graph'] == 'g1' and 'convolutional neural network' in client.calls[-1][1]['methodTerms']
    with pytest.raises(g.DatabaseUnavailable): app.api(Client('importing'), 'g1', '/api/publications', {})
