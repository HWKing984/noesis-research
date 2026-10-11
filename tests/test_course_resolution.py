import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from course_resolution import concept_key,person_identity


def test_typed_exact_normalization_and_signature_isolation():
    assert concept_key('Graph Neural Network','METHOD')==concept_key('graph neural networks','METHOD')
    assert concept_key('Machine Learning','METHOD')[0]=='machine learning'
    for a,b in [('BERT','DistilBERT'),('graph neural network','graph convolutional network'),('MNIST','Fashion-MNIST'),('GPT-4','GPT-4o')]:
        assert concept_key(a,'METHOD')[0]!=concept_key(b,'METHOD')[0]
    assert concept_key('Graph Neural Networks','TASK')[1]=='casefold_only_no_semantic_merge'
    a={'publicationId':'a','position':1,'identity':{'status':'unresolved_no_profile'}}
    assert person_identity(a)!=person_identity(a|{'publicationId':'b'})
    assert person_identity(a|{'identity':{'status':'dblp_homepage_resolved','key':'homepages/a'}})=='homepages/a'
