"""Course-only weak supervision contract, leakage controls and strict span agreement.

AI receipts detect content drift; they do not authenticate a provider or certify
semantic truth. No function marks an AI annotation as human gold.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / 'resources/course_v4_config.json'
SCHEMA_PATH = ROOT / 'schemas/annotation_course_v4.schema.json'
CONFIG = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA)
if (SCHEMA['$defs']['entity']['properties']['label']['enum'] != CONFIG['entityLabels'] or
        SCHEMA['$defs']['relation']['properties']['label']['enum'] != CONFIG['relationLabels']):
    raise ValueError('Course schema and configuration disagree')
HASH_PATTERN = re.compile(r'^[0-9a-f]{64}$')
METADATA_KEYS = {'provider','model','promptSha256','sourceArtifactSha256','createdAt'}


def canonical_sha256(value) -> str:
    serialized = json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024*1024):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(''.join(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n' for row in rows),encoding='utf-8')


def group_corpus(rows: list[dict], near_pairs: list[tuple[str,str]]) -> dict[str,str]:
    ids = [r['publicationId'] for r in rows]
    if len(set(ids)) != len(ids) or any(not isinstance(pid,str) or not pid for pid in ids):
        raise ValueError('Corpus publication IDs must be nonempty and unique')
    parent = {pid:pid for pid in ids}

    def find(pid):
        while parent[pid] != pid:
            parent[pid] = parent[parent[pid]]
            pid = parent[pid]
        return pid

    def join(left,right):
        a,b = find(left),find(right)
        parent[max(a,b)] = min(a,b)

    seen = {}
    for row in sorted(rows,key=lambda r:r['publicationId']):
        title = ' '.join(re.findall(r'\w+',unicodedata.normalize('NFKC',row['text']).casefold()))
        for key in (('legacy',row['groupId']),('title',title),('doi',row['doi'].strip().casefold())):
            if not key[1]:
                continue
            if key in seen:
                join(row['publicationId'],seen[key])
            else:
                seen[key] = row['publicationId']
    for left,right in near_pairs:
        if left not in parent or right not in parent:
            raise ValueError('Near-duplicate pair references an unknown publication')
        join(left,right)
    return {pid:'paper-group-'+hashlib.sha256(find(pid).encode()).hexdigest()[:20] for pid in sorted(ids)}


def assign_splits(rows,groups,train_only_ids,*,seed=None) -> dict[str,str]:
    seed = CONFIG['seed'] if seed is None else seed
    ids = {r['publicationId'] for r in rows}
    if set(groups) != ids or not set(train_only_ids) <= ids:
        raise ValueError('Split IDs and exposure IDs must belong to the corpus')
    forced = {groups[pid] for pid in train_only_ids}
    ratios = CONFIG['splitRatios']
    assigned = {}
    for group in sorted(set(groups.values())):
        value = int(hashlib.sha256(f'{seed}:split:{group}'.encode()).hexdigest(),16)/(1<<256)
        assigned[group] = ('train' if group in forced or value < ratios['train'] else
                           'dev' if value < ratios['train']+ratios['dev'] else 'test')
    return {pid:assigned[groups[pid]] for pid in sorted(ids)}


def select_cohort(rows,splits,train_only_ids,*,counts=None,seed=None) -> list[dict]:
    counts = CONFIG['sampleCounts'] if counts is None else counts
    seed = CONFIG['seed'] if seed is None else seed
    ids = {r['publicationId'] for r in rows}
    if (set(counts) != {'train','dev','test'} or set(splits) != ids or not set(train_only_ids) <= ids or
            any(type(n) is not int or n < 0 for n in counts.values()) or
            any(splits[pid] != 'train' for pid in train_only_ids) or
            not set(splits.values()) <= set(counts)):
        raise ValueError('Invalid cohort counts, splits or train-only exposure')
    selected = []
    for split in ('train','dev','test'):
        pool = [r for r in rows if splits[r['publicationId']]==split]
        required = [r for r in pool if r['publicationId'] in train_only_ids]
        if len(required) > counts[split] or len(pool) < counts[split]:
            raise ValueError(f'Cannot meet {split} quota without dropping exposed rows or inventing samples')
        ranked = sorted((r for r in pool if r['publicationId'] not in train_only_ids),
                        key=lambda r:hashlib.sha256(f"{seed}:sample:{r['publicationId']}".encode()).hexdigest())
        selected.extend(sorted(required+ranked[:counts[split]-len(required)],key=lambda r:r['publicationId']))
    return selected


def make_reference(row: dict, group: str, split: str, corpus_hash: str) -> dict:
    if split not in CONFIG['splitRatios'] or not HASH_PATTERN.fullmatch(corpus_hash):
        raise ValueError('Invalid source hash or split')
    return {'sampleId':'sample-'+hashlib.sha256(row['publicationId'].encode()).hexdigest()[:20],
            'publicationId':row['publicationId'],'text':row['text'],'textKind':CONFIG['textKind'],
            'textSha256':hashlib.sha256(row['text'].encode()).hexdigest(),'groupId':group,'split':split,
            'schemaVersion':CONFIG['version'],'contractSha256':file_sha256(SCHEMA_PATH),
            'configSha256':file_sha256(CONFIG_PATH),'sourceCorpusSha256':corpus_hash,
            'metadata':{key:copy.deepcopy(row[key]) for key in ('year','type','doi','topics','ambiguityFlags')}}


def model_payload(reference: dict) -> dict:
    return {key:reference[key] for key in ('sampleId','text','textSha256')}


def span_errors(span,text) -> list[str]:
    if type(span['start']) is not int or type(span['end']) is not int or not 0 <= span['start'] < span['end'] <= len(text):
        return ['invalid Unicode character span']
    return [] if text[span['start']:span['end']] == span['text'] else ['span text differs from original text']


def candidate_pairs(entities) -> dict[tuple[str,str],str]:
    return {(head['entityId'],tail['entityId']):label for head in entities for tail in entities
            for label,pair in CONFIG['relationPairs'].items() if [head['label'],tail['label']]==pair}


def validate_response(response,reference) -> list[str]:
    errors = [f"{'/'.join(map(str,e.absolute_path))}: {e.message}" for e in VALIDATOR.iter_errors(response)]
    if errors:
        return errors
    if response['sampleId'] != reference['sampleId'] or response['textSha256'] != reference['textSha256']:
        errors.append('sample identity or text hash differs from canonical reference')
    text = reference['text']
    for key,prefix,id_key in (('entities','e','entityId'),('groupMentions','g','groupId')):
        items = response[key]
        for index,item in enumerate(items,1):
            errors.extend(span_errors(item,text))
            if item[id_key] != f'{prefix}{index}':
                errors.append('mention IDs must follow contiguous source order')
        if any(a['end'] > b['start'] for a,b in zip(items,items[1:])):
            errors.append('mentions must be sorted and nonoverlapping')
    spans = sorted(response['entities']+response['groupMentions'],key=lambda e:e['start'])
    if any(a['end'] > b['start'] for a,b in zip(spans,spans[1:])):
        errors.append('entity and group mentions cannot overlap')
    for scope in ('entity','relation'):
        if response[scope+'Status']=='unresolved' and not response[scope+'Reason'].strip():
            errors.append(scope+' unresolved requires a reason')
    candidates = candidate_pairs(response['entities'])
    entities = {e['entityId']:e for e in response['entities']}
    annotated = {}
    for relation in response['relations']:
        pair = (relation['head'],relation['tail'])
        if pair not in candidates or pair in annotated:
            errors.append('invalid or duplicate directed relation candidate')
            continue
        annotated[pair] = relation['label']
        if relation['label'] not in {candidates[pair],'NO_RELATION','UNRESOLVED'}:
            errors.append('relation label incompatible with entity types')
        if not relation['reason'].strip():
            errors.append('relation requires a nonempty reason')
        evidence = relation['evidence']
        if evidence is None:
            if relation['label'] != 'UNRESOLVED':
                errors.append('resolved relation requires evidence')
        else:
            errors.extend(span_errors(evidence,text))
            if evidence['start'] > min(entities[pair[0]]['start'],entities[pair[1]]['start']) or evidence['end'] < max(entities[pair[0]]['end'],entities[pair[1]]['end']):
                errors.append('relation evidence must cover both endpoints')
    if response['entityStatus']=='complete' and set(annotated) != set(candidates):
        errors.append('complete entities require a decision for every scoped relation candidate')
    if response['relationStatus']=='complete' and (response['entityStatus']!='complete' or set(annotated)!=set(candidates) or 'UNRESOLVED' in annotated.values()):
        errors.append('relation completeness requires complete entities, all pairs and no unresolved relation')
    return errors


def metadata_errors(metadata) -> list[str]:
    if not isinstance(metadata,dict) or set(metadata) != METADATA_KEYS:
        return ['unexpected AI provenance fields']
    errors = []
    if any(not isinstance(metadata[key],str) or not metadata[key].strip() for key in ('provider','model')):
        errors.append('AI provider and model must be stated; use explicit unknown if unavailable')
    for key in ('promptSha256','sourceArtifactSha256'):
        if key=='promptSha256' and metadata['provider']=='legacy_ai_artifact' and metadata[key] is None:
            continue  # The original prompt was not provided; never invent its hash.
        if not isinstance(metadata[key],str) or not HASH_PATTERN.fullmatch(metadata[key]):
            errors.append('invalid AI provenance hash')
    try:
        if datetime.fromisoformat(metadata['createdAt'].replace('Z','+00:00')).tzinfo is None:
            raise ValueError('timezone required')
    except (ValueError,TypeError,AttributeError):
        errors.append('AI provenance requires an ISO timestamp with timezone')
    return errors


def content_sha256(annotation,reference) -> str:
    return canonical_sha256({'reference':reference,'annotation':annotation})


def make_receipt(response,reference,metadata,*,previous=None) -> dict:
    errors = validate_response(response,reference)+metadata_errors(metadata)
    if errors:
        raise ValueError('; '.join(errors))
    if previous is None:
        if response.get('reviewOfSha256') is not None:
            errors.append('generation cannot claim a previous review hash')
    else:
        errors.extend(validate_receipt(previous,reference))
        if errors:
            raise ValueError('; '.join(errors))
        if previous['review'] is not None:
            errors.append('This version supports one generation and one review; retain later revisions separately')
        if response.get('reviewOfSha256') != previous['contentSha256']:
            errors.append('AI review must bind the exact previous annotation content')
    if errors:
        raise ValueError('; '.join(errors))
    digest = content_sha256(response,reference)
    return {'reference':copy.deepcopy(reference),'annotation':copy.deepcopy(response),'labelSource':'ai_pseudo',
            'initialAnnotation':copy.deepcopy(response if previous is None else previous['initialAnnotation']),
            'initialContentSha256':digest if previous is None else previous['initialContentSha256'],
            'contentSha256':digest,'generation':copy.deepcopy(metadata if previous is None else previous['generation']),
            'review':None if previous is None else {'provenance':copy.deepcopy(metadata),
                'inputContentSha256':previous['contentSha256'],'contentSha256':digest}}


def validate_receipt(receipt,reference) -> list[str]:
    expected = {'reference','annotation','initialAnnotation','labelSource','initialContentSha256','contentSha256','generation','review'}
    if not isinstance(receipt,dict) or set(receipt)!=expected:
        return ['unexpected receipt fields']
    errors = validate_response(receipt['annotation'],reference)+metadata_errors(receipt['generation'])
    errors.extend(validate_response(receipt['initialAnnotation'],reference))
    if errors:
        return errors
    if (receipt['initialAnnotation']['reviewOfSha256'] is not None or
            receipt['initialContentSha256']!=content_sha256(receipt['initialAnnotation'],reference)):
        errors.append('initial AI annotation snapshot or hash changed')
    if receipt['reference'] != reference or receipt['labelSource']!='ai_pseudo':
        errors.append('canonical metadata or AI-only label source changed')
    for key in ('initialContentSha256','contentSha256'):
        if not isinstance(receipt[key],str) or not HASH_PATTERN.fullmatch(receipt[key]):
            errors.append('invalid receipt content hash')
    digest = content_sha256(receipt['annotation'],reference)
    if receipt['contentSha256']!=digest:
        errors.append('annotation content drifted from receipt')
    review = receipt['review']
    if review is None:
        if receipt['initialContentSha256']!=digest or receipt['annotation'].get('reviewOfSha256') is not None:
            errors.append('generation receipt must preserve initial content')
    elif not isinstance(review,dict) or set(review)!={'provenance','inputContentSha256','contentSha256'}:
        errors.append('unexpected AI review fields')
    else:
        errors.extend(metadata_errors(review['provenance']))
        if (review['contentSha256']!=digest or review['inputContentSha256']!=receipt['annotation'].get('reviewOfSha256') or
                review['inputContentSha256']!=receipt['initialContentSha256']):
            errors.append('AI review is not bound to input and final content')
    return errors


def eligible_tasks(receipt,reference) -> dict[str,bool]:
    valid = not validate_receipt(receipt,reference)
    ner = valid and receipt['review'] is not None and receipt['annotation']['entityStatus']=='complete' and not receipt['annotation']['groupMentions']
    return {'ner':bool(ner),'relation':bool(ner and receipt['annotation']['relationStatus']=='complete')}


def align_bio(offsets,entities,text) -> list[int]:
    for entity in entities:
        if span_errors(entity,text):
            raise ValueError('Cannot align invalid entity span')
    if any(a['end'] > b['start'] for a,b in zip(entities,entities[1:])):
        raise ValueError('Cannot align unsorted or overlapping entities')
    labels = []
    covered = {i:[] for i in range(len(entities))}
    last_end = 0
    for start,end in offsets:
        if start==end==0:
            labels.append(-100)
            continue
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text) or start < last_end:
            raise ValueError('Invalid tokenizer Unicode offsets')
        last_end = end
        hits = [i for i,e in enumerate(entities) if start < e['end'] and e['start'] < end]
        if not hits:
            labels.append(0)
            continue
        i = hits[0];entity = entities[i]
        if len(hits)!=1 or start < entity['start'] or end > entity['end']:
            raise ValueError('Entity boundary cuts through a tokenizer token')
        prefix = 'B-' if not covered[i] else 'I-'
        labels.append(CONFIG['bioLabels'].index(prefix+entity['label']))
        covered[i].append((start,end))
    if any(not covered[i] or covered[i][0][0]!=e['start'] or covered[i][-1][1]!=e['end'] or
           any(text[a[1]:b[0]].strip() for a,b in zip(covered[i],covered[i][1:])) for i,e in enumerate(entities)):
        raise ValueError('Entity truncated or not fully represented by tokenizer offsets')
    return labels


def entity_agreement(predictions,references) -> dict:
    predicted,expected = set(predictions),set(references)
    true_positive = len(predicted & expected)
    return {'evaluationTarget':CONFIG['evaluationTarget'],'truePositive':true_positive,
            'predicted':len(predicted),'reference':len(expected),
            'precision':true_positive/len(predicted) if predicted else None,
            'recall':true_positive/len(expected) if expected else None,
            'f1':2*true_positive/(len(predicted)+len(expected)) if predicted or expected else None}
