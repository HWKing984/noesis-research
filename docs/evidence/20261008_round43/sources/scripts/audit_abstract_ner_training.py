"""Train-only frozen NER diagnostics; no label edits, fitting, dev/test inference or deployment."""
import argparse
import hashlib
import os
import shutil
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import course_graph as g
import course_weak as c
import train_course_ner as ner
import train_revised_abstract_models as revised
from course_abstract_relation import rows_for
from course_abstract_v1 import read, seal

CONTRACT = c.ROOT/'resources/course_abstract_train_audit_v1.json'
REVIEW = c.ROOT/'annotations/course_v4/abstract_train_dataset_audit_20261008_43.json'


def load_inputs():
    config = read(CONTRACT)
    if config['version'] != 'abstract_train_audit_v1' or config['maxTokens'] != 512 or any(config[k] is not False for k in ('trainingAllowed', 'labelMutationAllowed', 'semanticDevReadAllowed', 'semanticTestReadAllowed', 'automaticPromotionAllowed')):
        raise ValueError('Train diagnostic contract drift')
    folder = c.ROOT/config['snapshot']; manifest = g.verified_files(folder, config['snapshotManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Snapshot source drift')
    refs = c.read_jsonl(folder/'train_references.jsonl'); receipts = c.read_jsonl(folder/'train_reviewed_receipts.jsonl')
    if len(refs) != config['expected']['references'] or len(receipts) != len(refs) or len({r['sampleId'] for r in refs}) != len(refs) or len({r['groupId'] for r in refs}) != len(refs): raise ValueError('Missing/duplicate train cohort')
    for ref, receipt in zip(refs, receipts):
        if ref['split'] != 'train' or ref['textKind'] != 'abstract' or hashlib.sha256(ref['text'].encode('utf-8')).hexdigest() != ref['textSha256'] or c.validate_receipt(receipt, ref) or receipt['review'] is None: raise ValueError('Invalid/unreviewed training source')
    generated = rows_for(refs, receipts); rows = c.read_jsonl(folder/'ner_train.jsonl')
    if generated[0] != rows or len(rows) != config['expected']['eligibleNER'] or len(generated[3]) != config['expected']['excludedNER'] or Counter(e['label'] for r in rows for e in r['entities']) != config['expected']['entities']: raise ValueError('Training rows/support drift')
    selected = [r for r in rows if any(e['label'] == 'DATASET' for e in r['entities'])]; by_id = {r['sampleId']: r for r in refs}; review = read(REVIEW)
    if len(selected) != config['expected']['datasetDocuments'] or review['kind'] != 'source_review_diagnostic_not_annotation_revision' or review['independent'] is not False or review['newAnnotationReceipt'] is not False or review['predictionsSeenBeforeReview'] is not False or [d['arxivId'] for d in review['documents']] != [by_id[r['sampleId']]['arxivId'] for r in selected]: raise ValueError('Incomplete/misrepresented source review')
    for row, judgment in zip(selected, review['documents']):
        if judgment['textSha256'] != row['textSha256'] or judgment['datasets'] != list(dict.fromkeys(e['text'] for e in row['entities'] if e['label'] == 'DATASET')) or not judgment['quote'] or judgment['quote'] not in row['text'] or any(not judgment[k].strip() for k in ('initialReason', 'selfReviewReason')): raise ValueError('Source review binding failed')
    for settings in config['models'].values():
        path = c.ROOT/settings['run']; g.verified_files(path, settings['manifestSha256'])
        if c.file_sha256(path/settings['checkpoint']/'model.safetensors') != settings['weightsSha256']: raise ValueError('Frozen model drift')
    return config, rows, refs, review


def errors_for(row, prediction):
    """Geometric diagnostic only; do not infer semantic label corrections from overlap."""
    key = lambda e: (e['start'], e['end'], e['label'])
    expected = {key(e) for e in row['entities']}; predicted = {key(e) for e in prediction}; errors = []
    if len(expected) != len(row['entities']) or len(predicted) != len(prediction): raise ValueError('Duplicate entity in diagnosis')
    for side, entities, other, matched in (('FN', row['entities'], prediction, predicted), ('FP', prediction, row['entities'], expected)):
        for entity in entities:
            if key(entity) in matched: continue
            overlaps = [e for e in other if e['start'] < entity['end'] and entity['start'] < e['end']]
            if any((e['start'], e['end']) == (entity['start'], entity['end']) for e in overlaps): cause = 'type'
            elif overlaps: cause = 'boundary' if any(e['label'] == entity['label'] for e in overlaps) else 'type_and_boundary'
            else: cause = 'missing' if side == 'FN' else 'extra'
            start = max(0, entity['start']-80); end = min(len(row['text']), entity['end']+80)
            errors.append({'sampleId': row['sampleId'], 'textSha256': row['textSha256'], 'side': side, 'label': entity['label'], 'cause': cause, 'entity': entity, 'overlaps': overlaps, 'contextStart': start, 'contextEnd': end, 'context': row['text'][start:end]})
    return errors


def inventory(rows):
    by_surface = defaultdict(list); docs = []; support = Counter(); label_docs = Counter()
    for row in rows:
        support.update(e['label'] for e in row['entities']); label_docs.update({e['label'] for e in row['entities']})
        for e in row['entities']: by_surface[e['text'].casefold()].append({'sampleId': row['sampleId'], 'label': e['label'], 'text': e['text'], 'start': e['start'], 'end': e['end']})
        datasets = [e for e in row['entities'] if e['label'] == 'DATASET']
        if datasets: docs.append({'sampleId': row['sampleId'], 'mentions': len(datasets), 'literalNames': list(dict.fromkeys(e['text'] for e in datasets))})
    return {'entitySupport': dict(support), 'documentsPerClass': dict(label_docs), 'datasetDocuments': sorted(docs, key=lambda r: (-r['mentions'], r['sampleId'])),
        'datasetLiteralNames': sorted({e['text'] for r in rows for e in r['entities'] if e['label'] == 'DATASET'}),
        'surfaceTypeConflicts': [{'surface': surface, 'occurrences': occurrences} for surface, occurrences in sorted(by_surface.items()) if len({e['label'] for e in occurrences}) > 1],
        'notice': 'Literal-name counts are not normalized dataset identities. Contextual type conflicts are review candidates, not automatic errors.'}


def run(output):
    if output.exists(): raise FileExistsError('Preserve diagnostic output; no automatic overwrite/retry')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp/course_v4_runs').resolve()): raise ValueError('Diagnostic output outside run directory')
    config, rows, refs, review = load_inputs(); paths = [CONTRACT, REVIEW, c.ROOT/config['snapshot']/'manifest.json']
    paths += [c.ROOT/'scripts'/name for name in ('audit_abstract_ner_training.py', 'train_revised_abstract_models.py', 'train_course_ner.py', 'train_course_relation.py', 'course_relation_model.py', 'course_abstract_relation.py', 'course_abstract_v1.py', 'course_weak.py', 'course_graph.py', 'infer_course_corpus.py')]
    paths += [c.CONFIG_PATH, c.SCHEMA_PATH, c.ROOT/'resources/course_abstract_v1.json', c.ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt', c.ROOT/'kg_datasets/models/scibert_24f92d32/config.json']
    paths += [c.ROOT/config['snapshot']/name for name in ('train_references.jsonl', 'train_reviewed_receipts.jsonl', 'ner_train.jsonl')]
    for settings in config['models'].values():
        path = c.ROOT/settings['run']; paths += [path/'manifest.json', path/settings['checkpoint']/'model.safetensors']
    paths += [c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl', c.ROOT/'resources/course_graph_runtime.json']
    hashes = {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in paths}
    output.mkdir(parents=True); state = {'status': 'running', 'createdAtUTC': datetime.now(UTC).isoformat(), 'trainingStarted': False, 'devSemanticallyRead': False, 'testSemanticallyRead': False, 'modelPromoted': False}; c.write_json(output/'status.json', state); started = time.perf_counter()
    try:
        os.environ.setdefault('HF_HUB_OFFLINE', '1'); os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        import torch
        import transformers
        from transformers import BertTokenizerFast
        parent = read(c.ROOT/'resources/course_abstract_v1.json'); device = revised.setup(parent['NERTraining'])
        tokenizer = BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32', local_files_only=True, do_lower_case=True)
        tokens = Counter()
        for row in rows:
            encoded = ner.encode_row(tokenizer, row, config['maxTokens']); labels = encoded['features']['labels']; offsets = encoded['offsets']
            decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else tag for o, tag in zip(offsets, labels)], offsets, row['text'])
            if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]: raise ValueError('Training BIO round-trip failed')
            tokens.update(parent['bioLabels'][tag] for tag in labels if tag != -100)
        results = {}; by_id = {r['sampleId']: r for r in refs}
        for name, settings in config['models'].items():
            predictions, metrics = revised.infer_ner(c.ROOT/settings['run']/settings['checkpoint'], rows, tokenizer, parent, device)
            metrics = revised.dev_scope(metrics, config['evaluationTarget']); errors = [e for row, prediction in zip(rows, predictions) for e in errors_for(row, prediction)]
            micro = metrics['metrics']['micro']
            if sum(e['side'] == 'FN' for e in errors) != micro['reference']-micro['truePositive'] or sum(e['side'] == 'FP' for e in errors) != micro['predicted']-micro['truePositive']: raise ValueError('Diagnostic FP/FN accounting failed')
            c.write_jsonl(output/(name+'_train_predictions.jsonl'), [{'sampleId': r['sampleId'], 'textSha256': r['textSha256'], 'referenceEntities': r['entities'], 'predictedEntities': p} for r, p in zip(rows, predictions)])
            c.write_jsonl(output/(name+'_train_errors.jsonl'), [e | {'arxivId': by_id[e['sampleId']]['arxivId']} for e in errors])
            results[name] = metrics | {'errorCounts': dict(Counter(e['side'] for e in errors)), 'errorClusters': dict(Counter(e['side']+'/'+e['label']+'/'+e['cause'] for e in errors))}
            print(name, results[name]['metrics']['micro'], results[name]['errorCounts'], flush=True)
        c.write_jsonl(output/'train_inputs.jsonl', rows); c.write_json(output/'source_review.json', review); c.write_json(output/'contract.json', config)
        report = {'version': config['version'], 'evaluationTarget': config['evaluationTarget'], 'trainDocuments': len(rows), 'queueDocuments': len(refs), 'excludedDocuments': 8, 'inventory': inventory(rows), 'BIOtokenCounts': dict(tokens), 'models': results,
            'trainingStarted': False, 'labelsChanged': False, 'devSemanticallyRead': False, 'testSemanticallyRead': False, 'qualityPromotionPassed': False, 'modelPromoted': False,
            'notice': 'In-sample diagnostic: new42 trained on these 50 documents, old35 on only 29. Neither score is a new dev/test/generalization result. AI source review is not independent gold.'}
        c.write_json(output/'audit.json', report); c.write_json(output/'environment.json', {'torch': torch.__version__, 'transformers': transformers.__version__, 'cuda': torch.version.cuda, 'gpu': torch.cuda.get_device_name(device)})
        archive = output/'sources'; archive.mkdir()
        for i, path in enumerate(paths):
            if path.suffix != '.safetensors': shutil.copy2(path, archive/(str(i)+'_'+path.name))
        if any(c.file_sha256(c.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Input/model/code drift during diagnostics')
        state.update(status='completed', finishedAtUTC=datetime.now(UTC).isoformat(), elapsedSeconds=time.perf_counter()-started); c.write_json(output/'status.json', state); seal(output, paths)
    except Exception as error:
        c.write_json(output/'status.json', state | {'status': 'failed_no_synthetic_fallback', 'errorType': type(error).__name__, 'error': str(error)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('preflight', 'diagnose')); parser.add_argument('--output', type=Path); args = parser.parse_args()
    if args.action == 'preflight':
        config, rows, _, _ = load_inputs(); print({'trainDocuments': len(rows), 'DATASET': config['expected']['entities']['DATASET'], 'testConsumed': False})
    else:
        if args.output is None: parser.error('diagnose requires a new --output')
        run(args.output.resolve())
