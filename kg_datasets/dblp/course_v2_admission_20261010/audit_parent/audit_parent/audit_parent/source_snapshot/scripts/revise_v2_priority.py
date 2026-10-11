"""Source-bound review of five candidates and two evidence chains; data only."""
import argparse
import ast
import copy
import csv
import itertools
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import complete_v2_evidence_pilot as parent_stage

c, g, pilot, evidence = parent_stage.c, parent_stage.g, parent_stage.pilot, parent_stage.evidence
CONTRACT = c.ROOT/'resources/course_v2_priority_revision_v1.json'
DECISIONS = c.ROOT/'annotations/course_v4/v2_priority_decisions_20261010.json'
OUTPUT = c.ROOT/'kg_datasets/dblp/course_v2_priority_revision_20261010_final'


def revise(ref, prior, ledger, decision):
    if ref['split'] != 'train' or ref['textKind'] != 'abstract' or g.digest(ref['text']) != ref['textSha256'] or c.validate_receipt(prior, ref):
        raise ValueError('Invalid TRAIN abstract receipt')
    annotation = copy.deepcopy(prior['annotation']); annotation['reviewOfSha256'] = None
    rows = copy.deepcopy(ledger); by_pair = {(r['head']['entityId'], r['tail']['entityId']): r for r in rows}
    pairs = {(p['head'], p['tail']): p for p in annotation['relations']}
    if len(by_pair) != len(rows) or set(by_pair) != set(pairs): raise ValueError('Ledger coverage drift')
    # Reuse the guarded parent export as the ledger/receipt trust boundary.
    parent_stage.candidate_rows(ref, prior, rows)
    if decision:
        if any(decision[k] != value for k, value in (('arxivId', ref['arxivId']), ('textSha256', ref['textSha256']),
                                                   ('upstreamReceiptSha256', prior['contentSha256']))) or not decision['selfReview'].strip():
            raise ValueError('Unbound priority review')
        decided = set()
        for index, group in enumerate(decision['groups'], 1):
            spans = [parent_stage.v.predicate_span(ref['text'], q) for q in group['predicateExcerpts']]
            if (not spans or group['label'] != 'USED_FOR' or not group['attribution'].strip()
                    or group['taskRole'] not in ('training_proxy', 'background_method_use', 'downstream_application', 'component_operation')
                    or (group['taskSubRole'] is not None and (group['taskSubRole'] != 'training_augmentation' or group['taskRole'] != 'training_proxy'))):
                raise ValueError('Invalid role or positive predicate')
            for key in itertools.product(group['heads'], group['tails']):
                row = by_pair.get(key)
                if not row or key in decided or row['label'] != 'UNRESOLVED' or row['tail']['label'] != 'TASK' or not row['newCandidate']:
                    raise ValueError('Only new unresolved METHOD-TASK candidates may be promoted')
                decided.add(key)
                anchors = [row['head'], row['tail']]+spans
                start, end = min(a['start'] for a in anchors), max(a['end'] for a in anchors)
                pairs[key].update(label='USED_FOR', evidence={'start': start, 'end': end, 'text': ref['text'][start:end]}, reason=group['attribution'])
                row.update(label='USED_FOR', candidateEligible=True, quarantineReason=None, evidence=pairs[key]['evidence'], reason=group['attribution'])
                row['support'] = {'predicateSpans': spans, 'attribution': group['attribution'], 'taskRole': group['taskRole'],
                    'taskSubRole': group['taskSubRole'], 'negativeBasis': None, 'supportGroup': f"{ref['arxivId']}:priority:g{index}"}
        linked = set()
        for group in decision['coreference']:
            links = [{'anaphorSpan': parent_stage.v.predicate_span(ref['text'], link['anaphorExcerpt']),
                      'antecedentSpan': parent_stage.v.predicate_span(ref['text'], link['antecedentExcerpt']),
                      'kind': link['kind'], 'explanation': link['explanation']} for link in group['links']]
            if not links or any(not link['kind'].strip() or not link['explanation'].strip() for link in links):
                raise ValueError('Missing coreference explanation')
            for key in itertools.product(group['heads'], group['tails']):
                if key not in by_pair or key in linked or pairs[key]['label'] != 'EVALUATED_ON' or not by_pair[key]['candidateEligible']:
                    raise ValueError('Coreference additions are evidence-only existing evaluation pairs')
                linked.add(key)
                by_pair[key]['support']['coreferenceEvidence'] = copy.deepcopy(links)
                by_pair[key]['support']['coreferenceStatus'] = 'ai_source_local_discourse_review_not_independent_gold'
    annotation['notes'] = 'V2 priority AI source review; five scoped candidates only, evidence-only coreference updates, no training.'
    errors = c.validate_response(annotation, ref)
    if errors: raise ValueError('; '.join(errors))
    for before, after in zip(ledger, rows):
        after.update(revisionPriorLabel=before['label'], revisionPriorEvidence=before['evidence'], revisionPriorSupport=before['support'],
                     labelChanged=after['label'] != before['label'], supportChanged=after['support'] != before['support'],
                     previousUpstreamReceiptSha256=before['upstreamReceiptSha256'], upstreamReceiptSha256=prior['contentSha256'])
    return annotation, rows


def summary_for(refs, ner, pairs, ledger, before_pairs):
    def literal_set(rows, fold=False):
        return {(r['arxivId'], r['head']['text'].casefold() if fold else r['head']['text'],
                 r['tail']['text'].casefold() if fold else r['tail']['text'], r['label']) for r in rows}
    return {'status': 'priority_review_and_evidence_chain_completed_negative_scope_pending_not_training_ready',
        'documents': len(refs), 'NERCandidateDocuments': len(ner), 'entityMentions': sum(len(r['entities']) for r in ner),
        'candidatePairs': len(ledger), 'relationSupport': dict(Counter(r['label'] for r in ledger)),
        'RECandidatePairs': len(pairs), 'RECandidateSupport': dict(Counter(r['label'] for r in pairs)),
        'totalSourcePapersWithEligibleRE': len({r['arxivId'] for r in pairs}),
        'sourcePapersByCandidateClass': {label: len({r['arxivId'] for r in pairs if r['label'] == label}) for label in ('USED_FOR', 'EVALUATED_ON', 'NO_RELATION')},
        'parentTotalSourcePapersWithEligibleRE': len({r['arxivId'] for r in before_pairs}),
        'parentLiteralPairsExact': len(literal_set(before_pairs)), 'parentLiteralPairsCasefold': len(literal_set(before_pairs, True)),
        'literalPairsExact': len(literal_set(pairs)), 'literalPairsCasefold': len(literal_set(pairs, True)),
        'supportGroups': len({r['supportGroup'] for r in pairs}), 'taskRoleSupport': dict(Counter(r['taskRole'] for r in pairs)),
        'reviewedNewPairs': sum(r['labelChanged'] for r in ledger),
        'coreferenceMentionPairs': sum(bool(r['support'].get('coreferenceEvidence')) for r in ledger),
        'quarantinedNegativePairs': sum(r['label'] == 'NO_RELATION' and not r['candidateEligible'] for r in ledger),
        'independentHumanGold': False, 'trainingExecuted': False, 'inferenceExecuted': False, 'modelPromoted': False, 'testContentParsed': False}


def build(output=OUTPUT, test_evidence=None):
    output = output.resolve()
    if output.exists(): raise FileExistsError('Preserve priority revision')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Output outside datasets')
    if test_evidence:
        root = ET.parse(test_evidence).getroot(); suites = list(root.iter('testsuite'))
        if not suites or any(int(s.get(k, '0')) for s in suites for k in ('errors', 'failures', 'skipped')) or 'tests.test_v2_priority_revision' not in {t.get('classname') for t in root.iter('testcase')}:
            raise ValueError('Priority JUnit is not passing')
    config = pilot.read(CONTRACT)
    if config['version'] != 'course_v2_priority_revision_v1' or any(config[k] is not False for k in parent_stage.FLAGS):
        raise ValueError('Data-only contract drift')
    parent = c.ROOT/config['parent']; manifest = g.verified_files(parent, config['parentManifestSha256'])
    for path, sha in manifest['inputSha256'].items():
        if c.file_sha256(Path(path) if Path(path).is_absolute() else c.ROOT/path) != sha: raise ValueError('Parent code or config drift')
    protection = pilot.read(parent/'production_protection.json')
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in protection.items()): raise ValueError('V1 drift')
    for key in ('externalAudit', 'externalQueue'):
        if c.file_sha256(Path(config[key])) != config[key+'Sha256']: raise ValueError('External audit drift')
    with Path(config['externalQueue']).open(encoding='utf-8-sig', newline='') as stream: queue = list(csv.DictReader(stream))
    refs = c.read_jsonl(parent/'references.jsonl'); old = c.read_jsonl(parent/'reviewed_receipts.jsonl')
    before = c.read_jsonl(parent/'relation_ledger.jsonl'); before_pairs = c.read_jsonl(parent/'re_candidates.jsonl')
    source = pilot.read(DECISIONS); decisions = {d['arxivId']: d for d in source['documents']}
    if len(refs) != 12 or len(old) != 12 or len(decisions) != 6 or source['independent'] is not False:
        raise ValueError('Priority source cohort drift')
    proposed = {(d['arxivId'], h, t) for d in decisions.values() for group in d['groups'] for h, t in itertools.product(group['heads'], group['tails'])}
    queued = {(r['arxivId'], r['headId'], r['tailId']) for r in queue if r['priority'] != 'audit-evidence'}
    if len(queue) != 7 or len(proposed) != 5 or proposed != queued: raise ValueError('Priority label changes differ from review queue')
    stamp = datetime.now(UTC).isoformat(); generated, receipts, ledger, ner, pairs = [], [], [], [], []
    for ref, prior in zip(refs, old):
        annotation, rows = revise(ref, prior, [r for r in before if r['arxivId'] == ref['arxivId']], decisions.get(ref['arxivId']))
        metadata = {'provider': source['provider'], 'model': source['model'], 'promptSha256': c.file_sha256(CONTRACT),
                    'sourceArtifactSha256': c.file_sha256(DECISIONS), 'createdAt': stamp}
        initial = c.make_receipt(annotation, ref, metadata); generated.append(initial)
        checked = copy.deepcopy(annotation); checked['reviewOfSha256'] = initial['contentSha256']
        checked['notes'] += ' Same-session self-review: '+(decisions[ref['arxivId']]['selfReview'] if ref['arxivId'] in decisions else 'Inherited labels/entities/evidence checked for conservation; no semantic relabeling.')
        receipt = c.make_receipt(checked, ref, metadata, previous=initial); receipts.append(receipt)
        for row in rows: row['sourceReceiptSha256'] = receipt['contentSha256']
        nr, pr = parent_stage.candidate_rows(ref, receipt, rows); ner.append(nr)
        lookup = {(r['head']['entityId'], r['tail']['entityId']): r for r in rows}
        for pair in pr:
            support = lookup[pair['head']['entityId'], pair['tail']['entityId']]['support']
            pair.update(taskSubRole=support.get('taskSubRole'), coreferenceEvidence=support.get('coreferenceEvidence', []),
                        coreferenceStatus=support.get('coreferenceStatus'))
        ledger += rows; pairs += pr
    summary = summary_for(refs, ner, pairs, ledger, before_pairs) | {'createdAtUTC': stamp, 'isolation': pilot.read(parent/'summary.json')['isolation'],
        'notice': 'No new representative split or near-duplicate proof. Parent TRAIN identity lock inherited; only current TRAIN artifacts parsed. Five negatives remain quarantined, no accepted negative or training authorization.'}
    if summary['reviewedNewPairs'] != 5 or summary['coreferenceMentionPairs'] != 3 or summary['candidatePairs'] != 684:
        raise ValueError('Review conservation failed')
    inputs = [CONTRACT, DECISIONS, c.ROOT/config['taskGuidelines'], Path(__file__), c.ROOT/'scripts/verify_v2_priority_bundle.py',
              c.ROOT/'tests/test_v2_priority_revision.py', parent/'manifest.json', Path(config['externalAudit']), Path(config['externalQueue'])]
    hashes = {str(p.relative_to(c.ROOT)) if p.is_relative_to(c.ROOT) else str(p): c.file_sha256(p) for p in inputs}
    output.mkdir(parents=True)
    for name, rows in (('references', refs), ('generation_receipts', generated), ('reviewed_receipts', receipts),
                       ('relation_ledger', ledger), ('ner_candidates', ner), ('re_candidates', pairs)):
        c.write_jsonl(output/(name+'.jsonl'), rows)
    c.write_json(output/'summary.json', summary); c.write_json(output/'contract.json', config); c.write_json(output/'production_protection.json', protection)
    shutil.copytree(parent, output/'audit_parent')
    for path in [Path(config['externalAudit']), Path(config['externalQueue']), c.ROOT/config['taskGuidelines'], DECISIONS]:
        shutil.copy2(path, output/path.name)
    checks = output/'check_history'; checks.mkdir()
    for path in ('outputs/v2_entity_completion_preflight_20261010.xml', 'outputs/v2_entity_completion_verified_20261010.xml'):
        shutil.copy2(c.ROOT/path, checks/Path(path).name)
    if test_evidence:
        shutil.copy2(test_evidence, checks/'priority_checks.xml')
    # Source snapshots are for code review; the portable checker does not import ML code.
    snapshot = output/'source_snapshot'; pending = [Path(__file__), Path(parent_stage.__file__),
        c.ROOT/'scripts/verify_v2_priority_bundle.py', c.ROOT/'scripts/train_course_ner.py', c.ROOT/'scripts/train_course_relation.py']
    paths = set(inputs[:5]+[c.CONFIG_PATH, c.SCHEMA_PATH, c.ROOT/'tests/test_v2_priority_revision.py',
        c.ROOT/'tests/test_v2_entity_completion.py', c.ROOT/'tests/test_v2_semantic_revision.py', c.ROOT/'tests/test_v2_evidence_pilot.py',
        c.ROOT/'requirements-validation.txt', c.ROOT/'requirements-training.lock.txt'])
    while pending:
        path = pending.pop()
        if path in paths and (snapshot/path.relative_to(c.ROOT)).exists(): continue
        paths.add(path)
        target = snapshot/path.relative_to(c.ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            modules = ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [a.name for a in node.names] if isinstance(node, ast.Import) else [])
            for module in modules:
                local = c.ROOT/'scripts'/(module.split('.')[0]+'.py')
                if local.exists() and not (snapshot/local.relative_to(c.ROOT)).exists(): pending.append(local)
    for path in paths:
        target = snapshot/path.relative_to(c.ROOT)
        if not target.exists(): target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
    c.write_json(snapshot/'source_bindings.json', {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in paths})
    audit_rows = []
    for row in ledger:
        if row['labelChanged'] or row['supportChanged']:
            audit_rows.append({'arxivId': row['arxivId'], 'headId': row['head']['entityId'], 'headText': row['head']['text'],
                'tailId': row['tail']['entityId'], 'tailText': row['tail']['text'], 'before': row['revisionPriorLabel'], 'after': row['label'],
                'taskRole': row['support']['taskRole'], 'taskSubRole': row['support'].get('taskSubRole'),
                'predicateEvidence': '\n'.join(s['text'] for s in row['support']['predicateSpans']),
                'coreferenceEvidence': '\n'.join(link['antecedentSpan']['text']+' → '+link['anaphorSpan']['text'] for link in row['support'].get('coreferenceEvidence', [])),
                'reason': row['reason']})
    parent_stage.v.write_csv(output/'priority_review.csv', audit_rows)
    body = '<p>仅AI源文复核：5条新增用途、两组共指证据（3提及对）。未训练、未推理、未改V1。</p>'
    body += evidence.table(['项目', '结果'], [['实体/候选对', '177 / 684，未变'], ['RE候选', summary['RECandidatePairs']],
        ['不同论文', summary['totalSourcePapersWithEligibleRE']], ['旧字面去重', '区分大小写50 / 忽略大小写49'],
        ['标签变化', 5], ['争议负例隔离', 5], ['状态', summary['status']]])
    body += '<p>先行句与谓词共同保存；来源+证据组不等于独立事实。标准库重放只验证保存数据及约束，不认证语义或模型准确率。</p>'
    (output/'09_annotation_expansion.html').write_text(evidence.page('V2优先语义裁决与共指证据', body, stamp, ['summary.json', 'priority_review.csv']), encoding='utf-8')
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in protection.items()) or any(c.file_sha256(Path(p) if Path(p).is_absolute() else c.ROOT/p) != sha for p, sha in hashes.items()):
        raise ValueError('Input or production drift')
    c.write_json(output/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'inputSha256': hashes,
        'filesSha256': {p.relative_to(output).as_posix(): c.file_sha256(p) for p in output.rglob('*') if p.is_file()}})
    print(summary); return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, default=OUTPUT); parser.add_argument('--test-evidence', type=Path)
    args = parser.parse_args(); build(args.output, args.test_evidence)
