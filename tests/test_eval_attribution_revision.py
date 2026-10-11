"""One attribution check: explicit retractions mask unknowns, never fabricate negatives."""
import copy
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import course_graph as g
import course_weak as c
from course_abstract_v1 import read
from course_abstract_relation import NER_FIELDS, rows_for
from review_eval_attribution import source_cohorts, revise_attribution


def test_eval_revision_preserves_ner_and_binds_every_old_judgment():
    _, sources = source_cohorts()
    folder = ROOT/'kg_datasets/dblp/course_abstract_eval_attribution_reviewed_20261008_41'
    manifest = g.verified_files(folder)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    decisions_path = ROOT/'annotations/course_v4/abstract_eval_attribution_decisions_20261008_41.json'
    reviews_path = ROOT/'annotations/course_v4/abstract_eval_attribution_reviews_20261008_41.json'
    decisions = read(decisions_path)['documents']; reviews = read(reviews_path)
    key = lambda d: (d['split'], d['arxivId'])
    decision_map = {key(d): d for d in decisions}
    assert len(decisions) == len(decision_map) == 15 and reviews['independent'] is False
    assert len(reviews['reviews']) == 15 and {key(d) for d in reviews['reviews']} == set(decision_map)
    retract = {('train', '2107.03374', 'e4', 'e5'), ('dev', '1904.04163', 'e14', 'e16'), ('dev', '1904.04163', 'e15', 'e16')}
    repaired = ('train', '2107.03374', 'e9', 'e5')
    inspections = c.read_jsonl(folder/'attribution_inspections.jsonl')
    actions = c.read_jsonl(folder/'quality_actions.jsonl')
    assert len(inspections) == 69 and actions == [r for r in inspections if r['action'] != 'keep'] and len(actions) == 4
    inspection_map = {(r['split'], r['arxivId'], r['before']['head'], r['before']['tail']): r for r in inspections}
    assert len(inspection_map) == 69
    expected_support = {'train': {'USED_FOR': 183, 'EVALUATED_ON': 58, 'NO_RELATION': 26}, 'dev': {'USED_FOR': 259, 'EVALUATED_ON': 8, 'NO_RELATION': 66}}
    changed_documents = set(); old_eval_documents = set(); pair_keys = set()
    for split, (refs, old) in sources.items():
        new = c.read_jsonl(folder/(split+'_reviewed_receipts.jsonl'))
        assert refs == c.read_jsonl(folder/(split+'_references.jsonl')) and len(refs) == len(old) == len(new) == (58 if split == 'train' else 19)
        for ref, prior, after in zip(refs, old, new):
            assert ref['split'] == split and not c.validate_receipt(after, ref) and after['review'] is not None
            assert all(prior['annotation'][k] == after['annotation'][k] for k in NER_FIELDS)
            identity = (split, ref['arxivId']); before_pairs = {(p['head'], p['tail']): p for p in prior['annotation']['relations']}
            after_pairs = {(p['head'], p['tail']): p for p in after['annotation']['relations']}
            assert set(before_pairs) == set(after_pairs)
            if any(p['label'] == 'EVALUATED_ON' for p in before_pairs.values()):
                old_eval_documents.add(identity)
                revised, checked = revise_attribution(prior, ref, decision_map[identity])
                assert revised['relations'] == after['annotation']['relations']
                assert len(checked) == sum(p['label'] == 'EVALUATED_ON' for p in before_pairs.values())
            if identity in {('train', '2107.03374'), ('dev', '1904.04163')}:
                changed_documents.add(identity)
                assert after['generation']['sourceArtifactSha256'] == c.file_sha256(decisions_path)
                assert after['review']['provenance']['sourceArtifactSha256'] == c.file_sha256(reviews_path)
                assert after['review']['inputContentSha256'] == after['initialContentSha256']
                initial = copy.deepcopy(revised); initial['reviewOfSha256'] = None
                assert not c.eligible_tasks(c.make_receipt(initial, ref, after['generation']), ref)['ner']
            else:
                assert prior == after
            for pair, previous in before_pairs.items():
                current = after_pairs[pair]; pid = identity+pair
                if previous['label'] == 'EVALUATED_ON':
                    pair_keys.add(pid); inspection = inspection_map[pid]
                    assert inspection['sampleId'] == ref['sampleId'] and inspection['textSha256'] == ref['textSha256'] and inspection['upstreamReceiptSha256'] == prior['contentSha256']
                    assert inspection['before'] == previous and inspection['after'] == current
                    assert inspection['beforeSha256'] == c.canonical_sha256(previous) and inspection['afterSha256'] == c.canonical_sha256(current)
                    assert inspection['supportExcerpt'].strip() and ref['text'].count(inspection['supportExcerpt']) == 1 and inspection['reason'].strip()
                    assert inspection['action'] == ('retract' if pid in retract else 'repair_evidence' if pid == repaired else 'keep')
                if pid in retract:
                    assert previous['label'] == 'EVALUATED_ON' and current['label'] == 'UNRESOLVED' and current['evidence'] is None and current['reason'].strip()
                elif pid == repaired:
                    assert previous['label'] == current['label'] == 'EVALUATED_ON'
                    assert {k: v for k, v in current.items() if k != 'evidence'} == {k: v for k, v in previous.items() if k != 'evidence'}
                    assert current['evidence']['start'] <= previous['evidence']['start'] and current['evidence']['end'] > previous['evidence']['end'] and 'Using this method' in current['evidence']['text']
                else:
                    assert current == previous
        before_rows = rows_for(refs, old); rows = rows_for(refs, new)
        for name, expected in zip(('ner', 'relation', 'full_relation', 'excluded_ner'), rows[:4]):
            assert expected == c.read_jsonl(folder/(name+'_'+split+'.jsonl'))
        assert len(rows[0]) == (50 if split == 'train' else 16) and rows[3] == before_rows[3] and len(rows[3]) == (8 if split == 'train' else 3)
        assert len(rows[1]) == (267 if split == 'train' else 333) and Counter(p['label'] for p in rows[1]) == expected_support[split]
        assert rows[4:] == ((1578, 1845) if split == 'train' else (99, 432)) and len(rows[2]) == len(before_rows[2]) == (6 if split == 'train' else 7)
        if split == 'dev':
            complete_ids = {d['sampleId'] for d in rows[2]}
            assert not any(p['label'] == 'EVALUATED_ON' for p in rows[1] if p['sampleId'] in complete_ids)
    assert pair_keys == set(inspection_map) and old_eval_documents == set(decision_map) and len(changed_documents) == 2
    summary = read(folder/'summary.json')
    assert not any(summary[k] for k in ('trainingExecuted', 'inferenceExecuted', 'newMetricsProduced', 'testContentAccessed', 'modelPromoted', 'qualityPromotionPassed'))
    refs, receipts = sources['train']; index = next(i for i, r in enumerate(refs) if r['arxivId'] == '2107.03374')
    ref, prior = refs[index], receipts[index]; original = decision_map[('train', '2107.03374')]
    invalids = []
    for field, value in [('textSha256', '0'*64), ('split', 'dev'), ('upstreamReceiptSha256', '0'*64)]:
        bad = copy.deepcopy(original); bad[field] = value; invalids.append(bad)
    bad = copy.deepcopy(original); bad['groups'].append(copy.deepcopy(bad['groups'][0])); invalids.append(bad)
    bad = copy.deepcopy(original); bad['groups'].pop(); invalids.append(bad)
    bad = copy.deepcopy(original); bad['groups'][0]['action'] = 'NO_RELATION'; invalids.append(bad)
    bad = copy.deepcopy(original); bad['groups'][0]['supportExcerpt'] = 'fabricated source quote'; invalids.append(bad)
    non_eval = next(pair for pair, label in c.candidate_pairs(prior['annotation']['entities']).items() if label == 'USED_FOR')
    bad = copy.deepcopy(original); bad['groups'][0]['heads'] = [non_eval[0]]; bad['groups'][0]['tails'] = [non_eval[1]]; invalids.append(bad)
    for bad in invalids:
        try: revise_attribution(prior, ref, bad)
        except ValueError: pass
        else: raise AssertionError('Invalid or unbound evaluation attribution decision was accepted')
