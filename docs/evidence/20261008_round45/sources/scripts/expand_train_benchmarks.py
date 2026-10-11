"""Collect four pre-locked train benchmark sources and append reviewed labels without held-out content."""
import argparse
import hashlib
import re
import shutil
import time
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.robotparser import RobotFileParser

import collect_train_abstracts as transport
import course_graph as g
import course_weak as c
import train_course_ner as ner
import train_course_relation as re_model
from course_abstract_relation import rows_for
from course_abstract_v1 import read, seal
from collect_course_abstract_pages import parse_page
from fetch_abstract_pilot import normalize_title, POLICY

CONTRACT = c.ROOT/'resources/course_abstract_benchmark_expansion_v1.json'
CORPUS = c.ROOT/'kg_datasets/dblp/ner_v1/corpus_manifest.jsonl'
SPLITS = c.ROOT/'kg_datasets/dblp/course_v4_weak/corpus_split_manifest.jsonl'
title_key = lambda value: normalize_title(unicodedata.normalize('NFKC', value))


def reject_identity_overlap(seeds, registry, existing):
    ids = [s['arxivId'] for s in seeds]; titles = [title_key(s['title']) for s in seeds]
    if not ids or len(set(ids)) != len(ids) or len(set(titles)) != len(titles) or any(not re.fullmatch(r'\d{4}\.\d{4,5}', i) for i in ids): raise ValueError('Malformed/duplicate benchmark seeds')
    aliases = {'arxiv:'+i for i in ids} | {'journals/corr/abs-'+i.replace('.', '-') for i in ids}
    if any(r['publicationId'] in aliases or r.get('arxivId') in ids or title_key(r.get('text', r.get('title', ''))) in titles for r in registry+existing): raise ValueError('Existing paper identity; never force a held-out group to train')


def locked():
    config = read(CONTRACT); folder = c.ROOT/config['snapshot']
    if config['version'] != 'abstract_train_benchmark_expansion_v1' or len(config['seeds']) != 4 or any(config[k] is not False for k in ('trainingAllowed', 'automaticPromotionAllowed', 'independentHumanGold')) or config['crawlDelaySeconds'] < 15.1: raise ValueError('Benchmark contract drift')
    manifest = g.verified_files(folder, config['snapshotManifestSha256'])
    if c.file_sha256(CORPUS) != config['corpusSha256'] or c.file_sha256(SPLITS) != config['splitManifestSha256'] or any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Identity/source manifest drift')
    refs = c.read_jsonl(folder/'train_references.jsonl'); receipts = c.read_jsonl(folder/'train_reviewed_receipts.jsonl')
    if len(refs) != len(receipts) or len(refs) != 58 or any(r['split'] != 'train' or c.validate_receipt(a, r) for r, a in zip(refs, receipts)): raise ValueError('Old train binding invalid')
    # Only normalized title/ID metadata used for collision rejection, never labels or held-out abstracts.
    registry = c.read_jsonl(CORPUS); splits = c.read_jsonl(SPLITS)
    if {r['publicationId'] for r in registry} != {r['publicationId'] for r in splits}: raise ValueError('Identity registry incomplete')
    old_titles = [{'publicationId': r['publicationId'], 'arxivId': r['arxivId'], 'title': r.get('referenceTitle', '')} for r in refs]
    reject_identity_overlap(config['seeds'], registry, old_titles)
    return config, folder, refs, receipts


def new_output(output):
    if output.exists(): raise FileExistsError('Preserve benchmark evidence; choose a new output')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Output outside dataset directory')


def inputs(config):
    folder = c.ROOT/config['snapshot']
    return [CONTRACT, CORPUS, SPLITS, Path(__file__), folder/'manifest.json', folder/'train_references.jsonl', folder/'train_reviewed_receipts.jsonl', c.CONFIG_PATH, c.SCHEMA_PATH, c.ROOT/'scripts/course_weak.py', c.ROOT/'scripts/course_graph.py', c.ROOT/'scripts/course_abstract_v1.py', c.ROOT/'scripts/course_abstract_relation.py', c.ROOT/'scripts/train_course_ner.py', c.ROOT/'scripts/train_course_relation.py', c.ROOT/'scripts/collect_train_abstracts.py', c.ROOT/'scripts/collect_course_abstract_pages.py', c.ROOT/'scripts/fetch_abstract_pilot.py', c.ROOT/'resources/course_abstract_scope_review_v1.json', c.ROOT/'resources/course_abstract_relation_v1.json', c.ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt', c.ROOT/'kg_datasets/models/scibert_24f92d32/config.json', c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl', c.ROOT/'resources/course_graph_runtime.json']


def collect(output):
    new_output(output); config, _, _, _ = locked(); paths = inputs(config); hashes = {p: c.file_sha256(p) for p in paths}
    output.mkdir(parents=True)
    try:
        c.write_json(output/'selection_lock.json', {'lockedAtUTC': datetime.now(UTC).isoformat(), 'selected': config['seeds'], 'policy': config['selection'], 'identityOverlap': False})
        robots_payload = transport.get('https://arxiv.org/robots.txt', 64*1024); (output/'robots.txt').write_bytes(robots_payload)
        robots = RobotFileParser(); robots.parse(robots_payload.decode('utf-8').splitlines()); delay = max(config['crawlDelaySeconds'], robots.crawl_delay(transport.AGENT) or 0)
        if any(not robots.can_fetch(transport.AGENT, 'https://arxiv.org/abs/'+s['arxivId']) for s in config['seeds']): raise ValueError('Robots prohibits source request')
        c.write_json(output/'policy.json', POLICY | {'policy_checked_on': '2026-10-08', 'robotsSha256': c.file_sha256(output/'robots.txt'), 'crawlDelaySeconds': delay, 'source': 'official citation metadata; no PDF/full text'})
        from transformers import BertTokenizerFast
        tokenizer = BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32', local_files_only=True, do_lower_case=True)
        refs = []; records = []; requests = []; excluded = []; last = time.monotonic()
        # ponytail: four serial sources only; use bulk metadata before corpus-scale collection.
        for i, seed in enumerate(config['seeds'], 1):
            time.sleep(max(0, delay-(time.monotonic()-last))); last = time.monotonic(); url = 'https://arxiv.org/abs/'+seed['arxivId']; request = {'arxivId': seed['arxivId'], 'startedAtUTC': datetime.now(UTC).isoformat(), 'url': url}
            try:
                raw = transport.get(url, 1024*1024); name = f'page_{i:03d}.html'; (output/name).write_bytes(raw); title, text = parse_page(raw, seed)
                match = title_key(title) == title_key(seed['title']); tokens = len(tokenizer(text, truncation=False)['input_ids']); digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
                records.append(seed | {'title': title, 'abstract': text, 'content_hash': digest, 'title_match': match, 'rawResponseFile': name, 'raw_response_sha256': hashlib.sha256(raw).hexdigest(), 'source_url': url, 'tokens': tokens})
                request.update(status='completed', titleMatch=match, tokens=tokens, rawResponseFile=name)
                if not match or tokens > 512: excluded.append({'arxivId': seed['arxivId'], 'reason': 'title_mismatch' if not match else 'overlength_no_truncation'})
                else: refs.append({'sampleId': 'sample-'+c.canonical_sha256(['whole_abstract', seed['arxivId'], digest])[:20], 'publicationId': 'arxiv:'+seed['arxivId'], 'arxivId': seed['arxivId'], 'referenceTitle': title, 'groupId': 'abstract-paper-'+seed['arxivId'], 'split': 'train', 'text': text, 'textKind': 'abstract', 'textSha256': digest, 'sourceURL': url, 'sourceOrigin': 'external_targeted_benchmark_train_only', 'schemaVersion': 'course-whole-abstract-1', 'contractSha256': c.canonical_sha256(config), 'tokens': tokens, 'annotationStatus': 'pending'})
            except Exception as error:
                request.update(status='failed_no_synthetic_fallback', errorType=type(error).__name__, error=str(error)); excluded.append({'arxivId': seed['arxivId'], 'reason': 'failed_request'})
            requests.append(request); c.write_json(output/'requests.json', requests); c.write_jsonl(output/'abstracts.jsonl', records); c.write_jsonl(output/'train_references.jsonl', refs); print({'requested': i, 'usable': len(refs), 'excluded': len(excluded)}, flush=True)
        c.write_json(output/'contract.json', config); c.write_jsonl(output/'excluded.jsonl', excluded)
        c.write_json(output/'summary.json', {'status': 'completed' if len(refs) == 4 else 'partial', 'requested': 4, 'fetched': len(records), 'usable': len(refs), 'excluded': len(excluded), 'annotated': False, 'trainingExecuted': False, 'heldOutAbstractsAccessed': False, 'modelPromoted': False})
        if any(c.file_sha256(p) != sha for p, sha in hashes.items()): raise ValueError('Source drift during collection')
        seal(output, paths)
    except Exception as error:
        c.write_json(output/'failure.json', {'status': 'failed_no_fallback', 'errorType': type(error).__name__, 'error': str(error)}); raise


def snapshot(source, reviewed, output):
    new_output(output); config, folder, refs, receipts = locked()
    for path in (source, reviewed):
        manifest = g.verified_files(path)
        if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('New source/annotation drift')
    fresh = c.read_jsonl(source/'train_references.jsonl'); annotated = c.read_jsonl(reviewed/'reviewed_receipts.jsonl'); records = {r['arxivId']: r for r in c.read_jsonl(source/'abstracts.jsonl')}
    if read(source/'selection_lock.json')['selected'] != config['seeds'] or not fresh or fresh != c.read_jsonl(reviewed/'references.jsonl') or len(fresh) != len(annotated) or any(c.validate_receipt(a, r) or a['review'] is None or r['split'] != 'train' or r['textKind'] != 'abstract' or r['text'] != records[r['arxivId']]['abstract'] or hashlib.sha256(r['text'].encode()).hexdigest() != r['textSha256'] for r, a in zip(fresh, annotated)): raise ValueError('Fresh source/receipt binding failed')
    refs += fresh; receipts += annotated
    if len({r['sampleId'] for r in refs}) != len(refs) or len({r['groupId'] for r in refs}) != len(refs) or len({r['arxivId'] for r in refs}) != len(refs): raise ValueError('Duplicate train identities')
    rows, pairs, full, excluded, unknown, total = rows_for(refs, receipts); tokenizer = re_model.prepare_tokenizer(c.ROOT/'kg_datasets/models/scibert_24f92d32'); alignment = []
    for row in rows:
        encoded = ner.encode_row(tokenizer, row, 512); offsets = encoded['offsets']; labels = encoded['features']['labels']; decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else tag for o, tag in zip(offsets, labels)], offsets, row['text'])
        if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]: raise ValueError('Strict BIO failed; no silently excluded examples')
        alignment.append({'sampleId': row['sampleId'], 'offsets': offsets, 'labels': labels})
    encoded_pairs = [re_model.encode_pair(tokenizer, p, 512) for p in pairs]
    paths = inputs(config)+[source/'manifest.json', reviewed/'manifest.json', c.ROOT/'scripts/compile_abstract_annotations.py', c.ROOT/'scripts/review_abstract_annotations.py']; hashes = {p: c.file_sha256(p) for p in paths}; output.mkdir(parents=True)
    try:
        dev = [p for p in folder.iterdir() if p.is_file() and 'dev' in p.stem]
        for p in dev: shutil.copy2(p, output/p.name)
        for name, values in [('train_references', refs), ('train_reviewed_receipts', receipts), ('ner_train', rows), ('relation_train', pairs), ('full_relation_train', full), ('excluded_ner_train', excluded), ('token_alignment_train', alignment)]: c.write_jsonl(output/(name+'.jsonl'), values)
        summary = {'status': 'completed', 'version': config['version'], 'trainQueue': len(refs), 'NERtrain': len(rows), 'NERexcluded': len(excluded), 'entitySupport': dict(Counter(e['label'] for r in rows for e in r['entities'])), 'DATASETSourcePapers': sum(any(e['label'] == 'DATASET' for e in r['entities']) for r in rows), 'knownPairs': len(pairs), 'relationSupport': dict(Counter(p['label'] for p in pairs)), 'unknownPairs': unknown, 'eligiblePairs': total, 'completeRelationDocuments': len(full), 'addedTrainPapers': len(fresh), 'oldReceiptLinesPreserved': 58, 'maxMarkedTokens': max(len(p['features']['input_ids']) for p in encoded_pairs), 'opaqueDevFilesIdentical': len(dev), 'trainingExecuted': False, 'inferenceExecuted': False, 'heldOutAbstractsAccessed': False, 'modelPromoted': False, 'qualityPromotionPassed': False, 'independentHumanGold': False, 'selectionBias': 'targeted reading-comprehension benchmark papers; not representative independent evaluation'}
        c.write_json(output/'summary.json', summary); c.write_json(output/'contract.json', config)
        if any(c.file_sha256(p) != sha for p, sha in hashes.items()) or any(c.file_sha256(p) != c.file_sha256(output/p.name) for p in dev): raise ValueError('Snapshot input/opaque dev drift')
        if (folder/'train_reviewed_receipts.jsonl').read_bytes().splitlines() != (output/'train_reviewed_receipts.jsonl').read_bytes().splitlines()[:58]: raise ValueError('Old receipt bytes changed')
        seal(output, paths); print(summary)
    except Exception as error:
        c.write_json(output/'failure.json', {'status': 'failed_no_fallback', 'errorType': type(error).__name__, 'error': str(error)}); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('preflight', 'collect', 'snapshot')); parser.add_argument('--sources', type=Path); parser.add_argument('--reviewed', type=Path); parser.add_argument('--output', type=Path); args = parser.parse_args()
    if args.action == 'preflight': print({'lockedSeeds': len(locked()[0]['seeds']), 'identityOverlap': False, 'trainingAllowed': False})
    elif args.output is None: parser.error('New output required')
    elif args.action == 'collect': collect(args.output.resolve())
    elif args.sources is None or args.reviewed is None: parser.error('sources/reviewed required')
    else: snapshot(args.sources.resolve(), args.reviewed.resolve(), args.output.resolve())
