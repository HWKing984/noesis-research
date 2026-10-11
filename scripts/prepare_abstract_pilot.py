"""Compile explicit AI excerpt annotations with parent Unicode offsets; never copy title labels."""
import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC,datetime
from pathlib import Path

import course_weak as c
import course_graph as g
from compile_course_ai import compile_decisions

def build(sources,decisions_path,output):
    if output.exists():raise FileExistsError('Preserve pilot annotation run')
    g.verified_files(sources)
    records={r['arxivId']:r for r in c.read_jsonl(sources/'abstracts.jsonl')}
    decisions=json.loads(decisions_path.read_text(encoding='utf-8'))
    groups={r['publicationId']:r for r in c.read_jsonl(c.ROOT/'kg_datasets/dblp/course_v4_weak/corpus_split_manifest.jsonl')}
    source_hash=c.file_sha256(sources/'manifest.json')
    contract={'version':'course-abstract-excerpt-1','textKind':'abstract_excerpt','offsetUnit':'unicode_codepoint',
        'split':'train_only_exposed_targeted_pilot','selectionBias':'AI-selected clear examples, not independent or representative evaluation',
        'entities':'Named models or distinctive algorithms/architectures/techniques as METHOD; explicit task descriptions as TASK; named datasets/benchmarks as DATASET. Generic models, tasks, datasets, URLs and pronouns excluded.',
        'relationScope':c.CONFIG['relationPairs'],'coreference':'Do not import entities or facts from outside the model-input excerpt.',
        'reviewPolicy':'Same-session AI self-review only; not independent human annotation.',
        'sourceAbstracts':'Original whole abstracts retained; excerpt offsets identify input boundaries and absolute entity positions.',
        'trainingPolicy':'Separate abstract unit; not accepted silently by title-only training loader; strict token alignment preflight required.',
        'modelPromotionAllowed':False}
    references=[];semantic=[]
    for row in decisions['decisions']:
        source=records[row['arxivId']];text=row['excerpt'];abstract=source['abstract']
        if source['split']!='train' or not source['title_match'] or abstract.count(text)!=1:
            raise ValueError('Excerpt absent, repeated, mismatched or not train-only')
        if source['publicationId'] in groups and groups[source['publicationId']]['split']!='train':
            raise ValueError('Existing paper belongs to held-out split')
        if source['content_hash']!=hashlib.sha256(abstract.encode()).hexdigest():raise ValueError('Parent abstract drifted')
        start=abstract.index(text);sample='sample-'+c.canonical_sha256([row['arxivId'],start,start+len(text),source['content_hash']])[:20]
        reference={'sampleId':sample,'publicationId':source['publicationId'],'arxivId':row['arxivId'],
            'text':text,'textSha256':hashlib.sha256(text.encode()).hexdigest(),'textKind':'abstract_excerpt',
            'groupId':groups[source['publicationId']]['groupId'] if source['publicationId'] in groups else 'abstract-paper-'+row['arxivId'],
            'split':'train','schemaVersion':contract['version'],'contractSha256':c.canonical_sha256(contract),
            'sourceCorpusSha256':source_hash,'sourceAbstractSha256':source['content_hash'],
            'sourceURL':source['source_url'],'sourceOffset':{'start':start,'end':start+len(text)},'sourceOrigin':source['sourceOrigin']}
        references.append(reference)
        semantic.append({'sampleId':sample,'entityStatus':'complete','entityReason':'','entities':row['entities'],
            'groupMentions':[],'relationStatus':'complete','relationReason':'','relations':row['relations'],
            'notes':'Explicit same-session AI labels on a targeted train-only source excerpt; no title label reuse or human-gold claim.'})
    responses=compile_decisions(semantic,references)
    if len({r['sampleId'] for r in references})!=len(references):raise ValueError('Duplicate excerpts')
    output.mkdir(parents=True)
    c.write_json(output/'contract.json',contract);c.write_jsonl(output/'references.jsonl',references)
    prompt='Annotate all explicit METHOD, TASK, named DATASET mentions in exact abstract excerpt, with Unicode boundaries and every typed candidate relation. Use unresolved for ambiguity; never invent outside context.'
    c.write_json(output/'prompt.json',{'instruction':prompt,'contract':contract})
    metadata={'provider':decisions['provider'],'model':decisions['model'],'promptSha256':c.file_sha256(output/'prompt.json'),
        'sourceArtifactSha256':c.file_sha256(decisions_path),'createdAt':datetime.now(UTC).isoformat()}
    receipts=[c.make_receipt(response,ref,metadata) for response,ref in zip(responses,references)]
    c.write_jsonl(output/'generation_receipts.jsonl',receipts)
    c.write_jsonl(output/'annotation_jobs.jsonl',[c.model_payload(r) for r in references])
    summary={'documents':len(references),'paperGroups':len({r['groupId'] for r in references}),
        'entityCounts':dict(Counter(e['label'] for r in responses for e in r['entities'])),
        'relationCounts':dict(Counter(e['label'] for r in responses for e in r['relations'])),
        'labelSource':'ai_pseudo','selfReviewCompleted':False,'independentHumanGold':False,
        'trainingExecuted':False,'modelPromoted':False,'testSourcesUsed':False,'titleLabelsReused':False}
    c.write_json(output/'summary.json',summary)
    inputs=[sources/'manifest.json',decisions_path,Path(__file__),c.ROOT/'scripts/compile_course_ai.py',c.ROOT/'scripts/course_weak.py',c.SCHEMA_PATH]
    c.write_json(output/'manifest.json',{'inputSha256':{p.relative_to(c.ROOT).as_posix():c.file_sha256(p) for p in inputs},
        'filesSha256':{p.name:c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True);parser.add_argument('--decisions',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();build(args.sources.resolve(),args.decisions.resolve(),args.output.resolve())
