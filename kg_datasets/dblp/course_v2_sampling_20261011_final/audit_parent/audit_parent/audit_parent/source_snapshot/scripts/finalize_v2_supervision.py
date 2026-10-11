"""Freeze source-scoped supervision and evidence metadata; never train or promote."""
import argparse
import copy
import hashlib
import itertools
import json
import re
import runpy
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT/'resources/course_v2_supervision_protocol_v1.json'
DECISIONS = ROOT/'annotations/course_v4/v2_supervision_decisions_20261010.json'
OUTPUT = ROOT/'kg_datasets/dblp/course_v2_supervision_protocol_20261010'
NEGATIVES = {('1903.10404', 'e1', 'e4'), ('1903.10404', 'e7', 'e4'), ('1903.10404', 'e9', 'e4'),
             ('2503.03790', 'e11', 'e14'), ('2503.03790', 'e13', 'e12')}
COREFERENCE = {('1606.05250', 'e4', 'e1'), ('1606.05250', 'e4', 'e2'), ('2107.03374', 'e9', 'e5')}
FLAGS = ('trainingAllowed', 'inferenceAllowed', 'testContentAccessAllowed', 'productionMutationAllowed',
         'automaticPromotionAllowed', 'independentHumanGold')


def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def rows(path): return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def key(row): return row['arxivId'], row['head']['entityId'], row['tail']['entityId']


def identity(row):
    result = {k: row[k] for k in ('publicationId', 'groupId', 'textSha256') if row.get(k)}
    if row.get('arxivId'):
        if not isinstance(row['arxivId'], str): raise ValueError('Invalid arXiv identity')
        result['arxivId'] = re.sub(r'v\d+$', '', row['arxivId'].strip().removeprefix('arxiv:'), flags=re.IGNORECASE)
    if any(not isinstance(v, str) or not v.strip() for v in result.values()): raise ValueError('Invalid paper identity')
    return {k: v.strip() for k, v in result.items()}


def validate_partition(assignments, excluded):
    """Metadata-only guard; it does not certify semantic near-duplicate isolation."""
    # shortcut: identity metadata misses paraphrased duplicates; audit them when a fresh evaluation inventory exists.
    forbidden = {(k, v) for row in excluded for k, v in identity(row).items()}
    owners = {}; publications = set()
    for row in assignments:
        if 'text' in row or row.get('split') not in ('train', 'dev', 'test', 'challenge'):
            raise ValueError('Metadata-only partition required')
        ids = identity(row)
        if not {'publicationId', 'groupId'} <= ids.keys() or ids['publicationId'] in publications:
            raise ValueError('Missing or duplicate publication identity')
        publications.add(ids['publicationId'])
        for item in ids.items():
            if row['split'] != 'train' and item in forbidden: raise ValueError('Exposed paper cannot enter new evaluation')
            if item in owners and owners[item] != row['split']: raise ValueError('Paper/group/version overlaps partitions')
            owners[item] = row['split']
    return dict(Counter(row['split'] for row in assignments))


def fine_links(ref, entities, inherited, decisions):
    if len(inherited) != len(decisions): raise ValueError('Coreference chain size drift')
    by_id = {e['entityId']: e for e in entities}; links = []
    for old, decision in zip(inherited, decisions):
        context, antecedent = old['anaphorSpan'], old['antecedentSpan']
        trigger = decision['trigger']; entity = by_id.get(decision['resolvedEntityId'])
        aliases = decision['referentAliasIds']; level = decision['evidenceLevel']
        if (not trigger or context['text'].count(trigger) != 1 or not entity or not aliases
                or len(set(aliases)) != len(aliases) or entity['entityId'] not in aliases
                or level not in ('direct', 'alias', 'discourse_inferred')):
            raise ValueError('Invalid coreference trigger or referent')
        for item in (context, antecedent):
            if ref['text'][item['start']:item['end']] != item['text']: raise ValueError('Context does not match source')
        if any(a not in by_id or by_id[a]['label'] != entity['label'] or not
               antecedent['start'] <= by_id[a]['start'] < by_id[a]['end'] <= antecedent['end'] for a in aliases):
            raise ValueError('Referent or alias outside antecedent')
        start = context['start']+context['text'].index(trigger)
        between = ref['text'][min(entity['end'], start):max(entity['end'], start)]
        if level == 'direct' and re.search(r'[.!?]\s', between): raise ValueError('Cross-sentence reference is not direct')
        if level == 'alias' and trigger not in {by_id[a]['text'] for a in aliases}: raise ValueError('Alias trigger is not an explicit mention')
        links.append({'anaphorContextSpan': copy.deepcopy(context), 'antecedentContextSpan': copy.deepcopy(antecedent),
            'triggerSpan': {'start': start, 'end': start+len(trigger), 'text': trigger},
            'resolvedEntityId': entity['entityId'], 'resolvedEntitySpan': {k: entity[k] for k in ('start', 'end', 'text')},
            'referentAliasIds': aliases, 'evidenceLevel': level, 'kind': old['kind'], 'explanation': old['explanation']})
    return links


def revise(ref, prior, ledger, decision):
    import revise_v2_priority as parent
    parent.parent_stage.candidate_rows(ref, prior, ledger)
    annotation = copy.deepcopy(prior['annotation']); annotation['reviewOfSha256'] = None
    after = copy.deepcopy(ledger); by_key = {key(r)[1:]: r for r in after}
    relations = {(r['head'], r['tail']): r for r in annotation['relations']}
    if decision:
        if (any(decision[k] != value for k, value in (('arxivId', ref['arxivId']), ('textSha256', ref['textSha256']),
                ('upstreamReceiptSha256', prior['contentSha256']))) or not decision['selfReview'].strip()):
            raise ValueError('Unbound supervision decision')
        changed = set()
        for pair in decision['withdrawNegativePairs']:
            pair = tuple(pair); row = by_key.get(pair)
            if not row or key(row) not in NEGATIVES or pair in changed or row['label'] != 'NO_RELATION' or row['candidateEligible']:
                raise ValueError('Negative withdrawal scope drift')
            changed.add(pair); reason = decision['withdrawReason']
            if not reason.strip(): raise ValueError('Missing withdrawal reason')
            relations[pair].update(label='UNRESOLVED', evidence=None, reason=reason)
            row.update(label='UNRESOLVED', evidence=None, reason=reason, candidateEligible=False,
                       quarantineReason='unresolved_after_broad_scope_adjudication')
            row['support']['negativeAdjudication'] = {'decision': 'withdraw_to_unresolved', 'reason': reason,
                'scopeVersion': 'course_v2_supervision_protocol_v1', 'independentGold': False}
        linked = set()
        for group in decision['coreference']:
            if not group['factId'] or group['relationEvidenceLevel'] != 'discourse_inferred': raise ValueError('Invalid relation inference level')
            for pair in itertools.product(group['heads'], group['tails']):
                row = by_key.get(pair)
                if not row or key(row) not in COREFERENCE or pair in linked or row['label'] != 'EVALUATED_ON':
                    raise ValueError('Fine coreference scope drift')
                linked.add(pair)
                row['support']['coreferenceEvidence'] = fine_links(ref, annotation['entities'], row['support']['coreferenceEvidence'], group['links'])
                row['support'].update(coreferenceFactId=group['factId'], relationEvidenceLevel=group['relationEvidenceLevel'])
    annotation['notes'] = 'V2 scope adjudication and fine coreference metadata; AI same-session review, not training or independent gold.'
    errors = parent.c.validate_response(annotation, ref)
    if errors: raise ValueError('; '.join(errors))
    for previous, row in zip(ledger, after):
        row.update(protocolPriorLabel=previous['label'], protocolPriorEvidence=previous['evidence'], protocolPriorReason=previous['reason'],
            protocolPriorSupport=previous['support'], protocolLabelChanged=row['label'] != previous['label'],
            protocolSupportChanged=row['support'] != previous['support'], protocolUpstreamReceiptSha256=prior['contentSha256'])
    return annotation, after


def build(output=OUTPUT, test_evidence=None):
    import revise_v2_priority as parent
    output = Path(output).resolve(); c = parent.c
    if output.exists(): raise FileExistsError('Preserve previous protocol bundle')
    if not output.is_relative_to((ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Output outside datasets')
    if test_evidence:
        suites = ET.parse(test_evidence).getroot()
        if (not list(suites.iter('testsuite')) or any(int(s.get(k, '0')) for s in suites.iter('testsuite') for k in ('errors', 'failures', 'skipped'))
                or 'tests.test_v2_supervision_protocol' not in {t.get('classname') for t in suites.iter('testcase')}):
            raise ValueError('Protocol JUnit is not passing')
    config = read(CONTRACT); old = ROOT/config['parent']
    if config['version'] != 'course_v2_supervision_protocol_v1' or any(config[k] is not False for k in FLAGS): raise ValueError('Data-only contract drift')
    if sha(old/'manifest.json') != config['parentManifestSha256'] or sha(config['externalAudit']) != config['externalAuditSha256']: raise ValueError('Review input drift')
    parent_result = runpy.run_path(str(old/'source_snapshot/scripts/verify_v2_priority_bundle.py'))['verify'](old)
    protection = read(old/'production_protection.json')
    upstream_inputs = read(old/'manifest.json')['inputSha256']
    if any(sha(Path(p) if Path(p).is_absolute() else ROOT/p) != h for p, h in upstream_inputs.items()): raise ValueError('Parent source drift')
    if any(sha(ROOT/p) != h for p, h in protection.items()): raise ValueError('V1 drift')
    refs = rows(old/'references.jsonl'); receipts = rows(old/'reviewed_receipts.jsonl'); before = rows(old/'relation_ledger.jsonl')
    source = read(DECISIONS); decisions = {d['arxivId']: d for d in source['documents']}
    if (source['independent'] is not False or len(source['documents']) != 4
            or set(decisions) != {k[0] for k in NEGATIVES | COREFERENCE}): raise ValueError('Decision cohort drift')
    proposed = {(d['arxivId'], *pair) for d in decisions.values() for pair in d['withdrawNegativePairs']}
    links = {(d['arxivId'], h, t) for d in decisions.values() for group in d['coreference'] for h, t in itertools.product(group['heads'], group['tails'])}
    if proposed != NEGATIVES or links != COREFERENCE: raise ValueError('Decision allowlist drift')
    pilot = read(parent.pilot.CONTRACT)
    metadata_paths = [ROOT/pilot[k] for k in ('splitMetadata', 'abstractSelectionMetadata', 'supplementMetadata')]
    if any(sha(ROOT/pilot[k]) != pilot[k+'Sha256'] for k in ('splitMetadata', 'abstractSelectionMetadata', 'supplementMetadata', 'reservedTest')):
        raise ValueError('Historical metadata or sealed test hash drift')
    train_path = ROOT/pilot['abstractSource']/'references.jsonl'
    parent.g.verified_files(train_path.parent, pilot['abstractSourceManifestSha256'])
    train_refs = rows(train_path)
    if any(r['split'] != 'train' for r in train_refs): raise ValueError('Only TRAIN bodies may be read')
    excluded = [identity(r) | {'origin': 'historical_corpus'} for r in rows(metadata_paths[0])]
    excluded += [identity(r) | {'origin': 'historical_train_abstract'} for r in train_refs]
    excluded += [identity(r) | {'origin': 'historical_abstract_selection'} for r in read(metadata_paths[1])['selected']]
    excluded += [identity(r) | {'origin': 'exposed_supplement_development'} for r in read(metadata_paths[2])['seeds']]
    assignments = [identity(r) | {'split': 'train'} for r in refs]; validate_partition(assignments, excluded)
    stamp = datetime.now(UTC).isoformat(); generated = []; reviewed = []; ledger = []; ner = []; pairs = []
    for ref, prior in zip(refs, receipts):
        annotation, revised = revise(ref, prior, [r for r in before if r['arxivId'] == ref['arxivId']], decisions.get(ref['arxivId']))
        metadata = {'provider': source['provider'], 'model': source['model'], 'promptSha256': sha(CONTRACT), 'sourceArtifactSha256': sha(DECISIONS), 'createdAt': stamp}
        initial = c.make_receipt(annotation, ref, metadata); generated.append(initial)
        checked = copy.deepcopy(annotation); checked['reviewOfSha256'] = initial['contentSha256']
        checked['notes'] += ' Self-review: '+(decisions[ref['arxivId']]['selfReview'] if ref['arxivId'] in decisions else 'Inherited entities, labels and evidence checked unchanged.')
        receipt = c.make_receipt(checked, ref, metadata, previous=initial); reviewed.append(receipt)
        for row in revised: row['sourceReceiptSha256'] = receipt['contentSha256']
        nr, pr = parent.parent_stage.candidate_rows(ref, receipt, revised); ner.append(nr)
        lookup = {key(r): r for r in revised}
        for pair in pr:
            support = lookup[key(pair)]['support']
            pair.update({k: support.get(k, [] if k == 'coreferenceEvidence' else None) for k in
                ('taskSubRole', 'coreferenceEvidence', 'coreferenceStatus', 'coreferenceFactId', 'relationEvidenceLevel')})
        ledger += revised; pairs += pr
    summary = {'status': 'scope_and_evaluation_protocol_frozen_missing_negatives_and_new_evaluation_not_training_ready',
        'documents': len(refs), 'entityMentions': sum(len(r['entities']) for r in ner), 'candidatePairs': len(ledger),
        'relationSupport': {k: sum(r['label'] == k for r in ledger) for k in ('USED_FOR', 'EVALUATED_ON', 'NO_RELATION', 'UNRESOLVED')},
        'RECandidatePairs': len(pairs), 'acceptedNegativePairs': 0, 'withdrawnNegatives': sum(r['protocolLabelChanged'] for r in ledger),
        'totalSourcePapersWithEligibleRE': len({r['arxivId'] for r in pairs}), 'supportGroups': len({r['supportGroup'] for r in pairs}),
        'fineCoreferencePairs': sum(bool(r.get('coreferenceEvidence')) for r in pairs),
        'fineCoreferenceFactChains': len({r['coreferenceFactId'] for r in pairs if r.get('coreferenceFactId')}),
        'protocolFrozen': True, 'evaluationInventoryLocked': False, 'validationDocuments': 0, 'testDocuments': 0,
        'trainingExecuted': False, 'inferenceExecuted': False, 'modelPromoted': False, 'testContentParsed': False, 'independentHumanGold': False,
        'createdAtUTC': stamp, 'notice': 'Metadata exclusion is not semantic near-duplicate proof; no new evaluation inventory or negative support. Fine coreference covers only three mention pairs.'}
    controlled = [CONTRACT, DECISIONS, Path(__file__), ROOT/'tests/test_v2_supervision_protocol.py', ROOT/'docs/course_v2_supervision_scope_v1.md']
    inputs = controlled+[old/'manifest.json', Path(config['externalAudit']), parent.pilot.CONTRACT, train_path]+metadata_paths+[ROOT/pilot['reservedTest']]
    hashes = {str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p): sha(p) for p in inputs}
    output.mkdir(parents=True)
    for name, data in (('references', refs), ('generation_receipts', generated), ('reviewed_receipts', reviewed),
                       ('relation_ledger', ledger), ('ner_candidates', ner), ('re_candidates', pairs), ('historical_exclusions', excluded)):
        c.write_jsonl(output/(name+'.jsonl'), data)
    c.write_json(output/'split_lock.json', {'protocolFrozen': True, 'evaluationInventoryLocked': False, 'assignments': assignments,
        'validation': [], 'test': [], 'challenge': [], 'exclusionsFile': 'historical_exclusions.jsonl',
        'exclusionsSha256': sha(output/'historical_exclusions.jsonl'), 'metadataOnly': True, 'nearDuplicateProof': False})
    c.write_json(output/'summary.json', summary); c.write_json(output/'contract.json', config); c.write_json(output/'production_protection.json', protection)
    c.write_json(output/'parent_replay.json', parent_result)
    shutil.copytree(old, output/'audit_parent')
    shutil.copy2(config['externalAudit'], output/Path(config['externalAudit']).name)
    snapshot = output/'source_snapshot'; shutil.copytree(old/'source_snapshot', snapshot)
    bindings = read(snapshot/'source_bindings.json')
    for p in controlled:
        relative = p.relative_to(ROOT).as_posix(); target = snapshot/relative
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, target); bindings[relative] = sha(p)
    c.write_json(snapshot/'source_bindings.json', bindings)
    if test_evidence:
        (output/'check_history').mkdir(); shutil.copy2(test_evidence, output/'check_history/protocol_checks.xml')
    audit_rows = [{'arxivId': r['arxivId'], 'headId': r['head']['entityId'], 'headText': r['head']['text'], 'tailId': r['tail']['entityId'],
        'tailText': r['tail']['text'], 'before': r['protocolPriorLabel'], 'after': r['label'], 'reason': r['reason'],
        'relationEvidenceLevel': r['support'].get('relationEvidenceLevel'),
        'triggers': ' | '.join(link['triggerSpan']['text'] for link in r['support'].get('coreferenceEvidence', []))}
        for r in ledger if r['protocolLabelChanged'] or r['protocolSupportChanged']]
    parent.parent_stage.v.write_csv(output/'protocol_review.csv', audit_rows)
    body = '<p>AI同会话源文裁决；未训练、未推理、未改V1。5条旧负例撤回未决；85正例保留。</p>'
    body += parent.evidence.table(['项目', '结果'], [['实体 / 候选', '177 / 684'], ['可用负例', 0], ['未决', 599],
        ['精细共指', '3提及对 / 2事实链'], ['评测协议', '已冻结；新验证/测试成员均为0'], ['状态', summary['status']]])
    body += parent.evidence.table(['论文', '主体', '目标', '原标签', '新标签', '最小回指'], [[r[k] for k in
        ('arxivId', 'headText', 'tailText', 'before', 'after', 'triggers')] for r in audit_rows])
    (output/'09_annotation_expansion.html').write_text(parent.evidence.page('V2监督作用域与精细共指', body, stamp,
        ['summary.json', 'protocol_review.csv', 'split_lock.json']), encoding='utf-8')
    if any(sha(ROOT/p) != h for p, h in protection.items()) or any(sha(Path(p) if Path(p).is_absolute() else ROOT/p) != h for p, h in hashes.items()):
        raise ValueError('Input or V1 drift')
    c.write_json(output/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'inputSha256': hashes,
        'filesSha256': {p.relative_to(output).as_posix(): sha(p) for p in output.rglob('*') if p.is_file()}})
    verify(output); return summary


def verify(bundle):
    """Portable stdlib checks certify bindings, not relation semantics or live production."""
    bundle = Path(bundle).resolve(); manifest = read(bundle/'manifest.json'); config = read(bundle/'contract.json')
    parent = bundle/'audit_parent'
    if sha(parent/'manifest.json') != config['parentManifestSha256']: raise ValueError('Parent manifest binding')
    parent_verifier = runpy.run_path(str(parent/'source_snapshot/scripts/verify_v2_priority_bundle.py'))
    result = parent_verifier['verify'](parent)
    passed = set(result['categories'])

    def check(condition, name):
        if not condition: raise ValueError('protocol_'+name)
        passed.add('protocol_'+name)

    for name, digest in manifest['filesSha256'].items():
        path = (bundle/name).resolve()
        check(path.is_relative_to(bundle) and sha(path) == digest, 'file_hashes')
    check(config['version'] == 'course_v2_supervision_protocol_v1' and all(config[k] is False for k in FLAGS), 'authorization')
    check(sha(bundle/Path(config['externalAudit']).name) == config['externalAuditSha256'], 'audit_binding')
    refs = rows(bundle/'references.jsonl'); receipts = rows(bundle/'reviewed_receipts.jsonl'); ner = rows(bundle/'ner_candidates.jsonl')
    ledger = rows(bundle/'relation_ledger.jsonl'); pairs = rows(bundle/'re_candidates.jsonl')
    before = {key(r): r for r in rows(parent/'relation_ledger.jsonl')}; old_pairs = {key(r): r for r in rows(parent/'re_candidates.jsonl')}
    check(refs == rows(parent/'references.jsonl') and len(refs) == len(receipts) == len(ner) == 12, 'reference_conservation')
    parents = {r['reference']['arxivId']: r for r in rows(parent/'reviewed_receipts.jsonl')}
    records = {r['reference']['arxivId']: r for r in receipts}; ref_by_id = {r['arxivId']: r for r in refs}
    canonical = parent_verifier['canonical']
    for ref, receipt, nr in zip(refs, receipts, ner):
        annotation = receipt['annotation']
        check(receipt['reference'] == ref and receipt['labelSource'] == 'ai_pseudo' and annotation['entities'] == parents[ref['arxivId']]['annotation']['entities'], 'receipt_entities')
        expected = {(p['head'], p['tail']) for p in parents[ref['arxivId']]['annotation']['relations']}
        check(len(annotation['relations']) == len(expected) and {(p['head'], p['tail']) for p in annotation['relations']} == expected, 'receipt_candidate_coverage')
        check(receipt['contentSha256'] == canonical({'reference': ref, 'annotation': annotation}) and receipt['initialContentSha256'] ==
              canonical({'reference': ref, 'annotation': receipt['initialAnnotation']}), 'receipt_hashes')
        check(annotation['reviewOfSha256'] == receipt['initialContentSha256'] == receipt['review']['inputContentSha256']
              and receipt['review']['contentSha256'] == receipt['contentSha256'], 'self_review_chain')
        check(nr['entities'] == annotation['entities'] and nr['text'] == ref['text'] and nr['sourceReceiptSha256'] == receipt['contentSha256']
              and nr['trainingAuthorized'] is False, 'ner_export')
    by_key = {key(r): r for r in ledger}
    check(len(by_key) == len(ledger) == 684 and by_key.keys() == before.keys(), 'candidate_conservation')
    for row in ledger:
        previous = before[key(row)]; ref = ref_by_id[row['arxivId']]; receipt = records[row['arxivId']]
        relation = next(p for p in receipt['annotation']['relations'] if (p['head'], p['tail']) == key(row)[1:])
        check(all(row['protocolPrior'+field] == previous[field.lower()] for field in ('Label', 'Evidence', 'Reason', 'Support')), 'prior_ledger')
        check(row['label'] == relation['label'] and row['evidence'] == relation['evidence'] and row['reason'] == relation['reason']
              and row['sourceReceiptSha256'] == receipt['contentSha256'] and row['protocolUpstreamReceiptSha256'] == parents[row['arxivId']]['contentSha256'], 'receipt_ledger')
        check(row['head'] == previous['head'] and row['tail'] == previous['tail'] and row['textSha256'] == ref['textSha256'], 'endpoints')
        check(row['protocolLabelChanged'] is (row['label'] != previous['label']) and row['protocolSupportChanged'] is (row['support'] != previous['support']), 'change_flags')
        if key(row) in NEGATIVES:
            check(previous['label'] == 'NO_RELATION' and row['label'] == 'UNRESOLVED' and row['evidence'] is None
                  and not row['candidateEligible'] and row['support']['negativeAdjudication']['decision'] == 'withdraw_to_unresolved', 'five_withdrawals')
        else:
            check(all(row[k] == previous[k] for k in ('label', 'evidence', 'reason', 'candidateEligible', 'quarantineReason')), 'other_labels_unchanged')
        if key(row) in COREFERENCE:
            links = row['support']['coreferenceEvidence']; old_links = previous['support']['coreferenceEvidence']
            decisions = next(d for d in read(bundle/'source_snapshot/annotations/course_v4/v2_supervision_decisions_20261010.json')['documents'] if d['arxivId'] == row['arxivId'])
            group = decisions['coreference'][0]
            check(links == fine_links(ref, receipt['annotation']['entities'], old_links, group['links']), 'fine_spans_and_referents')
            check(row['support']['relationEvidenceLevel'] == 'discourse_inferred' and row['support']['coreferenceFactId'] == group['factId'], 'inference_levels')
        elif key(row) not in NEGATIVES:
            check(row['support'] == previous['support'], 'other_support_unchanged')
    check({key(r) for r in ledger if r['protocolLabelChanged']} == NEGATIVES and
          {key(r) for r in ledger if r['protocolSupportChanged']} == NEGATIVES | COREFERENCE, 'change_allowlists')
    check(len(pairs) == len({key(r) for r in pairs}) == 85 and {key(r) for r in pairs} == old_pairs.keys(), 'positive_export_conservation')
    for pair in pairs:
        row = by_key[key(pair)]; previous = old_pairs[key(pair)]
        check(all(pair[k] == previous[k] for k in ('text', 'textSha256', 'head', 'tail', 'label', 'evidence', 'reason', 'taskRole', 'supportGroup', 'predicateSpans', 'attribution'))
              and pair['trainingAuthorized'] is False and pair['sourceReceiptSha256'] == row['sourceReceiptSha256'], 'positive_export_binding')
        check(all(pair[k] == row['support'].get(k, [] if k == 'coreferenceEvidence' else None) for k in
              ('taskSubRole', 'coreferenceEvidence', 'coreferenceStatus', 'coreferenceFactId', 'relationEvidenceLevel')), 'auxiliary_export')
    lock = read(bundle/'split_lock.json'); excluded = rows(bundle/lock['exclusionsFile'])
    check(sha(bundle/lock['exclusionsFile']) == lock['exclusionsSha256'] and all('text' not in r for r in excluded+lock['assignments']), 'metadata_only_lock')
    check(lock['protocolFrozen'] is True and lock['metadataOnly'] is True and lock['nearDuplicateProof'] is False
          and lock['evaluationInventoryLocked'] is False and lock['validation'] == lock['test'] == lock['challenge'] == [], 'no_fake_evaluation_inventory')
    check(lock['assignments'] == [identity(r) | {'split': 'train'} for r in refs] and validate_partition(lock['assignments'], excluded) == {'train': 12}, 'train_only_lock')
    summary = read(bundle/'summary.json')
    check(summary['relationSupport'] == {'USED_FOR': 68, 'EVALUATED_ON': 17, 'NO_RELATION': 0, 'UNRESOLVED': 599}
          == {k: sum(r['label'] == k for r in ledger) for k in summary['relationSupport']}, 'label_counts')
    check(summary['documents'] == 12 and summary['entityMentions'] == 177 and summary['candidatePairs'] == 684 and summary['RECandidatePairs'] == 85
          and summary['acceptedNegativePairs'] == 0 and summary['withdrawnNegatives'] == 5 and summary['supportGroups'] == len({r['supportGroup'] for r in pairs}) == 29, 'summary_counts')
    check(summary['totalSourcePapersWithEligibleRE'] == len({r['arxivId'] for r in pairs}) == 11, 'source_papers_eleven')
    check(summary['fineCoreferencePairs'] == 3 and summary['fineCoreferenceFactChains'] == len({r['coreferenceFactId'] for r in pairs if r.get('coreferenceFactId')}) == 2, 'fact_chains')
    check(all(summary[k] is False for k in ('trainingExecuted', 'inferenceExecuted', 'modelPromoted', 'testContentParsed', 'independentHumanGold', 'evaluationInventoryLocked'))
          and summary['validationDocuments'] == summary['testDocuments'] == 0 and summary['protocolFrozen'] is True, 'no_model_or_eval_claim')
    check(read(bundle/'production_protection.json') == read(parent/'production_protection.json'), 'protection_record_not_live_proof')
    for name, digest in read(bundle/'source_snapshot/source_bindings.json').items():
        path = (bundle/'source_snapshot'/name).resolve()
        check(path.is_relative_to(bundle/'source_snapshot') and sha(path) == digest, 'source_snapshot')
    return {'status': 'passed', 'assertionCategories': len(passed), 'categories': sorted(passed), 'RECandidatePairs': 85,
        'acceptedNegativePairs': 0, 'evaluationInventoryLocked': False, 'semanticAccuracyCertified': False, 'liveProductionVerified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, default=OUTPUT); parser.add_argument('--test-evidence', type=Path); parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.verify) if args.verify else build(args.output, args.test_evidence), ensure_ascii=False, indent=2))
