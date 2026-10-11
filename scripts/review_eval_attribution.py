"""Explicit source-bound benchmark attribution inspection and reversible label retractions."""
import argparse
import copy
import hashlib
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_graph as g
import course_weak as c
import train_course_ner as ner
import train_course_relation as re_model
from course_abstract_v1 import read, seal
from course_abstract_relation import NER_FIELDS, rows_for

CONTRACT = c.ROOT/'resources/course_abstract_eval_attribution_v1.json'


def source_cohorts():
    config = read(CONTRACT); parent = c.ROOT/config['parentRelationContract']; data = {}
    if config['version'] != 'abstract_eval_attribution_v1' or c.file_sha256(parent) != config['parentRelationContractSha256'] or config['automaticPromotionAllowed'] is not False or set(config['sources']) != {'train', 'dev'}:
        raise ValueError('Attribution contract drift')
    for split in ('train', 'dev'):
        source = config['sources'][split]; folder = c.ROOT/source['path']; manifest = g.verified_files(folder, source['manifestSha256'])
        if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Upstream attribution source drift')
        refs = c.read_jsonl(folder/'references.jsonl'); receipts = c.read_jsonl(folder/'reviewed_receipts.jsonl')
        if len(refs) != len(receipts) or len({r['sampleId'] for r in refs}) != len(refs) or len({r['groupId'] for r in refs}) != len(refs): raise ValueError('Missing/duplicate source cohort')
        for ref, receipt in zip(refs, receipts):
            if ref['split'] != split or ref['textKind'] != 'abstract' or hashlib.sha256(ref['text'].encode('utf-8')).hexdigest() != ref['textSha256'] or c.validate_receipt(receipt, ref) or receipt['review'] is None:
                raise ValueError('Source is not reviewed whole train/dev data')
        selected = [r['arxivId'] for r, a in zip(refs, receipts) if c.eligible_tasks(a, r)['ner'] and any(p['label'] == 'EVALUATED_ON' for p in a['annotation']['relations'])]
        if selected != config['reviewCohort'][split]: raise ValueError('Inspection differs from every resolved benchmark source')
        data[split] = (refs, receipts)
    if {r['groupId'] for r in data['train'][0]} & {r['groupId'] for r in data['dev'][0]}: raise ValueError('Cross-split paper group leakage')
    return config, data


def revise_attribution(prior, ref, decision):
    if c.validate_receipt(prior, ref) or not c.eligible_tasks(prior, ref)['ner']: raise ValueError('Attribution needs a reviewed complete NER source')
    if set(decision) != {'split', 'arxivId', 'textSha256', 'upstreamReceiptSha256', 'groups'} or decision['split'] != ref['split'] or decision['arxivId'] != ref['arxivId'] or decision['textSha256'] != ref['textSha256'] or decision['upstreamReceiptSha256'] != prior['contentSha256']:
        raise ValueError('Wrong split/source/upstream receipt binding')
    result = copy.deepcopy(prior['annotation']); entities = {e['entityId']: e for e in result['entities']}
    pairs = {(p['head'], p['tail']): p for p in result['relations']}; expected = {key for key, p in pairs.items() if p['label'] == 'EVALUATED_ON'}; seen = set(); inspections = []
    if not expected or not isinstance(decision['groups'], list): raise ValueError('No scoped benchmark pairs/groups')
    for group in decision['groups']:
        if set(group) != {'heads', 'tails', 'action', 'supportExcerpt', 'reason'} or group['action'] not in ('keep', 'retract', 'repair_evidence'): raise ValueError('Unsupported attribution action')
        quote = group['supportExcerpt']; reason = group['reason']
        if not isinstance(quote, str) or not quote.strip() or ref['text'].count(quote) != 1 or not isinstance(reason, str) or not reason.strip(): raise ValueError('Attribution excerpt absent/ambiguous or reason empty')
        if any(not isinstance(group[k], list) or not group[k] or any(not isinstance(v, str) for v in group[k]) or len(set(group[k])) != len(group[k]) for k in ('heads', 'tails')): raise ValueError('Empty/duplicate attribution endpoints')
        for head in group['heads']:
            for tail in group['tails']:
                key = (head, tail)
                if key not in expected or key in seen: raise ValueError('Duplicate or non-EVALUATED_ON attribution pair')
                seen.add(key); before = copy.deepcopy(pairs[key]); after = pairs[key]
                if group['action'] == 'retract': after.update(label='UNRESOLVED', evidence=None, reason=reason)
                elif group['action'] == 'repair_evidence':
                    old = before['evidence']; position = ref['text'].find(quote)
                    start = min(old['start'], entities[head]['start'], entities[tail]['start'], position)
                    end = max(old['end'], entities[head]['end'], entities[tail]['end'], position+len(quote))
                    after['evidence'] = {'start': start, 'end': end, 'text': ref['text'][start:end]}
                    if after['evidence'] == before['evidence']: raise ValueError('Evidence repair did not extend the clipped source span')
                inspections.append({'split': ref['split'], 'sampleId': ref['sampleId'], 'arxivId': ref['arxivId'], 'textSha256': ref['textSha256'], 'upstreamReceiptSha256': prior['contentSha256'],
                    'action': group['action'], 'before': before, 'after': copy.deepcopy(after), 'beforeSha256': c.canonical_sha256(before), 'afterSha256': c.canonical_sha256(after), 'supportExcerpt': quote, 'reason': reason})
    if seen != expected: raise ValueError('Attribution inspection omits existing benchmark pairs')
    if any(p['action'] != 'keep' for p in inspections):
        result['relationStatus'] = 'unresolved' if any(p['label'] == 'UNRESOLVED' for p in result['relations']) else 'complete'
        result['relationReason'] = 'Explicit attribution retractions and previous unknown pairs remain unresolved, never negative.' if result['relationStatus'] == 'unresolved' else ''
        result['reviewOfSha256'] = None; result['notes'] += ' Attribution revision: old pairs retained in a reversible quality ledger.'
    if c.validate_response(result, ref): raise ValueError('; '.join(c.validate_response(result, ref)))
    return result, inspections


def build(decisions_path, reviews_path, output):
    if output.exists(): raise FileExistsError('Preserve attribution revision snapshot')
    config, data = source_cohorts(); source = read(decisions_path); judgments = read(reviews_path)
    identities = [(s, arxiv) for s in ('train', 'dev') for arxiv in config['reviewCohort'][s]]
    identity = lambda d: (d['split'], d['arxivId'])
    if [identity(d) for d in source['documents']] != identities or [identity(j) for j in judgments['reviews']] != identities or judgments['independent'] is not False:
        raise ValueError('Incomplete/duplicate attribution generation and actual review cohort')
    decisions = {identity(d): d for d in source['documents']}; reviews = {identity(j): j for j in judgments['reviews']}
    collections = {}; inspections = []; summary = {'version': config['version'], 'splits': {}, 'trainingExecuted': False, 'inferenceExecuted': False, 'newMetricsProduced': False,
        'testContentAccessed': False, 'developmentPreviouslyExposed': True, 'independentHumanGold': False, 'modelPromoted': False, 'qualityPromotionPassed': False}
    def metadata(document, path):
        return {'provider': document['provider'], 'model': document['model'], 'promptSha256': c.file_sha256(CONTRACT), 'sourceArtifactSha256': c.file_sha256(path), 'createdAt': datetime.now(UTC).isoformat()}
    os.environ.setdefault('HF_HUB_OFFLINE', '1'); tokenizer = re_model.prepare_tokenizer(c.ROOT/'kg_datasets/models/scibert_24f92d32')
    for split, (refs, old) in data.items():
        receipts = []; initial = []; origins = []; local = []
        for ref, prior in zip(refs, old):
            key = (split, ref['arxivId']); receipt = prior; changed = False
            if key in decisions:
                judgment = reviews[key]
                if set(judgment) != {'split', 'arxivId', 'reason'} or not isinstance(judgment['reason'], str) or not judgment['reason'].strip(): raise ValueError('Missing actual source self-review')
                response, inspected = revise_attribution(prior, ref, decisions[key]); local.extend(inspected)
                changed = any(p['action'] != 'keep' for p in inspected)
                if changed:
                    generated = c.make_receipt(response, ref, metadata(source, decisions_path)); initial.append(generated)
                    reviewed = copy.deepcopy(response); reviewed['reviewOfSha256'] = generated['contentSha256']; reviewed['notes'] += ' Self-review: '+judgment['reason']
                    receipt = c.make_receipt(reviewed, ref, metadata(judgments, reviews_path), previous=generated)
            if any(prior['annotation'][k] != receipt['annotation'][k] for k in NER_FIELDS): raise ValueError('Attribution changed source NER')
            receipts.append(receipt); origins.append({'sampleId': ref['sampleId'], 'upstreamReceiptSha256': prior['contentSha256'], 'attributionInspected': key in decisions, 'relationRejudged': changed, 'NERReannotated': False})
        docs, pairs, full, excluded, unknown, total = rows_for(refs, receipts); before = rows_for(refs, old); retracted = sum(p['action'] == 'retract' for p in local)
        if len(pairs) != len(before[1])-retracted or unknown != before[4]+retracted or total != before[5] or excluded != before[3] or {d['sampleId'] for d in full} - {d['sampleId'] for d in before[2]}: raise ValueError('Attribution row/count/quarantine conservation failed')
        alignment = []
        for doc in docs:
            encoded = ner.encode_row(tokenizer, doc, 512); offsets = encoded['offsets']; labels = encoded['features']['labels']
            decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else label for o, label in zip(offsets, labels)], offsets, doc['text'])
            if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in doc['entities']]: raise ValueError('Strict NER BIO round-trip failed')
            alignment.append({'sampleId': doc['sampleId'], 'tokens': len(offsets), 'offsets': offsets, 'labels': labels})
        encoded_pairs = [re_model.encode_pair(tokenizer, p, 512) for p in pairs]; full_ids = {d['sampleId'] for d in full}
        summary['splits'][split] = {'queueDocuments': len(refs), 'nerDocuments': len(docs), 'NERExcluded': len(excluded), 'inspectedDocuments': len(config['reviewCohort'][split]), 'freshReceiptDocuments': len(initial),
            'previousKnownPairs': len(before[1]), 'knownPairs': len(pairs), 'relationSupport': dict(Counter(p['label'] for p in pairs)), 'eligiblePairs': total, 'unresolvedPairs': unknown,
            'knownPairCoverage': len(pairs)/total, 'completeRelationDocuments': len(full), 'fullDocumentCoverage': len(full)/len(refs), 'completeDocumentEVALSupport': sum(p['label'] == 'EVALUATED_ON' and p['sampleId'] in full_ids for p in pairs),
            'inspectedEVALPairs': len(local), 'retractedPairs': retracted, 'evidenceRepairedPairs': sum(p['action'] == 'repair_evidence' for p in local), 'maxMarkedTokens': max(len(e['features']['input_ids']) for e in encoded_pairs), 'strictBIORoundTripPassed': True}
        collections[split] = [('references', refs), ('generation_receipts', initial), ('reviewed_receipts', receipts), ('origins', origins), ('ner', docs), ('relation', pairs), ('full_relation', full), ('excluded_ner', excluded), ('token_alignment', alignment)]
        inspections.extend(local)
    source_cohorts(); output.mkdir(parents=True)
    for split, entries in collections.items():
        for name, rows in entries:
            filename = split+'_'+name if name in ('references', 'generation_receipts', 'reviewed_receipts', 'origins') else name+'_'+split
            c.write_jsonl(output/(filename+'.jsonl'), rows)
    c.write_jsonl(output/'attribution_inspections.jsonl', inspections); c.write_jsonl(output/'quality_actions.jsonl', [p for p in inspections if p['action'] != 'keep'])
    c.write_json(output/'summary.json', summary); c.write_json(output/'contract.json', config)
    seal(output, [CONTRACT, c.ROOT/config['parentRelationContract'], *[c.ROOT/s['path']/'manifest.json' for s in config['sources'].values()], decisions_path, reviews_path, Path(__file__),
        c.ROOT/'scripts/course_abstract_relation.py', c.ROOT/'scripts/course_abstract_v1.py', c.ROOT/'scripts/course_weak.py', c.ROOT/'scripts/train_course_ner.py', c.ROOT/'scripts/train_course_relation.py', c.SCHEMA_PATH,
        c.ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt', c.ROOT/'kg_datasets/models/scibert_24f92d32/config.json'])
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('decisions', 'reviews', 'output'): parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args(); existed = args.output.exists()
    try: build(args.decisions.resolve(), args.reviews.resolve(), args.output.resolve())
    except Exception as error:
        if not existed and args.output.exists() and not (args.output/'manifest.json').exists(): c.write_json(args.output/'failure.json', {'status': 'failed_no_synthetic_fallback', 'errorType': type(error).__name__, 'error': str(error)})
        raise
