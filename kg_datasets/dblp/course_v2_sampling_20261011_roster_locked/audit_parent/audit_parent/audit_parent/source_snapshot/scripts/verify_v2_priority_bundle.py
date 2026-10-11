"""Read-only, offline standard-library replay of saved V2 data invariants, not semantic gold."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def verify(bundle):
    bundle = Path(bundle).resolve(); passed = set()

    def check(condition, name):
        if not condition: raise ValueError(name)
        passed.add(name)

    def read(name): return json.loads((bundle/name).read_text(encoding='utf-8-sig'))
    def rows(name): return [json.loads(line) for line in (bundle/name).read_text(encoding='utf-8').splitlines()]
    def key(row): return row['arxivId'], row['head']['entityId'], row['tail']['entityId']
    def span(item, text):
        return (type(item.get('start')) is int and type(item.get('end')) is int
                and 0 <= item['start'] < item['end'] <= len(text) and text[item['start']:item['end']] == item.get('text'))

    manifest = read('manifest.json')
    for name, digest in manifest['filesSha256'].items():
        path = (bundle/name).resolve()
        check(path.is_relative_to(bundle), 'safe_manifest_paths')
        check(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'manifest_file_hashes')
    check(manifest['kind'] == 'real_artifact_visualization_not_original_console_ui', 'artifact_kind')
    config, summary = read('contract.json'), read('summary.json')
    check(all(config[k] is False for k in ('trainingAllowed', 'inferenceAllowed', 'testContentAccessAllowed',
        'productionMutationAllowed', 'automaticPromotionAllowed', 'independentHumanGold')), 'data_only_contract')
    check(hashlib.sha256((bundle/'audit_parent/manifest.json').read_bytes()).hexdigest() == config['parentManifestSha256'], 'parent_manifest_binding')
    for key_name in ('externalAudit', 'externalQueue'):
        check(hashlib.sha256((bundle/Path(config[key_name]).name).read_bytes()).hexdigest() == config[key_name+'Sha256'], 'review_input_hashes')
    refs = rows('references.jsonl'); receipts = rows('reviewed_receipts.jsonl'); ner = rows('ner_candidates.jsonl')
    ledger = rows('relation_ledger.jsonl'); pairs = rows('re_candidates.jsonl')
    parent_refs = rows('audit_parent/references.jsonl'); parent_receipts = rows('audit_parent/reviewed_receipts.jsonl')
    before = rows('audit_parent/relation_ledger.jsonl'); old_pairs = rows('audit_parent/re_candidates.jsonl')
    check(refs == parent_refs, 'references_unchanged')
    check(len(refs) == len(receipts) == len(ner) == 12, 'twelve_document_coverage')
    check(all(len({r[k] for r in refs}) == 12 for k in ('arxivId', 'sampleId', 'groupId', 'textSha256')), 'unique_paper_identity')
    check(all(r['split'] == 'train' and r['textKind'] == 'abstract' for r in refs), 'train_abstract_only')
    check(all(hashlib.sha256(r['text'].encode('utf-8')).hexdigest() == r['textSha256'] for r in refs), 'abstract_text_hashes')
    ref_by_id = {r['arxivId']: r for r in refs}; receipt_by_id = {}; expected = set()
    for ref, receipt, nr, prior in zip(refs, receipts, ner, parent_receipts):
        a = receipt['annotation']; text = ref['text']; receipt_by_id[ref['arxivId']] = receipt
        check(receipt['reference'] == ref and prior['reference'] == ref, 'receipt_reference_binding')
        check(receipt['labelSource'] == 'ai_pseudo' and receipt['review'] is not None, 'ai_label_provenance')
        check(receipt['contentSha256'] == canonical({'reference': ref, 'annotation': a}), 'receipt_content_hash')
        check(receipt['initialContentSha256'] == canonical({'reference': ref, 'annotation': receipt['initialAnnotation']}), 'initial_receipt_hash')
        check(a['reviewOfSha256'] == receipt['initialContentSha256'] == receipt['review']['inputContentSha256']
              and receipt['review']['contentSha256'] == receipt['contentSha256'], 'generation_review_chain')
        check(a['sampleId'] == ref['sampleId'] and a['textSha256'] == ref['textSha256'], 'annotation_identity_binding')
        entities = a['entities']
        check(entities == prior['annotation']['entities'], 'entities_unchanged')
        check(all(e['entityId'] == f'e{i}' for i, e in enumerate(entities, 1)), 'contiguous_source_order_ids')
        check(all(span(e, text) for e in entities), 'unicode_entity_offsets')
        check(all(e['label'] in ('METHOD', 'TASK', 'DATASET') for e in entities), 'entity_type_schema')
        check(all(x['end'] <= y['start'] for x, y in zip(entities, entities[1:])), 'nonoverlapping_entities')
        candidates = {(h['entityId'], t['entityId']) for h in entities for t in entities if h['label'] == 'METHOD' and t['label'] in ('TASK', 'DATASET')}
        actual = {(p['head'], p['tail']) for p in a['relations']}
        check(actual == candidates and len(actual) == len(a['relations']), 'complete_candidate_enumeration')
        expected |= {(ref['arxivId'], h, t) for h, t in candidates}
        check(nr['entities'] == entities and nr['text'] == text and nr['sourceReceiptSha256'] == receipt['contentSha256']
              and nr['sampleId'] == ref['sampleId'] and nr['textSha256'] == ref['textSha256'], 'ner_export_binding')
        check(nr['trainingAuthorized'] is False and nr['labelSource'] == 'ai_pseudo', 'ner_authorization_mask')
    by_key = {key(r): r for r in ledger}; before_by_key = {key(r): r for r in before}
    check(len(by_key) == len(ledger) == 684 and set(by_key) == expected == set(before_by_key), 'candidate_ledger_conservation')
    approved = {('2008.10400', 'e11', 'e13'), ('2008.10400', 'e12', 'e13'), ('2501.02474', 'e3', 'e4'),
                ('2312.03556', 'e24', 'e25'), ('2501.06756', 'e10', 'e11')}
    changed = set()
    for row in ledger:
        ref = ref_by_id[row['arxivId']]; receipt = receipt_by_id[row['arxivId']]; previous = before_by_key[key(row)]; text = ref['text']
        relation = next(p for p in receipt['annotation']['relations'] if (p['head'], p['tail']) == key(row)[1:])
        check(row['sourceReceiptSha256'] == receipt['contentSha256'] and row['textSha256'] == ref['textSha256'], 'ledger_receipt_binding')
        check(all(row[e] in receipt['annotation']['entities'] for e in ('head', 'tail')), 'endpoint_foreign_keys')
        check(row['label'] == relation['label'] and row['evidence'] == relation['evidence'] and row['reason'] == relation['reason'], 'ledger_relation_binding')
        check(row['revisionPriorLabel'] == previous['label'] and row['revisionPriorEvidence'] == previous['evidence']
              and row['revisionPriorSupport'] == previous['support'], 'revision_ledger_prior_binding')
        check(row['labelChanged'] is (row['label'] != previous['label']) and row['supportChanged'] is (row['support'] != previous['support']), 'change_flags')
        allowed = {'USED_FOR', 'NO_RELATION', 'UNRESOLVED'} if row['tail']['label'] == 'TASK' else {'EVALUATED_ON', 'NO_RELATION', 'UNRESOLVED'}
        check(row['label'] in allowed, 'relation_type_direction')
        check(row['candidateEligible'] is (row['label'] in ('USED_FOR', 'EVALUATED_ON')), 'eligibility_mask')
        if row['labelChanged']:
            changed.add(key(row)); check(previous['label'] == 'UNRESOLVED' and row['label'] == 'USED_FOR', 'unresolved_promotions_only')
        else:
            check(row['evidence'] == previous['evidence'] and row['reason'] == previous['reason'], 'unchanged_relation_evidence')
        if row['label'] == 'UNRESOLVED':
            check(row['evidence'] is None and not row['candidateEligible'], 'unknown_not_negative')
        else:
            check(span(row['evidence'], text) and row['evidence']['start'] <= min(row['head']['start'], row['tail']['start'])
                  and row['evidence']['end'] >= max(row['head']['end'], row['tail']['end']), 'endpoint_covering_evidence')
            check(row['support']['predicateSpans'] and all(span(s, text) for s in row['support']['predicateSpans']), 'literal_predicate_spans')
            check(row['support']['attribution'] == row['reason'] and row['support']['supportGroup'], 'attribution_support_groups')
        for link in row['support'].get('coreferenceEvidence', []):
            check(span(link['antecedentSpan'], text) and span(link['anaphorSpan'], text) and link['kind'] and link['explanation'], 'literal_coreference_links')
    check(changed == approved, 'five_scoped_label_changes')
    check(all(r['candidateEligible'] is False and r['support'] == before_by_key[key(r)]['support'] for r in ledger if r['label'] == 'NO_RELATION')
          and sum(r['label'] == 'NO_RELATION' for r in ledger) == 5, 'negative_quarantine_preserved')
    check({key(r) for r in ledger if r['support'].get('coreferenceEvidence')} ==
          {('1606.05250', 'e4', 'e1'), ('1606.05250', 'e4', 'e2'), ('2107.03374', 'e9', 'e5')}, 'two_coreference_chains_three_pairs')
    check(len(pairs) == len({key(r) for r in pairs}) == 85 and {key(r) for r in pairs} == {key(r) for r in ledger if r['candidateEligible']}, 're_export_exact_coverage')
    for pair in pairs:
        row = by_key[key(pair)]; ref = ref_by_id[pair['arxivId']]
        check(pair['trainingAuthorized'] is False and pair['labelSource'] == 'ai_pseudo', 're_authorization_mask')
        check(pair['text'] == ref['text'] and pair['textSha256'] == ref['textSha256'] and pair['sourceReceiptSha256'] == row['sourceReceiptSha256'], 're_export_source_binding')
        check(all(pair[k] == row[k] for k in ('head', 'tail', 'label', 'evidence', 'reason')), 're_export_label_binding')
        check(all(pair[k] == row['support'][k] for k in ('taskRole', 'predicateSpans', 'attribution', 'supportGroup')), 're_export_role_evidence')
        check(pair['coreferenceEvidence'] == row['support'].get('coreferenceEvidence', []) and pair['taskSubRole'] == row['support'].get('taskSubRole'), 're_export_auxiliary_evidence')
        check(pair['taskRole'] in ('training_proxy', 'downstream_application', 'background_method_use', 'component_operation', 'not_applicable'), 'role_vocabulary')
        check(pair['taskSubRole'] is None or pair['taskRole'] == 'training_proxy' and pair['taskSubRole'] == 'training_augmentation', 'augmentation_subrole_not_new_role')
    exact = lambda data: {(r['arxivId'], r['head']['text'], r['tail']['text'], r['label']) for r in data}
    check(summary['totalSourcePapersWithEligibleRE'] == len({r['arxivId'] for r in pairs}) == 11, 'total_source_papers_eleven')
    check(summary['parentTotalSourcePapersWithEligibleRE'] == len({r['arxivId'] for r in old_pairs}) == 11, 'parent_source_papers_eleven')
    check(summary['parentLiteralPairsExact'] == len(exact(old_pairs)) == 50 and summary['parentLiteralPairsCasefold'] ==
          len({(a, h.casefold(), t.casefold(), label) for a, h, t, label in exact(old_pairs)}) == 49, 'parent_literal_case_policy')
    check(summary['literalPairsExact'] == len(exact(pairs)) == 55 and summary['literalPairsCasefold'] == 54, 'current_literal_case_policy')
    check(summary['relationSupport'] == dict(Counter(r['label'] for r in ledger)) and summary['RECandidateSupport'] == dict(Counter(r['label'] for r in pairs)), 'summary_label_counts')
    check(summary['RECandidatePairs'] == 85 and summary['candidatePairs'] == 684 and summary['entityMentions'] == 177, 'summary_sizes')
    check(summary['taskRoleSupport'] == dict(Counter(r['taskRole'] for r in pairs)) and summary['supportGroups'] == len({r['supportGroup'] for r in pairs}) == 29, 'summary_role_groups')
    check(all(summary[k] is False for k in ('trainingExecuted', 'inferenceExecuted', 'modelPromoted', 'testContentParsed', 'independentHumanGold')), 'no_execution_or_gold_claim')
    check(read('production_protection.json') == read('audit_parent/production_protection.json'), 'protection_record_conservation_not_live_proof')
    for name, sha in read('source_snapshot/source_bindings.json').items():
        path = (bundle/'source_snapshot'/name).resolve()
        check(path.is_relative_to((bundle/'source_snapshot').resolve()) and hashlib.sha256(path.read_bytes()).hexdigest() == sha, 'controlled_source_snapshot_hashes')
    return {'status': 'passed', 'assertionCategories': len(passed), 'categories': sorted(passed), 'documents': 12,
            'entityMentions': 177, 'candidatePairs': 684, 'RECandidatePairs': 85, 'totalSourcePapersWithEligibleRE': 11,
            'semanticAccuracyCertified': False, 'trainingOrModelExecution': False, 'liveProductionVerified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('bundle', type=Path)
    print(json.dumps(verify(parser.parse_args().bundle), ensure_ascii=False, indent=2))
