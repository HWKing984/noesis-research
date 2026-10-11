"""Apply explicit, source-read AI entity decisions; never train or label unknowns negative."""
import argparse
import copy
import csv
import hashlib
import html
import itertools
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, UTC
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / 'annotations/course_v2/train43_entity_review_20261011.json'
PENDING = ROOT / 'kg_datasets/dblp/course_v2_train65_workset_20261011/pending43_sources.jsonl'
DEFAULT_OUTPUT = ROOT / 'kg_datasets/dblp/course_v2_train43_entity_review_20261011'
LABELS = {'METHOD', 'TASK', 'DATASET'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_lines(data):
    return [json.loads(line) for line in data.decode('utf-8-sig').splitlines() if line.strip()]


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def jsonl_bytes(rows):
    return ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows).encode('utf-8')


def anchor(e):
    return e['start'], e['end'], e['text'], e['label']


def validate_document(row):
    text = row['text']
    if digest(text.encode('utf-8')) != row['textSha256']:
        raise ValueError('Source hash mismatch: ' + row['arxivId'])
    ids = set()
    end = -1
    for e in sorted(row['entities'], key=lambda e: e['start']):
        if (e['entityId'] in ids or e['label'] not in LABELS
                or not 0 <= e['start'] < e['end'] <= len(text)
                or text[e['start']:e['end']] != e['text'] or e['start'] < end):
            raise ValueError('Invalid entity: ' + row['arxivId'] + ':' + e['entityId'])
        ids.add(e['entityId'])
        end = e['end']


def contained_span(text, literal, old):
    # A boundary edit must contain the original mention or lie within it.
    hits = [m for m in re.finditer(re.escape(literal), text)
            if (m.start() <= old['start'] and old['end'] <= m.end())
            or (old['start'] <= m.start() and m.end() <= old['end'])]
    if len(hits) != 1:
        raise ValueError('Boundary edit is not uniquely anchored: ' + literal)
    return hits[0].span()


def apply_decision(row, decision):
    row = copy.deepcopy(row)
    original = {e['entityId']: copy.deepcopy(e) for e in row['entities']}
    current = copy.deepcopy(original)
    events = []
    for eid in decision.get('remove', []):
        e = current.pop(eid)
        events.append({'action': 'REMOVE_ENTITY', 'before': e, 'after': None})
    for item in decision.get('replace', []):
        before = copy.deepcopy(current[item['id']])
        start, end = contained_span(row['text'], item['text'], before)
        after = {**before, 'start': start, 'end': end, 'text': item['text'],
                 'label': item.get('label', before['label']),
                 'provenance': 'same_session_ai_full_source_review'}
        if anchor(before) == anchor(after):
            raise ValueError('No-op boundary decision: ' + item['id'])
        current[item['id']] = after
        events.append({'action': 'REVISE_ENTITY', 'before': before, 'after': after})
    next_id = max(int(eid[1:]) for eid in original) + 1 if original else 1
    urls = [m.span() for m in re.finditer(r'https?://\S+', row['text'])]
    proposed = []
    for label, literals in decision.get('add', {}).items():
        if label not in LABELS or len(literals) != len(set(literals)):
            raise ValueError('Invalid literal declarations')
        for literal in literals:
            hits = list(re.finditer(r'(?<!\w)(?<!\w-)' + re.escape(literal) + r'(?!\w|-\w)', row['text']))
            if not hits:
                raise ValueError(row['arxivId'] + ': literal not found: ' + literal)
            for m in hits:
                proposed.append({'start': m.start(), 'end': m.end(), 'text': m.group(), 'label': label})
    # Only the explicit per-document additions use longest-span priority.
    skipped = []
    for e in sorted(proposed, key=lambda e: (-(e['end'] - e['start']), e['start'])):
        overlapping = [x for x in current.values() if e['start'] < x['end'] and x['start'] < e['end']]
        if overlapping or any(e['start'] < b and a < e['end'] for a, b in urls):
            skipped.append({**e, 'reason': 'flat_scope_existing_or_longer_entity_or_URL',
                            'overlapEntityIds': [x['entityId'] for x in overlapping]})
            continue
        e = {**e, 'entityId': f'e{next_id}', 'provenance': 'same_session_ai_full_source_review'}
        next_id += 1
        current[e['entityId']] = e
        events.append({'action': 'ADD_ENTITY', 'before': None, 'after': e})
    row['entities'] = sorted(current.values(), key=lambda e: e['start'])
    row.update({'annotationStatus': 'v2_ai_full_abstract_entity_review_candidate',
                'entityReviewStatus': 'same_session_ai_source_read_completed',
                'entityCompletenessClaim': 'candidate_complete_under_declared_flat_scope',
                'referenceComplete': False, 'relationReferenceComplete': False,
                'independentHumanGold': False, 'trainingAuthorized': False,
                'entityReviewReason': decision['reason']})
    validate_document(row)
    review = {'arxivId': row['arxivId'], 'sampleId': row['sampleId'],
              'textSha256': row['textSha256'], 'sourceURL': row.get('sourceURL'), 'split': 'train',
              'beforeEntities': len(original), 'afterEntities': len(current),
              'reviewStatus': 'same_session_ai_source_read_completed',
              'candidateCompletenessClaim': True, 'independentHumanGold': False,
              'trainingAuthorized': False, 'reason': decision['reason'],
              'changes': events, 'flatScopeSkippedAdditions': skipped}
    return row, review


def relation_key(p):
    return p['arxivId'], p['head']['entityId'], p['tail']['entityId']


def render_review(before, after, reviews, summary):
    escape = html.escape
    cards = []
    for review in reviews:
        aid = review['arxivId']
        row = after[aid]
        parts = []
        cursor = 0
        for e in row['entities']:
            parts += [escape(row['text'][cursor:e['start']]),
                      '<mark class="' + e['label'] + '" title="' + escape(f"{e['entityId']} {e['label']} {e['start']}:{e['end']}") + '">' + escape(e['text']) + '</mark>']
            cursor = e['end']
        parts.append(escape(row['text'][cursor:]))
        changes = []
        for change in review['changes']:
            old, new = change['before'], change['after']
            fmt = lambda e: '—' if e is None else f"{e['entityId']} {e['label']} [{e['start']},{e['end']}) {e['text']}"
            changes.append('<li>' + escape(change['action'] + ': ' + fmt(old) + ' → ' + fmt(new)) + '</li>')
        cards.append('<article><h2>' + escape(aid) + f" · {review['beforeEntities']} → {review['afterEntities']} entities</h2>"
                     + '<p class="reason">' + escape(review['reason']) + '</p><div class="abstract">' + ''.join(parts)
                     + '</div><details><summary>实际修改 ' + str(len(changes)) + '</summary><ul>' + ''.join(changes)
                     + '</ul></details><details><summary>原标注列表</summary><pre>'
                     + escape('\n'.join(f"{e['entityId']} {e['label']} {e['start']}:{e['end']} {e['text']}" for e in before[aid]['entities']))
                     + '</pre></details></article>')
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>V2 train43 实体源文复核</title>'
            '<style>body{font:16px/1.7 system-ui;max-width:1200px;margin:30px auto;padding:0 24px;color:#17212f;background:#f4f7fa}'
            'article{background:white;border:1px solid #d8e1eb;border-radius:12px;padding:22px;margin:24px 0}'
            '.abstract{white-space:pre-wrap;line-height:2.1}mark{padding:2px 3px;border-radius:4px}'
            '.METHOD{background:#cae8ff}.TASK{background:#dcf5d9}.DATASET{background:#ffe4bd}'
            '.reason{color:#45586f}pre{white-space:pre-wrap}summary{cursor:pointer}li{margin:10px 0}'
            '.warning{border-left:5px solid #d88900;background:#fff3dd;padding:14px}</style>'
            '<h1>43篇训练摘要 · AI逐篇实体复核候选</h1><p class="warning">这是同会话AI源文复核，不是独立人工金标准。'
            '未训练、未计算新F1；实体修改影响的旧正关系暂缓，未知关系不作负例。dev/test未改。</p>'
            '<p>METHOD 蓝色 · TASK 绿色 · DATASET 橙色；悬停查看 ID 与字符偏移。</p><pre>'
            + escape(json.dumps(summary, ensure_ascii=False, indent=2)) + '</pre>' + ''.join(cards) + '</html>').encode('utf-8')


def main(output):
    if output.exists():
        raise FileExistsError('Preserve existing work: ' + str(output))
    decisions_data = DECISIONS.read_bytes()
    decisions = json.loads(decisions_data)
    input_zip = Path(decisions['inputZip'])
    with zipfile.ZipFile(input_zip) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP CRC failure')
        files = {}
        for n in z.namelist():
            if n.endswith('/'):
                continue
            if '..' in n.replace('\\', '/').split('/') or n.startswith(('/', '\\')) or ':' in n:
                raise ValueError('Unsafe ZIP member')
            key = n.split('/')[-1]
            if key in files:
                raise ValueError('Duplicate ZIP basename')
            files[key] = z.read(n)
    parent_manifest = json.loads(files['manifest.json'])
    if any(digest(files[n]) != h for n, h in parent_manifest['outputs'].items()):
        raise ValueError('Parent manifest hash mismatch')
    base = parse_lines(files['train65_ner_revised.jsonl'])
    positives = parse_lines(files['train65_positive_revised.jsonl'])
    by_id = {r['arxivId']: r for r in base}
    pending_bytes = PENDING.read_bytes()
    pending = parse_lines(pending_bytes)
    wanted = {r['arxivId'] for r in pending}
    dc = {d['arxivId']: d for d in decisions['documents']}
    if len(base) != 65 or len(by_id) != 65 or len(wanted) != 43 or len(dc) != 43 or set(dc) != wanted:
        raise ValueError('Expected exactly the existing 43 pending train papers')
    for r in pending:
        if any(r[k] != by_id[r['arxivId']][k] for k in ('text', 'textSha256', 'sampleId', 'groupId', 'split')):
            raise ValueError('Pending-source binding mismatch')
    for r in base:
        validate_document(r)
        if r['split'] != 'train':
            raise ValueError('Non-train input')
    revised = copy.deepcopy(by_id)
    reviews = []
    for r in base:
        if r['arxivId'] in dc:
            revised[r['arxivId']], review = apply_decision(r, dc[r['arxivId']])
            reviews.append(review)
    untouched = set(by_id) - wanted
    if any(revised[aid] != by_id[aid] for aid in untouched):
        raise ValueError('Other 22 documents changed')
    emaps = {aid: {e['entityId']: e for e in r['entities']} for aid, r in revised.items()}
    retained, deferred, rebindings = [], [], []
    approved = {(x['arxivId'], x['headId'], x['tailId']): x for x in decisions.get('relationRebindings', [])}
    consumed = set()
    for p in positives:
        emap = emaps[p['arxivId']]
        touched = [side for side in ('head', 'tail')
                   if p[side]['entityId'] not in emap or anchor(p[side]) != anchor(emap[p[side]['entityId']])]
        if not touched:
            retained.append(p)
        elif relation_key(p) in approved:
            key = relation_key(p)
            decision = approved[key]
            q = copy.deepcopy(p)
            q['head'], q['tail'] = copy.deepcopy(emap[p['head']['entityId']]), copy.deepcopy(emap[p['tail']['entityId']])
            if q['head']['label'] != 'METHOD' or q['tail']['label'] != {'USED_FOR': 'TASK', 'EVALUATED_ON': 'DATASET'}[decision['label']]:
                raise ValueError('Invalid explicitly reviewed relation rebinding')
            if decision['label'] != p['label']:
                raise ValueError('Rebinding must not silently change relation label')
            q['reason'] = decision['reason']
            q['labelSource'] = 'same_session_ai_explicit_endpoint_readjudication'
            q['reviewPriority'] = 'entity_edit_source_readjudicated'
            q['warning'] = 'Explicitly re-read after entity boundary edit; AI weak label, not independent gold.'
            retained.append(q)
            rebindings.append({'action': 'SOURCE_READJUDICATE_RELATION_ENDPOINT', 'arxivId': p['arxivId'],
                               'before': p, 'after': q, 'reason': decision['reason'], 'trainingAuthorized': False})
            consumed.add(key)
        else:
            deferred.append({'arxivId': p['arxivId'], 'action': 'DEFER_POSITIVE_AFTER_ENTITY_EDIT',
                             'touchedEndpoints': touched, 'originalPositive': p,
                             'currentEndpoints': {side: emap.get(p[side]['entityId']) for side in ('head', 'tail')},
                             'reason': 'Entity boundary/type/removal changed; re-adjudicate this relation against the source, never auto-inherit or negate.',
                             'trainingAuthorized': False})
    if consumed != set(approved):
        raise ValueError('Rebinding decisions must refer exactly to changed existing positives')
    positive_map = {relation_key(p): p for p in retained}
    if len(positive_map) != len(retained):
        raise ValueError('Duplicate positives')
    pairs = []
    for row in revised.values():
        for h, t in itertools.product(row['entities'], repeat=2):
            if h['label'] != 'METHOD' or t['label'] not in {'TASK', 'DATASET'}:
                continue
            key = row['arxivId'], h['entityId'], t['entityId']
            pos = positive_map.get(key)
            pairs.append({'arxivId': row['arxivId'], 'sampleId': row['sampleId'], 'groupId': row['groupId'],
                          'split': 'train', 'headId': h['entityId'], 'tailId': t['entityId'],
                          'headText': h['text'], 'tailText': t['text'],
                          'label': pos['label'] if pos else 'UNRESOLVED',
                          'labelSource': 'ai_working_candidate', 'trainingAuthorized': False,
                          'referenceComplete': False})
    entities = [e for r in revised.values() for e in r['entities']]
    changes = [dict(event, arxivId=rev['arxivId'], textSha256=rev['textSha256'],
                    reason=rev['reason'], labelSource='same_session_ai_source_review_not_gold', trainingAuthorized=False)
               for rev in reviews for event in rev['changes']]
    summary = {'reviewedTrainDocuments': 43, 'previous22Unchanged': True,
               'fullTrainDocuments': len(revised), 'oldEntities': sum(len(r['entities']) for r in base),
               'newEntities': len(entities), 'entityLabels': dict(Counter(e['label'] for e in entities)),
               'changes': dict(Counter(c['action'] for c in changes)),
               'documentsWithEntityChanges': sum(bool(r['changes']) for r in reviews),
               'parentPositiveCandidates': len(positives), 'retainedPositiveCandidates': len(retained),
               'deferredPositiveCandidates': len(deferred), 'newPositiveRelations': 0,
               'sourceReadjudicatedRebindings': len(rebindings),
               'legalCandidatePairs': len(pairs), 'pairLabels': dict(Counter(p['label'] for p in pairs)),
               'confirmedNegatives': 0, 'independentHumanGold': False, 'trainingAuthorized': False,
               'formalF1Authorized': False, 'trainingExecuted': False, 'inferenceExecuted': False,
               'devModified': False, 'testContentRead': False, 'productionModified': False,
               'remainingWork': ['Re-adjudicate deferred and new train relation pairs',
                                 'Complete fixed dev20 reference adjudication',
                                 'Resolve ordinary negative supervision without relabeling unknowns',
                                 'Authorize a bounded experiment separately; final test stays sealed']}
    payload = {'train65_ner_reviewed_candidates.jsonl': jsonl_bytes(list(revised.values())),
               'train65_positive_retained.jsonl': jsonl_bytes(retained),
               'train65_relations_deferred.jsonl': jsonl_bytes(deferred),
               'relation_rebinding_ledger.jsonl': jsonl_bytes(rebindings),
               'train65_all_pairs_rebuilt.jsonl': jsonl_bytes(pairs),
               'train43_entity_reviews.jsonl': jsonl_bytes(reviews),
               'entity_change_ledger.jsonl': jsonl_bytes(changes),
               'summary.json': json_bytes(summary), 'review_decisions.json': decisions_data,
               'train43_entity_review.html': render_review(by_id, revised, reviews, summary)}
    # Reuse the existing BIO decoder and marker encoder; no network, weights or fitting.
    sys.path.insert(0, str(ROOT / 'scripts'))
    import train_course_ner as ner
    import train_course_relation as relation
    tokenizer_path = ROOT / 'kg_datasets/models/scibert_24f92d32'
    tokenizer = relation.prepare_tokenizer(tokenizer_path)
    max_ner = max_re = 0
    for row in revised.values():
        record = ner.encode_row(tokenizer, row, 512)
        # -100 marks ignored special tokens in training, not a prediction class.
        # Preserve all offsets and use O only at those ignored positions.
        decoded = ner.decode_bio([0 if x == -100 else x for x in record['features']['labels']], record['offsets'], row['text'])
        if decoded['invalidTransitions'] or [anchor(e) for e in decoded['entities']] != [anchor(e) for e in row['entities']]:
            raise ValueError('BIO round-trip failed: ' + row['arxivId'])
        max_ner = max(max_ner, len(record['features']['input_ids']))
    for p in retained:
        encoded = relation.encode_pair(tokenizer, p, 512)
        max_re = max(max_re, len(encoded['features']['input_ids']))
    encoding = {'kind': 'real_local_tokenization_not_model_evaluation',
                'NERDocumentsPassed': len(revised), 'relationPairsPassed': len(retained),
                'strictBIORoundtripPassed': True, 'entityMarkersPassed': True,
                'maxNERTokens': max_ner, 'maxRETokens': max_re, 'tokenLimit': 512, 'truncation': False,
                'trainingExecuted': False, 'inferenceExecuted': False, 'testContentRead': False}
    payload['encoding_checks.json'] = json_bytes(encoding)
    output.mkdir(parents=True)
    for name, data in payload.items():
        (output / name).write_bytes(data)
    with (output / 'train43_entity_review.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['arxivId', 'entityId', 'label', 'start', 'end', 'text', 'changed', 'reviewReason'])
        writer.writeheader()
        for aid in dc:
            oldmap = {e['entityId']: e for e in by_id[aid]['entities']}
            for e in revised[aid]['entities']:
                writer.writerow({'arxivId': aid, **{k: e[k] for k in ('entityId', 'label', 'start', 'end', 'text')},
                                 'changed': e['entityId'] not in oldmap or anchor(oldmap[e['entityId']]) != anchor(e),
                                 'reviewReason': dc[aid]['reason']})
    manifest = {'kind': 'same_session_ai_entity_revision_not_training_authorization',
                'createdAt': datetime.now(UTC).isoformat(),
                'inputs': {str(input_zip): digest(input_zip.read_bytes()), str(DECISIONS): digest(decisions_data),
                           str(PENDING): digest(pending_bytes), str(Path(__file__)): digest(Path(__file__).read_bytes())},
                'parentMemberSha256': {name: digest(files[name]) for name in
                                       ('train65_ner_revised.jsonl', 'train65_positive_revised.jsonl', 'train65_all_pairs_rebuilt.jsonl')},
                'filesSha256': {p.name: digest(p.read_bytes()) for p in output.iterdir() if p.is_file()},
                'trainingAuthorized': False, 'independentHumanGold': False, 'testContentRead': False}
    (output / 'manifest.json').write_bytes(json_bytes(manifest))
    bundle = ROOT / 'outputs' / (output.name + '.zip')
    if bundle.exists():
        raise FileExistsError('Preserve existing delivery ZIP')
    bundle.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(bundle, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(output.iterdir()):
            z.write(p, output.name + '/' + p.name)
    print(json.dumps({'summary': summary, 'bundle': str(bundle)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    main(parser.parse_args().output.resolve())
