"""Explicit per-title same-session candidate-aware review; revisions preserve first pass."""
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
(0,'confirmed','Expressway toll-lane optimization/visualization is one complete target with an explicit DL instrument.'),
(1,'confirmed','OCT boundary-segmentation phrase has uncertain method/task boundary; keep quarantine.'),
(2,'confirmed','LLMs and financial sentiment analysis are explicit review topics; generic Datasets supplies no DATASET name.'),
(3,'confirmed','Security/energy efficiency do not specify the DRL-controlled healthcare-IoT operation.'),
(4,'confirmed','Deep CNN explicitly recognizes finger veins; features are not named datasets.'),
(5,'revised','Complex Network is the complete family, not the trailing Based adjective; generic image analysis prevents certifying the combined task inventory.'),
(6,'confirmed','ML explicitly classifies rolling bearings; Novel and Techniques add no identity.'),
(7,'confirmed','ThreMA introduces the ontology-based ICT threat-modeling approach; no ontology dataset name.'),
(8,'confirmed','CNN-BiLSTM and hybrid DL detect intrusions; feature selection may only prepare inputs.'),
(9,'confirmed','Trailing KG-DEMATEL-ISM-MICMAC clearly modifies risk analysis, but graph-construction scope is uncertain.'),
(10,'confirmed','Multiscale CNN and calcification-bearing mammogram classification are literal.'),
(11,'confirmed','Preserve explicit associations quoted in correction title, without treating the notice as a new experiment or merging paper identity.'),
(12,'confirmed','Physical transformer core-loss estimation uses a loss-separation model; no neural Transformer is inferred.'),
(13,'confirmed','Two-level progressive-attention convolutional network directly performs fine-grained recognition.'),
(14,'confirmed','GDP-indicator role and investment forecaster role are not interchangeable; keep the pair uncertain.'),
(15,'confirmed','Fuzzy region competition and Gaussian mixture model explicitly perform remote-sensing segmentation.'),
(16,'confirmed','Recursive CNN explicitly detects exploit kits; Image Game is framing.'),
(17,'confirmed','GFHANet and its literal expansion explicitly detect salient sonar objects.'),
(18,'confirmed','Party prediction is a stated model target, not verified evidence of future political outcomes; historical data is unnamed.'),
(19,'confirmed','Rotation-invariant local-binary convolution architecture is explicit without a stated downstream task.'),
(20,'confirmed','Thai morning-glory price forecasting explicitly uses DL; crop identity is not DATASET.'),
(21,'confirmed','DRL is an explicit charging instrument; sensor networks are the application context.'),
(22,'confirmed','Inverted Transformer forecasts traffic; sleep-control execution may be downstream of those forecasts.'),
(23,'confirmed','The literal demand-forecasting phrase retains cooling/building context, including original awkward grammar.'),
(24,'confirmed','GLoU-MiT and Mamba-guided U-mix Transformer explicitly segment UAV pavement cracks.'),
(25,'confirmed','Facility data model may be a schema, not an energy-management algorithm; keep unresolved resource role.'),
(26,'confirmed','DL explicitly extracts non-debris glacier areas; time-series remote-sensing input is unnamed.'),
(27,'confirmed','Metaheuristic-assisted ANN explicitly supports PV-system design/control as a full composite.'),
(28,'confirmed','Transformer Semantics lacks disambiguating context; do not invent neural or physical identity.'),
(29,'confirmed','Review title explicitly associates ML and coffee classification without proving a new test.'),
(30,'confirmed','Environmental sustainability is a broad goal, not a specific literal computational task.'),
(31,'confirmed','Generative AI writing assistance is explicit; ChatGPT authorship question does not settle its implementing role.'),
(32,'revised','Machine Learning is the actual method family; trailing Based only links it to the independent intrusion task and should not extend its boundary.'),
(33,'confirmed','ML-service platform is software; integer-discretization evaluation versus technique role remains unresolved.'),
(34,'confirmed','Separable Gaussian networks explicitly concern function approximation; bare structure/analysis is framing.'),
(35,'confirmed','DNN stages COPD, but formula-driven pre-training is not necessarily itself the staging method.'),
(36,'confirmed','Spectroscopy measures inputs; black-plastic recycling does not literally identify the classifier target operation.'),
(37,'confirmed','FedDKD and decentralized-distillation FL form named/expanded complete methods without a task.'),
(38,'confirmed','Bare classification lacks object; unnamed corresponding classifier cannot complete the task inventory.'),
(39,'confirmed','Multiple-attention DNN explicitly forecasts metro flow; devices are measurement hardware.'),
(40,'confirmed','Multibranch cross-pseudo supervision explicitly supports medical segmentation; training settings are not dataset names.'),
(41,'confirmed','Full multimodal-mixup encoder implements multimodal translation; no nested method inside the task.'),
(42,'revised','Consistency and difference share the networks head; preserve a group, remove individual group relations, and keep ICDN/Transformer relations separately.'),
(43,'confirmed','Cyber resilience is a broad goal; no concrete defensive LLM task appears.'),
(44,'confirmed','Transformer-based self-supervised pre-training is a full composite explicitly for time-series prediction.'),
(45,'revised','The acceleration task contains an identifiable CNN target; complete flat inventory is overconfident, so preserve the pruning association but quarantine the overlap.'),
(46,'confirmed','Unnamed Semantic Web assistant framework does not identify an algorithm or operation.'),
(47,'confirmed','Educational personalization is explicit, while analytics/decision-making subtasks lack specific computation/object.'),
(48,'confirmed','DxFormer is a diagnostic system, but a disease/task operation is not literally stated; do not synthesize one.'),
(49,'confirmed','Attention networks predict phenotype from single-cell RNA-seq; unnamed modality is not DATASET.'),
(50,'confirmed','Hierarchical DL predicts GO annotations; protein-knowledge integration may be input preparation.'),
(51,'confirmed','DeepLUCIA and named learning annotator explicitly predict chromatin loops; no unnamed assay becomes a dataset.'),
(52,'confirmed','DCSO is an ontology and data-management plans are documents, not named datasets or learning methods.'),
(53,'confirmed','Neural causal model explicitly estimates electricity demand; Bolivia/El Espino is case location.'),
(54,'confirmed','Crop production is a broad application objective; keep uncertain rather than a concrete DL prediction task.'),
(55,'confirmed','Model-for-metastasis wording does not literally state prediction; ultrasound features are unnamed inputs.'),
(56,'confirmed','Classical ML and DL explicitly address sleep-stage classification; review is not new experimental evidence.'),
(57,'confirmed','ML-assisted drift-capacity prediction is stated; columns/alloy bars are physical target context.'),
(58,'confirmed','Elastic structural analysis is a concrete mechanics computation explicitly using GNN, not generic analysis.'),
(59,'confirmed','The LLM/UML assessment question states an investigated use, not demonstrated expert-grade performance.'),
(60,'confirmed','Both DL and transfer learning explicitly address breast-cell segmentation; early diagnosis is motivation.'),
(61,'revised','PAD diagnosis is specific, but management does not identify a computational intervention; do not certify the entire coordinated target as complete.'),
(62,'confirmed','Multichannel CNN explicitly detects wisdom teeth in panoramic radiographs; clinical knowledge is input.'),
(63,'confirmed','MFA-Net and its full association-network expansion explicitly segment medical images.'),
(64,'confirmed','RSAFormer and region-self-attention Transformer explicitly segment polyps.'),
(65,'confirmed','ML explicitly identifies at-risk fathers; neither title nor annotation proves valid clinical screening.'),
(66,'confirmed','From ontology to code lacks a literal operation/model name; do not add unstated code generation.'),
(67,'confirmed','Decomposed-subspace learning is explicitly for bidirectional image generation; supervised is setting.'),
(68,'confirmed','Gaussian-convolution-vector histogram explicitly supports leaf recognition; no named leaf dataset.'),
(69,'confirmed','Full tail-fin removal for mass estimation is stated with a computer-vision instrument.'),
(70,'confirmed','AgroPortal is a vocabulary/ontology repository, not automatically a dataset release or learning algorithm.'),
(71,'confirmed','GCN explicitly tracks animals in dense groups; crowd slogan is data, not an instruction.'),
(72,'confirmed','Knowledge-driven DL explicitly diagnoses dairy-cow diseases; illness reports are unnamed data.'),
(73,'confirmed','FL is explicit; optical network/control-plane architecture is infrastructure, not a stated separate computation.'),
(74,'confirmed','Keep nIntroduction typo and computer-vision family; special-section introduction is not experimental evidence.'),
(75,'confirmed','Social-network diffusion models describe propagation, not generative diffusion; no downstream task is named.'),
(76,'confirmed','Ship Detector is an artifact noun; uncertain full detection-task boundary remains quarantined.'),
(77,'confirmed','Review explicitly links DL and driving pedestrian detection, not a new evaluation.'),
(78,'confirmed','NLP explicitly summarizes related blogs; preserve literal apostrophe and unnamed inputs.'),
(79,'confirmed','Correction title quotes ANN/Spark anomaly association; Spark is platform and notice is not an independent experiment.'),
(80,'confirmed','Quoted LSTM detection association is clear, while quantum PSO may tune the detector; correction remains separate.'),
(81,'confirmed','Traffic encoding is explicit, but the literal prediction phrase lacks a target; keep incomplete task inventory.'),
(82,'confirmed','ML segmentation is clear; finite elements may consume anatomy, and full CT task span cannot be reconstructed.'),
(83,'confirmed','ML predicts post-thrombectomy outcomes; radiomics is an input feature, not a separately named model/dataset.'),
(84,'confirmed','Image processing and ML explicitly concern CT stroke diagnosis without any clinical accuracy claim.'),
(85,'confirmed','ML disease prediction/diagnosis association is explicit; preprocessing may only provide inputs.'),
(86,'confirmed','Visual-language foundation models are named; diagnostic/analytical application categories do not specify tasks.'),
(87,'confirmed','DualA-Net and adaptive dual-branch network explicitly segment medical images; generalizable is a quality claim.'),
(88,'confirmed','Iowa Gambling Task is a behavioral protocol, not automatically DATASET; cognitive model versus task execution stays uncertain.'),
(89,'confirmed','ANN explicitly addresses portfolio management with risk/uncertain-return constraints; no investment advice is asserted.'),
(90,'confirmed','Correlation utilization does not specify the sensor scheduling/control operation; goals alone do not establish a task.'),
(91,'confirmed','Spatiotemporal-decoupling Transformer explicitly recognizes 3D skeleton-based driver actions.'),
(92,'confirmed','Backstepping controller and RBF NN are complete methods; physical platform does not supply an absent task literal.'),
(93,'confirmed','Neural network and signal processing are explicit families; large-scale systems is context, not task.'),
(94,'confirmed','Deep RL explicitly performs UAV mission planning; no simulator dataset is inferred.'),
(95,'confirmed','Cybersecurity KG construction is a specific operation; survey supplies no named constructing model.'),
(96,'confirmed','Public safety is broad policy context without a concrete ML detection/prediction task.'),
(97,'confirmed','ML-driven sea-ice retrieval is clear, but the full assessment task overlaps entities; keep uncertainty.'),
(98,'confirmed','ML cloud services are selected products, not the selector; no automatic task-executing model is established.'),
(99,'confirmed','Differential privacy qualifies the full federated-learning method; non-IID is distribution setting.')
]


def review():
    run = ROOT / 'kg_datasets/dblp/course_v4_runs/pending_train_20261007_21'
    source = run / 'generation_decisions.json'
    digest = '6209238d09bacbc5ececd8529b806930cd4dfed8f177ab9e90272a5b0a09b4cf'
    assert c.file_sha256(source) == digest
    first = json.loads(source.read_text(encoding='utf-8'))['decisions']
    assert len(first) == 100 and [i for i,_,_ in JUDGMENTS] == list(range(100))
    replacements = {i:copy.deepcopy(first[i]) for i in (5,32,42,45,61)}
    replacements[5]['entities'][1]['text'] = 'Complex Network'
    replacements[5].update(entityStatus='unresolved',entityReason='Image Analysis is a generic operation without a specified technical subproblem in the coordinated target.',
        relationStatus='unresolved',relationReason='Cannot certify complete concrete-task inventory; the recognition association alone is insufficient.')
    replacements[32]['entities'][0]['text'] = 'Machine Learning'
    replacements[42].update(entityStatus='complete',entityReason='',relationStatus='complete',relationReason='',
        entities=[{'text':'ICDN','label':'METHOD'},{'text':'transformer','label':'METHOD'},{'text':'multimodal sentiment analysis','label':'TASK'}],
        groupMentions=[{'text':'consistency and difference networks','label':'METHOD'}],
        relations=[{'head':'e1','tail':'e3','label':'USED_FOR','reason':'ICDN explicitly targets multimodal sentiment analysis.'},
                   {'head':'e2','tail':'e3','label':'USED_FOR','reason':'The integration Transformer explicitly supports multimodal sentiment analysis.'}])
    replacements[45].update(entityStatus='unresolved',entityReason='CNN target identity overlaps the full accelerating-networks task in the flat schema.',
        relationStatus='unresolved',relationReason='Incomplete flat target/method inventory despite clear pruning-to-acceleration association.')
    replacements[61].update(entityStatus='unresolved',entityReason='Peripheral artery disease management is not a specified technical computational operation.',
        relationStatus='unresolved',relationReason='Full diagnosis-and-management target cannot be certified as complete from the title.')
    judgments = []
    for index,verdict,reason in JUDGMENTS:
        item = {'sampleId':first[index]['sampleId'],'verdict':verdict,'reason':reason}
        if verdict == 'revised': item['replacement'] = replacements[index]
        judgments.append(item)
    path = run / 'review_judgments.json'
    if path.exists(): raise FileExistsError('Preserve existing authored review.')
    c.write_json(path,{'provider':'codex_session','model':'unknown_session_model','round':'candidate_aware_ai_review',
                      'generationDecisionsSha256':digest,'judgments':judgments})
    shutil.copyfile(Path(__file__), run / 'authored_review.py')
    expand_artifact(source,path,run / 'review_expanded')
    dataset = ROOT / 'kg_datasets/dblp/course_v4_weak'
    previous = run / 'generation/receipts.jsonl'
    compile_artifact(dataset,run / 'jobs.jsonl',run / 'review_expanded/review_decisions.json',run / 'review_compiled',previous=previous)
    import_results(dataset,run / 'review_compiled/responses.jsonl',run / 'review',provider='codex_session',model='unknown_session_model',previous=previous)
    parent = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_13'
    target = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_14'
    summary = assemble(dataset,[parent / 'receipts.jsonl',run / 'review/receipts.jsonl'],target)
    original = c.read_jsonl(parent / 'receipts.jsonl')
    assert c.read_jsonl(target / 'receipts.jsonl')[:len(original)] == original
    assert all((parent / name).read_bytes() == (target / name).read_bytes() for name in
               ('ner_inputs_dev.jsonl','ner_inputs_test.jsonl','relation_inputs_dev.jsonl','relation_inputs_test.jsonl'))
    c.write_json(run / 'manifest.json',{'kind':'new_training_labels_same_session_candidate_aware_AI_self_review',
        'parentSnapshotManifestSha256':c.file_sha256(parent / 'manifest.json'),'newSnapshotManifestSha256':c.file_sha256(target / 'manifest.json'),
        'documents':100,'confirmed':95,'revised':5,'humanGold':False,'independentReviewer':False,'trainingStarted':False,
        'finalTestInferenceRepeated':False,'oldReceiptsUnchanged':True,'devTestInputsByteIdentical':True,
        'filesSha256':{p.relative_to(run).as_posix():c.file_sha256(p) for p in run.rglob('*') if p.is_file()}})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    review()
