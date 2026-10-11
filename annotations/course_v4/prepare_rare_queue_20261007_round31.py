"""Reserve benchmark-title candidates before annotation; keywords are not labels."""
import json
import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import course_weak as c

def main(output):
    if output.exists(): raise FileExistsError('Preserve reserved queue')
    corpus=ROOT/'kg_datasets/dblp/processed_ai/publications.csv'
    splits=ROOT/'kg_datasets/dblp/course_v4_weak/corpus_split_manifest.jsonl'
    refs=[ROOT/'kg_datasets/dblp'/p/'references.jsonl' for p in ('course_v4_weak','course_v4_holdout_20261007_29')]
    excluded={r['publicationId'] for p in refs for r in c.read_jsonl(p)}
    groups={r['publicationId']:r for r in c.read_jsonl(splits)}
    excluded_groups={groups[p]['groupId'] for p in excluded}
    pattern=re.compile(r'\b(?:CIFAR[ -]?(?:10|100)|MNIST|ImageNet|SQuAD|GLUE|COCO|KITTI|Cityscapes|PASCAL[ -]VOC|MovieLens|MIMIC[ -]?(?:III|IV)|Cora|Citeseer|UCF[ -]?101|WMT[ -]?\d+|CoNLL[ -]?\d+)\b',re.I)
    rows=[]
    with corpus.open(encoding='utf-8-sig',newline='') as stream:
        publications=[{'publicationId':r['publicationId:ID(Publication)'],'text':r['title']} for r in csv.DictReader(stream)]
    assert len(publications)==20000 and {r['publicationId'] for r in publications}==set(groups)
    for row in publications:
        group=groups[row['publicationId']]
        if group['groupId'] in excluded_groups: continue
        matches=list(pattern.finditer(row['text']))
        if matches:
            rows.append({'publicationId':row['publicationId'],'groupId':group['groupId'],'split':group['split'],
                'text':row['text'],'miningMatches':[{'start':m.start(),'end':m.end(),'text':m.group()} for m in matches],
                'annotationStatus':'pending','labels':None})
    assert not {r['groupId'] for r in rows}&excluded_groups
    group_splits={}
    for row in rows:
        assert group_splits.setdefault(row['groupId'],row['split'])==row['split']
        assert all(row['text'][m['start']:m['end']]==m['text'] for m in row['miningMatches'])
    output.mkdir()
    for split in ('train','dev','test'):
        c.write_jsonl(output/(split+'_candidates.jsonl'),[r for r in rows if r['split']==split])
    result={'counts':dict(Counter(r['split'] for r in rows)),'annotated':False,'trainingExecuted':False,
        'policy':'Existing group split fixed before labels. Exclude all prior annotation and closed holdout groups. Keyword matches are mining hints, not DATASET or EVALUATED_ON labels.',
        'decoderDecision':'rejected: dev micro F1 regressed; DATASET dev F1 unchanged at 1/3',
        'corpusDocuments':len(publications),'inputSha256':{p.relative_to(ROOT).as_posix():c.file_sha256(p) for p in [corpus,splits,*refs,Path(__file__)]}}
    c.write_json(output/'summary.json',result)
    c.write_json(output/'manifest.json',{'filesSha256':{p.name:c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args().output.resolve())
