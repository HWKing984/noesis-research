"""Explicit candidate-aware judgments for the new 100 training titles."""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_weak as c
from compile_course_ai import compile_artifact
from expand_course_ai_review import expand_artifact
from import_course_ai import import_results, assemble

# Every confirmation/revision below is authored, not supplied by a default loop.
JUDGMENTS = [
(0,'confirmed','Music-genre heading and automated-classification subtitle establish both target associations; the neural-network family is literal.'),
(1,'confirmed','Daily prognosis target is direct, while the uncertainty-handling component must remain unresolved.'),
(2,'confirmed','Educational game-based learning is not ML training; agent algorithms and computational operation are unspecified.'),
(3,'confirmed','Dictionary-based text classification is one composite; broad process analysis cannot be certified as a second flat technical task.'),
(4,'confirmed','Machine and production monitoring is a concrete explicit tool target; no unnamed algorithm is added.'),
(5,'confirmed','OWL language/schema objects are not datasets; diagram generation is the only explicit technical operation.'),
(6,'confirmed','Pseudo-language for temporal requirements leaves learning/translation/interpretation direction unclear.'),
(7,'confirmed','Two complete named method phrases explicitly implement non-query fake-news detection.'),
(8,'confirmed','MAST-NER implements named-entity recognition; trigger pool is unnamed, and low-resource is a setting.'),
(9,'confirmed','Authorship-hypothesis exploration is specified and explicitly linked to GCNs.'),
(10,'confirmed','Compared rescaling/sampling approaches and LLM family all concern dataset personalization; generic dataset is not DATASET.'),
(11,'confirmed','CoNLL-RDF is identified here by RDF/TSV data structures, not a named evaluation dataset; ontology remains an out-of-schema resource.'),
(12,'confirmed','RL instrument and full microservice autoscaling target are direct.'),
(13,'confirmed','Risk-/quantization-aware shared training head stays a group; no absent Risk-Aware Training phrase is reconstructed.'),
(14,'confirmed','Joint medication/adverse-event detection retains clinical-note object and does not invent duplicated verb spans.'),
(15,'confirmed','Ambiguous broad analysis/standardization cannot be turned into a complete empty-entity negative.'),
(16,'confirmed','Clinical-text deep-learning model family is known, but Painless model identity and downstream task remain unknown.'),
(17,'confirmed','Association is the reviewed DL machinery time-series classification topic, not new experiments carried out by this paper.'),
(18,'confirmed','Camera hardware/CAD geometry are not established learning algorithms; joint detection/pose operation is explicit.'),
(19,'confirmed','Reaction-diffusion is a mathematical biological model here, not a generative diffusion architecture.'),
(20,'confirmed','Non-pooling network modifier is retained with explicit medical segmentation.'),
(21,'confirmed','ML is explicitly one energy-saving instrument; IoT is not a separately named learner.'),
(22,'confirmed','Aortic-annulus target and aortic-dissection patient context are preserved without asserting clinical effectiveness.'),
(23,'confirmed','Full boundary-aware end-to-end network descriptor is method, not overlapping nested mentions.'),
(24,'confirmed','PitVQA name and image-grounded LLM expansion are disjoint and tied to pituitary-surgery VQA.'),
(25,'confirmed','ACLNet and DL family implement rupture classification; bone morphology remains an input feature.'),
(26,'confirmed','Ontology-based relationship learning may be a representation objective or method; segmentation alone is confidently typed.'),
(27,'confirmed','Diffusion imaging terminology does not imply generative models or a named benchmark; generalizability is a property.'),
(28,'confirmed','Named and expanded multimodal fusion method phrases both directly target breast-cancer response prediction.'),
(29,'confirmed','Named hybrid transformer and full multi-phase lesion classification target are explicit.'),
(30,'confirmed','Map refinement overlaps the DL phrase; model/map inputs do not automatically prove full quantification implementation.'),
(31,'confirmed','Siamese content-loss architecture is one method; class imbalance is a training/data setting.'),
(32,'confirmed','SPARQL inference is explicitly applied to guideline modelling/execution; unnamed ontologies are not datasets.'),
(33,'confirmed','Comparative LLM extraction topic is direct, but no quality improvement or clinical outcome is certified.'),
(34,'confirmed','Mass-spectrometry stage ambiguity remains unresolved even though the ML classification association is clear.'),
(35,'confirmed','Coordinated segmentation/identification task keeps the shared anatomical target, all in one original contiguous span.'),
(36,'confirmed','Attack-graph-embedded ML is identifiable; broad cyber awareness lacks a specified computational task.'),
(37,'confirmed','Offline RL is the model being selected, not the selection algorithm; preserve the explicit target-versus-instrument negative.'),
(38,'confirmed','Connectivity-reinforced method modifier and complete cerebrovascular delineation object are retained; TOF-MRA is a modality.'),
(39,'confirmed','Advertising does not identify a particular extraction/ranking/generation task; technique families alone do not resolve it.'),
(40,'confirmed','Multimodal learning and web extraction have an explicit for relation.'),
(41,'confirmed','Assembly Line is expressly a tool; software identity must not be assumed equivalent to an algorithm.'),
(42,'confirmed','DenseNet-based segmentation model remains composite, with document-level extraction as separate target.'),
(43,'confirmed','Controlling the IEEE contention window explicitly uses ML; the protocol is not a dataset.'),
(44,'revised','Self-generating figure patterns can be generated training material rather than an identifiable method; first-pass METHOD and direct USED_FOR were too definite.'),
(45,'confirmed','Word embeddings are used to improve the specified phrasal-verb translation operation; no nested MT-family method added.'),
(46,'confirmed','Both de-embedding and inverse NN are stated filter-design instruments; this is a physical filter target, not a transformer-model confusion.'),
(47,'confirmed','Personality expression is literal, but an ability investigation and PersonaLLM identity do not settle a deployed implementing model.'),
(48,'confirmed','LLM-driven knowledge injection is one composite method; zero-shot/cross-target remain settings outside the stance-detection span.'),
(49,'confirmed','Logic-based reasoning explicitly implements VQA; performance/explainability modifiers do not create extra entities.'),
(50,'confirmed','Transfer-learning and autoencoder families are explicit; coherent/consistent are properties and no downstream task is spelled out.'),
(51,'confirmed','Drone energy consumption prediction is explicit; MEC is infrastructure context, not a benchmark.'),
(52,'confirmed','FedRolex component extraction is stated, while reversing generic federated-learning family into the extractor is not settled.'),
(53,'confirmed','Text Painters is a figurative role, not an original Text Generation span; two method mentions remain without invented task.'),
(54,'confirmed','Tree Mover distance and GNN family are identifiable; stability is a property rather than a prediction task.'),
(55,'confirmed','Symplectic-integration/sparsity neural-network mechanism stays one complete method phrase.'),
(56,'confirmed','Personalize omits the object and operation; incomplete inventory cannot become a resolved no-pair negative.'),
(57,'confirmed','Nearest-neighbor is an algorithm learned by a transformer; current schema excludes method-to-method learning relations.'),
(58,'confirmed','Full temporal-polynomial GNN architecture is explicitly the multivariate forecasting instrument.'),
(59,'confirmed','Partial supervision modifies the RL mechanism, and visual active search is a distinct concrete target.'),
(60,'confirmed','Distral and multitask RL are name/family mentions without a literal separate target; robustness is a property.'),
(61,'confirmed','CARLA may be simulator rather than DATASET and world-model role is uncertain; keep only the explicit driving pairs.'),
(62,'confirmed','Cross-view geo-localization and complete layer-to-layer transformer are direct.'),
(63,'confirmed','Two explicit technical operations are tasks; no algorithm is named to implement them.'),
(64,'confirmed','Iconicity is a linguistic/data property, while transfer learning explicitly applies to sign-language recognition.'),
(65,'confirmed','Swedish-dialogue target and three disjoint method name/family mentions are directly associated; non-ASCII name is preserved.'),
(66,'confirmed','Full Clifford-group equivariant layer architecture, not generic layers alone, implements protein-structure prediction.'),
(67,'confirmed','Knowledge base is unnamed input and QA system is unnamed software; do not invent a neural method.'),
(68,'confirmed','Context/multidimensional mechanism is part of the contiguous transformer extension, not a second overlapping model.'),
(69,'confirmed','VPformer-to-forecasting pair is clear, but ambiguous shared-head transformer phrase is quarantined rather than reconstructed.'),
(70,'confirmed','DL family implements network intrusion detection; semi-supervision and robustness are not separate tasks.'),
(71,'confirmed','Spatial beam transformer, PLC and SDM fibers are optical hardware; this inspected title is a genuine neural-model keyword false positive.'),
(72,'confirmed','Agricultural-zone target retains El Jadida/Morocco; remote sensing is acquisition context rather than a named dataset.'),
(73,'confirmed','CNN predicts both driving-control quantities; shared target conjunction stays one literal task phrase.'),
(74,'confirmed','Named application ontology and geographic place are outside the current three entity classes; no algorithm is claimed.'),
(75,'confirmed','Ontology-enabled NLP is the composite processing method, provenance extraction the separate biomedical target.'),
(76,'confirmed','Deep learning may classify while radios jam; combined target cannot safely receive a resolved all-operations USED_FOR.'),
(77,'confirmed','ML is accelerated computation, not the accelerator; explicit target-role negative is retained.'),
(78,'confirmed','Model integration task overlaps generic model families and no named satellite dataset appears; unresolved is appropriate.'),
(79,'confirmed','Try-on is embedded inside the full diffusion-transformer method; flat schema cannot add its nested task span.'),
(80,'confirmed','Name, adaptation mechanism and LLM family explicitly concern change captioning; original Adaption spelling must remain.'),
(81,'confirmed','Target-aware bi-transformer implements segmentation; the title supplies no object modality to invent.'),
(82,'revised','Cosine fitting energy is a criterion within the Chan Vese model, not necessarily a standalone segmenter; direct relation needs an unresolved decision.'),
(83,'confirmed','Interpretive-inductive interview analysis is a scoped operation, unlike bare analysis; named technique families are explicit instruments.'),
(84,'confirmed','Nonstationarity describes the series target and selective recurrence describes the model mechanism.'),
(85,'confirmed','Reduction-step count estimation is concrete; preserve the unusual original Lambda- Term spacing.'),
(86,'confirmed','RL safety-improvement task overlaps RL and no specific flat nonoverlapping task can be invented; intervention is method-to-method.'),
(87,'confirmed','Matrix pseudoinverse names a concrete mathematical computation problem, with time-varying object and harmonic-resistant RNN instrument.'),
(88,'confirmed','LLMs explicitly structure/explore linguistic puzzles; Lingdex website and unnamed puzzles are not inferred methods/datasets.'),
(89,'confirmed','Gated architecture and exact turbine-blade icing detection object are explicit.'),
(90,'confirmed','Multi-task learning explicitly constructs event-centric temporal KGs; Automatic is not an additional entity.'),
(91,'confirmed','LLM support for recommendation is stated; LLMRec named reproducibility target retains uncertain implementation relation.'),
(92,'confirmed','Counsellor support remains a broad application goal; unnamed LLM tool does not establish a specific technical task.'),
(93,'confirmed','Depth and explainability interventions do not identify a named implementing method; unknown does not mean negative.'),
(94,'confirmed','No dataset is named, and RoboCup SSL is competition context; preserve the specified embedded detection task only.'),
(95,'confirmed','Slash-composed network stays one method with separate transfer-learning family and search/rescue segmentation target.'),
(96,'confirmed','Both independent auditing and HTML-validation tasks explicitly use the LLM family.'),
(97,'revised','RecKG is a named graph resource which could constitute a released dataset; complete empty entities overstates what the title establishes.'),
(98,'confirmed','Downstream malware-classification pair is clear but deriving models introduces an overlapping uncertain selection task; keep quarantine.'),
(99,'confirmed','WebAI could be an environment, while web tasks are unspecified and agent training roles unclear; do not synthesize a dataset or task.')
]

REPLACEMENTS = {
44: {'entityStatus':'unresolved','entityReason':'Self-generating figure patterns could be training materials rather than an identifiable implementing method.',
     'entities':[{'text':'Microscopy Image Segmentation','label':'TASK'}],'groupMentions':[],
     'relationStatus':'unresolved','relationReason':'The proposed strategy identity and its implementing role are not settled.',
     'relations':[],'notes':'Keep the explicit microscopy task; unnamed training material is not a named DATASET. Do not certify a pattern-to-segmentation method relation.'},
82: {'entityStatus':'complete','entityReason':'','entities':[{'text':'Image Segmentation','label':'TASK'},
     {'text':'Local Chan Vese Model','label':'METHOD'},{'text':'Cosine Fitting Energy','label':'METHOD'}], 'groupMentions':[],
     'relationStatus':'unresolved','relationReason':'The energy functional is a model criterion; standalone segmentation implementation is uncertain.',
     'relations':[{'head':'e2','tail':'e1','label':'USED_FOR','reason':'The local Chan Vese model explicitly implements image segmentation.'},
                  {'head':'e3','tail':'e1','label':'UNRESOLVED','reason':'The criterion is employed inside a model and is not explicitly a standalone segmenter.'}],
     'notes':'Preserve the named computational criterion mention but do not force its component role into a resolved end-to-end relation.'},
97: {'entityStatus':'unresolved','entityReason':'RecKG explicitly names a knowledge-graph resource; title alone cannot distinguish schema/system from a released named dataset.',
     'entities':[],'groupMentions':[],'relationStatus':'unresolved','relationReason':'Resource type unresolved, not an inspected complete negative.',
     'relations':[],'notes':'Recommender systems is a broad application; no literal recommendation operation or learning algorithm is named.'}
}


def review():
    output = ROOT / 'kg_datasets/dblp/course_v4_runs/pending_train_20261007_19'
    source_path = output / 'generation_decisions.json'
    expected = 'f44bc708e6bb35153754c874842f6a14524e8cad5039eda64ca3061a6b77f9af'
    assert c.file_sha256(source_path) == expected
    first = json.loads(source_path.read_text(encoding='utf-8'))['decisions']
    assert [i for i,_,_ in JUDGMENTS] == list(range(100)) and len(first) == 100
    judgments = []
    for index, verdict, reason in JUDGMENTS:
        sid = first[index]['sampleId']; item = {'sampleId':sid, 'verdict':verdict, 'reason':reason}
        if verdict == 'revised': item['replacement'] = REPLACEMENTS[index] | {'sampleId':sid}
        judgments.append(item)
    path = output / 'review_judgments.json'
    if path.exists(): raise FileExistsError('Preserve existing authored review')
    c.write_json(path, {'provider':'codex_session','model':'unknown_session_model','round':'candidate_aware_ai_review',
                       'generationDecisionsSha256':expected,'judgments':judgments})
    shutil.copyfile(Path(__file__), output / 'authored_review.py')
    expanded = output / 'review_expanded'
    expand_artifact(source_path, path, expanded)
    compiled = output / 'review_compiled'
    previous = output / 'generation/receipts.jsonl'
    dataset = ROOT / 'kg_datasets/dblp/course_v4_weak'
    compile_artifact(dataset, output / 'jobs.jsonl', expanded / 'review_decisions.json', compiled, previous=previous)
    import_results(dataset, compiled / 'responses.jsonl', output / 'review',provider='codex_session',model='unknown_session_model',previous=previous)
    parent = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_11'
    target = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_12'
    summary = assemble(dataset, [parent / 'receipts.jsonl', output / 'review/receipts.jsonl'], target)
    original = c.read_jsonl(parent / 'receipts.jsonl'); current = c.read_jsonl(target / 'receipts.jsonl')
    assert current[:len(original)] == original
    assert all(c.file_sha256(target / name) == c.file_sha256(parent / name) for name in
               ('ner_inputs_dev.jsonl','ner_inputs_test.jsonl','relation_inputs_dev.jsonl','relation_inputs_test.jsonl'))
    c.write_json(output / 'manifest.json', {'kind':'new_training_labels_same_session_candidate_aware_AI_self_review',
        'parentSnapshotManifestSha256':c.file_sha256(parent / 'manifest.json'),'newSnapshotManifestSha256':c.file_sha256(target / 'manifest.json'),
        'documents':100,'confirmed':97,'revised':3,'humanGold':False,'independentReviewer':False,
        'trainingStarted':False,'finalTestInferenceRepeated':False,'oldReceiptsUnchanged':True,'devTestInputsByteIdentical':True,
        'filesSha256':{p.relative_to(output).as_posix():c.file_sha256(p) for p in output.rglob('*') if p.is_file()}})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__': review()
