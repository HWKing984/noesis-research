"""Recover exact DBLP author identities from the local XML; never fuzzy-merge names."""
import argparse
import csv
import gzip
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from lxml import etree
import course_weak as c
from process_dblp_ai import LocalDTDResolver, inspect_dtd, clean_text, element_text, RECORD_TAGS

ROOT = Path(__file__).resolve().parents[1]


def resolve_signature(signature, aliases, profiles, redirects):
    keys = set(aliases.get(signature['name'], []))
    resolved = set()
    for key in keys:
        seen = set()
        while key in redirects:
            if key in seen: return {'status':'unresolved_redirect_cycle','keys':sorted(keys)}
            seen.add(key);key=redirects[key]
        if key not in profiles or profiles[key]['disambiguation']:
            return {'status':'unresolved_profile','keys':sorted(keys)}
        resolved.add(key)
    if len(resolved)==1: return {'status':'dblp_homepage_resolved','key':resolved.pop(),'matchedExactName':signature['name']}
    return {'status':'unresolved_ambiguous_alias' if resolved else 'unresolved_no_profile','keys':sorted(keys)}


def scan(source, bibliography, output):
    if output.exists(): raise FileExistsError('Preserve author recovery; use a new output')
    output.mkdir(parents=True)
    state={'status':'running','createdAtUTC':datetime.now(UTC).isoformat(),'recordsScanned':0,'databaseWritten':False}
    c.write_json(output/'status.json',state)
    dtd=inspect_dtd(source)
    with (bibliography/'publications.csv').open(encoding='utf-8-sig',newline='') as stream:
        publications={r['publicationId:ID(Publication)']:r['title'] for r in csv.DictReader(stream)}
    with (bibliography/'persons.csv').open(encoding='utf-8-sig',newline='') as stream:
        persons={r['personId:ID(Person)']:r['name'] for r in csv.DictReader(stream)}
    with (bibliography/'authored.csv').open(encoding='utf-8-sig',newline='') as stream:
        expected={(r[':END_ID(Publication)'],int(r['position:int'])):persons[r[':START_ID(Person)']] for r in csv.DictReader(stream)}
    needed={clean_text(name).casefold() for name in persons.values()}
    inputs={p.relative_to(ROOT).as_posix():c.file_sha256(p) for p in [source,dtd,Path(__file__)]+[bibliography/(f+'.csv') for f in ('publications','persons','authored')]}
    signatures=[];profiles={};redirects={};aliases=defaultdict(set);seen_papers=set()
    try:
        with gzip.open(source,'rb') as stream:
            parser=etree.iterparse(stream,events=('end',),tag=RECORD_TAGS+('person',),load_dtd=True,
                resolve_entities=True,no_network=True,huge_tree=True)
            parser.resolvers.add(LocalDTDResolver(dtd))
            for _,element in parser:
                state['recordsScanned']+=1
                key=element.get('key','')
                if key in publications:
                    if key in seen_papers or element_text(element.find('title'))!=publications[key]:
                        raise ValueError('Duplicate or changed selected raw publication')
                    seen_papers.add(key);position=0
                    for author in element.findall('author'):
                        literal=''.join(author.itertext()).strip()
                        if not literal: continue
                        position+=1
                        if expected.get((key,position))!=clean_text(literal):
                            raise ValueError('Raw author signature differs from sealed bibliography')
                        signatures.append({'publicationId':key,'position':position,'name':literal,'orcid':author.get('orcid','')})
                if element.tag in ('www','person') and key.startswith('homepages/'):
                    cross=element_text(element.find('crossref'))
                    if cross:
                        if key in redirects and redirects[key]!=cross: raise ValueError('Conflicting homepage redirect')
                        redirects[key]=cross
                    names=list(dict.fromkeys(''.join(a.itertext()).strip() for a in element.findall('author') if ''.join(a.itertext()).strip()))
                    if any(clean_text(name).casefold() in needed for name in names):
                        if key in profiles: raise ValueError('Duplicate relevant author profile')
                        profiles[key]={'key':key,'names':names,'orcidURLs':[element_text(u) for u in element.findall('url') if element_text(u).startswith('https://orcid.org/')],
                            'disambiguation':element.get('type')=='disambiguation' or element.get('publtype')=='disambiguation' or any(n.get('type')=='disambiguation' for n in element.findall('note'))}
                        for name in names: aliases[name].add(key)
                element.clear()
                parent=element.getparent()
                while parent is not None and element.getprevious() is not None: del parent[0]
                if state['recordsScanned']%500000==0:
                    print(json.dumps({'recordsScanned':state['recordsScanned'],'selectedPapers':len(seen_papers),'relevantProfiles':len(profiles)}),flush=True)
        if seen_papers!=set(publications) or len(signatures)!=len(expected): raise ValueError('Raw author coverage incomplete')
        counts=Counter()
        for signature in signatures:
            signature['identity']=resolve_signature(signature,aliases,profiles,redirects)
            counts[signature['identity']['status']]+=1
        if any(c.file_sha256(ROOT/p)!=sha for p,sha in inputs.items()): raise ValueError('Source changed during author scan')
        c.write_jsonl(output/'signatures.jsonl',sorted(signatures,key=lambda s:(s['publicationId'],s['position'])))
        c.write_json(output/'profiles.json',profiles)
        c.write_json(output/'redirects.json',redirects)
        c.write_json(output/'summary.json',{'publications':len(seen_papers),'signatures':len(signatures),'relevantProfiles':len(profiles),'identityCounts':dict(counts),
            'exactCaseSensitiveAliases':True,'suffixNumbersPreserved':True,'fuzzyMatching':False,'unknownSignaturesNeverJoined':True,
            'notice':'Identity is DBLP profile authority, not independently verified real-world identity; ORCIDs retained only as source evidence, not merge keys.'})
        state.update(status='completed',finishedAtUTC=datetime.now(UTC).isoformat());c.write_json(output/'status.json',state)
        c.write_json(output/'manifest.json',{'kind':'local_dblp_identity_recovery','inputSha256':inputs,
            'authorityURL':'https://dblp.dagstuhl.de/faq/12451885.html','filesSha256':{p.name:c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
        print(json.dumps({'status':'completed','identityCounts':dict(counts)}),flush=True)
    except Exception as error:
        state.update(status='failed',errorType=type(error).__name__,error=str(error));c.write_json(output/'status.json',state);raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'kg_datasets/dblp/dblp.xml.gz')
    parser.add_argument('--bibliography',type=Path,default=ROOT/'kg_datasets/dblp/processed_ai')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();scan(args.source.resolve(),args.bibliography.resolve(),args.output.resolve())
