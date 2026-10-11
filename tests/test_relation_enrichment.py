"""One source-role enrichment check; unknown/component evaluations must not become fabricated labels."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import course_graph as g
import course_weak as c
from course_abstract_v1 import read
from course_abstract_relation import NER_FIELDS, revise, rows_for
from enrich_abstract_relations import source_cohort


def test_enrichment_preserves_entities_old_labels_and_unknown_component_evaluations():
    config, parent, refs, old = source_cohort()
    folder = ROOT/'kg_datasets/dblp/course_abstract_relation_enriched_20261008_39'; g.verified_files(folder)
    new = c.read_jsonl(folder/'reviewed_receipts.jsonl')
    assert c.read_jsonl(folder/'references.jsonl') == refs and len(new) == len(old) == 58
    selected = set(config['revisionCohort'])
    for ref, prior, after in zip(refs, old, new):
        assert not c.validate_receipt(after, ref) and after['review'] is not None
        assert all(prior['annotation'][k] == after['annotation'][k] for k in NER_FIELDS)
        if ref['arxivId'] not in selected: assert prior == after
    before = rows_for(refs, old); after = rows_for(refs, new)
    assert len(before[0]) == len(after[0]) == 50 and before[3] == after[3] and len(after[2]) == len(before[2]) == 6
    assert len(before[1]) == 201 and len(after[1]) == 268 and after[4] == 1577 and after[5] == 1845
    summary = read(folder/'summary.json')
    assert summary['additionalSupport'] == {'USED_FOR': 32, 'NO_RELATION': 19, 'EVALUATED_ON': 16}
    assert summary['relationSupport'] == {'EVALUATED_ON': 59, 'USED_FOR': 183, 'NO_RELATION': 26}
    assert summary['positiveEVALSourceDocuments'] == 3 and not summary['trainingExecuted'] and not summary['devContentAccessed'] and not summary['qualityPromotionPassed']
    changed = {r['reference']['arxivId']: r for r in new if r['reference']['arxivId'] in selected}
    scan = changed['2503.01309']['annotation']; entities = {e['entityId']: e for e in scan['entities']}
    assert all(p['label'] == 'UNRESOLVED' for p in scan['relations'] if entities[p['tail']]['label'] == 'DATASET')
    assert sum(p['label'] == 'NO_RELATION' for p in scan['relations']) == 6
    critic = changed['2402.14245']['annotation']; evals = [p for p in critic['relations'] if p['label'] == 'EVALUATED_ON']
    assert [(p['head'], p['tail']) for p in evals] == [('e16', 'e14')]
    decision = read(ROOT/'annotations/course_v4/abstract_relation_enrichment_decisions_20261008_39.json')['documents'][0]
    index = next(i for i, r in enumerate(refs) if r['arxivId'] == decision['arxivId'])
    invalid = copy.deepcopy(decision); invalid['groups'][2].pop('negativeBasis')
    try: revise(old[index]['annotation'], refs[index], invalid, parent)
    except ValueError: pass
    else: raise AssertionError('A negative without an explicit contrast basis was accepted')
    invalid = copy.deepcopy(decision); invalid['groups'][0]['supportExcerpt'] = 'fabricated support quote'
    try: revise(old[index]['annotation'], refs[index], invalid, parent)
    except ValueError: pass
    else: raise AssertionError('A fabricated source excerpt was accepted')
    initial = c.read_jsonl(folder/'generation_receipts.jsonl')
    assert len(initial) == 4 and all(not c.eligible_tasks(r, r['reference'])['ner'] for r in initial)
