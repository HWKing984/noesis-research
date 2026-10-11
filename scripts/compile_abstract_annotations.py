"""Compile explicit per-document AI labels; no global dictionary, negative filling or test access."""
import argparse
import json
import re
from collections import Counter
from datetime import UTC,datetime
from pathlib import Path

import course_graph as g
import course_weak as c

def mention_spans(text,declared,excluded=()):
    protected=[m.span() for m in re.finditer(r'https?://\S+',text)]
    for literal in excluded:
        hits=list(re.finditer(re.escape(literal),text))
        if not hits:raise ValueError('Declared exclusion absent')
        protected += [m.span() for m in hits]
    spans=[]
    for label,literals in declared.items():
        if label not in c.CONFIG['entityLabels']:raise ValueError('Unknown entity class')
        if len(set(literals))!=len(literals):raise ValueError('Repeated declared literal')
        for literal in literals:
            if not isinstance(literal,str) or not literal.strip():raise ValueError('Empty declared literal')
            # Double dashes are punctuation; a single word-hyphen is part of a name.
            hits=list(re.finditer(r'(?<!\w)(?<!\w-)'+re.escape(literal)+r'(?!\w|-\w)',text))
            if not hits:raise ValueError('Declared literal absent or not standalone: '+literal)
            for m in hits:
                if any(m.start()<end and start<m.end() for start,end in protected):continue
                spans.append({'start':m.start(),'end':m.end(),'text':m.group(),'label':label})
    selected=[]
    for span in sorted(spans,key=lambda s:(-(s['end']-s['start']),s['start'])):
        overlaps=[p for p in selected if span['start']<p['end'] and p['start']<span['end']]
        if any(span['label']!=p['label'] for p in overlaps):raise ValueError('Declared cross-type overlap')
        if not overlaps:selected.append(span)
    return [{'entityId':f'e{i}',**s} for i,s in enumerate(sorted(selected,key=lambda s:s['start']),1)]

def annotate(decision,reference):
    text=reference['text'];entities=mention_spans(text,decision['mentions'],decision.get('excludedLiterals',[]))
    group=[]
    for literal in decision.get('groupMentions',[]):
        hits=list(re.finditer(re.escape(literal),text))
        if len(hits)!=1:raise ValueError('Group literal absent or ambiguous')
        m=hits[0];group.append({'groupId':f'g{len(group)+1}','start':m.start(),'end':m.end(),'text':literal,'label':'METHOD'})
    candidates=c.candidate_pairs(entities);positive={}
    for item in decision.get('positives',[]):
        hits=list(re.finditer(re.escape(item['evidence']),text))
        if len(hits)!=1:raise ValueError('Evidence absent or ambiguous')
        evidence=hits[0]
        def endpoint(role):
            matches=[e for e in entities if e['text']==item[role] and evidence.start()<=e['start'] and e['end']<=evidence.end()]
            occurrence=item.get(role+'Occurrence')
            if occurrence is None and len(matches)!=1:raise ValueError('Endpoint ambiguous within evidence: '+item[role])
            if occurrence is not None and (type(occurrence)is not int or not 1<=occurrence<=len(matches)):raise ValueError('Invalid endpoint occurrence')
            return matches[(occurrence or 1)-1]['entityId']
        pair=(endpoint('head'),endpoint('tail'))
        if pair in positive or candidates.get(pair)!=item['label']:raise ValueError('Duplicate or invalid typed positive')
        positive[pair]={'label':item['label'],'evidence':{'start':evidence.start(),'end':evidence.end(),'text':evidence.group()},
            'reason':'Explicit AI decision supported by the preserved excerpt; no label inferred from entity types.'}
    relations=[{'head':h,'tail':t,**positive.get((h,t),{'label':'UNRESOLVED','evidence':None,
        'reason':'AI deliberately deferred this pair; coexistence, alias identity, coreference or training mention alone does not certify the scoped relation.'})} for h,t in candidates]
    entity_status=decision.get('entityStatus','complete');relation_status='unresolved' if entity_status!='complete' or any(r['label']=='UNRESOLVED' for r in relations) else 'complete'
    response={'sampleId':reference['sampleId'],'textSha256':reference['textSha256'],'reviewOfSha256':None,
        'entityStatus':entity_status,'entityReason':decision.get('reason',''),'entities':entities,'groupMentions':group,
        'relationStatus':relation_status,'relationReason':'Pending semantic pair review; not a negative example.' if relation_status=='unresolved' else '',
        'relations':relations,'notes':'Same-session AI whole-abstract candidate. '+decision.get('notes','')}
    errors=c.validate_response(response,reference)
    if errors:raise ValueError('; '.join(errors))
    return response

def compile_batch(queue,decisions_path,output):
    if output.exists():raise FileExistsError('Preserve annotated batch')
    g.verified_files(queue)
    source=json.loads(decisions_path.read_text(encoding='utf-8'));references=c.read_jsonl(queue/'train_references.jsonl')
    lookup={r['arxivId']:r for r in references};decisions=source['documents']
    if len(decisions)!=len(lookup) or {d['arxivId'] for d in decisions}!=set(lookup):raise ValueError('Decisions must cover entire train queue exactly')
    responses=[annotate(d,lookup[d['arxivId']]) for d in decisions]
    output.mkdir(parents=True)
    c.write_json(output/'annotation_policy.json',{'policy':source['policy'],'testAccessed':False,'devAccessed':False,
        'nerStatus':'AI completeness claim, not independent semantic validation','relationStatus':'Unresolved candidates retained and excluded from negative training',
        'iterationCompact':{'goal':'Whole-abstract DATASET support with source-bound labels','baseline':'8 excerpts do not annotate whole abstracts',
            'mistakeBudget':'No source rewriting, title label copying, implied evaluated-on labels or negative filling',
            'nextExperiment':'Same-session AI review and strict token/offset round-trip preflight','promotionAllowed':False}})
    metadata={'provider':source['provider'],'model':source['model'],'promptSha256':c.file_sha256(output/'annotation_policy.json'),
        'sourceArtifactSha256':c.file_sha256(decisions_path),'createdAt':datetime.now(UTC).isoformat()}
    refs=[lookup[d['arxivId']] for d in decisions]
    receipts=[c.make_receipt(r,ref,metadata) for r,ref in zip(responses,refs)]
    c.write_jsonl(output/'references.jsonl',refs);c.write_jsonl(output/'generation_receipts.jsonl',receipts)
    summary={'judgedDocuments':len(refs),'completeNERClaims':sum(r['entityStatus']=='complete' for r in responses),
        'groupQuarantinedDocuments':sum(bool(r['groupMentions']) for r in responses),
        'entityCounts':dict(Counter(e['label'] for r in responses for e in r['entities'])),
        'relationCounts':dict(Counter(e['label'] for r in responses for e in r['relations'])),
        'selfReviewed':False,'trainingExecuted':False,'modelPromoted':False,'testEvaluated':False}
    c.write_json(output/'summary.json',summary)
    inputs=[queue/'manifest.json',decisions_path,Path(__file__),c.ROOT/'scripts/course_weak.py',c.SCHEMA_PATH]
    c.write_json(output/'manifest.json',{'inputSha256':{p.relative_to(c.ROOT).as_posix():c.file_sha256(p) for p in inputs},
        'filesSha256':{p.name:c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps(summary))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--queue',type=Path,required=True);parser.add_argument('--decisions',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();compile_batch(args.queue.resolve(),args.decisions.resolve(),args.output.resolve())
