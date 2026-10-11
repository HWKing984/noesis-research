"""Frozen-model local expression diagnostic; never document negatives or training."""
import argparse
import hashlib
import os
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import train_revised_abstract_models as prior
import train_pair_window_relation as windows
from course_abstract_v1 import read, seal

c, g, ner, relation = prior.c, prior.g, prior.ner, prior.re_model
CONTRACT = c.ROOT/'resources/course_evidence_blocks_v1.json'
BOUNDARY = r'(?<=[.!?])\s+(?=[A-Z])'
TARGET = 'source_bound_local_mention_predicate_expression_AI_dev_not_document_truth'
REVIEW = c.ROOT/'annotations/course_v4/evidence_block_reviews_20261010_61.json'


def load_sources():
    config = read(CONTRACT)
    if (config['version'] != 'abstract_evidence_blocks_v1' or config['boundaryPattern'] != BOUNDARY
            or config['sentencesPerBlock'] != 2 or config['maxTokens'] != 512 or config['target'] != TARGET
            or any(config[k] is not False for k in ('trainingAllowed', 'thresholdSelectionAllowed',
                'testContentAccessAllowed', 'automaticPromotionAllowed', 'oldWholeAbstractMetricsReplaced', 'independentHumanGold'))):
        raise ValueError('Local diagnostic contract drift')
    folder = c.ROOT/config['source']; manifest = g.verified_files(folder, config['sourceManifestSha256'])
    paths = {c.ROOT/p for p in manifest['inputSha256']}
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()):
        raise ValueError('Source inputs changed; reserved test is checked only as binary SHA')
    paths.update(folder/p for p in manifest['filesSha256']); paths.add(folder/'manifest.json')
    for settings in config['models'].values():
        checkpoint = c.ROOT/settings['checkpoint']
        if c.file_sha256(checkpoint/'model.safetensors') != settings['weightsSha256']:
            raise ValueError('Frozen model weights changed')
        paths.update(p for p in checkpoint.iterdir() if p.is_file())
    refs = c.read_jsonl(folder/'references.jsonl'); receipts = c.read_jsonl(folder/'reviewed_receipts.jsonl')
    if [r['arxivId'] for r in refs] != config['papers'] or len(refs) != len(receipts):
        raise ValueError('Entire fixed eight-paper cohort required')
    if any(c.validate_receipt(r, d) or r['review'] is None for d, r in zip(refs, receipts)):
        raise ValueError('Invalid or unreviewed source receipts')
    paths.update([CONTRACT, Path(__file__), Path(prior.__file__), Path(windows.__file__),
                  Path(ner.__file__), Path(relation.__file__), Path(c.__file__),
                  c.ROOT/'scripts/evaluate_course_relation.py', c.ROOT/'scripts/infer_course_corpus.py',
                  c.ROOT/'scripts/train_abstract_relation.py', c.ROOT/'scripts/course_relation_model.py',
                  c.ROOT/'tests/test_evidence_blocks.py'])
    return config, refs, receipts, sorted(paths)


def build_units(refs, receipts):
    if not refs or len(refs) != len(receipts) or len({r['sampleId'] for r in refs}) != len(refs):
        raise ValueError('Source inventory missing or duplicated')
    units = []
    for ref, receipt in zip(refs, receipts):
        text = ref['text']; annotation = receipt['annotation']
        if (receipt['reference'] != ref or ref['split'] != 'dev' or ref['textKind'] != 'abstract'
                or not text.strip()
                or hashlib.sha256(text.encode()).hexdigest() != ref['textSha256']
                or any(c.span_errors(e, text) for e in annotation['entities']+annotation['groupMentions'])):
            raise ValueError('Source reference/hash/span drift')
        ner.score_rows([ref | {'entities': annotation['entities']}], [annotation['entities']])
        # shortcut: deterministic English punctuation, not a general sentence parser; upgrade for new sources.
        bounds = [0]+[m.end() for m in re.finditer(BOUNDARY, text)]+[len(text)]
        for block, i in enumerate(range(0, len(bounds)-1, 2), 1):
            start, end = bounds[i], bounds[min(i+2, len(bounds)-1)]
            local = []; ambiguity = []
            for entity in annotation['entities']:
                if entity['start'] < end and start < entity['end']:
                    if start <= entity['start'] < entity['end'] <= end:
                        local.append(entity | {'entityId': 'e'+str(len(local)+1),
                                     'start': entity['start']-start, 'end': entity['end']-start})
                    else: ambiguity.append('Entity crosses a fixed block boundary')
            if any(e['start'] < end and start < e['end'] for e in annotation['groupMentions']):
                ambiguity.append('Shared-head group cannot become complete flat BIO entities')
            unit = {k: ref[k] for k in ('arxivId', 'groupId', 'sourceURL', 'split')}
            unit.update(sampleId='sample-'+c.canonical_sha256([ref['sampleId'], start, end])[:20],
                        sourceSampleId=ref['sampleId'], sourceTextSha256=ref['textSha256'],
                        sourceStart=start, sourceEnd=end, block=block, textKind='abstract_evidence_block',
                        text=text[start:end], textSha256=hashlib.sha256(text[start:end].encode()).hexdigest(),
                        entities=local, entityStatus='unresolved' if ambiguity else 'complete',
                        entityReason='; '.join(sorted(set(ambiguity))))
            units.append(unit)
    return units


def compile_units(units, decisions):
    if len(units) != len(decisions) or len({u['sampleId'] for u in units}) != len(units):
        raise ValueError('Every block needs one explicit ordered judgment')
    result = {'ner': [], 'complete': [], 'excluded': [], 'pairStates': [], 'positives': [], 'trainableNegativePairs': 0}
    for unit, decision in zip(units, decisions):
        if (set(decision) != {'arxivId', 'block', 'entityReview', 'pairReview', 'positives', 'unresolved'}
                or (decision['arxivId'], decision['block']) != (unit['arxivId'], unit['block'])
                or not decision['entityReview'].strip() or not decision['pairReview'].strip()):
            raise ValueError('Incomplete/incorrect local source review')
        if unit['entityStatus'] != 'complete':
            if decision['positives'] or decision['unresolved']: raise ValueError('Group quarantine cannot gain reference pairs')
            result['excluded'].append(unit | {'reason': unit['entityReason']}); continue
        result['ner'].append(unit); pairs = prior.candidate_rows(unit, unit['entities'])
        candidates = {(p['head']['entityId'], p['tail']['entityId']): p for p in pairs}; judgments = {}
        for item in decision['positives']:
            if len(item) != 4: raise ValueError('Positive judgment needs two IDs, label and evidence interpretation')
            head, tail, state, reason = item
            key = (head, tail)
            if (key not in candidates or key in judgments or not reason.strip()
                    or state != ('USED_FOR' if candidates[key]['tail']['label'] == 'TASK' else 'EVALUATED_ON')):
                raise ValueError('Duplicate or illegal positive pair')
            judgments[key] = (state, reason)
        for item in decision['unresolved']:
            if len(item) != 3: raise ValueError('Unresolved judgment needs two IDs and reason')
            head, tail, reason = item; key = (head, tail)
            if key not in candidates or key in judgments or not reason.strip(): raise ValueError('Duplicate or illegal unresolved pair')
            judgments[key] = ('UNRESOLVED', reason)
        unresolved = False
        for key, pair in candidates.items():
            state, reason = judgments.get(key, ('NOT_EXPRESSED', decision['pairReview']))
            result['pairStates'].append(pair | {'state': state, 'reason': reason,
                'sourceSampleId': unit['sourceSampleId'], 'sourceStart': unit['sourceStart'], 'sourceEnd': unit['sourceEnd']})
            if state in ('USED_FOR', 'EVALUATED_ON'):
                result['positives'].append(pair | {'label': state, 'reason': reason,
                    'evidence': {'start': 0, 'end': len(unit['text']), 'text': unit['text']}})
            unresolved |= state == 'UNRESOLVED'
        if unresolved: result['excluded'].append(unit | {'reason': 'At least one local pair remains UNRESOLVED'})
        else: result['complete'].append(unit)
    return result


def new_output(output):
    output = output.resolve()
    if output.exists(): raise FileExistsError('Preserve diagnostic outputs and failures')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Output outside task dataset')
    return output


def checked_snapshot(folder):
    manifest = g.verified_files(folder)
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()):
        raise ValueError('Diagnostic snapshot input drift')
    return manifest


def lock(output):
    output = new_output(output); config, refs, receipts, paths = load_sources(); units = build_units(refs, receipts)
    output.mkdir(parents=True); c.write_jsonl(output/'units.jsonl', units)
    c.write_json(output/'selection_lock.json', {'lockedAtUTC': datetime.now(UTC).isoformat(), 'contract': config,
        'sourcePapers': len(refs), 'allBlocks': len(units), 'nonoverlapping': True,
        'annotationsCompiled': False, 'modelInferenceExecuted': False, 'testContentConsumed': False})
    seal(output, paths); print({'lockedBlocks': len(units), 'sourcePapers': len(refs)}, flush=True)


def compile_snapshot(queue, decisions_path, output):
    output = new_output(output); queue_manifest = checked_snapshot(queue)
    config, refs, receipts, paths = load_sources(); units = build_units(refs, receipts)
    if units != c.read_jsonl(queue/'units.jsonl'): raise ValueError('Fixed unit queue drift')
    decisions = read(decisions_path)
    if decisions['provider'] != 'Codex AI' or decisions['independentHumanGold'] is not False:
        raise ValueError('Misstated annotation provenance')
    compiled = compile_units(units, decisions['blocks'])
    review = read(REVIEW)
    if (review['reviewOfSha256'] != c.file_sha256(decisions_path) or review['independent'] is not False
            or [(r['arxivId'], r['block']) for r in review['reviews']] != [(u['arxivId'], u['block']) for u in units]
            or any(set(r) != {'arxivId', 'block', 'reason'} or not r['reason'].strip() for r in review['reviews'])):
        raise ValueError('Actual same-session source review missing or misbound')
    output.mkdir(parents=True)
    try:
        tokenizer = relation.prepare_tokenizer(c.ROOT/config['models']['NER52']['checkpoint']); alignment = []
        for row in compiled['ner']:
            record = ner.encode_row(tokenizer, row, 512); offsets = record['offsets']; labels = record['features']['labels']
            decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else v for o, v in zip(offsets, labels)], offsets, row['text'])
            if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]:
                raise ValueError('Strict local BIO round-trip failure')
            alignment.append({'sampleId': row['sampleId'], 'offsets': offsets, 'labels': labels})
        for row in compiled['ner']:
            for pair in prior.candidate_rows(row, row['entities']): relation.encode_pair(tokenizer, pair, 512)
        for name in ('ner', 'complete', 'excluded', 'pairStates', 'positives'): c.write_jsonl(output/(name+'.jsonl'), compiled[name])
        c.write_jsonl(output/'units.jsonl', units); c.write_jsonl(output/'token_alignment.jsonl', alignment)
        ids = {u['sampleId'] for u in compiled['complete']}; positives = [p for p in compiled['positives'] if p['sampleId'] in ids]
        summary = {'target': TARGET, 'lockedQueue': len(units), 'sourcePapers': len(refs), 'NERBlocks': len(compiled['ner']),
            'entities': dict(Counter(e['label'] for u in compiled['ner'] for e in u['entities'])),
            'completeBlocks': len(ids), 'blockCoverage': len(ids)/len(units), 'eligibleReferencePairs': len(compiled['pairStates']),
            'pairStates': dict(Counter(p['state'] for p in compiled['pairStates'])),
            'completePositiveSupport': dict(Counter(p['label'] for p in positives)),
            'zeroPositiveCompleteBlocks': sum(not any(p['sampleId'] == u['sampleId'] for p in positives) for u in compiled['complete']),
            'trainableNegativePairs': 0, 'independentHumanGold': False, 'trainingExecuted': False, 'testEvaluated': False,
            'notice': 'Exposed targeted AI dev, correlated mentions/blocks. Local non-expression is not a factual negative. Original whole-abstract evaluation unchanged.'}
        c.write_json(output/'summary.json', summary)
        paths += [decisions_path, REVIEW, queue/'manifest.json', queue/'selection_lock.json', queue/'units.jsonl']
        seal(output, sorted(set(paths))); print(summary, flush=True)
    except Exception as error:
        c.write_json(output/'failure.json', {'status': 'failed_no_synthetic_fallback', 'error': str(error)}); raise


def evaluate(snapshot, output):
    output = new_output(output); manifest = checked_snapshot(snapshot); config, _, _, paths = load_sources()
    docs = c.read_jsonl(snapshot/'ner.jsonl'); complete = c.read_jsonl(snapshot/'complete.jsonl')
    ids = {d['sampleId'] for d in complete}; refs = [p for p in c.read_jsonl(snapshot/'positives.jsonl') if p['sampleId'] in ids]
    if not complete or not refs: raise ValueError('Supported complete expression blocks required')
    output.mkdir(parents=True); started = time.perf_counter()
    try:
        os.environ.setdefault('HF_HUB_OFFLINE', '1'); os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        import torch
        import transformers
        from transformers import DataCollatorWithPadding
        device = prior.setup({'seed': 61}); tokenizer = relation.prepare_tokenizer(c.ROOT/config['models']['NER52']['checkpoint'])
        predictions, ner_result = prior.infer_ner(c.ROOT/config['models']['NER52']['checkpoint'], docs, tokenizer,
            {'bioLabels': ['O', 'B-METHOD', 'I-METHOD', 'B-TASK', 'I-TASK', 'B-DATASET', 'I-DATASET']}, device)
        ner_result = prior.dev_scope(ner_result, TARGET); by_id = {d['sampleId']: p for d, p in zip(docs, predictions)}
        c.write_jsonl(output/'ner_predictions.jsonl', [{'sampleId': d['sampleId'], 'predictedEntities': p} for d, p in zip(docs, predictions)])
        module = [p for d in complete for p in prior.candidate_rows(d, d['entities'])]
        pipeline = [p for d in complete for p in prior.candidate_rows(d, by_id[d['sampleId']])]
        comparison = {}
        for name in ('RE57', 'RE60'):
            checkpoint = c.ROOT/config['models'][name]['checkpoint']; tokenizer = relation.prepare_tokenizer(checkpoint)
            model = relation.load_relation_model(checkpoint, tokenizer, 'entity_markers').to(device).requires_grad_(False)
            collator = DataCollatorWithPadding(tokenizer, return_tensors='pt'); results = {}
            for scope, rows in (('reference_entity_module', module), ('predicted_entity_pipeline', pipeline)):
                local = [windows.window_pair(r) for r in rows] if name == 'RE60' else rows
                predicted = prior.predict(model, tokenizer, local, 512, collator, device, 4)
                if name == 'RE60': predicted = windows.restore_predictions(rows, predicted)
                c.write_jsonl(output/(name+'_'+scope+'_predictions.jsonl'), predicted)
                metrics = prior.dev_scope(prior.score_pipeline(complete, refs, predicted), TARGET)
                metrics.update(entityScope=scope,
                    notice='Exact local mention-predicate expression. All candidates and zero-positive complete blocks retained. NO_RELATION output is abstention/no edge, not true-negative document accuracy. Exposed AI dev, not final test or production truth.')
                results[scope] = metrics
            comparison[name] = results; del model; torch.cuda.empty_cache()
        lookup = {d['sampleId']: d for d in complete}
        support = {label: {'mentionPairs': sum(p['label'] == label for p in refs),
            'blocks': len({p['sampleId'] for p in refs if p['label'] == label}),
            'independentSourcePapers': len({lookup[p['sampleId']]['arxivId'] for p in refs if p['label'] == label})}
            for label in ('USED_FOR', 'EVALUATED_ON')}
        summary = read(snapshot/'summary.json')
        c.write_json(output/'comparison.json', {'evaluationTarget': TARGET, 'NER52': ner_result, 'comparison': comparison,
            'support': support, 'coverage': summary, 'allModuleCandidates': len(module), 'allPipelineCandidates': len(pipeline),
            'trained': False, 'testEvaluated': False, 'modelPromoted': False, 'qualityPromotionPassed': False,
            'oldWholeAbstractMetricsReplaced': False,
            'notice': 'A separately locked exposed local expression diagnostic, not a substitute for full abstracts or independent test. Repeated mentions and blocks do not increase independent paper support.'})
        c.write_json(output/'environment.json', {'torch': torch.__version__, 'transformers': transformers.__version__,
            'cuda': torch.version.cuda, 'gpu': torch.cuda.get_device_name(device), 'inferenceFeaturesContainLabels': False})
        checked_snapshot(snapshot); load_sources()
        c.write_json(output/'status.json', {'status': 'completed', 'elapsedSeconds': time.perf_counter()-started,
            'inferenceExecuted': True, 'trainingExecuted': False, 'testEvaluated': False, 'modelPromoted': False})
        paths += [snapshot/'manifest.json']+[snapshot/p for p in manifest['filesSha256']]
        seal(output, sorted(set(paths))); print({'completeBlocks': len(complete), 'support': support,
            'pipeline': {k: v['predicted_entity_pipeline']['positiveMicro'] for k, v in comparison.items()}}, flush=True)
    except Exception as error:
        c.write_json(output/'status.json', {'status': 'failed_no_synthetic_fallback', 'error': str(error), 'modelPromoted': False}); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('lock', 'compile', 'evaluate'))
    parser.add_argument('--source', type=Path); parser.add_argument('--decisions', type=Path); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'lock': lock(args.output)
    elif args.source is None: parser.error('source required')
    elif args.action == 'compile':
        if args.decisions is None: parser.error('decisions required')
        compile_snapshot(args.source.resolve(), args.decisions.resolve(), args.output)
    else: evaluate(args.source.resolve(), args.output)
