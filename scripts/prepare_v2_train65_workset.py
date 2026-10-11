"""Export existing train sources and explicit AI decisions; encode only, never fit.

The sealed twelve-paper training roster is not changed. This is a separate
65-paper annotation workset, not a formal three-class training authorization.
External dev drafts are checked structurally, never routed into train features.
"""
import argparse
import csv
import hashlib
import html
import io
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_weak as c
import train_course_ner as ner
import train_course_relation as relation
from compile_abstract_annotations import annotate
from course_v2_identity import canonical_arxiv

BASE = ROOT / 'kg_datasets/dblp/course_diverse_train_roles_20261010_56_final'
V2 = ROOT / 'kg_datasets/dblp/course_v2_admission_20261010'
SAMPLING = ROOT / 'kg_datasets/dblp/course_v2_sampling_20261011_roster_locked_v2'
DEV = ROOT / 'kg_datasets/dblp/course_v2_dev_sources_20261011'
DECISIONS = ROOT / 'annotations/course_v2/train65_batch10_20261011.json'
DEFAULT_OUTPUT = ROOT / 'kg_datasets/dblp/course_v2_train65_workset_20261011'
EXTERNAL = Path('D:/Users/Y7000P/Downloads/v2_dev20_ai_extraction_20261011.zip')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def bound_file(folder, name):
    path = folder / name
    expected = read(folder / 'manifest.json')['filesSha256'].get(name)
    if expected is None or c.file_sha256(path) != expected:
        raise ValueError('Sealed input missing or changed: ' + str(path))
    return path


def validate_entities(row):
    text = row['text']
    if sha_bytes(text.encode('utf-8')) != row['textSha256']:
        raise ValueError('Text SHA mismatch')
    previous = -1
    ids = set()
    for e in sorted(row['entities'], key=lambda e: e['start']):
        if (e['label'] not in c.CONFIG['entityLabels'] or not 0 <= e['start'] < e['end'] <= len(text)
                or text[e['start']:e['end']] != e['text'] or e['start'] < previous
                or e['entityId'] in ids):
            raise ValueError('Invalid entity span, type, overlap or ID')
        previous = e['end']
        ids.add(e['entityId'])


def dev_intake(output):
    refs = rows(bound_file(DEV, 'references.jsonl'))
    fixed = {canonical_arxiv(r['arxivId']): r for r in refs}
    with zipfile.ZipFile(EXTERNAL) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(
            Path(n).is_absolute() or '..' in Path(n.replace('\\', '/')).parts or ':' in n
            for n in names
        ):
            raise ValueError('Unsafe archive member names')
        if any(m.file_size > 2_000_000 for m in archive.infolist()):
            raise ValueError('Unexpected large external draft')
        parse = lambda name: [json.loads(line) for line in archive.read(name).decode('utf-8-sig').splitlines() if line.strip()]
        docs = parse('dev20_ner_ai_draft.jsonl')
        pairs = parse('dev20_re_positive_ai_draft.jsonl')
        unresolved = parse('dev20_relation_unresolved_examples.jsonl')
        if len(docs) != 20 or {d['arxivId'] for d in docs} != set(fixed):
            raise ValueError('Fixed dev roster mismatch')
        by_id = {d['arxivId']: d for d in docs}
        if len(by_id) != 20:
            raise ValueError('Duplicate dev document')
        for d in docs:
            f = fixed[d['arxivId']]
            for key in ('publicationId', 'groupId', 'text', 'textSha256'):
                if d[key] != f[key]:
                    raise ValueError('External dev changed source identity or text')
            if (d['split'] != 'dev' or d['textKind'] != 'abstract' or d['trainingAuthorized'] is not False
                    or d['evaluationAuthorized'] is not False or d['referenceComplete'] is not False
                    or d['independentHumanGold'] is not False):
                raise ValueError('External dev overstates authorization')
            validate_entities(d)
        for p in pairs + unresolved:
            d = by_id[p['arxivId']]
            emap = {e['entityId']: e for e in d['entities']}
            if any(p[k] != d[k] for k in ('publicationId', 'groupId', 'textSha256', 'split')):
                raise ValueError('Dev relation identity mismatch')
            if any(p[r] != emap.get(p[r]['entityId']) for r in ('head', 'tail')):
                raise ValueError('Dev relation endpoint mismatch')
            if p['head']['label'] != 'METHOD' or p['tail']['label'] not in ('TASK', 'DATASET'):
                raise ValueError('Invalid dev relation direction')
            if p['label'] not in ('UNRESOLVED', {'TASK': 'USED_FOR', 'DATASET': 'EVALUATED_ON'}[p['tail']['label']]):
                raise ValueError('Dev label/type mismatch')
            ev = p['evidence']
            if not 0 <= ev['start'] < ev['end'] <= len(d['text']) or d['text'][ev['start']:ev['end']] != ev['text']:
                raise ValueError('Dev evidence span mismatch')
            if p['trainingAuthorized'] is not False or p['evaluationAuthorized'] is not False:
                raise ValueError('Dev relation authorization mismatch')
        if len({(p['arxivId'], p['head']['entityId'], p['tail']['entityId']) for p in pairs + unresolved}) != len(pairs + unresolved):
            raise ValueError('Duplicate external candidate')
        artifact_matches = {}
        for name in ('dev20_relation_review.csv', 'dev20_annotation_review.html'):
            upload = EXTERNAL.parent / name
            artifact_matches[name] = upload.read_bytes() == archive.read(name)
            if not artifact_matches[name]:
                raise ValueError('Standalone review file differs from archive')
        folder = output / 'dev_intake'
        folder.mkdir()
        # Preserve bytes; do not run either executable script from the upload.
        for name in ('dev20_ner_ai_draft.jsonl', 'dev20_re_positive_ai_draft.jsonl',
                     'dev20_relation_unresolved_examples.jsonl', 'summary.json', 'annotation_warnings.json',
                     'dev20_relation_review.csv', 'dev20_annotation_review.html'):
            (folder / name).write_bytes(archive.read(name))
    candidate_count = sum(sum(e['label'] == 'METHOD' for e in d['entities'])
                          * sum(e['label'] in ('TASK', 'DATASET') for e in d['entities']) for d in docs)
    report = {'structuralChecksPassed': True, 'documents': len(docs),
              'entityCounts': dict(Counter(e['label'] for d in docs for e in d['entities'])),
              'positiveRelations': dict(Counter(p['label'] for p in pairs)),
              'legalCandidatePairs': candidate_count, 'explicitUnresolvedExamples': len(unresolved),
              'unadjudicatedOrUnresolvedPairs': candidate_count-len(pairs), 'negativeRelations': 0,
              'standaloneArtifactsEqualArchive': artifact_matches, 'externalZipSha256': c.file_sha256(EXTERNAL),
              'sourceJSONLSha256': c.file_sha256(DEV / 'references.jsonl'),
              'semanticReviewExhaustive': False, 'formalF1Authorized': False,
              'devReturnedToTraining': False, 'testContentRead': False, 'externalScriptsExecuted': False}
    c.write_json(folder / 'intake_checks.json', report)
    return report


def compile_new(ref, decision):
    annotation = annotate(decision, ref)
    base = {k: ref[k] for k in ('sampleId', 'publicationId', 'groupId', 'arxivId', 'split', 'textKind', 'text', 'textSha256', 'sourceURL')}
    base.update(labelSource='assistant_ai_weak_labels', independentHumanGold=False,
                trainingAuthorized=False, annotationStatus='ai_self_reviewed_ner_candidate',
                referenceComplete=True, relationReferenceComplete=False,
                decisionFileSha256=c.file_sha256(DECISIONS), notes=decision['notes'])
    document = base | {'entities': annotation['entities']}
    validate_entities(document)
    decisions = decision['positives']
    entities = {e['entityId']: e for e in annotation['entities']}
    ledger, positive = [], []
    for p in annotation['relations']:
        item = None
        if p['label'] != 'UNRESOLVED':
            matching = [d for d in decisions if d['head'] == entities[p['head']]['text']
                        and d['tail'] == entities[p['tail']]['text'] and d['evidence'] == p['evidence']['text']]
            if len(matching) != 1:
                raise ValueError('Ambiguous explicit semantic decision')
            item = matching[0]
        entry = base | {'head': entities[p['head']], 'tail': entities[p['tail']],
                        'label': p['label'], 'evidence': p['evidence'], 'referenceComplete': False,
                        'reason': item['reason'] if item else p['reason'],
                        'annotationStatus': 'ai_positive_candidate' if item else 'unresolved',
                        'taskRole': item['taskRole'] if item else 'unresolved',
                        'supportGroup': (ref['arxivId'] + ':' + item['supportGroup']) if item else None}
        if item and 'methodScope' in item:
            entry['methodScope'] = item['methodScope']
        ledger.append(entry)
        if item:
            positive.append(entry)
    return document, ledger, positive


def build(output):
    if output.exists():
        raise FileExistsError('Preserve existing workset; choose a new output path')
    used = [bound_file(BASE, n) for n in ('references.jsonl', 'ner_train_frozen.jsonl', 'reviewed_receipts.jsonl',
                                       'relation_train.jsonl', 'excluded_ner_train.jsonl')]
    used += [bound_file(V2, n) for n in ('references.jsonl', 'ner_candidates.jsonl', 're_candidates.jsonl', 'relation_ledger.jsonl')]
    used += [bound_file(DEV, 'references.jsonl'), SAMPLING / 'selected_members.json',
             SAMPLING / 'training_roster_lock.json', DECISIONS, EXTERNAL,
             ROOT / 'resources/course_v2_supervision_protocol_v1.json', ROOT / 'docs/course_v2_task_scope_v1.md',
             ROOT / 'resources/course_graph_runtime.json', Path(__file__)]
    # Validate the selected metadata file against its sealed sampling manifest.
    bound_file(SAMPLING, 'selected_members.json')
    before = {str(p): c.file_sha256(p) for p in used}
    old_refs = rows(BASE / 'references.jsonl')
    old_ner = rows(BASE / 'ner_train_frozen.jsonl')
    source_by_sample = {r['sampleId']: r for r in old_refs}
    refs = [source_by_sample[d['sampleId']] for d in old_ner]
    by_arxiv = {canonical_arxiv(r['arxivId']): r for r in refs}
    eval_members = read(SAMPLING / 'selected_members.json')  # Metadata only, including test IDs, never test text.
    if len(old_refs) != 70 or len(refs) != 65 or len(by_arxiv) != 65:
        raise ValueError('Expected immutable old 70-source / 65-NER inventory')
    if set(by_arxiv) & {canonical_arxiv(e['arxivId']) for e in eval_members}:
        raise ValueError('Training workset overlaps locked evaluation identities')
    dev_refs = rows(DEV / 'references.jsonl')
    if {r['textSha256'] for r in refs} & {r['textSha256'] for r in dev_refs}:
        raise ValueError('Train/dev exact text overlap')
    for r in refs:
        if r['split'] != 'train' or r['textKind'] != 'abstract' or sha_bytes(r['text'].encode('utf-8')) != r['textSha256']:
            raise ValueError('Bad train reference')
        if canonical_arxiv(r['sourceURL']) != r['arxivId']:
            raise ValueError('Train source URL disagrees with canonical identity')
    revised_refs = rows(V2 / 'references.jsonl')
    for r in revised_refs:
        if by_arxiv[r['arxivId']]['textSha256'] != r['textSha256'] or by_arxiv[r['arxivId']]['text'] != r['text']:
            raise ValueError('Revised twelve is not an exact original-source match')
    decision = read(DECISIONS)
    new_ids = [d['arxivId'] for d in decision['documents']]
    revised_ids = {r['arxivId'] for r in revised_refs}
    if len(new_ids) != 10 or len(set(new_ids)) != 10 or not set(new_ids) <= set(by_arxiv)-revised_ids:
        raise ValueError('Batch10 is not ten unique previously unreviewed train papers')
    new_ner, new_ledger, new_positive = [], [], []
    for d in decision['documents']:
        n, ledger, positive = compile_new(by_arxiv[d['arxivId']], d)
        new_ner.append(n); new_ledger.extend(ledger); new_positive.extend(positive)
    ner_candidates = rows(V2 / 'ner_candidates.jsonl') + new_ner
    positives = rows(V2 / 're_candidates.jsonl') + new_positive
    for d in ner_candidates:
        validate_entities(d)
        if d['split'] != 'train' or d['trainingAuthorized'] is not False:
            raise ValueError('Candidate authorization drift')
    tokenizer = relation.prepare_tokenizer(ROOT / 'kg_datasets/models/scibert_24f92d32')
    ner_encoded, re_encoded, encoding_errors = [], [], []
    for d in ner_candidates:
        try:
            record = ner.encode_row(tokenizer, d, 512)
            decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else v for o, v in zip(record['offsets'], record['features']['labels'])], record['offsets'], d['text'])
            if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in d['entities']]:
                raise ValueError('BIO round-trip mismatch')
            ner_encoded.append(record)
        except ValueError as error:
            encoding_errors.append({'sampleId': d['sampleId'], 'task': 'NER', 'error': str(error)})
    for d in positives:
        try:
            re_encoded.append(relation.encode_pair(tokenizer, d, 512))
        except ValueError as error:
            encoding_errors.append({'sampleId': d['sampleId'], 'task': 'RE', 'error': str(error)})
    output.mkdir(parents=True)
    dev_report = dev_intake(output)
    for name, data in (
        ('train65_sources', refs), ('source70_inventory', old_refs), ('legacy_ner65_unreviewed', old_ner),
        ('legacy_relation_inventory_unreviewed', rows(BASE / 'relation_train.jsonl')),
        ('legacy_receipts70', rows(BASE / 'reviewed_receipts.jsonl')),
        ('quarantine5_sources', [r for r in old_refs if r['sampleId'] not in {d['sampleId'] for d in old_ner}]),
        ('batch10_ner_candidates', new_ner), ('batch10_relation_ledger', new_ledger),
        ('batch10_positive_candidates', new_positive), ('ner22_candidates', ner_candidates),
        ('relation_positive_candidates', positives), ('ner_encoded', ner_encoded), ('relation_encoded', re_encoded),
        ('encoding_exclusions', encoding_errors), ('revised12_relation_ledger', rows(V2 / 'relation_ledger.jsonl'))
    ):
        c.write_jsonl(output / (name + '.jsonl'), data)
    (output / 'batch10_decisions.json').write_bytes(DECISIONS.read_bytes())
    c.write_json(output / 'legacy_quarantine5.json', rows(BASE / 'excluded_ner_train.jsonl'))
    c.write_json(output / 'workset_roster.json', {'kind': 'annotation_workset_not_formal_training_lock',
        'version': 'train65_ai_workset_v1', 'createdAtUTC': datetime.now(UTC).isoformat(),
        'trainingAuthorized': False, 'originalTwelveRosterUnchanged': True,
        'members': [{k: r[k] for k in ('arxivId', 'sampleId', 'publicationId', 'groupId', 'textSha256', 'split')} for r in refs]})
    statuses = {r['arxivId']: ('reused_v2_12' if r['arxivId'] in revised_ids else
                'batch10_ai_self_reviewed_candidate' if r['arxivId'] in new_ids else 'pending_v2_review') for r in refs}
    pending = [r for r in refs if statuses[r['arxivId']] == 'pending_v2_review']
    c.write_jsonl(output / 'pending43_sources.jsonl', pending)
    with (output / 'train65_review.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['arxivId', 'status', 'sourceURL', 'textSha256', 'text'])
        writer.writeheader()
        for r in refs:
            writer.writerow({k: r[k] for k in ('arxivId', 'sourceURL', 'textSha256', 'text')} | {'status': statuses[r['arxivId']]})
    new_by_id = {r['arxivId']: r for r in new_ner}
    sections = []
    for r in refs:
        text = r['text']; row = new_by_id.get(r['arxivId'])
        if row:
            parts = []; last = 0
            for e in row['entities']:
                parts.extend([html.escape(text[last:e['start']]), '<mark title="' + e['label'] + '" class="' + e['label'] + '">' + html.escape(e['text']) + '</mark>'])
                last = e['end']
            parts.append(html.escape(text[last:])); displayed = ''.join(parts)
        else:
            displayed = html.escape(text)
        rels = [p for p in new_positive if p['arxivId'] == r['arxivId']]
        table = ''.join('<tr><td>' + html.escape(p['head']['text']) + '</td><td>' + p['label'] + '</td><td>' + html.escape(p['tail']['text']) + '</td><td>' + html.escape(p['evidence']['text']) + '</td></tr>' for p in rels)
        sections.append('<section><h2>' + r['arxivId'] + ' — ' + statuses[r['arxivId']] + '</h2><a href="' + html.escape(r['sourceURL'], quote=True) + '">原始来源</a><p>' + displayed + '</p>' + ('<table><tr><th>方法</th><th>关系</th><th>目标</th><th>原文证据</th></tr>' + table + '</table>' if table else '') + '</section>')
    (output / 'train65_review.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>V2 train65 实际数据复核</title><style>body{font:16px/1.8 system-ui;margin:30px auto;max-width:1200px;background:#fafafa}section{background:white;padding:24px;margin:20px 0;border:1px solid #ddd}mark{padding:2px}.METHOD{background:#c9e4ff}.TASK{background:#d2efca}.DATASET{background:#ffe3a3}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px;vertical-align:top}</style><h1>V2 train65 原文与首批10篇 AI 补标</h1><p>12篇既有V2修订复用；10篇新增实体补标与正关系候选；43篇待复核。蓝：METHOD，绿：TASK，黄：DATASET。AI弱标签，不是人工金标准；未决不是负例；未训练、未评分。这里只高亮新增10篇，既有12篇详见JSONL。</p>' + ''.join(sections), encoding='utf-8')
    entity_change = []
    old_by_id = {source_by_sample[d['sampleId']]['arxivId']: d for d in old_ner}
    for d in new_ner:
        key = lambda e: (e['start'], e['end'], e['text'], e['label'])
        before_entities = {key(e) for e in old_by_id[d['arxivId']]['entities']}
        after_entities = {key(e) for e in d['entities']}
        entity_change.append({'arxivId': d['arxivId'], 'added': sorted(after_entities-before_entities),
                              'removed': sorted(before_entities-after_entities), 'reason': d['notes']})
    c.write_json(output / 'batch10_entity_changes.json', entity_change)
    evidence_groups = {(p.get('arxivId', canonical_arxiv(p['publicationId'])), p.get('supportGroup')) for p in positives}
    summary = {'version': 'train65_ai_workset_v1', 'sourceDocuments': 70, 'oldNERDocuments': 65,
        'legacyQuarantinedDocuments': 5, 'reusedV2Documents': 12, 'newAIReviewedDocuments': 10,
        'pendingV2Documents': len(pending), 'candidateNERDocuments': len(ner_candidates),
        'newEntitySupport': dict(Counter(e['label'] for d in new_ner for e in d['entities'])),
        'candidateEntitySupport': dict(Counter(e['label'] for d in ner_candidates for e in d['entities'])),
        'newRelationSupport': dict(Counter(p['label'] for p in new_positive)),
        'candidateRelationSupport': dict(Counter(p['label'] for p in positives)),
        'positiveEvidenceGroupsDescriptiveOnly': len(evidence_groups),
        'newUnresolvedPairs': sum(p['label'] == 'UNRESOLVED' for p in new_ledger),
        'newLegalCandidatePairs': len(new_ledger), 'encodedNERDocuments': len(ner_encoded),
        'encodedPositiveRelationPairs': len(re_encoded), 'encodingExclusions': len(encoding_errors),
        'ordinaryThreeClassREReady': False, 'negativeRelations': 0,
        'devStructuralIntake': dev_report, 'trainingAuthorized': False,
        'formalF1Authorized': False, 'testContentRead': False, 'trainingExecuted': False,
        'modelPromoted': False, 'independentHumanGold': False,
        'sourceIdentityOverlapWithFixedDevTest': 0, 'exactTrainDevTextOverlap': 0,
        'originalTwelveRosterUnchanged': True, 'sourceFilesUnchanged': True,
        'notice': 'Executable tokenizer inputs only, not fitting authorization. New labels are AI self-reviewed candidates; unresolved pairs are masked. No independent near-duplicate certification or exhaustive relation truth is claimed.'}
    if any(c.file_sha256(Path(path)) != sha for path, sha in before.items()):
        raise ValueError('Source or production configuration changed during export')
    c.write_json(output / 'summary.json', summary)
    c.write_json(output / 'encoding_contract.json', {'kind': 'model_input_compatibility_not_training_authorization',
        'input': 'whole_original_abstract', 'maxTokens': 512, 'truncation': False,
        'tokenizer': 'kg_datasets/models/scibert_24f92d32', 'bioLabels': c.CONFIG['bioLabels'],
        'relationLabels': relation.LABELS, 'NERHelper': 'scripts/train_course_ner.py:encode_row',
        'REHelper': 'scripts/train_course_relation.py:encode_pair', 'trainingAllowed': False,
        'featuresExclude': ['evidence', 'taskRole', 'notes', 'sourceURL', 'title', 'dev_reference', 'test_reference'],
        'NERInput': 'ner22_candidates.jsonl', 'REInput': 'relation_positive_candidates.jsonl',
        'NEREncoded': 'ner_encoded.jsonl', 'REEncoded': 'relation_encoded.jsonl',
        'blockingItems': ['43 training abstracts pending V2 semantic revision',
                          'No admitted explicit negative pairs under current broad scope',
                          'Fixed dev20 is AI draft, not complete scored reference',
                          'Independent final test reference remains unprepared and sealed']})
    (output / 'README.md').write_text('# V2 train65 原始训练摘要与实际补标\n\n'
        '完整原文：`train65_sources.jsonl`（65篇）；70篇来源与5篇旧隔离记录也保留。\n\n'
        '本批复用已修订12篇，另逐篇补标10篇；剩余43篇见 `pending43_sources.jsonl`。'
        '旧标签/收据以legacy命名单独保存，不能自动当作新V2标签。\n\n'
        '新增实体与关系见 `batch10_ner_candidates.jsonl`、`batch10_relation_ledger.jsonl`；'
        '最直观的审核入口是 `train65_review.html`。关系只接受有原文证据的候选正例，未决不变成负例。\n\n'
        '已通过本地冻结SciBERT tokenizer生成BIO和实体标记输入，见 `ner_encoded.jsonl` 和 '
        '`relation_encoded.jsonl`。这是输入可编码检查，不是模型训练。没有新增F1。\n\n'
        '12篇原训练身份锁保持不变；65篇是独立标注工作集，不是绕过原准入规则的正式训练锁。'
        'dev20上传包仅做结构性检查且单独归档；test20只使用身份元数据，不读取正文。\n\n'
        '所有新旧AI标签均不是独立人工金标准。当前没有合格负例、dev覆盖不完整，普通三分类RE仍不准入。\n', encoding='utf-8')
    c.write_json(output / 'manifest.json', {'inputSha256': before,
        'filesSha256': {p.relative_to(output).as_posix(): c.file_sha256(p) for p in output.rglob('*') if p.is_file()}})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = build(args.output)
    archive = ROOT / 'outputs/v2_train65_sources_and_batch10_20261011.zip'
    if archive.exists():
        raise FileExistsError('Preserve existing delivery archive')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(args.output.rglob('*')):
            if p.is_file():
                z.write(p, p.relative_to(args.output).as_posix())
    print(json.dumps({'output': str(args.output), 'archive': str(archive),
                      'archiveSha256': c.file_sha256(archive), 'summary': summary}, ensure_ascii=False))


if __name__ == '__main__':
    main()
