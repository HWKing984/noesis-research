import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import collect_v2_dev as d


def payload(identifier='2502.00001v2',title='Synthetic title',abstract='Synthetic abstract &amp; evidence.'):
    return ('<meta name="citation_arxiv_id" content="'+identifier+'">'
            '<meta name="citation_title" content="'+title+'">'
            '<meta name="citation_abstract" content="'+abstract+'">').encode()


def test_official_metadata_retains_version_and_exact_decoded_text():
    row=d.parse(payload(),{'arxivId':'2502.00001'},'Synthetic title')
    assert row['sourceArxivVersion']=='2502.00001v2'
    assert row['text']=='Synthetic abstract & evidence.'


@pytest.mark.parametrize('fault',['wrong_identity','wrong_title','missing_abstract','duplicate_abstract','invalid_utf8'])
def test_source_errors_reject_no_fallback(fault):
    body=payload()
    if fault=='wrong_identity':body=payload(identifier='2502.00002')
    elif fault=='wrong_title':body=payload(title='Different title')
    elif fault=='missing_abstract':body=body.replace(b'citation_abstract',b'other')
    elif fault=='duplicate_abstract':body+=b'<meta name="citation_abstract" content="extra">'
    else:body+=b'\xff'
    with pytest.raises((ValueError,UnicodeDecodeError)):
        d.parse(body,{'arxivId':'2502.00001'},'Synthetic title')


def test_existing_acquisition_is_preserved(tmp_path):
    with pytest.raises(FileExistsError):d.collect(tmp_path/'unused_bundle',tmp_path)
