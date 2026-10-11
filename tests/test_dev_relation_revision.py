"""One development-revision check: source-only labels, unchanged history, honest unknown coverage."""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import course_graph as g
import course_weak as c
from course_abstract_v1 import read
from course_abstract_relation import NER_FIELDS, revise, rows_for
from complete_dev_relations import build, source_cohort


def test_dev_revision_preserves_history_and_does_not_manufacture_complete_dataset_documents(tmp_path):
    config, parent, refs, old = source_cohort()
    folder = ROOT/'kg_datasets/dblp/course_abstract_dev_relation_reviewed_20261008_40'
    manifest = g.verified_files(folder)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    new = c.read_jsonl(folder/'reviewed_receipts.jsonl'); origins = c.read_jsonl(folder/'origins.jsonl')
    assert refs == c.read_jsonl(folder/'references.jsonl') and len(new) == len(old) == len(origins) == 19
    selected = set(config['revisionCohort'])
    for ref, prior, after, origin in zip(refs, old, new, origins):
        assert not c.validate_receipt(after, ref) and after['review'] is not None
        assert all(prior['annotation'][k] == after['annotation'][k] for k in NER_FIELDS)
        assert origin == {'sampleId': ref['sampleId'], 'upstreamReceiptSha256': prior['contentSha256'], 'relationRejudged': ref['arxivId'] in selected, 'NERReannotated': False}
        if ref['arxivId'] not in selected: assert prior == after
    before = rows_for(refs, old); after = rows_for(refs, new)
    assert len(before[0]) == len(after[0]) == 16 and before[3] == after[3] and len(after[3]) == 3
    assert len(before[1]) == 242 and len(after[1]) == 335 and after[4:] == (97, 432)
    assert len(before[2]) == 5 and len(after[2]) == 7
    key = lambda p: (p['sampleId'], p['head']['entityId'], p['tail']['entityId'])
    prior_pairs = {key(p): p for p in before[1]}; revised_pairs = {key(p): p for p in after[1]}
    assert set(prior_pairs) <= set(revised_pairs)
    assert all(all(row[k] == revised_pairs[pid][k] for k in ('head', 'tail', 'label', 'evidence', 'reason')) for pid, row in prior_pairs.items())
    added = [p for p in after[1] if key(p) not in prior_pairs]
    assert added == c.read_jsonl(folder/'additional_relation_dev.jsonl') and len(added) == 93
    summary = read(folder/'summary.json')
    assert summary['additionalSupport'] == {'USED_FOR': 57, 'NO_RELATION': 36} and summary['relationSupport'] == {'USED_FOR': 259, 'NO_RELATION': 66, 'EVALUATED_ON': 10}
    assert summary['completeDocumentEVALSupport'] == 0 and not any(p['label'] == 'EVALUATED_ON' and p['sampleId'] in {d['sampleId'] for d in after[2]} for p in after[1])
    assert summary['developmentPreviouslyExposed'] and not any(summary[k] for k in ('trainingExecuted', 'inferenceExecuted', 'newMetricsProduced', 'testContentAccessed', 'modelPromoted', 'qualityPromotionPassed'))
    parking = next(r['annotation'] for r in new if r['reference']['arxivId'] == '2001.11639')
    assert next(p for p in parking['relations'] if (p['head'], p['tail']) == ('e10', 'e3'))['label'] == 'UNRESOLVED'
    decisions = read(ROOT/'annotations/course_v4/abstract_dev_relation_decisions_20261008_40.json')['documents']
    for bad_change in ('negativeBasis', 'supportExcerpt'):
        decision = copy.deepcopy(next(d for d in decisions if d['arxivId'] == '1904.04163'))
        index = next(i for i, r in enumerate(refs) if r['arxivId'] == decision['arxivId'])
        if bad_change == 'negativeBasis': decision['groups'][0].pop('negativeBasis')
        else: decision['groups'][0]['supportExcerpt'] = 'fabricated evidence'
        with pytest.raises(ValueError): revise(old[index]['annotation'], refs[index], decision, parent)
    invalid_source = read(ROOT/'annotations/course_v4/abstract_dev_relation_decisions_20261008_40.json')
    invalid_source['documents'][0]['textSha256'] = '0'*64
    invalid_path = tmp_path/'wrong_source.json'; c.write_json(invalid_path, invalid_source)
    with pytest.raises(ValueError, match='Wrong source hash'):
        build(invalid_path, ROOT/'annotations/course_v4/abstract_dev_relation_reviews_20261008_40.json', tmp_path/'rejected')
    assert not (tmp_path/'rejected').exists()
    initial = c.read_jsonl(folder/'generation_receipts.jsonl')
    assert len(initial) == 11 and all(not c.eligible_tasks(r, r['reference'])['ner'] for r in initial)
    assert [d['arxivId'] for d in decisions if not d['groups']] == ['1903.09296', '2411.06463', '2001.11639', '2207.11187', '2307.15425']
    with pytest.raises(FileExistsError):
        build(Path('unused'), Path('unused'), folder)
