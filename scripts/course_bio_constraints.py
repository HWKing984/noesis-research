"""Maximum-emission legal BIO decoding; no learned transitions or test-specific rules."""
import math
import course_weak as c


def legal_bio_labels(logits, offsets):
    labels=c.CONFIG['bioLabels'];classes=len(labels)
    if len(logits)!=len(offsets): raise ValueError('Logits and offsets differ')
    previous=[float('-inf')]*classes;previous[0]=0.0;trace=[]
    for scores,offset in zip(logits,offsets):
        if len(scores)!=classes or any(type(s)not in (float,int) or not math.isfinite(s) for s in scores):
            raise ValueError('Nonfinite or malformed BIO scores')
        current=[float('-inf')]*classes;parents=[0]*classes
        for j,tag in enumerate(labels):
            if offset[0]==offset[1] and j!=0: continue  # special/padding tokens are always O
            allowed=range(classes) if not tag.startswith('I-') else [i for i,t in enumerate(labels) if t in ('B-'+tag[2:],'I-'+tag[2:])]
            best=max(allowed,key=lambda i:previous[i])
            current[j]=previous[best]+scores[j];parents[j]=best
        previous=current;trace.append(parents)
    if not trace:return []
    state=max(range(classes),key=lambda i:previous[i]);result=[]
    for parents in reversed(trace):result.append(state);state=parents[state]
    return list(reversed(result))
