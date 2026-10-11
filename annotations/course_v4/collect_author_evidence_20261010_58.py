"""Two publisher metadata requests only; DBLP and ORCID robots prohibit their pages."""
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import course_weak as c

output = ROOT/'kg_datasets/dblp/course_v4_identity_evidence_20261010_58'
if output.exists(): raise FileExistsError('Preserve author evidence; use a new output')
output.mkdir(parents=True)
requests = []
for i, doi in enumerate(('10.1109/IJCNN60899.2024.10651323', '10.1109/KSE59128.2023.10299416'), 1):
    url = 'https://api.crossref.org/works/'+doi
    row = {'url': url, 'requestedAtUTC': datetime.now(UTC).isoformat()}
    try:
        with urlopen(Request(url, headers={'User-Agent': 'AI-Literature-KG/course-author-audit58 (bounded course metadata research)', 'Accept': 'application/json'}), timeout=20) as response:
            assert response.url.startswith('https://api.crossref.org/')
            raw = response.read(1024*1024+1)
            if len(raw)>1024*1024: raise ValueError('Oversized response')
            body = json.loads(raw)
            if body['status']!='ok' or body['message']['DOI'].casefold()!=doi.casefold(): raise ValueError('DOI response mismatch')
            filename = f'crossref_{i:02d}.json'; (output/filename).write_bytes(raw)
            row.update(status=response.status, finalURL=response.url, rawFile=filename, rawSha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
            print(json.dumps({'doi': doi, 'author': body['message'].get('author', [])}), flush=True)
    except HTTPError as error:
        raw = error.read(1024*1024+1); filename=f'crossref_{i:02d}_error.txt'; (output/filename).write_bytes(raw)
        row.update(status=error.code, error=str(error), rawFile=filename, rawSha256=hashlib.sha256(raw).hexdigest())
    except Exception as error: row.update(status='failed', errorType=type(error).__name__, error=str(error))
    requests.append(row); c.write_json(output/'requests.json', requests)
    if i==1: time.sleep(1)
