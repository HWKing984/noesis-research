// Read-only example, candidate assertions are not verified research facts.
MATCH (p:CoursePublication {graphId:'ai-literature-1020b3aaea22e8e72eb2', publicationId:'conf/3dim/VavilalaVF25'})
OPTIONAL MATCH (author:CoursePerson)-[w:AUTHORED]->(p)
OPTIONAL MATCH (p)-[vrel:PUBLISHED_IN]->(venue:CourseVenue)
OPTIONAL MATCH (p)-[mr:MENTIONS]->(m:CourseMention)-[dr:DENOTES]->(c:CourseConcept)
OPTIONAL MATCH (a:CourseAssertion)-[s:SUPPORTED_BY]->(p)
OPTIONAL MATCH (a)-[hr:HAS_HEAD]->(h:CourseMention)
OPTIONAL MATCH (a)-[tr:HAS_TAIL]->(t:CourseMention)
RETURN p,author,w,venue,vrel,m,mr,c,dr,a,s,h,hr,t,tr LIMIT 30;
