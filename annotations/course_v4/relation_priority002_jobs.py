"""Replay the explicit train-only title selection, not semantic AI annotation."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_weak as c
from train_course_ner import verify_files
from prepare_course_weak import verify_dataset

SELECTED = '''4152fad07f88dabc29f9 ce4f4b7f722715636877 f0f1cb8a7cbb36f9bfe0
e5067ea6166807e7658d a2763e935ff89cc2f10e 733cd0fe508c8d67a8c8
e16787a3e0d5f3f69119 8d8c233a329fe6cc004d 311cb1ed53c99dafcd7f
cc55f3e34f6f4b2a134a a53e5bd5ef0bc14054e8 95d5dd73313e388f078d
387b3765cc7e28914a15 de089502a0204f5ec85e 836a2db5203ba688798b
ce39355f46f7c85b80b4 4d161ce9c31cf0477001 42f54fff6bd123c8f226
5a8571b62840b7a7a8cc 8579e55f5304e7d7f4d3 120725376486636fb088
e8ea14a44e289e88a0ed 5092ab68204e3e4cb412 f4f63dcba713225d1053
b538c8259df364dc6f90'''.split()


def prepare():
    dataset = ROOT / 'kg_datasets/dblp/course_v4_weak'
    snapshot = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_09'
    output = ROOT / 'kg_datasets/dblp/course_v4_runs/relation_priority002_jobs'
    if output.exists():
        raise FileExistsError('Preserve selected jobs; choose a new selection version')
    verify_files(snapshot)
    refs = {r['sampleId']: r for r in verify_dataset(dataset)}
    pending = {r['sampleId']: r for r in c.read_jsonl(snapshot / 'pending_generation.jsonl')}
    annotated = {r['reference']['sampleId'] for r in c.read_jsonl(snapshot / 'receipts.jsonl')}
    ids = ['sample-' + suffix for suffix in SELECTED]
    if len(ids) != 25 or len(set(ids)) != 25:
        raise ValueError('Explicit selection must contain 25 unique IDs')
    for sample in ids:
        if (sample not in pending or sample in annotated or refs[sample]['split'] != 'train'
                or pending[sample] != c.model_payload(refs[sample])):
            raise ValueError('Selection must be unannotated canonical train titles')
    output.mkdir(parents=True, exist_ok=False)
    c.write_jsonl(output / 'jobs.jsonl', [pending[s] for s in ids])
    c.write_json(output / 'manifest.json', {
        'kind': 'explicit_train_only_role_priority_selection', 'documents': 25,
        'sourceSnapshotManifestSha256': c.file_sha256(snapshot / 'manifest.json'),
        'sourceDatasetManifestSha256': c.file_sha256(dataset / 'manifest.json'),
        'selectionCodeSha256': c.file_sha256(Path(__file__)),
        'modelCallExecutedBySelector': False, 'semanticLabelsCreatedBySelector': False,
        'notice': 'Purposive train-only sampling after dev error analysis; not random, blind or unbiased. No dev/test titles included. Jobs contain only anonymous ID, original title and title hash.',
        'filesSha256': {'jobs.jsonl': c.file_sha256(output / 'jobs.jsonl')}})
    return output


if __name__ == '__main__':
    print(prepare())
