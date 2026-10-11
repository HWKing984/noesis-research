"""Occurrence-aware TRAIN label revision; preserve historical compilers, receipts and models."""
import argparse
import copy
import hashlib
import json
import os
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_graph as g
import course_weak as c
import train_course_ner as ner
from compile_abstract_annotations import annotate
from course_abstract_v1 import read, seal
from course_abstract_relation import CONTRACT as RELATION_CONTRACT, rows_for, revise
from train_expanded_abstract_ner import new_row

CONTRACT = c.ROOT / 'resources/course_abstract_occurrence_v1.json'


def source_cohort():
    config = read(CONTRACT)
    if config['version'] != 'abstract_occurrence_v1' or c.file_sha256(c.ROOT/config['parentContract']) != config['parentContractSha256'] or config['automaticPromotionAllowed'] is not False:
        raise ValueError('Occurrence contract drift')
    refs, receipts = [], []
    for source in config['upstreams']:
        folder = c.ROOT/source['folder']; manifest = g.verified_files(folder, source['manifestSha256'])
        if any(c.file_sha256(c.ROOT/path) != sha for path, sha in manifest['inputSha256'].items()):
            raise ValueError('Upstream source drift')
        refs.extend(c.read_jsonl(folder/(source['prefix']+'references.jsonl')))
        receipts.extend(c.read_jsonl(folder/(source['prefix']+'reviewed_receipts.jsonl')))
    if len(refs) != len(receipts) or len({r['sampleId'] for r in refs}) != len(refs) or len({r['groupId'] for r in refs}) != len(refs):
        raise ValueError('Missing or duplicate train cohort')
    for ref, receipt in zip(refs, receipts):
        if ref['split'] != 'train' or ref['textKind'] != 'abstract' or hashlib.sha256(ref['text'].encode('utf-8')).hexdigest() != ref['textSha256'] or c.validate_receipt(receipt, ref) or receipt['review'] is None:
            raise ValueError('Invalid whole-train source or receipt')
    return config, refs, receipts


def occurrence_spans(text, declarations):
    selected, deferred, literals, by_selector = [], [], set(), {}
    urls = [m.span() for m in re.finditer(r'https?://\S+', text)]
    for item in declarations:
        if set(item) != {'text', 'occurrences'} or not isinstance(item['text'], str) or not item['text'].strip() or item['text'] in literals:
            raise ValueError('Empty, duplicate or malformed literal declaration')
        literal = item['text']; literals.add(literal)
        matches = list(re.finditer(r'(?<!\w)(?<!\w-)'+re.escape(literal)+r'(?!\w|-\w)', text))
        decisions = item['occurrences']
        if not matches or [d['occurrence'] for d in decisions] != list(range(1, len(matches)+1)) or any(type(d['occurrence']) is not int for d in decisions):
            raise ValueError('Every declared occurrence must be judged exactly once in source order')
        for match, decision in zip(matches, decisions):
            allowed = {'occurrence', 'label', 'reason'} | ({'container'} if decision['label'] == 'WITHIN_ENTITY' else set())
            if set(decision) != allowed or not isinstance(decision['reason'], str) or not decision['reason'].strip():
                raise ValueError('Missing explicit occurrence reason or unexpected field')
            span = {'start': match.start(), 'end': match.end(), 'text': literal, 'label': decision['label']}
            if decision['label'] in c.CONFIG['entityLabels']:
                if any(span['start'] < end and start < span['end'] for start, end in urls):
                    raise ValueError('URL substring cannot become an entity')
                selected.append(span)
                by_selector[(literal, decision['occurrence'])] = span
            elif decision['label'] in ('OUT_OF_SCOPE', 'WITHIN_ENTITY'):
                deferred.append((span, decision))
            else:
                raise ValueError('Unknown occurrence judgment')
    selected.sort(key=lambda e: e['start'])
    if any(a['end'] > b['start'] for a, b in zip(selected, selected[1:])):
        raise ValueError('Explicit entity spans overlap; retain unresolved instead of deleting one')
    for span, decision in deferred:
        covering = [e for e in selected if e['start'] <= span['start'] and span['end'] <= e['end']]
        if decision['label'] == 'WITHIN_ENTITY':
            container = decision['container']
            if set(container) != {'text', 'occurrence'} or type(container['occurrence']) is not int:
                raise ValueError('Invalid covering entity selector')
            if by_selector.get((container['text'], container['occurrence'])) not in covering:
                raise ValueError('Lexical modifier has no declared covering entity')
        elif any(span['start'] < e['end'] and e['start'] < span['end'] for e in selected):
            raise ValueError('OUT_OF_SCOPE conflicts with an entity; use explicit WITHIN_ENTITY')
    return [{'entityId': f'e{i}', **span} for i, span in enumerate(selected, 1)]


def response_for(decision, reference):
    if decision['textSha256'] != reference['textSha256'] or decision['arxivId'] != reference['arxivId']:
        raise ValueError('Revision is not bound to the exact source')
    result = annotate({'mentions': {}, 'entityStatus': 'complete'}, reference)
    result.update(entities=occurrence_spans(reference['text'], decision['mentions']), entityStatus=decision['entityStatus'], entityReason=decision['reason'])
    result['relations'] = [{'head': h, 'tail': t, 'label': 'UNRESOLVED', 'evidence': None,
        'reason': 'Endpoint IDs rebuilt after entity revision; no inherited relationship or negative filling.'} for h, t in c.candidate_pairs(result['entities'])]
    result['relationStatus'] = 'unresolved' if result['entityStatus'] != 'complete' or result['relations'] else 'complete'
    result['relationReason'] = 'Requires separate evidence judgments, not inferred from types.' if result['relationStatus'] == 'unresolved' else ''
    result['notes'] = 'AI pseudo-label occurrence revision, not independent gold. '+decision['reason']
    if decision.get('relationGroups'):
        result = revise(result, reference, {'groups': decision['relationGroups']}, read(RELATION_CONTRACT))
    errors = c.validate_response(result, reference)
    if errors: raise ValueError('; '.join(errors))
    return result


def metadata(source, path):
    return {'provider': source['provider'], 'model': source['model'], 'promptSha256': c.file_sha256(CONTRACT),
        'sourceArtifactSha256': c.file_sha256(path), 'createdAt': datetime.now(UTC).isoformat()}


def generate(decisions_path, output):
    if output.exists(): raise FileExistsError('Preserve generation artifact')
    config, refs, old = source_cohort(); source = read(decisions_path); lookup = {r['arxivId']: (r, a) for r, a in zip(refs, old)}
    if [d['arxivId'] for d in source['documents']] != config['revisionCohort']: raise ValueError('Revision cohort differs from locked policy')
    chosen = [lookup[d['arxivId']][0] for d in source['documents']]
    receipts = [c.make_receipt(response_for(d, ref), ref, metadata(source, decisions_path)) for d, ref in zip(source['documents'], chosen)]
    output.mkdir(parents=True)
    c.write_jsonl(output/'references.jsonl', chosen); c.write_jsonl(output/'generation_receipts.jsonl', receipts)
    c.write_jsonl(output/'origins.jsonl', [{'sampleId': r['sampleId'], 'upstreamReceiptSha256': lookup[r['arxivId']][1]['contentSha256']} for r in chosen])
    seal(output, [CONTRACT, RELATION_CONTRACT, decisions_path, Path(__file__), c.ROOT/'scripts/course_weak.py', c.ROOT/'scripts/compile_abstract_annotations.py', c.ROOT/'scripts/course_abstract_relation.py', c.SCHEMA_PATH])
    print(json.dumps({'generated': len(receipts), 'testAccessed': False, 'trainingExecuted': False}))


def review(generation, judgments_path, output):
    if output.exists(): raise FileExistsError('Preserve reviewed revision')
    config, refs, old = source_cohort(); manifest = g.verified_files(generation)
    if any(c.file_sha256(c.ROOT/path) != sha for path, sha in manifest['inputSha256'].items()): raise ValueError('Generation input drift')
    chosen = c.read_jsonl(generation/'references.jsonl'); initial = c.read_jsonl(generation/'generation_receipts.jsonl'); origins = c.read_jsonl(generation/'origins.jsonl')
    judgments = read(judgments_path); reviews = judgments['reviews']; lookup = {r['arxivId']: (r, a) for r, a in zip(refs, old)}
    if judgments['independent'] is not False or [j['arxivId'] for j in reviews] != config['revisionCohort'] or chosen != [lookup[i][0] for i in config['revisionCohort']] or len(initial) != len(chosen):
        raise ValueError('Incomplete or incorrectly scoped self-review')
    if origins != [{'sampleId': r['sampleId'], 'upstreamReceiptSha256': lookup[r['arxivId']][1]['contentSha256']} for r in chosen]: raise ValueError('Revision origins changed')
    revised = {}
    for ref, prior, judgment in zip(chosen, initial, reviews):
        if set(judgment) != {'arxivId', 'reason'} or not judgment['reason'].strip() or c.validate_receipt(prior, ref): raise ValueError('Invalid actual self-review')
        response = copy.deepcopy(prior['annotation']); response['reviewOfSha256'] = prior['contentSha256']; response['notes'] += ' Self-review: '+judgment['reason']
        revised[ref['sampleId']] = c.make_receipt(response, ref, metadata(judgments, judgments_path), previous=prior)
    receipts = [revised.get(r['sampleId'], a) for r, a in zip(refs, old)]
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    from transformers import BertTokenizerFast
    tokenizer = BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32', local_files_only=True, do_lower_case=True)
    parent = c.ROOT/config['parentContract']; rows, excluded, alignment = [], [], []
    for ref, receipt in zip(refs, receipts):
        row = new_row(ref, receipt, parent)
        if row is None:
            excluded.append({'sampleId': ref['sampleId'], 'reason': receipt['annotation']['entityReason'] or 'Group quarantine'}); continue
        encoded = ner.encode_row(tokenizer, row, read(parent)['maxTokens']); offsets = encoded['offsets']; labels = encoded['features']['labels']
        decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else label for o, label in zip(offsets, labels)], offsets, row['text'])
        if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]: raise ValueError('Strict BIO round-trip failed')
        rows.append(row); alignment.append({'sampleId': ref['sampleId'], 'tokens': len(offsets), 'offsets': offsets, 'labels': labels})
    _, pairs, full, _, unknown, total = rows_for(refs, receipts)
    summary = {'version': config['version'], 'trainCohort': len(refs), 'freshlyRejudged': len(revised), 'inheritedReceipts': len(refs)-len(revised),
        'nerCandidates': len(rows), 'excludedNER': len(excluded), 'entitySupport': dict(Counter(e['label'] for r in rows for e in r['entities'])),
        'resolvedRelationSupport': dict(Counter(p['label'] for p in pairs)), 'unresolvedPairs': unknown, 'eligibleRelationPairs': total, 'completeRelationDocuments': len(full),
        'independentHumanGold': False, 'devContentAccessed': False, 'testContentAccessed': False, 'trainingExecuted': False, 'modelPromoted': False, 'qualityPromotionPassed': False}
    output.mkdir(parents=True)
    for name, values in [('references', refs), ('reviewed_receipts', receipts), ('ner_train', rows), ('excluded_ner', excluded), ('token_alignment', alignment), ('relation_train', pairs), ('full_relation_train', full)]:
        c.write_jsonl(output/(name+'.jsonl'), values)
    c.write_jsonl(output/'origins.jsonl', [{'sampleId': r['sampleId'], 'upstreamReceiptSha256': a['contentSha256'], 'NERReannotated': r['sampleId'] in revised,
        'inheritedRelationsInvalidated': r['sampleId'] in revised} for r, a in zip(refs, old)])
    c.write_json(output/'summary.json', summary)
    seal(output, [CONTRACT, parent, RELATION_CONTRACT, generation/'manifest.json', judgments_path, Path(__file__),
        c.ROOT/'scripts/course_weak.py', c.ROOT/'scripts/compile_abstract_annotations.py', c.ROOT/'scripts/train_course_ner.py',
        c.ROOT/'scripts/course_abstract_relation.py', c.ROOT/'scripts/train_expanded_abstract_ner.py', c.SCHEMA_PATH,
        c.ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt', c.ROOT/'kg_datasets/models/scibert_24f92d32/config.json'] + [c.ROOT/s['folder']/'manifest.json' for s in config['upstreams']])
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('generate', 'review'))
    for key in ('decisions', 'generation', 'reviews'): parser.add_argument('--'+key, type=Path)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    try:
        if args.action == 'generate': generate(args.decisions.resolve(), args.output.resolve())
        else: review(args.generation.resolve(), args.reviews.resolve(), args.output.resolve())
    except Exception as error:
        if args.output.exists() and not (args.output/'manifest.json').exists(): c.write_json(args.output/'failure.json', {'status': 'failed_no_synthetic_fallback', 'errorType': type(error).__name__, 'error': str(error)})
        raise
