"""Prepare bounded TRAIN evidence dossiers, not a training or evaluation run."""
import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_graph as g
import course_weak as c
import export_course_evidence as evidence

CONTRACT = c.ROOT/'resources/course_v2_evidence_pilot_v1.json'
OUTPUT = c.ROOT/'kg_datasets/dblp/course_v2_evidence_pilot_20261010'
PROTECTED = [c.ROOT/p for p in (
    'resources/course_graph_quality_v3_runtime.json', 'scripts/course_quality_app.py',
    'resources/course_literature.html', 'kg_datasets/dblp/course_v4_graph_concepts_20261010_58/manifest.json',
    'kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/checkpoint_epoch_04/model.safetensors',
    'kg_datasets/dblp/course_v4_runs/re_entity_development_20261006_15/checkpoint_epoch_03/model.safetensors',
)]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def inventory(refs, receipts):
    if len(refs) != len(receipts):
        raise ValueError('Reference/receipt coverage mismatch')
    documents = []; excluded = []
    for ref, receipt in zip(refs, receipts):
        if (ref['split'] != 'train' or ref['textKind'] != 'abstract'
                or c.canonical_sha256(ref) != c.canonical_sha256(receipt['reference'])
                or g.digest(ref['text']) != ref['textSha256'] or c.validate_receipt(receipt, ref)):
            raise ValueError('Invalid source-bound TRAIN abstract')
        if not c.eligible_tasks(receipt, ref)['ner']:
            excluded.append({'sampleId': ref['sampleId'], 'reason': receipt['annotation']['entityReason']})
            continue
        documents.append((ref, receipt))
    for key in ('sampleId', 'groupId', 'arxivId', 'textSha256'):
        if len({ref[key] for ref in refs}) != len(refs):
            raise ValueError('Duplicate source paper/text: '+key)
    counts = Counter(); papers = {label: set() for label in c.CONFIG['entityLabels']+c.CONFIG['relationLabels']}
    for ref, receipt in documents:
        for item in receipt['annotation']['entities']+receipt['annotation']['relations']:
            counts[item['label']] += 1; papers[item['label']].add(ref['arxivId'])
    return documents, excluded, {'queueDocuments': len(refs), 'NEREligibleDocuments': len(documents),
        'excludedNERDocuments': len(excluded), 'entitySupport': {k: counts[k] for k in c.CONFIG['entityLabels']},
        'relationSupport': {k: counts[k] for k in c.CONFIG['relationLabels']},
        'sourcePapersByClass': {k: len(v) for k, v in papers.items()},
        'completeRelationDocuments': sum(c.eligible_tasks(r, ref)['relation'] for ref, r in documents)}


def check_isolation(refs, split_rows, selected_metadata, supplement_seeds):
    groups = {r['groupId']: r['split'] for r in split_rows}
    publications = {r['publicationId']: r for r in split_rows}
    if len(publications) != len(split_rows):
        raise ValueError('Duplicate split metadata')
    locked = {r['arxivId']: r for r in selected_metadata}
    if len(locked) != len(selected_metadata):
        raise ValueError('Duplicate abstract selection metadata')
    forbidden = {r['arxivId'] for r in selected_metadata if r['split'] != 'train'} | {r['arxivId'] for r in supplement_seeds}
    for ref in refs:
        old = publications.get(ref['publicationId']); selection = locked.get(ref['arxivId'])
        if (ref['split'] != 'train' or groups.get(ref['groupId'], 'train') != 'train'
                or ref['arxivId'] in forbidden
                or (old and (old['split'] != 'train' or old['groupId'] != ref['groupId']))
                or (selection and any(selection[k] != ref[k] for k in ('publicationId', 'groupId', 'split')))):
            raise ValueError('TRAIN paper overlaps or conflicts with held-out metadata')
        # External benchmark sources intentionally have no DBLP split row.
        if old is None and selection is None and (ref['publicationId'] != 'arxiv:'+ref['arxivId'] or ref['groupId'] != 'abstract-paper-'+ref['arxivId']):
            raise ValueError('Unregistered non-benchmark source')
    return {'publicationGroupAndArxivMetadataConflicts': 0,
        'externalTrainOnlyPapers': sum(r['publicationId'] not in publications for r in refs),
        'reservedTestTextOverlapChecked': False,
        'notice': 'Metadata identity isolation, not a new representative split or proof against all semantic/near-duplicate overlap. Reserved test text was not parsed.'}


def select_pilot(documents, strata):
    selected = []; seen = set()
    for name, count in strata.items():
        chosen = []
        for ref, receipt in documents:
            a = receipt['annotation']; labels = Counter(p['label'] for p in a['relations'])
            match = {'evaluation_positive': labels['EVALUATED_ON'] > 0,
                     'explicit_negative': labels['NO_RELATION'] > 0,
                     'dataset_unresolved': any(e['label'] == 'DATASET' for e in a['entities']) and labels['UNRESOLVED'] > 0 and labels['EVALUATED_ON'] == 0}[name]
            if match and ref['arxivId'] not in seen:
                chosen.append((ref, receipt, name)); seen.add(ref['arxivId'])
            if len(chosen) == count:
                break
        if len(chosen) != count:
            raise ValueError('Insufficient distinct source papers for '+name)
        selected.extend(chosen)
    return selected


def title_inventory(ner, pairs, references, split_rows):
    lookup = {r['sampleId']: r for r in references}
    splits = {r['publicationId']: r for r in split_rows}
    if len(lookup) != len(references) or len({r['sampleId'] for r in ner}) != len(ner):
        raise ValueError('Duplicate title reference/input')
    for ref in references:
        old = splits.get(ref['publicationId'])
        if (not old or ref['split'] != 'train' or ref['textKind'] != 'title'
                or old['split'] != 'train' or old['groupId'] != ref['groupId']
                or g.digest(ref['text']) != ref['textSha256']):
            raise ValueError('Invalid canonical TRAIN title')
    for row in ner+pairs:
        ref = lookup.get(row['sampleId'])
        if (not ref or row['text'] != ref['text'] or row['textSha256'] != ref['textSha256']
                or row['referenceSha256'] != c.canonical_sha256(ref) or row['labelSource'] != 'ai_pseudo'):
            raise ValueError('Title row differs from canonical TRAIN reference')
        entities = row['entities'] if 'entities' in row else [row['head'], row['tail']]
        if any(c.span_errors(e, row['text']) or e['label'] not in c.CONFIG['entityLabels'] for e in entities):
            raise ValueError('Invalid title entity span/type')
    if any(p['label'] not in ('USED_FOR', 'EVALUATED_ON', 'NO_RELATION') for p in pairs):
        raise ValueError('Unresolved title pair admitted')
    return {'NERDocuments': len(ner), 'entitySupport': dict(Counter(e['label'] for r in ner for e in r['entities'])),
        'relationPairs': len(pairs), 'relationSupport': dict(Counter(p['label'] for p in pairs))}


def prepare(output=OUTPUT):
    if output.exists():
        raise FileExistsError('Preserve V2 evidence pilot')
    if not output.resolve().is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()):
        raise ValueError('Output outside datasets')
    config = read(CONTRACT)
    if (config['version'] != 'course_v2_evidence_pilot_v1'
            or any(config[k] is not False for k in ('trainingAllowed', 'inferenceAllowed', 'testContentAccessAllowed', 'automaticPromotionAllowed', 'productionMutationAllowed'))
            or config['pilotStrata'] != {'evaluation_positive': 4, 'explicit_negative': 4, 'dataset_unresolved': 4}):
        raise ValueError('V2 data-only contract drift')
    inputs = [CONTRACT, Path(__file__), Path(c.__file__), Path(g.__file__), c.SCHEMA_PATH]
    sources = {}
    for name in ('abstractSource', 'titleSource'):
        folder = c.ROOT/config[name]; sources[name] = folder
        g.verified_files(folder, config[name+'ManifestSha256']); inputs.append(folder/'manifest.json')
    for name in ('splitMetadata', 'abstractSelectionMetadata', 'supplementMetadata', 'reservedTest', 'titleTrainReferences'):
        path = c.ROOT/config[name]
        if c.file_sha256(path) != config[name+'Sha256']:
            raise ValueError('Metadata/reserved test hash drift: '+name)
        inputs.append(path)
    protected = {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in PROTECTED}
    source = sources['abstractSource']; refs = c.read_jsonl(source/'references.jsonl'); receipts = c.read_jsonl(source/'reviewed_receipts.jsonl')
    documents, excluded, totals = inventory(refs, receipts)
    split_rows = c.read_jsonl(c.ROOT/config['splitMetadata'])
    isolation = check_isolation(refs, split_rows, read(c.ROOT/config['abstractSelectionMetadata'])['selected'], read(c.ROOT/config['supplementMetadata'])['seeds'])
    pilot = select_pilot(documents, config['pilotStrata'])
    title = sources['titleSource']; ner = c.read_jsonl(title/'ner_inputs_train.jsonl'); pairs = c.read_jsonl(title/'relation_inputs_train.jsonl')
    title_counts = title_inventory(ner, pairs, c.read_jsonl(c.ROOT/config['titleTrainReferences']), split_rows)
    _, _, pilot_counts = inventory([r for r, _, _ in pilot], [a for _, a, _ in pilot])
    stamp = datetime.now(UTC).isoformat(); output.mkdir(parents=True)
    c.write_json(output/'contract.json', config)
    lock = [{'arxivId': r['arxivId'], 'sampleId': r['sampleId'], 'groupId': r['groupId'], 'textSha256': r['textSha256'],
             'stratum': name, 'upstreamReceiptSha256': a['contentSha256']} for r, a, name in pilot]
    c.write_json(output/'selection_lock.json', {'selectedAtUTC': stamp, 'selected': lock, 'annotationStatus': 'inherited_for_review_not_v2_certified'})
    c.write_jsonl(output/'references.jsonl', [r for r, _, _ in pilot])
    c.write_jsonl(output/'inherited_receipts.jsonl', [a for _, a, _ in pilot])
    c.write_jsonl(output/'source_quarantines.jsonl', excluded)
    dossiers = []
    for ref, receipt, name in pilot:
        a = receipt['annotation']; by_id = {e['entityId']: e for e in a['entities']}
        dossiers.append({'reference': ref, 'stratum': name, 'entities': a['entities'],
            'priorPairs': [p | {'headMention': by_id[p['head']], 'tailMention': by_id[p['tail']]} for p in a['relations']],
            'upstreamReceiptSha256': receipt['contentSha256'], 'reviewStatus': 'pending_source_semantics',
            'trainingAdmitted': False})
    c.write_jsonl(output/'review_dossiers.jsonl', dossiers)
    summary = {'version': config['version'], 'createdAtUTC': stamp, 'status': 'prepared_not_training_ready',
        'abstractInventory': totals, 'titleInventory': title_counts, 'pilotInventory': pilot_counts, 'isolation': isolation,
        'freshlyCollectedPapers': 0, 'newlyAnnotatedPapers': 0, 'pilotReviewPending': len(pilot),
        'inheritedAIReferencesNotHumanGold': True, 'testContentParsed': False, 'trainingExecuted': False, 'modelPromoted': False,
        'next': 'Whole-source semantic review of twelve dossiers, then a separately locked training/evaluation snapshot; no automatic fit.'}
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in protected.items()):
        raise ValueError('V1 protected file changed')
    summary['V1ProtectedFilesUnchanged'] = True
    c.write_json(output/'summary.json', summary); c.write_json(output/'production_protection.json', protected)
    rows = [[label, totals['entitySupport'].get(label, totals['relationSupport'].get(label, 0)), totals['sourcePapersByClass'][label]]
            for label in c.CONFIG['entityLabels']+c.CONFIG['relationLabels']]
    body = '<p>V2首批数据准备；训练、推理和上线均未执行。所有标签来自既有训练侧AI收据，等待原文复核，不是新增金标准。</p>'
    body += evidence.table(['历史摘要类别', '提及/实体对', '不同来源论文'], rows)
    body += evidence.table(['首批论文', '选择分层'], [[r['arxivId'], name] for r, _, name in pilot])
    body += '<p>70篇来源、65篇NER可用、5篇隔离；12篇定向复核并非代表性测试。保留未决，题名和摘要不混标。V1保护文件未变；保留test只读二进制哈希，未解析正文。</p>'
    (output/'09_annotation_expansion.html').write_text(evidence.page('V2证据数据准备与隔离检查', body, stamp, ['summary.json', 'selection_lock.json', 'production_protection.json']), encoding='utf-8')
    c.write_json(output/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui',
        'inputSha256': {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in inputs},
        'filesSha256': {p.name: c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps(summary, ensure_ascii=False))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    prepare(parser.parse_args().output)
