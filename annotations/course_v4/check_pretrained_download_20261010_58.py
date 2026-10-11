"""Post-run official revision/weight check; not a retroactive inference environment seal."""
import json
import platform
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'.runtime-gliner'))
import course_graph as g

output = ROOT/'kg_datasets/dblp/course_v4_runs/pretrained_runtime_provenance_20261010_58'
if output.exists(): raise FileExistsError('Preserve provenance check')
output.mkdir()
state = {'checkedAtUTC': datetime.now(UTC).isoformat(), 'kind': 'post_run_provenance_not_inference_time_seal', 'status': 'running'}
try:
    config = json.loads((ROOT/'resources/course_pretrained_ner_comparison_v1.json').read_text())
    url = f"https://huggingface.co/api/models/{config['modelId']}/revision/{config['modelRevision']}?blobs=true"
    with urlopen(url, timeout=30) as response: raw = response.read(); status = response.status
    (output/'official_model_metadata.json').write_bytes(raw)
    info = json.loads(raw); weights = ROOT/config['modelDirectory']/'model.safetensors'
    expected = next(f['lfs']['sha256'] for f in info['siblings'] if f['rfilename'] == 'model.safetensors')
    receipt = ROOT/config['modelDirectory']/'.cache/huggingface/download/model.safetensors.metadata'
    lines = receipt.read_text().splitlines()
    assert status == 200 and info['sha'] == config['modelRevision'] == lines[0]
    assert expected == lines[1] == g.c.file_sha256(weights)
    import torch
    state.update(status='passed', metadataURL=url, officialRevision=info['sha'], weightsSha256=expected,
                 metadataSha256=g.c.file_sha256(output/'official_model_metadata.json'), downloadReceiptSha256=g.c.file_sha256(receipt),
                 python=sys.version, platform=platform.platform(), cudaRuntime=torch.version.cuda,
                 gpu=torch.cuda.get_device_name(0), versions={p: version(p) for p in ('torch', 'transformers', 'gliner', 'sentencepiece', 'protobuf')},
                 originalRunModified=False, currentHelperSha256={p: g.c.file_sha256(ROOT/'scripts'/p) for p in ('course_graph.py', 'course_weak.py', 'course_abstract_v1.py')})
except Exception as error:
    state.update(status='failed', errorType=type(error).__name__, error=str(error)); raise
finally:
    state['checkerSha256'] = g.c.file_sha256(Path(__file__))
    g.c.write_json(output/'check.json', state)
print({'provenanceCheck': state['status'], 'originalRunModified': False}, flush=True)
