"""Verify all bounded source receipts and seal an evidence-only author review."""
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import course_graph as g

output = ROOT/'kg_datasets/dblp/course_v4_identity_evidence_20261010_58'
if (output/'manifest.json').exists(): raise FileExistsError('Preserve completed evidence seal')
audit = ROOT/'kg_datasets/dblp/course_v4_identity_alias_audit_20261010_57'; g.verified_files(audit)
read = lambda path: json.loads(path.read_text(encoding='utf-8'))
review = read(output/'review.json'); requests = read(output/'requests.json')
policy = read(output/'policy_and_directory_requests.json'); aliases = g.c.read_jsonl(audit/'changed_rejections.jsonl')
assert len(policy)==6 and len(requests)==2 and len(review['selected'])==4
assert {(r['publicationId'],r['position']) for r in review['selected']}=={(r['publicationId'],r['position']) for r in aliases}
assert all(r['newIdentity'] is None for r in review['selected'])
for record in policy:
    raw = record['text'].encode('utf-8')
    assert len(raw)==record['bytes'] and hashlib.sha256(raw).hexdigest()==record['sha256']
    datetime.fromisoformat(record['requestedAtUTC'])
    if record['url'].endswith('/robots.txt'):
        robots = RobotFileParser(); robots.parse(record['text'].splitlines() if record['status']==200 else [])
        allowed = robots.can_fetch('AI-Literature-KG/course-author-audit58',record['url'].rsplit('/',1)[0]+'/example')
        assert allowed == (record['url'].startswith('https://api.crossref.org/') or record['url'].startswith('https://people.epfl.ch/'))
for i, record in enumerate(requests):
    assert record['status']==200 and record['bytes']==(output/record['rawFile']).stat().st_size
    assert record['rawSha256']==g.c.file_sha256(output/record['rawFile'])
    datetime.fromisoformat(record['requestedAtUTC'])
    fact = review['selected'][0]['evidence'][i]; message=read(output/record['rawFile'])['message']
    assert message['DOI'].casefold()==fact['doi'].casefold()
    author = message['author'][5 if i==0 else 3]
    assert author['given']+' '+author['family']==fact['name'] and author['affiliation'][0]['name']==fact['affiliation']
    assert 'ORCID' not in author
summary = {'checkedAtUTC':datetime.now(UTC).isoformat(),'candidatesReviewed':4,'externalCandidatesProbed':1,
           'directHTTPRequestsRecorded':8,'publisherMetadataRetrieved':2,'identityRecovered':0,'remainingUnresolved':9062,
           'databaseWritten':False,'modelTestContentRead':False,'independentRealWorldVerification':False,
           'notice':'Evidence-only review. Publisher spelling and institution corroboration do not approve an identity link.'}
g.c.write_json(output/'summary.json',summary)
paths = [Path(__file__), ROOT/'annotations/course_v4/collect_author_evidence_20261010_58.py',
         audit/'manifest.json',ROOT/'kg_datasets/dblp/course_v4_identity_crosswalk_20261009_51/manifest.json',Path(g.__file__),Path(g.c.__file__)]
g.c.write_json(output/'manifest.json',{'kind':'bounded_author_authority_evidence_v1',
              'inputSha256':{p.relative_to(ROOT).as_posix():g.c.file_sha256(p) for p in paths},
              'filesSha256':{p.name:g.c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
g.verified_files(output); print(json.dumps(summary),flush=True)
