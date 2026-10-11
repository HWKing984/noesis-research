"""Live read-only alias acceptance; no model evaluation or database writes."""
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_graph as g


def main():
    output = ROOT / 'kg_datasets/dblp/course_v4_runs/chinese_acceptance_20261007_27.json'
    if output.exists(): raise FileExistsError('Preserve actual acceptance')
    state = {'status': 'running', 'startedAtUTC': datetime.now(UTC).isoformat(),
             'readOnly': True, 'modelQualityEvaluation': False, 'checks': [], 'comparisons': []}
    def request(path, expected=200):
        try:
            with urlopen('http://127.0.0.1:8765' + path, timeout=30) as response:
                status, raw = response.status, response.read()
        except HTTPError as error:
            status, raw = error.code, error.read()
        body = json.loads(raw)
        state['checks'].append({'path': path, 'httpStatus': status, 'body': body})
        assert status == expected, (path, status)
        return body
    try:
        health = request('/api/health')['data']
        assert health['source'] == 'live_neo4j'
        assert health['scope'] == {'bibliographyTitles': 20000, 'modelTitles': 19999,
                                   'rejectedNERTitles': 1, 'candidateAssertions': 21497}
        assert health['terminology'] == g.TERMINOLOGY
        state['graphId'] = health['graphId']
        for field, zh, en in [('q', '知识图谱', 'knowledge graph'), ('q', '大语言模型', 'large language model'),
                              ('method', '扩散模型', 'diffusion model'), ('task', '机器翻译', 'machine translation'),
                              ('venue', 'AAAI会议', 'aaai')]:
            chinese = request('/api/publications?' + urlencode({field: zh, 'limit': 100}))
            english = request('/api/publications?' + urlencode({field: en, 'limit': 100}))
            assert chinese['data'] and chinese['data'] == english['data'], (field, zh)
            assert chinese['meta']['expandedTerms'][field][0] == zh.lower()
            assert english['meta']['expandedTerms'] == {}
            state['comparisons'].append({'field': field, 'zh': zh, 'en': en,
                                          'pageSize': len(chinese['data']), 'hasNext': chinese['meta']['hasNext'],
                                          'orderedFirstPageEqual': True, 'allPagesCompared': False})
        pid = 'conf/3dim/VavilalaVF25'
        selected = request('/api/publications?' + urlencode({'method': '扩散模型', 'q': 'Denoising Monte Carlo Renders'}))
        assert len(selected['data']) == 1 and selected['data'][0]['publicationId'] == pid
        detail = request('/api/publication?' + urlencode({'id': pid}))['data']
        title = detail['publication']['title']
        assert title == 'Denoising Monte Carlo Renders with Diffusion Models.'
        assert detail['assertions'][0]['assertion']['status'] == 'candidate'
        assert detail['assertions'][0]['assertion']['confidenceCalibrated'] is False
        for m in detail['mentions']:
            assert title[m['start']:m['end']] == m['text']
            assert m['textSha256'] == hashlib.sha256(title.encode()).hexdigest()
        original = json.loads((ROOT / 'kg_datasets/dblp/course_v4_runs/application_acceptance_20261007_26_final.json').read_text(encoding='utf-8'))
        old = next(c['body']['data'] for c in original['checks'] if c['path'].startswith('/api/publication?id=conf%2F3dim'))
        assert detail == old, 'Underlying detail/evidence changed'
        assert request('/api/publications?' + urlencode({'method': '未知中文术语27'}))['data'] == []
        unknown = request('/api/publications?' + urlencode({'q': '用扩散模型的论文有哪些'}))
        assert unknown['meta']['expandedTerms'] == {} and not unknown['data']
        request('/api/publications?' + urlencode({'q': '中' * 201}), 400)
        request('/api/publications?qTerms=forged', 400)
        request('/api/publications?q=a&q=b', 400)
        state.update(status='completed', passed=True, checkedRequests=len(state['checks']))
    except Exception as error:
        state.update(status='failed', passed=False, error=str(error))
        raise
    finally:
        state['finishedAtUTC'] = datetime.now(UTC).isoformat()
        g.c.write_json(output, state)
    print(json.dumps({key: state[key] for key in ('status', 'checkedRequests', 'graphId')}, ensure_ascii=False))


if __name__ == '__main__': main()
