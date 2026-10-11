"""Build a source-bound AI semantic revision; never train or overwrite prior data."""
import argparse
import copy
import csv
import itertools
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import prepare_v2_evidence_pilot as pilot
from collect_course_abstract_pages import CitationMetadata, parse_page

c, g, evidence = pilot.c, pilot.g, pilot.evidence
CONTRACT = c.ROOT/'resources/course_v2_semantic_revision_v1.json'
DECISIONS = c.ROOT/'annotations/course_v4/v2_pilot_semantic_decisions_20261010.json'
REVIEWS = c.ROOT/'annotations/course_v4/v2_pilot_semantic_reviews_20261010.json'
OUTPUT = c.ROOT/'kg_datasets/dblp/course_v2_semantic_revision_20261010_final'


def predicate_span(text, excerpt):
    if not isinstance(excerpt, str) or not excerpt.strip() or text.count(excerpt) != 1:
        raise ValueError('Predicate excerpt must identify one literal source span')
    start = text.index(excerpt)
    return {'start': start, 'end': start+len(excerpt), 'text': excerpt}


def revise(ref, prior, decision):
    if (decision['arxivId'] != ref['arxivId'] or decision['textSha256'] != ref['textSha256']
            or decision['upstreamReceiptSha256'] != prior['contentSha256']
            or decision['entityStatus'] not in ('complete', 'unresolved')
            or not decision['entityReview'].strip() or not decision['deferred'].strip()):
        raise ValueError('Unbound or undocumented semantic decision')
    if c.validate_receipt(prior, ref):
        raise ValueError('Invalid upstream receipt')
    annotation = copy.deepcopy(prior['annotation']); annotation['reviewOfSha256'] = None
    annotation['entityStatus'] = decision['entityStatus']; annotation['entityReason'] = decision['entityReview']
    by_id = {e['entityId']: e for e in annotation['entities']}
    old = {(p['head'], p['tail']): p for p in annotation['relations']}
    resolved, supports, withdrawn = {}, {}, {}
    for index, group in enumerate(decision['groups']):
        spans = [predicate_span(ref['text'], q) for q in group['predicateExcerpts']]
        if (not spans or not group['attribution'].strip() or group['label'] == 'UNRESOLVED'
                or group['taskRole'] not in ('downstream_application', 'component_operation', 'training_proxy',
                                            'background_method_use', 'direct_operator_contrast', 'not_applicable')):
            raise ValueError('Missing predicate/attribution/task role')
        if group['label'] == 'NO_RELATION' and (group.get('negativeBasis') != 'explicit_argument_role_contrast'
                                               or group['taskRole'] != 'direct_operator_contrast'):
            raise ValueError('Negative requires scoped role contrast')
        for key in itertools.product(group['heads'], group['tails']):
            if key not in old or key in resolved:
                raise ValueError('Invalid or duplicate decided candidate')
            anchors = [by_id[key[0]], by_id[key[1]]] + spans
            start, end = min(s['start'] for s in anchors), max(s['end'] for s in anchors)
            resolved[key] = {'head': key[0], 'tail': key[1], 'label': group['label'],
                'evidence': {'start': start, 'end': end, 'text': ref['text'][start:end]}, 'reason': group['attribution']}
            supports[key] = {'predicateSpans': spans, 'attribution': group['attribution'], 'taskRole': group['taskRole'],
                'negativeBasis': group.get('negativeBasis'), 'supportGroup': f"{ref['arxivId']}:g{index+1}"}
    for group in decision['withdrawals']:
        if not group['reason'].strip():
            raise ValueError('Withdrawal needs reason')
        for key in itertools.product(group['heads'], group['tails']):
            if key not in old or old[key]['label'] == 'UNRESOLVED' or key in resolved or key in withdrawn:
                raise ValueError('Invalid/duplicate withdrawal')
            withdrawn[key] = group['reason']
    if any(p['label'] != 'UNRESOLVED' and key not in resolved and key not in withdrawn for key, p in old.items()):
        raise ValueError('Every old resolved pair must be reviewed explicitly')
    annotation['relations'] = [resolved.get(key, {'head': key[0], 'tail': key[1], 'label': 'UNRESOLVED',
        'evidence': None, 'reason': withdrawn.get(key, decision['deferred'])}) for key in old]
    complete = decision['entityStatus'] == 'complete' and all(p['label'] != 'UNRESOLVED' for p in annotation['relations'])
    annotation['relationStatus'] = 'complete' if complete else 'unresolved'
    annotation['relationReason'] = decision['deferred']
    annotation['notes'] = 'V2 AI source review, not independent human gold. Original references/entities preserved. '+decision['entityReview']
    errors = c.validate_response(annotation, ref)
    if errors:
        raise ValueError('; '.join(errors))
    return annotation, supports


def provenance(ref, repair):
    folder = c.ROOT/repair['folder']; manifest = g.verified_files(folder, repair['manifestSha256'])
    requests = pilot.read(folder/'requests.json')
    matches = [r for r in requests if r['arxivId'] == ref['arxivId'] and r['status'] == 'completed']
    if len(matches) != 1 or matches[0]['url'] != ref['sourceURL']:
        raise ValueError('Collection request does not identify this source')
    request = matches[0]; path = folder/request['rawResponseFile']
    if not path.resolve().is_relative_to(folder.resolve()):
        raise ValueError('Unsafe raw source path')
    title, text = parse_page(path.read_bytes(), ref)
    if text != ref['text'] or g.digest(text) != ref['textSha256']:
        raise ValueError('Raw collected abstract differs from reference')
    contract = c.ROOT/repair['collectionContract']; sha = c.file_sha256(contract)
    if manifest['inputSha256'].get(repair['collectionContract']) != sha:
        raise ValueError('Unbound collection contract')
    parser = CitationMetadata(); parser.feed(path.read_text(encoding='utf-8'))
    missing = [k for k in ('schemaVersion', 'contractSha256', 'sourceCorpusSha256', 'annotationStatus') if k not in ref]
    return {'arxivId': ref['arxivId'], 'textSha256': ref['textSha256'], 'originalMissingFields': missing,
        'originalFieldsNotBackfilled': {k: None for k in missing}, 'explanation': 'Historical collector did not emit these fields; a raw page/collection manifest is not a guessed corpus hash or original annotation schema.',
        'rawPage': path.relative_to(c.ROOT).as_posix(), 'rawPageSha256': c.file_sha256(path),
        'sourceManifest': (folder/'manifest.json').relative_to(c.ROOT).as_posix(), 'sourceManifestSha256': repair['manifestSha256'],
        'requestRecord': request, 'requestFileSha256': c.file_sha256(folder/'requests.json'), 'citationArxivId': parser.values['citation_arxiv_id'],
        'sourceTitle': title, 'collectionContract': repair['collectionContract'], 'collectionContractFileSha256': sha,
        'rawSourceVerified': True}


def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def build(output=OUTPUT):
    output = output.resolve()
    if output.exists():
        raise FileExistsError('Preserve semantic revision')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()):
        raise ValueError('Output outside datasets')
    config = pilot.read(CONTRACT)
    if config['version'] != 'course_v2_semantic_revision_v1' or any(config[k] is not False for k in
            ('trainingAllowed', 'inferenceAllowed', 'testContentAccessAllowed', 'productionMutationAllowed', 'automaticPromotionAllowed', 'independentHumanGold')):
        raise ValueError('Semantic data-only contract drift')
    folder = c.ROOT/config['pilot']; manifest = g.verified_files(folder, config['pilotManifestSha256'])
    inputs = [CONTRACT, DECISIONS, REVIEWS, Path(__file__), Path(pilot.__file__), Path(c.__file__), Path(g.__file__),
              Path(evidence.__file__), c.ROOT/'scripts/collect_course_abstract_pages.py', c.SCHEMA_PATH, c.CONFIG_PATH,
              c.ROOT/'tests/test_v2_semantic_revision.py', folder/'manifest.json']
    for key in ('externalQueue', 'externalReport'):
        path = Path(config[key])
        if c.file_sha256(path) != config[key+'Sha256']:
            raise ValueError('External audit input drift')
        inputs.append(path)
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()):
        raise ValueError('Pilot inputs changed')
    protection = pilot.read(folder/'production_protection.json')
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in protection.items()):
        raise ValueError('V1 protection drift')
    refs = c.read_jsonl(folder/'references.jsonl'); old = c.read_jsonl(folder/'inherited_receipts.jsonl')
    pilot.inventory(refs, old)
    pilot_config = pilot.read(pilot.CONTRACT)
    isolation = pilot.check_isolation(refs, c.read_jsonl(c.ROOT/pilot_config['splitMetadata']),
        pilot.read(c.ROOT/pilot_config['abstractSelectionMetadata'])['selected'],
        pilot.read(c.ROOT/pilot_config['supplementMetadata'])['seeds'])
    source, reviews = pilot.read(DECISIONS), pilot.read(REVIEWS)
    ids = [r['arxivId'] for r in refs]
    if (len(refs) != 12 or [d['arxivId'] for d in source['documents']] != ids or [d['arxivId'] for d in reviews['reviews']] != ids
            or source['independent'] is not False or reviews['independent'] is not False):
        raise ValueError('Incomplete or misrepresented AI review cohort')
    fixed = {}; receipts = []; generated = []; ledger = []; report = ['# V2 首批语义修订审核包', '', 'AI原文复核与同会话自查，非独立人工gold。仅摘要训练侧；不训练、不覆盖旧数据。', '']
    stamp = datetime.now(UTC).isoformat()
    def metadata(document, path):
        return {'provider': document['provider'], 'model': document['model'], 'promptSha256': c.file_sha256(CONTRACT),
                'sourceArtifactSha256': c.file_sha256(path), 'createdAt': stamp}
    for ref, prior, decision, review in zip(refs, old, source['documents'], reviews['reviews']):
        if not review['reason'].strip():
            raise ValueError('Missing source self-review')
        annotation, supports = revise(ref, prior, decision)
        initial = c.make_receipt(annotation, ref, metadata(source, DECISIONS)); generated.append(initial)
        checked = copy.deepcopy(annotation); checked['reviewOfSha256'] = initial['contentSha256']; checked['notes'] += ' Self-review: '+review['reason']
        receipt = c.make_receipt(checked, ref, metadata(reviews, REVIEWS), previous=initial); receipts.append(receipt)
        report += [f"## {ref['arxivId']}", '', f"来源：{ref['sourceURL']}", '', '### 摘要原文', '', ref['text'], '',
                   '### 实体审核', '', f"完整性状态：{decision['entityStatus']}。{decision['entityReview']}", '', '| ID | 类别 | 原文提及 | 偏移 |', '|---|---|---|---|']
        report += [f"| {e['entityId']} | {e['label']} | {e['text']} | {e['start']}:{e['end']} |" for e in annotation['entities']]
        report += ['', '### 关系复核（包含全部旧已判项、新增项和撤回项）', '']
        for before, after in zip(prior['annotation']['relations'], annotation['relations']):
            key = (after['head'], after['tail']); support = supports.get(key, {})
            by_id = {e['entityId']: e for e in annotation['entities']}
            row = {'arxivId': ref['arxivId'], 'sampleId': ref['sampleId'], 'headId': key[0], 'headText': by_id[key[0]]['text'],
                'tailId': key[1], 'tailText': by_id[key[1]]['text'], 'oldLabel': before['label'], 'newLabel': after['label'],
                'labelChanged': before['label'] != after['label'], 'entityCompleteness': decision['entityStatus'],
                'candidateEligible': decision['entityStatus'] == 'complete' and after['label'] != 'UNRESOLVED',
                'taskRole': support.get('taskRole', 'unresolved'), 'supportGroup': support.get('supportGroup', ''),
                'predicateEvidence': '\n'.join(s['text'] for s in support.get('predicateSpans', [])), 'reason': after['reason']}
            fixed[(ref['arxivId'], *key)] = row
            ledger.append(row | {'textSha256': ref['textSha256'], 'upstreamReceiptSha256': prior['contentSha256'],
                'reviewedReceiptSha256': receipt['contentSha256'], 'oldRelation': before, 'newRelation': after, 'support': support})
            if before['label'] != 'UNRESOLVED' or after['label'] != 'UNRESOLVED':
                report += [f"- `{key[0]} {row['headText']} → {key[1]} {row['tailText']}`：**{before['label']} → {after['label']}**；角色 `{row['taskRole']}`。", '',
                           '  理由：'+after['reason'], '']
                for span in support.get('predicateSpans', []):
                    report += [f"  谓词证据 [{span['start']}:{span['end']}]：{span['text']}", '']
        report += ['保留未决说明：'+decision['deferred'], '', '同会话自查：'+review['reason'], '']
    with Path(config['externalQueue']).open(encoding='utf-8-sig', newline='') as stream:
        queue = list(csv.DictReader(stream))
    if len(queue) != 12 or len({(q['arxiv_id'], q['head_entity_id'], q['tail_entity_id']) for q in queue}) != 12:
        raise ValueError('External priority cohort changed')
    adjudicated = []
    for q in queue:
        doc = refs[int(q['line_in_review_dossiers_jsonl'])-1]
        row = fixed.get((q['arxiv_id'], q['head_entity_id'], q['tail_entity_id']))
        if doc['arxivId'] != q['arxiv_id'] or not row or row['oldLabel'] != q['prior_label']:
            raise ValueError('External queue binding mismatch')
        adjudicated.append(q | row)
    sidecars = [provenance(next(r for r in refs if r['arxivId'] == arxiv), repair) for arxiv, repair in config['sourceRepairs'].items()]
    for sidecar in sidecars:
        inputs += [c.ROOT/sidecar[k] for k in ('rawPage', 'sourceManifest', 'collectionContract')]
        inputs.append((c.ROOT/sidecar['sourceManifest']).parent/'requests.json')
    hashes = {str(p.relative_to(c.ROOT)) if p.is_relative_to(c.ROOT) else str(p): c.file_sha256(p) for p in inputs}
    counts = Counter(r['newLabel'] for r in ledger); before_counts = Counter(r['oldLabel'] for r in ledger)
    eligible = [r for r in ledger if r['candidateEligible']]
    summary = {'status': 'semantic_review_complete_with_entity_coverage_quarantines_not_training_ready', 'createdAtUTC': stamp,
        'reviewedDocuments': len(receipts), 'existingEntityMentionsReviewed': sum(len(r['annotation']['entities']) for r in receipts),
        'priorResolvedPairsReviewed': sum(n for label, n in before_counts.items() if label != 'UNRESOLVED'), 'isolation': isolation,
        'candidatePairs': len(ledger), 'priorSupport': dict(before_counts), 'revisedSupport': dict(counts),
        'withdrawnToUnresolved': sum(r['oldLabel'] != 'UNRESOLVED' and r['newLabel'] == 'UNRESOLVED' for r in ledger),
        'newlyResolvedPairs': sum(r['oldLabel'] == 'UNRESOLVED' and r['newLabel'] != 'UNRESOLVED' for r in ledger),
        'NEREligibleDocuments': sum(r['annotation']['entityStatus'] == 'complete' for r in receipts),
        'NERQuarantinedDocuments': [r['reference']['arxivId'] for r in receipts if r['annotation']['entityStatus'] != 'complete'],
        'candidateEligibleRelationPairs': len(eligible), 'candidateEligibleSupport': dict(Counter(r['newLabel'] for r in eligible)),
        'distinctLiteralPairsPerPaper': {label: len({(r['arxivId'], r['headText'], r['tailText']) for r in ledger if r['newLabel'] == label}) for label in counts if label != 'UNRESOLVED'},
        'sourcePapersByClass': {label: len({r['arxivId'] for r in ledger if r['newLabel'] == label}) for label in counts if label != 'UNRESOLVED'},
        'supportGroupsByClass': {label: len({r['supportGroup'] for r in ledger if r['newLabel'] == label}) for label in counts if label != 'UNRESOLVED'},
        'priorityQueueAdjudicated': len(adjudicated), 'sourceMetadataSidecars': len(sidecars), 'independentHumanGold': False,
        'trainingExecuted': False, 'inferenceExecuted': False, 'modelPromoted': False, 'testContentParsed': False,
        'notice': 'Candidate eligibility is not training execution/admission. Four entity coverage gaps and a locked future split/selection contract remain. Retained negatives are scoped operator-role decisions, not global factual negations.'}
    output.mkdir(parents=True)
    for name, rows in (('references', refs), ('generation_receipts', generated), ('reviewed_receipts', receipts),
                       ('change_ledger', ledger), ('source_provenance_sidecars', sidecars)):
        c.write_jsonl(output/(name+'.jsonl'), rows)
    write_csv(output/'relation_review.csv', [fixed[k] for k in fixed]); write_csv(output/'priority_adjudications.csv', adjudicated)
    (output/'semantic_review.md').write_text('\n'.join(report), encoding='utf-8')
    c.write_json(output/'summary.json', summary); c.write_json(output/'contract.json', config)
    for key in ('externalQueue', 'externalReport'):
        shutil.copy2(config[key], output/Path(config[key]).name)
    body = '<p>12篇原文与151旧提及已复核；102旧已判逐项裁决。AI同会话复核，不是独立人工gold；未训练或上线。</p>'
    body += evidence.table(['类别', '旧提及对', '修订提及对'], [[k, before_counts[k], counts[k]] for k in c.CONFIG['relationLabels']])
    body += evidence.table(['项目', '结果'], [['优先队列', len(adjudicated)], ['撤回为未决', summary['withdrawnToUnresolved']],
        ['新增有证据判断', summary['newlyResolvedPairs']], ['NER完整性隔离', ', '.join(summary['NERQuarantinedDocuments'])],
        ['来源补证', '2份原始页面与采集记录侧车；不猜填旧字段'], ['候选可用关系对', len(eligible)]])
    body += '<p>详细审核见semantic_review.md及relation_review.csv。谓词片段与实体指代分开保存；不同提及不冒充独立证据。V1保护文件未改；预留test仅二进制哈希核对。</p>'
    (output/'09_annotation_expansion.html').write_text(evidence.page('V2首批语义修订与准入隔离', body, stamp,
        ['summary.json', 'change_ledger.jsonl', 'source_provenance_sidecars.jsonl']), encoding='utf-8')
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in protection.items()) or any(c.file_sha256(Path(p) if Path(p).is_absolute() else c.ROOT/p) != sha for p, sha in hashes.items()):
        raise ValueError('Source or V1 changed during revision')
    c.write_json(output/'production_protection.json', protection)
    c.write_json(output/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui',
        'inputSha256': hashes, 'filesSha256': {p.name: c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
    print(summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    build(parser.parse_args().output)
