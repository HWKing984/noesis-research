"""Source-bound train scope review; keep unknowns, old artifacts and opaque dev bytes intact."""
import argparse
import copy
import hashlib
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_graph as g
import course_weak as c
import train_course_ner as ner
from compile_abstract_annotations import annotate
from course_abstract_relation import rows_for
from course_abstract_v1 import read, seal

CONTRACT = c.ROOT/'resources/course_abstract_scope_review_v1.json'
DECISIONS = c.ROOT/'annotations/course_v4/abstract_scope_decisions_20261008_44.json'


def load_inputs():
    config = read(CONTRACT); folder = (c.ROOT/config['snapshot']).resolve()
    if config['version'] != 'abstract_train_scope_review_v1' or any(config[k] is not False for k in ('trainingAllowed', 'automaticPromotionAllowed', 'independentHumanGold')) or not folder.is_relative_to(c.ROOT/'kg_datasets/dblp'): raise ValueError('Scope contract drift')
    manifest = g.verified_files(folder, config['snapshotManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Parent input drift')
    refs = c.read_jsonl(folder/'train_references.jsonl'); receipts = c.read_jsonl(folder/'train_reviewed_receipts.jsonl')
    if len(refs) != len(receipts) or len(refs) != 58 or len({r['sampleId'] for r in refs}) != 58 or len({r['groupId'] for r in refs}) != 58: raise ValueError('Train cohort incomplete/duplicated')
    for ref, receipt in zip(refs, receipts):
        if ref['split'] != 'train' or ref['textKind'] != 'abstract' or hashlib.sha256(ref['text'].encode('utf-8')).hexdigest() != ref['textSha256'] or c.validate_receipt(receipt, ref) or receipt['review'] is None: raise ValueError('Wrong/unreviewed train source')
    source = read(DECISIONS); documents = source['documents']; lookup = {r['arxivId']: (r, a) for r, a in zip(refs, receipts)}
    if source['independent'] is not False or [d['arxivId'] for d in documents] != config['reviewCohort'] or len(set(config['reviewCohort'])) != 11: raise ValueError('Review cohort/review independence drift')
    for decision in documents:
        ref, prior = lookup[decision['arxivId']]
        if decision['textSha256'] != ref['textSha256'] or not decision['quote'] or decision['quote'] not in ref['text'] or not decision['reason'].strip(): raise ValueError('Judgment not source-bound')
        response_for(decision, ref, prior)
    if {r['arxivId'] for r, a in zip(refs, receipts) if not c.eligible_tasks(a, r)['ner']} != set(config['reviewCohort'][:8]): raise ValueError('All quarantines must be reviewed')
    if Counter(d['action'] for d in documents) != {'keep': 6, 'admit': 4, 'edit': 1}: raise ValueError('Declared action inventory drift')
    return config, refs, receipts, source


def response_for(decision, ref, prior):
    if decision['arxivId'] != ref['arxivId'] or decision['textSha256'] != ref['textSha256'] or ref['split'] != 'train': raise ValueError('Response source drift')
    base_keys = {'arxivId', 'textSha256', 'action', 'quote', 'reason'}
    if decision['action'] == 'keep':
        if set(decision) != base_keys: raise ValueError('Keep action must not edit annotation')
        return None
    if decision['action'] == 'admit':
        if set(decision) != base_keys | {'entities'} or c.eligible_tasks(prior, ref)['ner'] or prior['annotation']['groupMentions']: raise ValueError('Admission cannot clear shared-head quarantine or reannotate a valid document')
        ann = annotate({'mentions': {}, 'entityStatus': 'complete'}, ref); ann['entities'] = copy.deepcopy(decision['entities'])
        if [e['entityId'] for e in ann['entities']] != [f'e{i}' for i in range(1, len(ann['entities'])+1)]: raise ValueError('Noncanonical entity IDs')
        ann['relations'] = [{'head': h, 'tail': t, 'label': 'UNRESOLVED', 'evidence': None, 'reason': 'Fresh endpoints after whole-source NER review; no inherited resolved edge or negative filling.'} for h, t in c.candidate_pairs(ann['entities'])]
        ann['relationStatus'] = 'unresolved' if ann['relations'] else 'complete'; ann['relationReason'] = 'Needs separate evidence judgments.' if ann['relations'] else ''
    elif decision['action'] == 'edit':
        if set(decision) != base_keys | {'before', 'after', 'touchingPairs'} or not c.eligible_tasks(prior, ref)['ner']: raise ValueError('Invalid edit action')
        ann = copy.deepcopy(prior['annotation']); before = decision['before']; after = decision['after']
        if before['entityId'] != after['entityId'] or before['label'] != after['label'] or before not in ann['entities']: raise ValueError('Edit is not the declared span-only change')
        ann['entities'][ann['entities'].index(before)] = copy.deepcopy(after)
        touching = { (p['head'], p['tail']): p for p in ann['relations'] if before['entityId'] in (p['head'], p['tail']) }
        judgments = decision['touchingPairs']; mapping = {(p['head'], p['tail']): p for p in judgments}
        if len(mapping) != len(judgments) or set(mapping) != set(touching): raise ValueError('Every touching pair requires explicit rejudgment')
        replacements = {}
        for key, original in touching.items():
            judgment = mapping[key]
            if set(judgment) != {'head', 'tail', 'previousLabel', 'label', 'evidence', 'reason'} or judgment['previousLabel'] != original['label'] or not judgment['reason'].strip() or (original['label'] == 'UNRESOLVED' and judgment['label'] != 'UNRESOLVED'): raise ValueError('Prior label mismatch or unsupported unknown promotion')
            evidence = judgment['evidence']
            if evidence is not None:
                if set(evidence) != {'start', 'end'} or type(evidence['start']) is not int or type(evidence['end']) is not int or not 0 <= evidence['start'] < evidence['end'] <= len(ref['text']): raise ValueError('Invalid literal relation evidence')
                evidence = evidence | {'text': ref['text'][evidence['start']:evidence['end']]}
            replacements[key] = {'head': key[0], 'tail': key[1], 'label': judgment['label'], 'evidence': evidence, 'reason': judgment['reason']}
        ann['relations'] = [replacements.get((p['head'], p['tail']), p) for p in ann['relations']]
    else: raise ValueError('Unknown review action')
    ann['reviewOfSha256'] = None; ann['notes'] += ' Source-scope AI judgment: '+decision['reason']
    if c.validate_response(ann, ref): raise ValueError('Revised source spans/candidates/evidence invalid')
    return ann


def metadata(source, path):
    return {'provider': source['provider'], 'model': source['model'], 'promptSha256': c.file_sha256(CONTRACT), 'sourceArtifactSha256': c.file_sha256(path), 'createdAt': datetime.now(UTC).isoformat()}


def inputs(config):
    folder = c.ROOT/config['snapshot']
    return [CONTRACT, DECISIONS, folder/'manifest.json', folder/'train_references.jsonl', folder/'train_reviewed_receipts.jsonl', Path(__file__), c.CONFIG_PATH, c.SCHEMA_PATH,
        c.ROOT/'scripts/course_weak.py', c.ROOT/'scripts/course_graph.py', c.ROOT/'scripts/compile_abstract_annotations.py', c.ROOT/'scripts/course_abstract_relation.py', c.ROOT/'scripts/course_abstract_v1.py', c.ROOT/'scripts/train_course_ner.py', c.ROOT/'resources/course_abstract_relation_v1.json', c.ROOT/'docs/course_v4_ai_prompt.md', c.ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt', c.ROOT/'kg_datasets/models/scibert_24f92d32/config.json', c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl', c.ROOT/'resources/course_graph_runtime.json']


def new_output(output):
    if output.exists(): raise FileExistsError('Preserve scope artifact; no automatic overwrite/retry')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Scope output outside dataset directory')


def generate(output):
    new_output(output); config, refs, old, source = load_inputs(); lookup = {r['arxivId']: (r, a) for r, a in zip(refs, old)}; receipts = []; origins = []
    for decision in source['documents']:
        ref, previous = lookup[decision['arxivId']]; response = response_for(decision, ref, previous)
        if response is None: continue
        receipt = c.make_receipt(response, ref, metadata(source, DECISIONS)); receipts.append(receipt); origins.append({'sampleId': ref['sampleId'], 'arxivId': ref['arxivId'], 'action': decision['action'], 'upstreamReceiptSha256': previous['contentSha256']})
    paths = inputs(config); hashes = {p: c.file_sha256(p) for p in paths}; output.mkdir(parents=True)
    try:
        c.write_jsonl(output/'generation_receipts.jsonl', receipts); c.write_jsonl(output/'origins.jsonl', origins); c.write_json(output/'contract.json', config)
        c.write_json(output/'summary.json', {'status': 'generated_not_reviewed', 'sourceJudgments': 11, 'freshInitialReceipts': 5, 'trainingAllowed': False, 'independent': False})
        if any(c.file_sha256(p) != sha for p, sha in hashes.items()): raise ValueError('Generation input drift')
        seal(output, paths); print({'generatedReceipts': len(receipts), 'reviewed': False, 'trainingExecuted': False})
    except Exception as error:
        c.write_json(output/'failure.json', {'status': 'failed_no_fallback', 'errorType': type(error).__name__, 'error': str(error)}); raise


def review(generation, judgments_path, output):
    new_output(output); config, refs, old, source = load_inputs(); judgments = read(judgments_path)
    manifest = g.verified_files(generation, judgments['generationManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Generation drift')
    reviews = judgments['documents']
    if judgments['independent'] is not False or [r['arxivId'] for r in reviews] != config['reviewCohort'] or any(not r['reason'].strip() or set(r) != {'arxivId', 'generationContentSha256', 'reason'} for r in reviews): raise ValueError('Actual review missing/wrong cohort')
    initial = c.read_jsonl(generation/'generation_receipts.jsonl'); by_id = {r['reference']['arxivId']: r for r in initial}; lookup = {r['arxivId']: (r, a) for r, a in zip(refs, old)}; replacements = {}; ledger = []
    expected_initial = [d['arxivId'] for d in source['documents'] if d['action'] != 'keep']
    if [r['reference']['arxivId'] for r in initial] != expected_initial or len(by_id) != 5: raise ValueError('Generated revision cohort drift')
    for decision, judgment in zip(source['documents'], reviews):
        ref, previous = lookup[decision['arxivId']]; prior = by_id.get(decision['arxivId'])
        if decision['action'] == 'keep':
            if prior is not None or judgment['generationContentSha256'] is not None: raise ValueError('Keep must not invent a new receipt')
            ledger.append({'arxivId': ref['arxivId'], 'action': 'keep', 'sourceTextSha256': ref['textSha256'], 'receiptSha256': previous['contentSha256'], 'reviewReason': judgment['reason']}); continue
        if c.validate_receipt(prior, ref) or prior['review'] is not None or judgment['generationContentSha256'] != prior['contentSha256'] or prior['annotation'] != response_for(decision, ref, previous): raise ValueError('Review must bind exact generation')
        ann = copy.deepcopy(prior['annotation']); ann['reviewOfSha256'] = prior['contentSha256']; ann['notes'] += ' Actual same-session self-review: '+judgment['reason']
        reviewed = c.make_receipt(ann, ref, metadata(judgments, judgments_path), previous=prior); replacements[ref['sampleId']] = reviewed
        ledger.append({'arxivId': ref['arxivId'], 'action': decision['action'], 'sourceTextSha256': ref['textSha256'], 'oldReceiptSha256': previous['contentSha256'], 'newReceiptSha256': reviewed['contentSha256'], 'reviewReason': judgment['reason']})
    receipts = [replacements.get(r['sampleId'], a) for r, a in zip(refs, old)]; rows, pairs, full, excluded, unknown, total = rows_for(refs, receipts)
    support = Counter(e['label'] for r in rows for e in r['entities'])
    if (len(rows), len(pairs), len(full), len(excluded), unknown, total) != (54, 267, 8, 4, 1632, 1899) or support != {'METHOD': 402, 'TASK': 196, 'DATASET': 44} or Counter(p['label'] for p in pairs) != {'USED_FOR': 183, 'EVALUATED_ON': 58, 'NO_RELATION': 26}: raise ValueError('Unexpected revised support/candidate counts')
    from transformers import BertTokenizerFast
    tokenizer = BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32', local_files_only=True, do_lower_case=True); alignments = []
    for row in rows:
        record = ner.encode_row(tokenizer, row, 512); offsets = record['offsets']; labels = record['features']['labels']; decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else tag for o, tag in zip(offsets, labels)], offsets, row['text'])
        if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]: raise ValueError('Exact BIO round-trip failed; no exception dropping')
        alignments.append({'sampleId': row['sampleId'], 'offsets': offsets, 'labels': labels})
    paths = inputs(config)+[judgments_path, generation/'manifest.json']; hashes = {p: c.file_sha256(p) for p in paths}; parent = c.ROOT/config['snapshot']; output.mkdir(parents=True)
    try:
        opaque = [p for p in parent.iterdir() if p.is_file() and ('dev' in p.stem or p.name == 'train_references.jsonl')]
        for path in opaque: shutil.copy2(path, output/path.name)
        for name, values in [('train_reviewed_receipts', receipts), ('ner_train', rows), ('relation_train', pairs), ('full_relation_train', full), ('excluded_ner_train', excluded), ('token_alignment_train', alignments), ('scope_review_ledger', ledger)]: c.write_jsonl(output/(name+'.jsonl'), values)
        summary = {'status': 'completed', 'version': config['version'], 'sourceJudgments': 11, 'freshReviewedReceipts': 5, 'inheritedReceiptDocuments': 53, 'trainQueue': 58, 'NERtrain': 54, 'NERexcluded': 4, 'entitySupport': dict(support), 'resolvedRelations': 267, 'relationSupport': dict(Counter(p['label'] for p in pairs)), 'unknownPairs': unknown, 'eligiblePairs': total, 'completeRelationDocuments': len(full), 'newZeroCandidateDocuments': 2, 'explicitlyRejudgedTouchedPairs': 8, 'explicitlyRejudgedResolvedPairs': 3, 'DATASETSupportIncreased': False, 'trainingExecuted': False, 'devCopiedAsOpaqueBytes': True, 'testSemanticallyRead': False, 'modelPromoted': False, 'qualityPromotionPassed': False, 'independentHumanGold': False}
        c.write_json(output/'summary.json', summary); c.write_json(output/'contract.json', config)
        if any(c.file_sha256(p) != sha for p, sha in hashes.items()) or any(c.file_sha256(p) != c.file_sha256(output/p.name) for p in opaque): raise ValueError('Input or opaque dev drift')
        g.verified_files(parent, config['snapshotManifestSha256']); seal(output, paths); print(summary)
    except Exception as error:
        c.write_json(output/'failure.json', {'status': 'failed_no_fallback', 'errorType': type(error).__name__, 'error': str(error)}); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('preflight', 'generate', 'review')); parser.add_argument('--output', type=Path); parser.add_argument('--generation', type=Path); parser.add_argument('--reviews', type=Path); args = parser.parse_args()
    if args.action == 'preflight':
        _, refs, _, _ = load_inputs(); print({'sourceTrain': len(refs), 'reviewCohort': 11, 'testAccessed': False})
    elif args.output is None: parser.error('A new --output is required')
    elif args.action == 'generate': generate(args.output.resolve())
    else:
        if args.generation is None or args.reviews is None: parser.error('review requires --generation and --reviews')
        review(args.generation.resolve(), args.reviews.resolve(), args.output.resolve())
