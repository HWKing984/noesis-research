// Run individually in Neo4j Browser. Read only, current graph scope.
// Full database counts, not visualization counts.
MATCH (n:CourseNode {graphId:'ai-literature-1020b3aaea22e8e72eb2'})
RETURN count(n) AS contentNodes;

MATCH (a:CourseNode {graphId:'ai-literature-1020b3aaea22e8e72eb2'})-[r]->
      (b:CourseNode {graphId:'ai-literature-1020b3aaea22e8e72eb2'})
WHERE r.graphId=a.graphId
RETURN type(r) AS relationship,count(r) AS count ORDER BY relationship;

// Bibliographic two-hop coauthor path; names are NOT disambiguated identities.
MATCH path=(a:CoursePerson {graphId:'ai-literature-1020b3aaea22e8e72eb2',name:'Vaibhav Vavilala'})
  -[:AUTHORED]->(p:CoursePublication)<-[:AUTHORED]-(b:CoursePerson)
WHERE a<>b AND all(n IN nodes(path) WHERE n.graphId=a.graphId)
RETURN path LIMIT 30;

// Three-hop author -> paper -> predicted mention -> method concept.
MATCH path=(a:CoursePerson {graphId:'ai-literature-1020b3aaea22e8e72eb2',name:'Vaibhav Vavilala'})
  -[:AUTHORED]->(p:CoursePublication)-[:MENTIONS]->(m:CourseMention)-[:DENOTES]->(c:CourseConcept)
WHERE c.entityType='METHOD' AND all(n IN nodes(path) WHERE n.graphId=a.graphId)
RETURN path LIMIT 30;

// Candidate assertion and its actual evidence endpoints, not a direct USED_FOR edge.
MATCH (a:CourseAssertion {graphId:'ai-literature-1020b3aaea22e8e72eb2'})-[s:SUPPORTED_BY]->
      (p:CoursePublication {publicationId:'conf/3dim/VavilalaVF25'})
MATCH (a)-[hr:HAS_HEAD]->(h:CourseMention)-[hd:DENOTES]->(hc:CourseConcept)
MATCH (a)-[tr:HAS_TAIL]->(t:CourseMention)-[td:DENOTES]->(tc:CourseConcept)
WHERE all(n IN [a,p,h,hc,t,tc] WHERE n.graphId=a.graphId)
RETURN a,s,p,hr,h,hd,hc,tr,t,td,tc LIMIT 10;
