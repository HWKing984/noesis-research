"""Collect a fixed NER-only training cohort and preserve old RE/dev bytes."""
import argparse
import hashlib
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.robotparser import RobotFileParser

import collect_train_abstracts as transport
import course_graph as g
import train_course_ner as ner
import train_course_relation as relation
from course_abstract_v1 import read, seal
from collect_course_abstract_pages import parse_page
from expand_train_benchmarks import CORPUS, reject_identity_overlap, title_key

c = g.c
CONTRACT = c.ROOT/'resources/course_abstract_boundary_expansion_v1.json'


def locked():
    config = read(CONTRACT); base = c.ROOT/config['snapshot']; supplement = c.ROOT/config['supplement']
    if config['version'] != 'abstract_boundary_train_expansion_v1' or len(config['seeds']) != 8 or config['maxTokens'] != 512 or config['crawlDelaySeconds'] < 15.1 or config['automaticPromotionAllowed'] is not False: raise ValueError('Boundary contract drift')
    manifest = g.verified_files(base, config['snapshotManifestSha256']); g.verified_files(supplement, config['supplementManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Base training input drift')
    existing = []
    for folder, names in ((base, ('train_references.jsonl', 'dev_references.jsonl')), (supplement, ('references.jsonl',))):
        for name in names:
            for r in c.read_jsonl(folder/name): existing.append({k: r.get(k, '') for k in ('publicationId', 'arxivId')} | {'title': r.get('referenceTitle', '')})
    existing += read(c.ROOT/config['metadataLock'])['selected']
    reject_identity_overlap(config['seeds'], c.read_jsonl(CORPUS), existing)
    return config, base


def inputs():
    config, base = locked()
    return [CONTRACT, Path(__file__), CORPUS, c.ROOT/config['metadataLock'], base/'manifest.json', c.ROOT/config['supplement']/'manifest.json',
        c.ROOT/'scripts/collect_train_abstracts.py', c.ROOT/'scripts/collect_course_abstract_pages.py', c.ROOT/'scripts/expand_train_benchmarks.py',
        c.ROOT/'scripts/course_weak.py', c.SCHEMA_PATH, c.ROOT/'scripts/train_course_ner.py', c.ROOT/'scripts/train_course_relation.py',
        c.ROOT/'resources/course_graph_runtime.json', c.ROOT/'resources/course_graph_quality_runtime.json',
        c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl']


def fresh(output):
    if output.exists(): raise FileExistsError('Preserve boundary expansion')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Output outside datasets')


def collect(output):
    fresh(output); config, _ = locked(); paths = inputs(); hashes = {p: c.file_sha256(p) for p in paths}
    output.mkdir(parents=True)
    c.write_json(output/'selection_lock.json', {'lockedAtUTC': datetime.now(UTC).isoformat(), 'selected': config['seeds'], 'selection': config['selection'], 'identityOverlap': False})
    try:
        raw = transport.get('https://arxiv.org/robots.txt', 64*1024); (output/'robots.txt').write_bytes(raw)
        robots = RobotFileParser(); robots.parse(raw.decode().splitlines()); delay = max(config['crawlDelaySeconds'], robots.crawl_delay(transport.AGENT) or 0)
        if any(not robots.can_fetch(transport.AGENT, 'https://arxiv.org/abs/'+r['arxivId']) for r in config['seeds']): raise ValueError('Robots prohibits sources')
        c.write_json(output/'policy.json', {'robotsSha256': c.file_sha256(output/'robots.txt'), 'crawlDelaySeconds': delay, 'checkedAtUTC': datetime.now(UTC).isoformat(), 'source': 'official HTML abstracts, no PDF'})
        tokenizer = relation.prepare_tokenizer(c.ROOT/'kg_datasets/models/scibert_24f92d32'); refs = []; requests = []; last = time.monotonic()
        for i, seed in enumerate(config['seeds'], 1):
            time.sleep(max(0, delay-(time.monotonic()-last))); last = time.monotonic(); url = 'https://arxiv.org/abs/'+seed['arxivId']
            request = seed | {'url': url, 'startedAtUTC': datetime.now(UTC).isoformat()}
            try:
                payload = transport.get(url, 1024*1024); filename = f'page_{i:03d}.html'; (output/filename).write_bytes(payload)
                title, text = parse_page(payload, seed); tokens = len(tokenizer(text, truncation=False)['input_ids']); digest = hashlib.sha256(text.encode()).hexdigest()
                if title_key(title) != title_key(seed['title']) or tokens > 512: raise ValueError('Source title mismatch or overlength; no truncation')
                refs.append({'sampleId': 'sample-'+c.canonical_sha256(['whole_abstract', seed['arxivId'], digest])[:20], 'publicationId': 'arxiv:'+seed['arxivId'], 'arxivId': seed['arxivId'], 'referenceTitle': title, 'groupId': 'abstract-paper-'+seed['arxivId'], 'split': 'train', 'textKind': 'abstract', 'text': text, 'textSha256': digest, 'sourceURL': url, 'sourceOrigin': 'targeted_boundary_train_only', 'tokens': tokens})
                request.update(status='completed', tokens=tokens, rawResponseFile=filename, rawResponseSha256=c.file_sha256(output/filename))
            except Exception as error: request.update(status='failed_no_synthetic_fallback', errorType=type(error).__name__, error=str(error))
            requests.append(request); c.write_json(output/'requests.json', requests); c.write_jsonl(output/'train_references.jsonl', refs)
            print({'requested': i, 'usable': len(refs)}, flush=True)
        if any(c.file_sha256(p) != sha for p, sha in hashes.items()): raise ValueError('Collection source drift')
        c.write_json(output/'summary.json', {'requested': 8, 'usable': len(refs), 'status': 'completed' if len(refs) == 8 else 'partial', 'testAccessed': False, 'trainingExecuted': False})
        seal(output, paths)
    except Exception as error:
        c.write_json(output/'failure.json', {'status': 'failed_no_synthetic_fallback', 'error': str(error)}); raise


def snapshot(reviewed, output):
    fresh(output); config, base = locked(); manifest = g.verified_files(reviewed)
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Reviewed source drift')
    refs = c.read_jsonl(reviewed/'references.jsonl'); receipts = c.read_jsonl(reviewed/'reviewed_receipts.jsonl'); new = c.read_jsonl(reviewed/'ner_train_candidates.jsonl')
    if not refs or len(refs) != len(receipts) or {r['arxivId'] for r in refs} != {r['arxivId'] for r in config['seeds']} or any(r['split'] != 'train' or c.validate_receipt(a, r) or a['review'] is None for r, a in zip(refs, receipts)): raise ValueError('Incomplete new training references')
    if any(p['label'] != 'UNRESOLVED' for a in receipts for p in a['annotation']['relations']): raise ValueError('NER-only experiment cannot add known RE labels')
    old = c.read_jsonl(base/'ner_train.jsonl'); combined = old+new
    if len(old) != 58 or len({r['sampleId'] for r in combined}) != len(combined) or len({r['groupId'] for r in combined}) != len(combined): raise ValueError('Training identity overlap')
    tokenizer = relation.prepare_tokenizer(c.ROOT/'kg_datasets/models/scibert_24f92d32')
    for row in combined:
        encoded = ner.encode_row(tokenizer, row, 512); offsets = encoded['offsets']; labels = encoded['features']['labels']
        decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else t for o, t in zip(offsets, labels)], offsets, row['text'])
        if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]: raise ValueError('BIO round-trip failed')
    paths = inputs()+[reviewed/'manifest.json']; hashes = {p: c.file_sha256(p) for p in paths}; output.mkdir(parents=True)
    for p in base.iterdir():
        if p.is_file() and p.name != 'manifest.json': shutil.copy2(p, output/p.name)
    # Only new NER rows are appended; all original RE and dev files stay byte-identical.
    c.write_jsonl(output/'ner_train.jsonl', combined); c.write_jsonl(output/'additional_references.jsonl', refs); c.write_jsonl(output/'additional_receipts.jsonl', receipts)
    preserved = [p for p in base.iterdir() if p.is_file() and ('dev' in p.stem or p.name.startswith(('relation_', 'full_relation_')))]
    if any(c.file_sha256(p) != c.file_sha256(output/p.name) for p in preserved) or any(c.file_sha256(p) != sha for p, sha in hashes.items()): raise ValueError('Frozen data drift')
    c.write_json(output/'boundary_expansion_summary.json', {'NERtrain': len(combined), 'originalNER': 58, 'addedNER': len(new), 'newNERExcluded': len(refs)-len(new), 'entitySupport': dict(Counter(e['label'] for r in combined for e in r['entities'])), 'knownRETrainUnchanged': 271, 'preservedDevAndREFiles': len(preserved), 'trainingExecuted': False, 'testAccessed': False, 'qualityPromotionPassed': False, 'independentHumanGold': False})
    seal(output, paths); print(read(output/'boundary_expansion_summary.json'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('preflight', 'collect', 'snapshot')); parser.add_argument('--reviewed', type=Path); parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'preflight': print({'seeds': len(locked()[0]['seeds']), 'identityOverlap': False, 'testContentAccessed': False})
    elif args.output is None: parser.error('New output required')
    elif args.action == 'collect': collect(args.output.resolve())
    elif args.reviewed is None: parser.error('Reviewed annotations required')
    else: snapshot(args.reviewed.resolve(), args.output.resolve())
