"""Complete four TRAIN inventories and export evidence-preserving V2 candidates, never train."""
import argparse
import copy
import re
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import review_v2_evidence_pilot as v

c, g, pilot, evidence = v.c, v.g, v.pilot, v.evidence
CONTRACT = c.ROOT/'resources/course_v2_entity_completion_v1.json'
DECISIONS = c.ROOT/'annotations/course_v4/v2_entity_completion_decisions_20261010.json'
OUTPUT = c.ROOT/'kg_datasets/dblp/course_v2_entity_completion_20261010'
FLAGS = ('trainingAllowed', 'inferenceAllowed', 'testContentAccessAllowed',
         'productionMutationAllowed', 'automaticPromotionAllowed', 'independentHumanGold')


def anchor(entity):
    return tuple(entity[k] for k in ('start', 'end', 'text', 'label'))


def complete(ref, prior, ledger, decision):
    if ref['split'] != 'train' or ref['textKind'] != 'abstract' or g.digest(ref['text']) != ref['textSha256'] or c.validate_receipt(prior, ref):
        raise ValueError('Unbound TRAIN source')
    annotation = copy.deepcopy(prior['annotation']); annotation['reviewOfSha256'] = None
    old_entities = {e['entityId']: e for e in annotation['entities']}
    additions = []
    if decision is not None:
        if any(decision[k] != value for k, value in (('arxivId', ref['arxivId']), ('textSha256', ref['textSha256']),
                                                      ('upstreamReceiptSha256', prior['contentSha256']))):
            raise ValueError('Entity decision source drift')
        if not decision['exclusions'].strip() or not decision['review'].strip():
            raise ValueError('Whole-text review and exclusion rationale required')
        for item in decision['additions']:
            hits = list(re.finditer(re.escape(item['text']), ref['text']))
            index = item['occurrence']
            if type(index) is not int or not 0 <= index < len(hits) or item['label'] not in c.CONFIG['entityLabels']:
                raise ValueError('Invalid literal entity decision')
            hit = hits[index]
            additions.append({'start': hit.start(), 'end': hit.end(), 'text': item['text'], 'label': item['label']})
        annotation['entityStatus'] = 'complete'; annotation['entityReason'] = decision['review']+' '+decision['exclusions']
    elif annotation['entityStatus'] != 'complete':
        raise ValueError('Missing incomplete-document decision')
    entities = sorted(annotation['entities']+additions, key=lambda e: (e['start'], e['end']))
    for index, entity in enumerate(entities, 1): entity['entityId'] = f'e{index}'
    by_anchor = {anchor(e): e for e in entities}
    if len(by_anchor) != len(entities): raise ValueError('Duplicate entity anchors')
    remap = {key: by_anchor[anchor(e)]['entityId'] for key, e in old_entities.items()}
    old_pairs = {(p['head'], p['tail']): p for p in prior['annotation']['relations']}
    rows = {(r['headId'], r['tailId']): r for r in ledger}
    if len(rows) != len(ledger) or set(rows) != set(old_pairs): raise ValueError('Prior ledger coverage drift')
    inherited = {}
    for key, relation in old_pairs.items():
        row = rows[key]
        if (row['arxivId'] != ref['arxivId'] or row['textSha256'] != ref['textSha256']
                or row['reviewedReceiptSha256'] != prior['contentSha256'] or row['newRelation'] != relation):
            raise ValueError('Prior judgment/receipt drift')
        inherited[remap[key[0]], remap[key[1]]] = (relation, row)
    annotation['entities'] = entities; annotation['relations'] = []
    after_ledger = []
    for key in c.candidate_pairs(entities):
        before, row = inherited.get(key, (None, None))
        relation = copy.deepcopy(before) if before else {'label': 'UNRESOLVED', 'evidence': None,
            'reason': 'New candidate after inventory completion; no semantic decision. Not a negative.'}
        relation.update(head=key[0], tail=key[1]); annotation['relations'].append(relation)
        support = copy.deepcopy(row['support']) if row else {}
        label = relation['label']
        if label != 'UNRESOLVED':
            allowed_roles = {'USED_FOR': {'downstream_application', 'component_operation', 'training_proxy', 'background_method_use'},
                             'EVALUATED_ON': {'not_applicable'}, 'NO_RELATION': {'direct_operator_contrast'}}
            if (not support.get('predicateSpans') or not support.get('supportGroup')
                    or support.get('taskRole') not in allowed_roles[label] or support.get('attribution') != relation['reason']
                    or any(c.span_errors(s, ref['text']) for s in support['predicateSpans'])):
                raise ValueError('Missing or drifted relation evidence/role')
        pending = label == 'NO_RELATION'
        by_id = {e['entityId']: e for e in entities}
        after_ledger.append({'arxivId': ref['arxivId'], 'sampleId': ref['sampleId'], 'textSha256': ref['textSha256'],
            'head': by_id[key[0]], 'tail': by_id[key[1]], 'priorHeadId': before['head'] if before else None,
            'priorTailId': before['tail'] if before else None, 'priorLabel': before['label'] if before else None,
            'label': label, 'newCandidate': before is None, 'candidateEligible': label in ('USED_FOR', 'EVALUATED_ON'),
            'quarantineReason': 'pending_direct_indirect_negative_scope' if pending else ('unresolved' if label == 'UNRESOLVED' else None),
            'support': support, 'evidence': relation['evidence'], 'reason': relation['reason'],
            'upstreamReceiptSha256': prior['contentSha256']})
    annotation['relationStatus'] = 'unresolved'
    annotation['relationReason'] = 'Partial relation supervision; new and inherited undecided pairs masked, scoped negatives quarantined in export.'
    annotation['notes'] = 'V2 AI pseudo-label completion, not independent human gold; prior labels retained by literal anchors.'
    errors = c.validate_response(annotation, ref)
    if errors: raise ValueError('; '.join(errors))
    return annotation, after_ledger, [{'oldId': key, 'newId': value, 'anchor': list(anchor(old_entities[key]))} for key, value in remap.items()]


def candidate_rows(ref, receipt, ledger):
    if c.validate_receipt(receipt, ref) or not c.eligible_tasks(receipt, ref)['ner']:
        raise ValueError('Invalid reviewed export receipt')
    common = {k: ref[k] for k in ('sampleId', 'publicationId', 'groupId', 'arxivId', 'text', 'textSha256', 'textKind', 'split', 'sourceURL')}
    common.update(labelSource='ai_pseudo', sourceReceiptSha256=receipt['contentSha256'], trainingAuthorized=False)
    ner = common | {'entities': receipt['annotation']['entities']}
    relations = {(p['head'], p['tail']): p for p in receipt['annotation']['relations']}
    keys = [(r['head']['entityId'], r['tail']['entityId']) for r in ledger]
    if len(set(keys)) != len(keys) or set(keys) != set(relations):
        raise ValueError('Export ledger coverage drift')
    pairs = []
    for row in ledger:
        key = (row['head']['entityId'], row['tail']['entityId']); relation = relations.get(key)
        if (row['sampleId'] != ref['sampleId'] or row['textSha256'] != ref['textSha256']
                or not relation or row['label'] != relation['label'] or row['evidence'] != relation['evidence']
                or row['reason'] != relation['reason'] or row['sourceReceiptSha256'] != receipt['contentSha256']
                or row['head'] not in ner['entities'] or row['tail'] not in ner['entities']):
            raise ValueError('Export ledger does not match receipt')
        if row['candidateEligible'] is not (row['label'] in ('USED_FOR', 'EVALUATED_ON')):
            raise ValueError('Export eligibility differs from locked scope')
        if not row['candidateEligible']: continue
        if row['label'] not in ('USED_FOR', 'EVALUATED_ON') or row['quarantineReason']:
            raise ValueError('Quarantined target cannot enter V2 candidate export')
        support = row['support']
        roles = {'USED_FOR': {'downstream_application', 'component_operation', 'training_proxy', 'background_method_use'},
                 'EVALUATED_ON': {'not_applicable'}}
        if (not support.get('predicateSpans') or support.get('attribution') != row['reason'] or not support.get('supportGroup')
                or support.get('taskRole') not in roles[row['label']]
                or any(c.span_errors(s, ref['text']) for s in support['predicateSpans'])):
            raise ValueError('Evidence-preserving export requires support metadata')
        pairs.append(common | {k: row[k] for k in ('head', 'tail', 'label', 'evidence', 'reason', 'upstreamReceiptSha256')}
            | {k: support[k] for k in ('taskRole', 'supportGroup', 'predicateSpans', 'attribution', 'negativeBasis')})
    return ner, pairs


def build(output=OUTPUT, test_evidence=None):
    output = output.resolve()
    if output.exists(): raise FileExistsError('Preserve previous completion')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Output outside datasets')
    config = pilot.read(CONTRACT)
    if config['version'] != 'course_v2_entity_completion_v1' or any(config[k] is not False for k in FLAGS):
        raise ValueError('V2 data-only contract drift')
    parent = c.ROOT/config['parent']; manifest = g.verified_files(parent, config['parentManifestSha256'])
    audit = Path(config['externalAudit'])
    if c.file_sha256(audit) != config['externalAuditSha256']: raise ValueError('Audit input drift')
    for path, sha in manifest['inputSha256'].items():
        if c.file_sha256(Path(path) if Path(path).is_absolute() else c.ROOT/path) != sha: raise ValueError('Parent input drift')
    protection = pilot.read(parent/'production_protection.json')
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in protection.items()): raise ValueError('V1 protection drift')
    refs = c.read_jsonl(parent/'references.jsonl'); old = c.read_jsonl(parent/'reviewed_receipts.jsonl')
    before = c.read_jsonl(parent/'change_ledger.jsonl'); source = pilot.read(DECISIONS)
    expected = {'2008.10400', '2501.02474', '2501.06756', '2312.03556'}
    decisions = {d['arxivId']: d for d in source['documents']}
    if len(refs) != 12 or len(old) != 12 or len(decisions) != 4 or set(decisions) != expected or source['independent'] is not False:
        raise ValueError('Completion cohort drift')
    pilot_config = pilot.read(pilot.CONTRACT)
    parent_config = pilot.read(parent/'contract.json')
    ancestor = g.verified_files(c.ROOT/parent_config['pilot'], parent_config['pilotManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in ancestor['inputSha256'].items()):
        raise ValueError('Preparation binding drift')
    # Only identity metadata is parsed; reserved test contents remain unopened.
    isolation = pilot.check_isolation(refs, c.read_jsonl(c.ROOT/pilot_config['splitMetadata']),
        pilot.read(c.ROOT/pilot_config['abstractSelectionMetadata'])['selected'],
        pilot.read(c.ROOT/pilot_config['supplementMetadata'])['seeds'])
    if any(c.file_sha256(c.ROOT/pilot_config[k]) != pilot_config[k+'Sha256'] for k in
            ('splitMetadata', 'abstractSelectionMetadata', 'supplementMetadata', 'reservedTest')):
        raise ValueError('Split/test binding drift')
    stamp = datetime.now(UTC).isoformat(); generated, receipts, ledger, migrations, ner, pairs = [], [], [], [], [], []
    report = ['# V2四篇实体完整性修订', '', 'AI同会话补标与自查，非独立人工金标准。所有新增关系对未决；5条争议负例仅隔离导出，不改标签。', '']
    for ref, prior in zip(refs, old):
        annotation, rows, mapping = complete(ref, prior, [r for r in before if r['arxivId'] == ref['arxivId']], decisions.get(ref['arxivId']))
        metadata = {'provider': source['provider'], 'model': source['model'], 'promptSha256': c.file_sha256(CONTRACT),
                    'sourceArtifactSha256': c.file_sha256(DECISIONS), 'createdAt': stamp}
        initial = c.make_receipt(annotation, ref, metadata); generated.append(initial)
        checked = copy.deepcopy(annotation); checked['reviewOfSha256'] = initial['contentSha256']
        checked['notes'] += ' Same-session check: literal additions/exclusions reviewed; inherited decisions preserved; candidate universe rebuilt.'
        receipt = c.make_receipt(checked, ref, metadata, previous=initial); receipts.append(receipt)
        for row in rows: row['sourceReceiptSha256'] = receipt['contentSha256']
        ledger += rows; migrations.append({'arxivId': ref['arxivId'], 'textSha256': ref['textSha256'], 'entityIdMap': mapping})
        nr, pr = candidate_rows(ref, receipt, rows); ner.append(nr); pairs += pr
        if ref['arxivId'] in decisions:
            report += [f"## {ref['arxivId']}", '', ref['sourceURL'], '', '### 全文与提及', '', ref['text'], '',
                       annotation['entityReason'], '', '| ID | 类别 | 原文 | 偏移 | 原有/新增 |', '|---|---|---|---|---|']
            anchors = {anchor(e) for e in prior['annotation']['entities']}
            report += [f"| {e['entityId']} | {e['label']} | {e['text']} | {e['start']}:{e['end']} | {'原有' if anchor(e) in anchors else '新增'} |" for e in annotation['entities']]
            report += ['', f"候选对：{len(prior['annotation']['relations'])} → {len(rows)}；新对全部未决。", '']
    if sum(r['label'] == 'NO_RELATION' for r in ledger) != 5 or sum(not r['newCandidate'] for r in ledger) != 499:
        raise ValueError('Inherited judgments not conserved')
    summary = {'status': 'entity_completion_and_role_export_done_negative_scope_pending_not_training_ready', 'createdAtUTC': stamp,
        'documents': 12, 'completedInventoryDocuments': 4, 'NERCandidateDocuments': len(ner),
        'entityMentions': sum(len(r['entities']) for r in ner), 'entitySupport': dict(Counter(e['label'] for r in ner for e in r['entities'])),
        'addedEntityMentions': sum(len(d['additions']) for d in decisions.values()), 'candidatePairs': len(ledger),
        'inheritedPairs': 499, 'newUnresolvedPairs': sum(r['newCandidate'] for r in ledger),
        'relationSupport': dict(Counter(r['label'] for r in ledger)), 'RECandidatePairs': len(pairs),
        'RECandidateSupport': dict(Counter(r['label'] for r in pairs)),
        'taskRoleSupport': dict(Counter(r['taskRole'] for r in pairs)),
        'quarantinedNegativePairs': 5, 'sourcePapersByCandidateClass': {label: len({r['arxivId'] for r in pairs if r['label'] == label}) for label in ('USED_FOR', 'EVALUATED_ON', 'NO_RELATION')},
        'supportGroupsByCandidateClass': {label: len({r['supportGroup'] for r in pairs if r['label'] == label}) for label in ('USED_FOR', 'EVALUATED_ON')},
        'isolation': isolation, 'independentHumanGold': False, 'trainingExecuted': False, 'inferenceExecuted': False,
        'testContentParsed': False, 'modelPromoted': False,
        'openIssues': ['Five inherited negatives require scope adjudication or evidence-based withdrawal; no accepted negative target.',
                       'New entity pairs have not been semantically adjudicated.', 'Independent V2 evaluation and selection contract not yet authorized.',
                       'AI label completeness is policy-dependent, not an independent semantic accuracy guarantee.']}
    inputs = [CONTRACT, DECISIONS, Path(__file__), Path(v.__file__), Path(pilot.__file__), Path(c.__file__), Path(g.__file__), Path(evidence.__file__),
              c.SCHEMA_PATH, c.CONFIG_PATH, parent/'manifest.json', audit, c.ROOT/'tests/test_v2_entity_completion.py',
              c.ROOT/'scripts/course_abstract_relation.py', c.ROOT/'scripts/train_course_ner.py', c.ROOT/'scripts/train_course_relation.py']
    input_hashes = {str(p.relative_to(c.ROOT)) if p.is_relative_to(c.ROOT) else str(p): c.file_sha256(p) for p in inputs}
    output.mkdir(parents=True)
    for name, rows in (('references', refs), ('generation_receipts', generated), ('reviewed_receipts', receipts), ('relation_ledger', ledger),
                       ('entity_id_migrations', migrations), ('ner_candidates', ner), ('re_candidates', pairs)):
        c.write_jsonl(output/(name+'.jsonl'), rows)
    v.write_csv(output/'relation_review.csv', [{'arxivId': r['arxivId'], 'headId': r['head']['entityId'], 'headText': r['head']['text'],
        'tailId': r['tail']['entityId'], 'tailText': r['tail']['text'], 'label': r['label'], 'newCandidate': r['newCandidate'],
        'candidateEligible': r['candidateEligible'], 'quarantineReason': r['quarantineReason'], 'taskRole': r['support'].get('taskRole', 'unresolved'),
        'supportGroup': r['support'].get('supportGroup', ''), 'predicateEvidence': '\n'.join(s['text'] for s in r['support'].get('predicateSpans', [])),
        'reason': r['reason']} for r in ledger])
    (output/'entity_review.md').write_text('\n'.join(report), encoding='utf-8')
    c.write_json(output/'summary.json', summary); c.write_json(output/'contract.json', config)
    c.write_json(output/'production_protection.json', protection)
    package = output/'audit_sources'; package.mkdir()
    for name in ('references.jsonl', 'reviewed_receipts.jsonl', 'change_ledger.jsonl', 'source_provenance_sidecars.jsonl', 'contract.json', 'manifest.json'):
        shutil.copy2(parent/name, package/('parent_'+name))
    shutil.copy2(audit, package/audit.name)
    shutil.copy2(c.ROOT/'outputs/v2_semantic_revision_final_20261010.xml', package/'parent_39_checks.xml')
    shutil.copy2(DECISIONS, package/DECISIONS.name)
    # Include the two missing-metadata raw pages, not guessed historical fields.
    for sidecar in c.read_jsonl(parent/'source_provenance_sidecars.jsonl'):
        for key, suffix in (('rawPage', 'html'), ('sourceManifest', 'manifest.json'), ('collectionContract', 'contract.json')):
            source_path = c.ROOT/sidecar[key]
            if c.file_sha256(source_path) != sidecar[{'rawPage': 'rawPageSha256', 'sourceManifest': 'sourceManifestSha256', 'collectionContract': 'collectionContractFileSha256'}[key]]:
                raise ValueError('Source proof drift')
            shutil.copy2(source_path, package/(sidecar['arxivId']+'.'+suffix))
        c.write_json(package/(sidecar['arxivId']+'.request.json'), sidecar['requestRecord'])
        requests = (c.ROOT/sidecar['sourceManifest']).parent/'requests.json'
        if c.file_sha256(requests) != sidecar['requestFileSha256']:
            raise ValueError('Collection request file drift')
        shutil.copy2(requests, package/(sidecar['arxivId']+'.requests.json'))
    if test_evidence:
        import xml.etree.ElementTree as ET
        tree = ET.parse(test_evidence); suites = list(tree.getroot().iter('testsuite'))
        classes = {case.get('classname') for case in tree.getroot().iter('testcase')}
        if (not {'tests.test_v2_entity_completion', 'tests.test_v2_semantic_revision', 'tests.test_v2_evidence_pilot'} <= classes
                or not suites or any(int(s.get('failures', '0')) or int(s.get('errors', '0'))
                                     or int(s.get('skipped', '0')) or not int(s.get('tests', '0')) for s in suites)):
            raise ValueError('Test evidence is not passing JUnit')
        shutil.copy2(test_evidence, package/'completion_checks.xml')
    body = '<p>本批数据修复与V2候选导出；没有训练、推理或生产替换。AI复核，不是独立人工金标准。</p>'
    body += evidence.table(['项目', '结果'], [['摘要', 12], ['补齐完整性', 4], ['新增实体', summary['addedEntityMentions']],
        ['实体提及', summary['entityMentions']], ['候选对重建', f"499 → {len(ledger)}"], ['新增对全部未决', summary['newUnresolvedPairs']],
        ['有证据正关系候选', len(pairs)], ['争议负例隔离', 5], ['状态', summary['status']]])
    body += '<p>角色、支持组、谓词片段与指代归属保留；不能当推理特征。当前没有已接受负例，尚不能启动RE训练。审核材料见audit_sources和entity_review.md。</p>'
    (output/'09_annotation_expansion.html').write_text(evidence.page('V2实体完整性、作用域隔离与导出', body, stamp, ['summary.json', 'relation_ledger.jsonl', 're_candidates.jsonl']), encoding='utf-8')
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in protection.items()) or any(c.file_sha256(Path(p) if Path(p).is_absolute() else c.ROOT/p) != sha for p, sha in input_hashes.items()):
        raise ValueError('Input or V1 changed during completion')
    c.write_json(output/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'inputSha256': input_hashes,
        'filesSha256': {p.relative_to(output).as_posix(): c.file_sha256(p) for p in output.rglob('*') if p.is_file()}})
    print(summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--test-evidence', type=Path)
    args = parser.parse_args(); build(args.output, args.test_evidence)
