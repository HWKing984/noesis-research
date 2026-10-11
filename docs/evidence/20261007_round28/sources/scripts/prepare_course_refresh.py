"""Reserve grouped holdout IDs before expanded train/dev runs; no new test labels."""
import json
from datetime import UTC, datetime
from pathlib import Path

import course_weak as c

ROOT = Path(__file__).resolve().parents[1]


def select_holdout(corpus, references, count=200):
    if type(count) is not int or count < 1: raise ValueError('Positive holdout size required')
    if len({r['publicationId'] for r in corpus}) != len(corpus): raise ValueError('Duplicate publication')
    used = {r['groupId'] for r in references}
    groups = {}
    for row in corpus:
        if row['split'] == 'test' and row['groupId'] not in used and not row['historicalTrainOnly']:
            groups.setdefault(row['groupId'], []).append(row)
    ranked = sorted(groups, key=lambda gid: c.canonical_sha256(['course-refresh-20261007-28', gid]))
    if len(ranked) < count: raise ValueError('Insufficient unused test groups')
    # One representative per group; no title or old prediction used for selection.
    return [min(groups[gid], key=lambda row: row['publicationId']) for gid in ranked[:count]]


def main():
    output = ROOT / 'kg_datasets/dblp/course_v4_runs/refresh_lock_20261007_28.json'
    if output.exists(): raise FileExistsError('Preserve refresh policy and reserved holdout')
    dataset = ROOT / 'kg_datasets/dblp/course_v4_weak'
    rows = c.read_jsonl(dataset / 'corpus_split_manifest.jsonl')
    refs = c.read_jsonl(dataset / 'references.jsonl')
    selected = select_holdout(rows, refs)
    state = {'createdAtUTC': datetime.now(UTC).isoformat(), 'holdout': selected,
        'holdoutDocuments': len(selected), 'selectionUsesTitleOrPrediction': False,
        'overlapWithOriginalAnnotatedGroups': 0, 'labelsPending': True, 'newTestEvaluated': False,
        'trainingSnapshot': 'kg_datasets/dblp/course_v4_training_inputs_17',
        'inputSha256': {p.relative_to(ROOT).as_posix(): c.file_sha256(p) for p in
            (dataset / 'corpus_split_manifest.jsonl', dataset / 'references.jsonl',
             ROOT / 'kg_datasets/dblp/course_v4_training_inputs_17/manifest.json', Path(__file__))},
        'experiment': 'Expanded training data only; same architectures, settings and dev-selection rules.',
        'NERConfig': {'seed': 20261006, 'batchSize': 8, 'learningRate': 5e-5, 'maxLength': 128, 'epochs': 6},
        'REConfig': {'seed': 20261006, 'batchSize': 8, 'learningRate': 2e-5, 'maxLength': 128, 'epochs': 6,
                     'balancedLoss': True, 'representation': 'entity_markers', 'selection': 'all_class_macro'},
        'promotionPolicy': 'Never replace deployed old graph/model from dev score alone; require new labeled holdout and complete pipeline evaluation.',
        'limitations': ['Dev reused after prior development; scores are development evidence only.',
                       'Reserved corpus already received old-model production inference; not a pristine unseen corpus.',
                       'No independent human/second-model gold; no claimed independent semantic evaluation.',
                       'Rare training support unchanged: DATASET 12, EVALUATED_ON 3.']}
    c.write_json(output, state)
    print(json.dumps({'lock': output.relative_to(ROOT).as_posix(), 'holdoutDocuments': len(selected), 'labelsPending': True}))


if __name__ == '__main__': main()
