"""Prepare isolated whole-abstract jobs, retaining paper splits and rejecting overlength."""
import csv
import hashlib
import json
import os
import sys
from collections import Counter,defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import course_graph as g
import course_weak as c
from fetch_abstract_pilot import normalize_title

def main():
    source=ROOT/'kg_datasets/dblp/course_abstract_pages_20261008_32'
    output=ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32'
    if output.exists():raise FileExistsError('Preserve queued data')
    g.verified_files(source)
    records=c.read_jsonl(source/'abstracts.jsonl')
    split_file=ROOT/'kg_datasets/dblp/course_v4_weak/corpus_split_manifest.jsonl'
    publication_file=ROOT/'kg_datasets/dblp/processed_ai/publications.csv'
    splits={r['publicationId']:r for r in c.read_jsonl(split_file)}
    by_title=defaultdict(list)
    with publication_file.open(encoding='utf-8-sig',newline='') as stream:
        for r in csv.DictReader(stream):by_title[normalize_title(r['title'])].append(splits[r['publicationId:ID(Publication)']])
    os.environ.setdefault('HF_HUB_OFFLINE','1')
    from transformers import BertTokenizerFast
    tokenizer=BertTokenizerFast.from_pretrained(ROOT/'kg_datasets/models/scibert_24f92d32',local_files_only=True,do_lower_case=True)
    contract={'version':'course-whole-abstract-1','textKind':'abstract','offsetUnit':'unicode_codepoint',
        'entityLabels':c.CONFIG['entityLabels'],'bioLabels':c.CONFIG['bioLabels'],'relationPairs':c.CONFIG['relationPairs'],
        'splitPolicy':'Original paper-group split. Cached exposed sources train-only; any existing held-out conflict is quarantined. All excerpts inherit parent group.',
        'annotationPolicy':'Fresh AI annotations required. Do not copy title/excerpt labels to whole abstracts. Pronoun-dependent or ambiguous relations unresolved, not negative.',
        'normalization':'Exact extracted abstract metadata Unicode text retained; no title concatenation or whitespace rewriting.',
        'maxTokens':512,'overlengthPolicy':'Reject without truncation; raw source retained for later explicit windowing.',
        'annotationSource':'ai_pseudo_not_independent_human_gold','promotionAllowed':False,
        'testPolicy':'Test jobs only reserved; no model inference, fitting, selection or test label generation in this step.'}
    refs=[];excluded=[];seen=set()
    for row in records:
        abstract=row['abstract'];key=row['arxivId']
        if key in seen or not row['title_match'] or hashlib.sha256(abstract.encode()).hexdigest()!=row['content_hash']:
            raise ValueError('Duplicate, mismatched or drifted abstract')
        seen.add(key)
        linked=by_title.get(normalize_title(row['title']),[])
        if row['publicationId'] in splits:linked=linked+[splits[row['publicationId']]]
        if any(r['split']!=row['split'] for r in linked):
            excluded.append({'arxivId':key,'reason':'existing_paper_split_conflict','sourceSplit':row['split']});continue
        encoded=tokenizer(abstract,add_special_tokens=True,truncation=False)
        if len(encoded['input_ids'])>512:
            excluded.append({'arxivId':key,'reason':'overlength_no_truncation','tokens':len(encoded['input_ids']),'split':row['split']});continue
        group=splits[row['publicationId']]['groupId'] if row['publicationId'] in splits else (linked[0]['groupId'] if linked else 'abstract-paper-'+key)
        refs.append({'sampleId':'sample-'+c.canonical_sha256(['whole_abstract',key,row['content_hash']])[:20],
            'publicationId':row['publicationId'],'arxivId':key,'text':abstract,'textKind':'abstract','textSha256':row['content_hash'],
            'sourceURL':row['source_url'],'sourceOrigin':row['sourceOrigin'],'groupId':group,'split':row['split'],
            'schemaVersion':contract['version'],'contractSha256':c.canonical_sha256(contract),
            'sourceCorpusSha256':c.file_sha256(source/'manifest.json'),'tokens':len(encoded['input_ids']),'annotationStatus':'pending'})
    groups={}
    for ref in refs:
        if groups.setdefault(ref['groupId'],ref['split'])!=ref['split']:raise ValueError('Cross-split paper group')
    output.mkdir(parents=True);c.write_json(output/'contract.json',contract)
    for split in ('train','dev','test'):
        queue=[r for r in refs if r['split']==split]
        c.write_jsonl(output/(split+'_references.jsonl'),queue)
        c.write_jsonl(output/(split+'_jobs.jsonl'),[c.model_payload(r) for r in queue])
    c.write_jsonl(output/'excluded.jsonl',excluded)
    summary={'usableAbstracts':len(refs),'bySplit':dict(Counter(r['split'] for r in refs)),'excluded':len(excluded),
        'exclusionReasons':dict(Counter(r['reason'] for r in excluded)),'annotated':False,'trainingExecuted':False,
        'testEvaluated':False,'maxTokens':max((r['tokens'] for r in refs),default=0),'modelPromoted':False}
    c.write_json(output/'summary.json',summary)
    inputs=[source/'manifest.json',split_file,publication_file,Path(__file__),ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt',ROOT/'kg_datasets/models/scibert_24f92d32/config.json']
    c.write_json(output/'manifest.json',{'inputSha256':{p.relative_to(ROOT).as_posix():c.file_sha256(p) for p in inputs},
        'filesSha256':{p.name:c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps(summary))

if __name__=='__main__':main()
