"""Explicit same-session candidate-aware self-review for round20; not human gold."""
import copy
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

JUDGMENTS = [
(0,'revised','A recoding validator may check generated triples rather than itself complete the KG; its implementing relation must remain uncertain.'),
(1,'confirmed','Automotive tracking explicitly uses ML and image processing; no named scenario dataset is asserted.'),
(2,'confirmed','Stable neural networks and UAV fault detection are explicit; safe design describes construction of the stated model.'),
(3,'confirmed','Ensemble DL is stated in the tracking/re-identification approach; edge deployment is not an entity or benchmark.'),
(4,'confirmed','Gesture recognition is a stated ML target, whereas recognition support alone does not identify the flight-control algorithm.'),
(5,'confirmed','CMOS transformers and a 60 GHz power amplifier are electronic components, not neural Transformer models.'),
(6,'confirmed','Analytics and exaflops scale do not specify a computational operation; keep unresolved rather than a complete empty negative.'),
(7,'confirmed','Binomial intervals are a known statistical technique explicitly used for KG accuracy estimation.'),
(8,'confirmed','LLMs are the interpretation target; do not turn interpreting a model into that model implementing interpretation.'),
(9,'confirmed','Named attack and translation family are recorded, but the attack-task span overlaps the family and stays quarantined.'),
(10,'confirmed','RL explicitly trains satisfaction of timed/untimed temporal-logic specifications; no dataset is named.'),
(11,'confirmed','A prototyping resource is not automatically a learning algorithm; multimodal federated learning remains the clear family.'),
(12,'confirmed','Data augmentation can provide training inputs rather than classify hallucinating text; SemEval event is not automatically DATASET.'),
(13,'confirmed','Shared model head and fine-tuning phrase remain one group, with separate literal tasks; no reconstructed missing member words.'),
(14,'confirmed','Challenge versus released dataset identity is uncertain; mining the stated web product data is the explicit task.'),
(15,'revised','Publishing linked data is technical, but Using specifies no concrete computation; the coordinated full task cannot be certified complete.'),
(16,'confirmed','Learning reference alignments and ontology matching are distinct literal operations without a named implementing method.'),
(17,'confirmed','FLORA and fuzzy logic explicitly implement KG alignment; unsupervised is a setting, not a reconstructed task span.'),
(18,'confirmed','The variable-construction operation is explicit; an ontology blueprint is not a named neural method or dataset.'),
(19,'confirmed','Backdoor attack targets the LiDAR detector and does not implement detection; preserve the explicit adversarial-role negative.'),
(20,'confirmed','Transformer models explicitly identify automatically generated text; preserve original unhyphenated Based wording.'),
(21,'confirmed','Financial ML systems are evaluated by fairness testing, not named as the test generator; role negative is justified.'),
(22,'confirmed','Agent user experience and affordance analysis introduce no identifiable algorithm, named dataset, or concrete computation in scope.'),
(23,'confirmed','LLM family is explicit; teachers/students and implications are not concrete computational tasks.'),
(24,'confirmed','GNN-to-fraud detection is explicit but model-inconsistency alleviation cannot be represented fully without overlap; keep quarantine.'),
(25,'confirmed','Mean Shift, incremental learning and GCNs are complete literal methods presented for social-user geolocation.'),
(26,'confirmed','Synthetic scalar-map generation is explicit; augmentation is its purpose and need not itself be the generator.'),
(27,'confirmed','Networks are implementation targets, not implementers; overlapping characterization operation prevents complete flat inventory.'),
(28,'confirmed','Similarity-informed classification is one stated mapping method; do not invent separate similarity algorithms or nested task entities.'),
(29,'confirmed','Light Transformer and speech-to-intent are explicit; no named speech benchmark appears.'),
(30,'confirmed','ML monitors physical transmission/distribution lines; physical electrical domain does not invalidate the explicit ML use.'),
(31,'confirmed','MARLander and multiagent deep RL both explicitly concern drone-swarm local path planning.'),
(32,'confirmed','Deep RL directly addresses task offloading; preserve multi-gateway-assisted edge context.'),
(33,'confirmed','Partitioning-strategy identity remains uncertain, so the clear GCN recognition pair does not certify complete annotation.'),
(34,'confirmed','Ontology-based profile adaptation may prepare retrieval inputs; do not force it into the retrieval algorithm role.'),
(35,'confirmed','Employment practices are broad application context; AI is not an additional independently identifiable method here.'),
(36,'confirmed','ML-based soft sensing is one composite method explicitly predicting leaf wetness; agriculture remains task context.'),
(37,'confirmed','Neural networks explicitly compute direct robot kinematics; the robot problem is preserved without inventing a solver.'),
(38,'confirmed','Modified auto encoder and CNNs are separately complete methods explicitly used for detection.'),
(39,'confirmed','Motion-state estimation and CNNs are stated tracking instruments; no Kalman-filter name is supplied.'),
(40,'confirmed','Intrusion detection is the stated operation; System and Investigation are generic artifact/research framing.'),
(41,'confirmed','Differential evolution selects parameters while the Transformer forecasts; overlap and indirect forecasting relation remain unresolved.'),
(42,'confirmed','Quantum and neuromorphic substrates are computing platforms, not separately named learning algorithms or tasks.'),
(43,'confirmed','Cardiac-MRI right-ventricle segmentation uses late-ensemble DL; retain task variants, not Efficient evaluation wording.'),
(44,'confirmed','KG-enhanced semantic matching directly supports plan recommendation as one composite method.'),
(45,'confirmed','Metaheuristics perform tuning; ML target-versus-tuner role is not explicit and remains unresolved.'),
(46,'confirmed','Handwriting Datasets is unnamed plural input and no literal handwriting-recognition operation should be invented.'),
(47,'confirmed','RF repeater placement is explicit; the power transformer is physical equipment, not neural architecture.'),
(48,'confirmed','Emotion recognition retains facial-expression input context with a lightweight DL instrument.'),
(49,'confirmed','Hardware-optimized DL explicitly supports FPGA character recognition; FPGA is platform, not DATASET.'),
(50,'confirmed','LLM and Behaviour Tree are independently identifiable complete names; no missing Based member suffix is synthesized.'),
(51,'confirmed','Subset selection may scale Bayesian Transformers, not be executed by them; preserve unresolved role direction.'),
(52,'confirmed','Cloud infrastructure is not a model/dataset; a chatbot artifact does not identify its concrete conversational computation.'),
(53,'confirmed','FCN detection is explicit but AICity challenge release identity is not; no EVALUATED_ON is fabricated.'),
(54,'confirmed','LLM-based agents are vulnerability targets; the slogan does not identify the detector algorithm.'),
(55,'confirmed','Model assessment is distinct from segmentation, and its full task overlaps the DL target; keep whole record quarantined.'),
(56,'confirmed','Transfer learning and single-pass DL architectures explicitly support industrial detection; Robust is quality framing.'),
(57,'confirmed','Diagnostic visualization is stated; ML practitioners are users rather than an implementing ML model.'),
(58,'confirmed','Neural networks explicitly generate quaternion transitions; no motion dataset is named.'),
(59,'confirmed','Deep RL drives UAV-network deployment; attention-aware description does not name an extra attention algorithm.'),
(60,'confirmed','Binary networks are search targets; the full network-search task overlaps them and cannot become a confident partial inventory.'),
(61,'confirmed','Cross-task GNN decoder explicitly classifies both sewer defects and properties; task coordination does not reconstruct methods.'),
(62,'confirmed','Loss-guided diffusion is the stated layout-control method; preserve guidance qualifier.'),
(63,'confirmed','Fourier representation role cannot be equated to a complete deblurrer; keep that pair unresolved and remaining literal techniques.'),
(64,'confirmed','Language-specific translation and broader morphology-rich translation are disjoint stated tasks; unnamed system is not a named method.'),
(65,'confirmed','Cooperative driving is explicitly addressed with ML; highway context is retained.'),
(66,'confirmed','Capsule networks explicitly recognize conversational personality; conversations are unnamed input data.'),
(67,'confirmed','Super-resolution CNN is literal and used for remote-sensing sharpening; do not correct Transfering or invent absent Transfer Learning words.'),
(68,'confirmed','Stars introduces its sensor-agnostic Transformer architecture; remote sensing alone does not imply segmentation or classification.'),
(69,'confirmed','Graph representations may be resources, and separate spatial-modeling component roles remain uncertain; no words are appended to segmentation.'),
(70,'confirmed','DL-to-mobility-management is a title-level topic association, not evidence of a new experiment by this invited paper.'),
(71,'confirmed','Federated learning is the system being incentivized, not the explicit design instrument; keep the role negative.'),
(72,'confirmed','Supervised and unsupervised share the Machine Learning head; record group rather than invented full member strings.'),
(73,'confirmed','The lockdown/unlock decision is an explicit RL target; annotation is not public-health guidance or efficacy evidence.'),
(74,'confirmed','Time-aware responses are output descriptions; no specific temporal-reasoning or dialogue-generation task literal is supplied.'),
(75,'confirmed','History-aware Transformers explicitly implement personalised outfit recommendation with the original spelling.'),
(76,'confirmed','Ada-GNN adapts to local patterns; generic GNNs may be the improved targets, so their adaptation role stays unresolved.'),
(77,'confirmed','Personalized style recommendation is explicitly via RL; no catalog dataset is inferred.'),
(78,'confirmed','Global homophily is a graph property; do not invent an unstated node-classification task.'),
(79,'confirmed','Templet is a system and Wikidata is a KB; neither software METHOD nor dataset-evaluation identity is settled by this title.'),
(80,'confirmed','NLP explicitly supports social-media sexism detection and classification; the complete coordinated task is literal.'),
(81,'confirmed','ML results are the validation object; the full validation task overlaps the family and the unnamed framework is not an algorithm name.'),
(82,'confirmed','IoT and precision agriculture are infrastructure/domain; no downstream computation is stated beyond the ML family.'),
(83,'confirmed','Advection-diffusion is a physical memristor model, not generative diffusion; no migration prediction task is explicitly written.'),
(84,'confirmed','Techniques, Datasets and Models are generic categories; computer networks are application context.'),
(85,'confirmed','Both transfer learning and decision fusion explicitly implement the distortion-classification approach; no named laparoscopic dataset.'),
(86,'confirmed','SHIFA and SBERT explicitly concern Arabic healthcare QA; preserve full language/context task qualifiers.'),
(87,'confirmed','Intelligent-network architectures/use cases do not provide named algorithms, datasets, or a concrete downstream task beyond ML.'),
(88,'confirmed','Distributed deep RL explicitly performs multi-domain IoT task offloading; edge context is deployment, not DATASET.'),
(89,'confirmed','GNNs explicitly classify cryptocurrency transactions; anti-money laundering is broader application context.'),
(90,'revised','Text Guide itself appears to be the text-selection approach; improving classification through selected inputs does not certify it as the classifier.'),
(91,'confirmed','SAM and its explicitly stated zero-shot-transfer technique concern medical segmentation; the title phrase No More Training remains data.'),
(92,'revised','The full synchronization-control task contains a recognizable chaotic-neural-network target; the flat inventory cannot separately represent it, so complete status is too strong.'),
(93,'confirmed','Airflow sensor is a device, and estimation is not a literal task; pressure sensors do not become datasets.'),
(94,'confirmed','WAFFLe, named factorization and FL family are explicit; weight anonymization is a nested mechanism, not an extra overlapping task.'),
(95,'confirmed','Reward-shaping-based federated RL is one complete composite method without a stated downstream task.'),
(96,'confirmed','Sensing/reconstruction may feed the controller; neither is proven to implement avoidance itself, so both pairs remain uncertain.'),
(97,'confirmed','Terahertz technology is application domain; review achievements/challenges supply no concrete downstream task.'),
(98,'confirmed','Hybrid TEMPODE method explicitly classifies phase-wise pediatric gait; title association is not clinical performance evidence.'),
(99,'confirmed','DL explicitly performs plastic-bottle visual inspection; bottles are objects, not a named dataset.')
]


def review():
    run = ROOT / 'kg_datasets/dblp/course_v4_runs/pending_train_20261007_20'
    source = run / 'generation_decisions.json'
    digest = 'd4d4e7921749a7622e37508304df359f00a07c9893cc6ba0be9bd9997e5f71d2'
    assert c.file_sha256(source) == digest
    first = json.loads(source.read_text(encoding='utf-8'))['decisions']
    assert len(first) == 100 and [i for i,_,_ in JUDGMENTS] == list(range(100))
    replacements = {i:copy.deepcopy(first[i]) for i in (0,15,90,92)}
    replacements[0]['relations'][2].update(label='UNRESOLVED', reason='A validator may check proposed triples without itself implementing graph completion.')
    replacements[0].update(relationStatus='unresolved', relationReason='Recoding validation versus implementing completion is not specified.')
    replacements[15].update(entityStatus='unresolved', entityReason='Using Biographical Linked Data does not specify a concrete computation in the coordinated operation.',
        relationStatus='unresolved', relationReason='Complete technical-task inventory cannot be certified from generic data use.')
    replacements[90]['relations'][0].update(label='UNRESOLVED', reason='Text Guide may select classifier inputs rather than be the classification algorithm.')
    replacements[90]['relationReason'] = 'Both named and expanded text-selection approach may be input preparation rather than classification implementation.'
    replacements[92].update(entityStatus='unresolved', entityReason='The full synchronization-control task overlaps its identifiable chaotic-neural-network target in the flat schema.',
        relationStatus='unresolved', relationReason='Incomplete flat inventory despite the clear Lyapunov-to-control association.')
    judgments = []
    for index,verdict,reason in JUDGMENTS:
        item = {'sampleId':first[index]['sampleId'], 'verdict':verdict, 'reason':reason}
        if verdict == 'revised':
            item['replacement'] = replacements[index]
        judgments.append(item)
    path = run / 'review_judgments.json'
    if path.exists():
        raise FileExistsError('Preserve existing review records.')
    c.write_json(path, {'provider':'codex_session','model':'unknown_session_model','round':'candidate_aware_ai_review',
                       'generationDecisionsSha256':digest,'judgments':judgments})
    shutil.copyfile(Path(__file__), run / 'authored_review.py')
    expand_artifact(source, path, run / 'review_expanded')
    dataset = ROOT / 'kg_datasets/dblp/course_v4_weak'
    previous = run / 'generation/receipts.jsonl'
    compile_artifact(dataset, run / 'jobs.jsonl', run / 'review_expanded/review_decisions.json', run / 'review_compiled', previous=previous)
    import_results(dataset, run / 'review_compiled/responses.jsonl', run / 'review', provider='codex_session',model='unknown_session_model', previous=previous)
    parent = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_12'
    target = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_13'
    summary = assemble(dataset, [parent / 'receipts.jsonl', run / 'review/receipts.jsonl'], target)
    original = c.read_jsonl(parent / 'receipts.jsonl')
    assert c.read_jsonl(target / 'receipts.jsonl')[:len(original)] == original
    assert all((parent / name).read_bytes() == (target / name).read_bytes() for name in
               ('ner_inputs_dev.jsonl','ner_inputs_test.jsonl','relation_inputs_dev.jsonl','relation_inputs_test.jsonl'))
    c.write_json(run / 'manifest.json', {'kind':'new_training_labels_same_session_candidate_aware_AI_self_review',
        'parentSnapshotManifestSha256':c.file_sha256(parent / 'manifest.json'),'newSnapshotManifestSha256':c.file_sha256(target / 'manifest.json'),
        'documents':100,'confirmed':96,'revised':4,'humanGold':False,'independentReviewer':False,'trainingStarted':False,
        'finalTestInferenceRepeated':False,'oldReceiptsUnchanged':True,'devTestInputsByteIdentical':True,
        'filesSha256':{p.relative_to(run).as_posix():c.file_sha256(p) for p in run.rglob('*') if p.is_file()}})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    review()
