"""Strict, uncertainty-aware positive-triple scoring for textscope V2.

Point scores are conditional on the adjudicated scope, not complete-pipeline F1.
Unknown exact-reference pairs are reported, never treated as known negatives.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

POSITIVE = {'USED_FOR', 'EVALUATED_ON'}


def endpoint_key(row):
    h, t = row['head'], row['tail']
    return (row['arxivId'], h['start'], h['end'], h['label'],
            t['start'], t['end'], t['label'])


def prf(tp, fp, fn):
    denominator = 2 * tp + fp + fn
    return {'TP': tp, 'FP': fp, 'FN': fn,
            'precision': tp / (tp + fp) if tp + fp else (0.0 if fn else None),
            'recall': tp / (tp + fn) if tp + fn else None,
            'f1': 2 * tp / denominator if denominator else None}


def score(reference, predictions):
    pairs = {endpoint_key(r): r for r in reference}
    if len(pairs) != len(reference):
        raise ValueError('Duplicate reference endpoints')
    paper_ids = {r['arxivId'] for r in reference}
    positive_reference = {(endpoint_key(r), r['label']) for r in reference if r['label'] in POSITIVE}
    unknown = {endpoint_key(r) for r in reference if r['label'] == 'UNRESOLVED'}
    raw = []
    for p in predictions:
        if p['arxivId'] not in paper_ids:
            raise ValueError('Prediction outside fixed evaluated paper scope')
        if p['label'] not in POSITIVE | {'NO_RELATION'}:
            raise ValueError('Invalid prediction relation label')
        if p['label'] in POSITIVE:
            raw.append((endpoint_key(p), p['label']))
    predicted = set(raw)
    # An impossible type direction is a real strict error, not an uncertainty mask.
    compatible = lambda item: item[0][3] == 'METHOD' and item[0][6] == {'USED_FOR':'TASK','EVALUATED_ON':'DATASET'}[item[1]]
    masked = {item for item in predicted if item[0] in unknown and compatible(item)}
    scored = predicted - masked
    true = scored & positive_reference
    wrong = scored - positive_reference
    missed = positive_reference - scored
    metrics = prf(len(true), len(wrong), len(missed))
    per_class = {}
    for label in sorted(POSITIVE):
        per_class[label] = prf(sum(x[1] == label for x in true),
                               sum(x[1] == label for x in wrong),
                               sum(x[1] == label for x in missed))
    total_predictions = len(predicted)
    upper_tp = len(true) + len(masked)
    upper_gold = len(positive_reference) + len(masked)
    bounds = {
        'precisionLower': len(true)/total_predictions if total_predictions else None,
        'precisionUpper': upper_tp/total_predictions if total_predictions else None,
        'recallConservativeLower': len(true)/(len(positive_reference)+len(unknown)) if positive_reference or unknown else None,
        'recallUpper': upper_tp/upper_gold if upper_gold else None,
        'note': 'Conservative bounds within the fixed annotated entity-pair universe, relative to AI entity references; not independent semantic accuracy.'
    }
    return {'scope': 'adjudicated_reference_scope_only',
            'referenceComplete': not unknown,
            'fullPipelineF1': metrics['f1'] if not unknown else None,
            'conditionalPositiveMetrics': metrics, 'perClassConditionalMetrics': per_class,
            'positiveReferenceTriples': len(positive_reference),
            'referencePairs': len(reference), 'maskedReferencePairs': len(unknown),
            'referencePairCoverage': (len(reference)-len(unknown))/len(reference) if reference else None,
            'maskedPredictionCount': len(masked), 'allPositivePredictionCount': total_predictions,
            'duplicatePredictionCount': len(raw)-len(predicted),
            'maskedReferencePairsByPossibleClass': dict(Counter('USED_FOR' if r['tail']['label']=='TASK' else 'EVALUATED_ON' for r in reference if r['label']=='UNRESOLVED')),
            'fullUniverseBounds': bounds,
            'warning': 'Do not call conditional F1 complete end-to-end F1 while masked references remain.'}


def read(path):
    return [json.loads(x) for x in Path(path).read_text(encoding='utf-8-sig').splitlines() if x.strip()]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--predictions', required=True)
    args = parser.parse_args()
    print(json.dumps(score(read(args.reference), read(args.predictions)), ensure_ascii=False, indent=2))
