"""One occurrence/source/receipt regression check, without model or reserved-test access."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import course_weak as c
from course_abstract_v1 import read
from revise_contextual_abstracts import occurrence_spans, source_cohort, response_for


def test_contextual_spans_preserve_source_and_reject_missing_overlap_or_url_labels():
    text = '甲 alpha framework solves alpha; see https://example.org/alpha.'
    declarations = [
        {'text': 'alpha framework', 'occurrences': [{'occurrence': 1, 'label': 'METHOD', 'reason': 'Named method.'}]},
        {'text': 'alpha', 'occurrences': [
            {'occurrence': 1, 'label': 'WITHIN_ENTITY', 'reason': 'Lexical modifier.', 'container': {'text': 'alpha framework', 'occurrence': 1}},
            {'occurrence': 2, 'label': 'TASK', 'reason': 'Distinct locally asserted task.'},
            {'occurrence': 3, 'label': 'OUT_OF_SCOPE', 'reason': 'URL substring.'}]}]
    spans = occurrence_spans(text, declarations)
    assert [(e['text'], e['label']) for e in spans] == [('alpha framework', 'METHOD'), ('alpha', 'TASK')]
    assert all(text[e['start']:e['end']] == e['text'] for e in spans)
    sparse_container = [
        {'text': 'alpha framework', 'occurrences': [{'occurrence': 1, 'label': 'OUT_OF_SCOPE', 'reason': 'Quoted non-entity context.'}, {'occurrence': 2, 'label': 'METHOD', 'reason': 'Technical name.'}]},
        {'text': 'alpha', 'occurrences': [{'occurrence': 1, 'label': 'OUT_OF_SCOPE', 'reason': 'Quoted context.'}, {'occurrence': 2, 'label': 'WITHIN_ENTITY', 'reason': 'Part of technical name.', 'container': {'text': 'alpha framework', 'occurrence': 2}}]}]
    assert occurrence_spans('alpha framework. alpha framework', sparse_container)[0]['start'] == 17
    variants = []
    missing = copy.deepcopy(declarations); missing[1]['occurrences'].pop(); variants.append(missing)
    url = copy.deepcopy(declarations); url[1]['occurrences'][2]['label'] = 'METHOD'; variants.append(url)
    overlap = copy.deepcopy(declarations); overlap[1]['occurrences'][0].update(label='TASK'); overlap[1]['occurrences'][0].pop('container'); variants.append(overlap)
    boolean = copy.deepcopy(declarations); boolean[0]['occurrences'][0]['occurrence'] = True; variants.append(boolean)
    bad_container = copy.deepcopy(declarations); bad_container[1]['occurrences'][0]['container']['occurrence'] = 2; variants.append(bad_container)
    conflict = copy.deepcopy(declarations); conflict[1]['occurrences'][0].update(label='OUT_OF_SCOPE'); conflict[1]['occurrences'][0].pop('container'); variants.append(conflict)
    for malformed in variants:
        try: occurrence_spans(text, malformed)
        except ValueError: pass
        else: raise AssertionError('Malformed occurrence decision was admitted')
    _, refs, old = source_cohort(); assert len(refs) == len(old) == 58
    lookup = {r['arxivId']: r for r in refs}
    decisions = read(ROOT/'annotations/course_v4/abstract_occurrence_decisions_20261008_38.json')['documents']
    for decision in decisions:
        ref = lookup[decision['arxivId']]; result = response_for(decision, ref)
        assert not c.validate_response(result, ref)
        bad = copy.deepcopy(decision); bad['textSha256'] = '0'*64
        try: response_for(bad, ref)
        except ValueError: pass
        else: raise AssertionError('Wrong original-text hash was admitted')
    folder = ROOT/'kg_datasets/dblp/course_abstract_occurrence_reviewed_20261008_38'
    new = c.read_jsonl(folder/'reviewed_receipts.jsonl'); revised = set(read(ROOT/'resources/course_abstract_occurrence_v1.json')['revisionCohort'])
    assert c.read_jsonl(folder/'references.jsonl') == refs and len(new) == 58
    for ref, before, after in zip(refs, old, new):
        assert not c.validate_receipt(after, ref) and after['review'] is not None
        if ref['arxivId'] not in revised: assert before == after
        else: assert before['annotation']['entityStatus'] == 'unresolved' and after['annotation']['entityStatus'] == 'complete'
    generated = c.read_jsonl(ROOT/'kg_datasets/dblp/course_abstract_occurrence_generated_20261008_38/generation_receipts.jsonl')
    assert all(not c.eligible_tasks(r, r['reference'])['ner'] for r in generated)
    fixed = next(r for r in new if r['reference']['arxivId'] == '2409.13884')['annotation']
    by_id = {e['entityId']: e for e in fixed['entities']}
    assert by_id['e13']['text'] == 'debiasing' and by_id['e13']['start'] == 771
    assert sum(p['label'] == 'USED_FOR' for p in fixed['relations']) == 6
    assert sum(p['label'] == 'UNRESOLVED' for p in fixed['relations']) == 46
    summary = read(folder/'summary.json')
    assert summary['nerCandidates'] == 50 and summary['excludedNER'] == 8 and summary['freshlyRejudged'] == 2
    assert summary['resolvedRelationSupport'] == {'EVALUATED_ON': 43, 'USED_FOR': 151, 'NO_RELATION': 7}
    assert not any(summary[k] for k in ('trainingExecuted', 'modelPromoted', 'qualityPromotionPassed', 'testContentAccessed', 'devContentAccessed'))
