"""Conservative graph enrichment: DBLP profile identities and typed exact vocabulary aliases."""
import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import course_graph as g

ROOT=g.ROOT


def concept_key(name, entity_type):
    if entity_type not in ('METHOD','TASK','DATASET') or not isinstance(name,str) or not name.strip():
        raise ValueError('Concept needs a typed nonempty literal')
    field={'METHOD':'method','TASK':'task','DATASET':'dataset'}[entity_type]
    literal=name.casefold()
    for group in g.TERMINOLOGY['aliases']:
        if field in group['fields'] and literal in group['terms']:
            return group['terms'][0],'controlled_vocabulary_v1'
    return literal,'casefold_only_no_semantic_merge'


def person_identity(signature):
    identity=signature['identity']
    if identity['status']=='dblp_homepage_resolved': return identity['key']
    # ponytail: unresolved identities are signature-local; add reviewed linking only with source evidence.
    return 'unresolved-signature:'+json.dumps([signature['publicationId'],signature['position']],ensure_ascii=False)


def enrich(base, identities, output):
    if output.exists(): raise FileExistsError('Preserve enriched bundle')
    original=g.verify_bundle(base);author_manifest=g.verified_files(identities)
    signatures=g.c.read_jsonl(identities/'signatures.jsonl')
    profiles=json.loads((identities/'profiles.json').read_text(encoding='utf-8'))
    inputs={p.relative_to(ROOT).as_posix():g.c.file_sha256(p) for p in (base/'manifest.json',identities/'manifest.json',Path(__file__),Path(g.__file__))}
    vocabulary_sha=g.c.canonical_sha256(g.TERMINOLOGY['aliases'])
    graph='ai-literature-'+g.c.canonical_sha256({'inputs':inputs,'vocabulary':vocabulary_sha,'schema':3})[:20]
    old_graph=original['manifest']['graphId'];nodes={};mapping={};concept_aliases=defaultdict(set);concept_members=defaultdict(list)
    source_nodes={n['id']:n for n in original['nodes']}
    def add(kind,key,props):
        nid=g.identifier(graph,kind,key)
        row={'kind':kind,'id':nid,'props':props|{'id':nid,'graphId':graph}}
        if nid in nodes and nodes[nid]!=row: raise ValueError('Conflicting enriched node')
        nodes[nid]=row;return nid
    for node in original['nodes']:
        if node['kind']=='Person': continue
        if node['kind']=='Concept':
            p=node['props'];key,policy=concept_key(p['name'],p['entityType'])
            nid=g.identifier(graph,'Concept',[p['entityType'],key]);mapping[node['id']]=nid
            concept_members[nid].append(node['id']);concept_aliases[nid].add(p['name'])
            nodes[nid]={'kind':'Concept','id':nid,'props':{'id':nid,'graphId':graph,'name':key,'entityType':p['entityType'],
                'canonicalKey':key,'normalization':policy,'vocabularySha256':vocabulary_sha,'source':'derived_typed_vocabulary_not_dblp_fact'}}
        else:
            if not node['id'].startswith(old_graph+':'): raise ValueError('Unexpected base graph identity')
            nid=graph+node['id'][len(old_graph):];mapping[node['id']]=nid
            nodes[nid]={'kind':node['kind'],'id':nid,'props':node['props']|{'id':nid,'graphId':graph}}
    edges=[]
    for edge in original['edges']:
        if edge['kind']=='AUTHORED': continue
        if edge['kind']=='DENOTES': concept_aliases[mapping[edge['tail']]].add(source_nodes[edge['head']]['props']['text'])
        edges.append({'kind':edge['kind'],'head':mapping[edge['head']],'tail':mapping[edge['tail']],
            'props':{k:v for k,v in edge['props'].items() if k!='id'}|{'graphId':graph}})
    for nid in concept_members:
        nodes[nid]['props'].update(aliases=sorted(concept_aliases[nid]),legacyConceptIds=sorted(concept_members[nid]))
    publications={n['props']['publicationId']:n['id'] for n in nodes.values() if n['kind']=='Publication'}
    people=defaultdict(list)
    for s in signatures: people[person_identity(s)].append(s)
    for key,rows in people.items():
        first=rows[0];resolved=first['identity']['status']=='dblp_homepage_resolved'
        profile=profiles[key] if resolved else None
        props={'personId':key,'name':profile['names'][0] if profile else first['name'],
            'aliases':profile['names'] if profile else [first['name']], 'identityStatus':first['identity']['status'],
            'identityEvidence':'dblp_exact_case_sensitive_homepage_alias' if resolved else 'publication_author_signature_only',
            'source':'dblp_structured_xml','identitySourceManifestSha256':g.c.file_sha256(identities/'manifest.json'),
            'orcidSourceValues':sorted({r['orcid'] for r in rows if r['orcid']}),
            'independentlyVerified':False}
        if resolved: props.update(dblpProfileKey=key,dblpPid=key[len('homepages/'):],dblpUrl='https://dblp.org/pid/'+quote(key[len('homepages/'):],safe='/')+'.html',profileOrcidURLs=profile['orcidURLs'])
        else: props['unresolvedReason']=first['identity']['status']
        nid=add('Person',key,props)
        for row in rows:
            edges.append({'kind':'AUTHORED','head':nid,'tail':publications[row['publicationId']],
                'props':{'graphId':graph,'position':row['position'],'signatureName':row['name'],'legacyName':row['legacyName'],
                    'source':'dblp_structured_xml','identityStatus':row['identity']['status'],'orcidSourceValue':row['orcid']}})
    for edge in edges:
        edge['id']=g.identifier(graph,'Edge',[edge['kind'],edge['head'],edge['tail'],edge['props'].get('position')]);edge['props']['id']=edge['id']
    if any(g.c.file_sha256(ROOT/p)!=sha for p,sha in inputs.items()): raise ValueError('Sources drifted during enrichment')
    if sum(e['kind']=='AUTHORED' for e in edges)!=original['manifest']['counts']['edges']['AUTHORED']: raise ValueError('Author signature count changed')
    output.mkdir(parents=True)
    g.c.write_jsonl(output/'nodes.jsonl',list(nodes.values()));g.c.write_jsonl(output/'edges.jsonl',edges)
    summary={'oldPersonNodes':original['manifest']['counts']['nodes']['Person'],'newPersonNodes':len(people),
        'resolvedPersonNodes':sum(rows[0]['identity']['status']=='dblp_homepage_resolved' for rows in people.values()),
        'unresolvedSignatureNodes':sum(rows[0]['identity']['status']!='dblp_homepage_resolved' for rows in people.values()),
        'oldConceptNodes':len(mapping)-sum(n['kind']not in ('Person','Concept') for n in original['nodes']),
        'newConceptNodes':len(concept_members),'controlledConceptNodes':sum(n['props']['normalization']=='controlled_vocabulary_v1' for n in nodes.values() if n['kind']=='Concept'),
        'sourceConceptsGrouped':sum(len(v)-1 for v in concept_members.values()),'authorSignatures':len(signatures),
        'literalMentionsUnchanged':True,'candidateAssertionCountUnchanged':True,'modelReliabilityPromoted':False}
    g.c.write_json(output/'resolution_summary.json',summary)
    manifest=original['manifest']|{'graphId':graph,'createdAtUTC':datetime.now(UTC).isoformat(),'inputSha256':inputs,
        'counts':{'nodes':dict(Counter(n['kind'] for n in nodes.values())),'edges':dict(Counter(e['kind'] for e in edges))},
        'liveDatabaseImported':False,'resolution':summary,'baseGraphId':old_graph,'vocabularySha256':vocabulary_sha,
        'baseExporterCodeSha256':original['manifest']['exporterCodeSha256'],'exporterCodeSha256':g.c.file_sha256(Path(__file__)),
        'notice':'DBLP profile-author resolution and exact typed vocabulary aliases; unresolved signatures never merged. Original predictions and title evidence unchanged, not verified facts.',
        'filesSha256':{p.name:g.c.file_sha256(p) for p in output.iterdir() if p.is_file()}}
    g.c.write_json(output/'manifest.json',manifest);g.verify_bundle(output)
    print(json.dumps(summary,ensure_ascii=False))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,default=ROOT/'kg_datasets/dblp/course_v4_graph_production_20261007_25')
    parser.add_argument('--identities',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();enrich(args.base.resolve(),args.identities.resolve(),args.output.resolve())
