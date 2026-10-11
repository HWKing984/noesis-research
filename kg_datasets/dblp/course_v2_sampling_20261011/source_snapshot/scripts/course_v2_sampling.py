"""Metadata-only sampled inventory. No abstracts, labels, inference or training."""
import json
import random
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

import course_v2_admission as admission
import course_v2_identity as identity

META = {'arxivId', 'sourceURL', 'title'}
METHOD = 'python_random_sample_without_replacement_publication_group_v1'


class Listing(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []; self.row = None; self.title_depth = 0; self.depth = 0
        self.title_parts = []; self.all_parts = []; self.has_abstract = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs); classes = attrs.get('class', '').split()
        if 'abstract' in classes: self.has_abstract = True
        if tag == 'dt': self.row = {}
        if tag == 'a' and self.row is not None:
            path = attrs.get('href', '')
            if re.fullmatch(r'/abs/\d{4}\.\d{5}(?:v\d+)?', path):
                value = identity.canonical_arxiv('https://arxiv.org'+path)
                self.row.update(arxivId=value, sourceURL='https://arxiv.org/abs/'+value)
        if tag == 'div':
            self.depth += 1
            if 'list-title' in classes: self.title_depth = self.depth; self.title_parts = []

    def handle_endtag(self, tag):
        if tag == 'div':
            if self.title_depth == self.depth and self.title_depth:
                if self.row is None: raise ValueError('Listing title without identity')
                self.row['title'] = re.sub(r'^Title:\s*', '', ' '.join(' '.join(self.title_parts).split()))
                self.title_depth = 0
            self.depth -= 1
        if tag == 'dd':
            if self.row is None or set(self.row) != META or not self.row['title']: raise ValueError('Incomplete metadata record')
            self.rows.append(self.row); self.row = None

    def handle_data(self, data):
        self.all_parts.append(data)
        if self.title_depth: self.title_parts.append(data)


def parse_listing(payload):
    parser = Listing(); parser.feed(payload.decode('utf-8'))
    total = re.search(r'Total of\s+(\d+)\s+entries', ' '.join(parser.all_parts))
    if parser.has_abstract or not total or not parser.rows: raise ValueError('Expected metadata-only listing, not abstracts')
    if len({r['arxivId'] for r in parser.rows}) != len(parser.rows): raise ValueError('Duplicate listing identities')
    return int(total[1]), parser.rows


def population(pages, protocol, excluded, aliases):
    raw = []; total = None; offset = 0
    for page in pages:
        url = urlsplit(page['sourceURL']); expected = urlsplit(protocol['sourceURL'])
        query = parse_qs(url.query)
        if (url.scheme != 'https' or url.netloc != expected.netloc or url.path != expected.path
                or query != {'skip': [str(offset)], 'show': [str(protocol['pageSize'])]}):
            raise ValueError('Listing source/pagination drift')
        size, records = parse_listing(page['payload'])
        if total is not None and size != total: raise ValueError('Listing count changed during acquisition')
        total = size
        if len(records) != min(protocol['pageSize'], total-offset): raise ValueError('Incomplete listing page')
        raw.extend(records); offset += len(records)
    if offset != total or len({r['arxivId'] for r in raw}) != total: raise ValueError('Population listing incomplete or duplicate')
    forbidden = {(k,v) for r in excluded for k,v in identity.identity(r, aliases).items()}
    eligible = []; rejected = []
    for row in raw:
        if set(row) != META: raise ValueError('Metadata-only population required')
        candidate = {'publicationId':'arxiv:'+row['arxivId'], 'groupId':'arxiv-group:'+row['arxivId'],
            'arxivId':row['arxivId'], 'sourceURL':row['sourceURL'], 'split':'dev'}
        ids = identity.identity(candidate, aliases)
        if any(pair in forbidden for pair in ids.items()): rejected.append(row)
        else:
            # Exposure matches were checked against the normalized set above; do not
            # re-normalize the 20,138-row historical inventory once per new paper.
            identity.validate_partition([candidate], [], aliases); eligible.append(row)
    return sorted(eligible, key=lambda r:r['arxivId']), rejected, total


def draw(rows, protocol):
    if (protocol['samplingMethod'] != METHOD or type(protocol['seed']) is not int
            or any(type(protocol[k]) is not int or protocol[k] < 1 for k in ('devSize','testSize'))
            or protocol['challengeSize'] != 0): raise ValueError('Fixed representative sampling contract required')
    ids = [r['arxivId'] for r in rows]
    if ids != sorted(set(ids)) or not rows: raise ValueError('Sorted unique population required')
    count = protocol['devSize']+protocol['testSize']
    if count > len(rows): raise ValueError('Insufficient fresh population, do not shrink or resample silently')
    selected = random.Random(protocol['seed']).sample(rows, count)
    return [{'publicationId':'arxiv:'+r['arxivId'], 'groupId':'arxiv-group:'+r['arxivId'],
        'arxivId':r['arxivId'], 'sourceURL':r['sourceURL'],
        'split':'dev' if n < protocol['devSize'] else 'test'} for n,r in enumerate(selected)]


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()]


def validate_frame(folder, excluded, aliases):
    folder = Path(folder).resolve(); protocol = read(folder/'sampling_protocol.json'); receipt = read(folder/'sampling_frame.json')
    if (protocol['version'] != 'course_v2_sampling_v1' or protocol['population'] != admission.FRAME['population']
            or protocol['sourceURL'] != 'https://arxiv.org/list/'+protocol['category']+'/'+protocol['listingMonth']):
        raise ValueError('Unsupported sampling protocol')
    if (receipt['protocolSha256'] != admission.digest(protocol) or receipt['exclusionsSha256'] != admission.digest(excluded)
            or receipt['aliasIndexSha256'] != admission.digest(aliases)): raise ValueError('Sampling context changed')
    pages = []
    for page in receipt['sourcePages']:
        pages.append({'sourceURL':page['sourceURL'], 'payload':admission.artifact(folder, page)})
    eligible, rejected, total = population(pages, protocol, excluded, aliases)
    if (rows(folder/'population.jsonl') != eligible or rows(folder/'excluded_population.jsonl') != rejected
            or receipt['eligiblePopulationCount'] != len(eligible) or receipt['sourceListingCount'] != total
            or receipt['excludedPopulationCount'] != len(rejected) or receipt['populationSha256'] != admission.digest(eligible)):
        raise ValueError('Sampling population/source mismatch')
    selected = draw(eligible, protocol)
    if read(folder/'selected_members.json') != selected or receipt['selectedMembersSha256'] != admission.digest(selected):
        raise ValueError('Seed/method/member draw mismatch')
    if (receipt['selectionCounts'] != {'dev':protocol['devSize'],'test':protocol['testSize'],'challenge':0}
            or receipt['seed'] != protocol['seed'] or receipt['samplingMethod'] != protocol['samplingMethod']
            or receipt['inclusionProbabilities'] != {'dev':protocol['devSize']/len(eligible), 'test':protocol['testSize']/len(eligible)}
            or receipt['samplingFrameLocked'] is not True or receipt['fullDBLPRepresentative'] is not False
            or receipt['contentBindingCompleted'] is not False or receipt['evaluationAuthorized'] is not False):
        raise ValueError('Sampling status/probabilities mismatch')
    return selected, receipt


def prelock(folder, train, excluded, aliases):
    selected, receipt = validate_frame(folder, excluded, aliases)
    if any(r.get('split') != 'train' for r in train): raise ValueError('Parent inventory must remain train-only')
    frame = admission.FRAME | {'samplingFrameLocked':True, 'samplingFrameSha256':admission.digest(receipt),
        'notice':read(Path(folder)/'sampling_protocol.json')['scope']}
    return admission.prelock(train+selected, excluded, aliases, frame)


def validate_lock(folder, lock, excluded, aliases):
    train = [r for r in lock['assignments'] if r['split']=='train']
    expected = prelock(folder, train, excluded, aliases)
    # Content hashes may be added after metadata sampling; identities/members may not change.
    plain = [dict(r) for r in lock['assignments']]
    for row in plain:
        if row['split'] != 'train': row.pop('textSha256', None)
    if admission.prelock(plain,excluded,aliases,lock['samplingFrame']) != expected:
        raise ValueError('Content lock does not belong to verified sample')


def bind_content(folder, lock, bindings, excluded, aliases, root):
    validate_lock(folder,lock,excluded,aliases)
    return admission.bind_content(lock,bindings,excluded,aliases,root)


def finalize(folder, lock, bindings, excluded, aliases, root):
    validate_lock(folder,lock,excluded,aliases)
    return admission.finalize(lock,bindings,excluded,aliases,root)
