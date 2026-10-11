"""Codex-authored RE-only judgments on frozen NER entities, not a model API call.

U/N/? are explicit USED_FOR/NO_RELATION/UNRESOLVED decisions in canonical pair
order. E is EVALUATED_ON. '-' means no scoped pair, not a generated negative.
Review comments are candidate-visible same-session AI self-review, not gold.
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_weak as c
from import_course_ai import import_results, assemble
from train_course_ner import verify_files

# The integer index is bound to the exact immutable 10 receipt file and test order.
# Each row was read from its literal title, not from model scores or predictions.
DECISIONS = [
(0,'UU','Both graph networks and augmentation are instruments for social classification.','Both named instruments have the same explicit to-classify target.'),
(1,'U','Federated learning predicts irrigation requirements.','For links FL to the full prediction task.'),
(2,'N','Retrieval assists the speech-recognition mechanism, not the reverse direction.','The METHOD is the beneficiary after For; it is not stated to perform retrieval.'),
(3,'UU','NexusSum and its agent family perform narrative summarization.','Named system and expanded agents share the summarization target.'),
(5,'UU','KG-LLM and its full name are for link prediction.','Both literal model mentions refer to the stated link predictor.'),
(6,'?','Retrieval meets LLMs does not specify which mechanism performs retrieval.','Meets alone is insufficient for a directed use claim or definite negative.'),
(7,'U','Sweep frequency response analysis monitors electrical plant transformers.','Power transformers are equipment in TASK, not a competing neural method.'),
(8,'-','Only two mechanisms; no nonoverlapping TASK or DATASET.','METHOD-to-METHOD control composition is outside this schema.'),
(9,'-','Offline RL only; rewards are not a named dataset.','No scoped tail, hence no relation instance or negative.'),
(10,'U','Hybrid ML predicts student performance.','Educational datasets are unnamed, not an additional evaluation tail.'),
(11,'U','Deep RL is the UAV trajectory optimizer.','RL-Based explicitly links instrument and trajectory target.'),
(13,'U','Hybrid neural network detects methylation.','For names the complete detection target.'),
(14,'UU','FSAM and fine-tuned SAM segment medical images.','Fine-tuning describes the adapted segmenter, not a protected network.'),
(15,'UU','Brain-CDM and its cascaded diffusion model perform MRI super-resolution.','Named model and architecture share the restoration task.'),
(16,'U','Spiking networks perform quadruped closed-loop control.','With denotes the stated control instrument.'),
(18,'-','Transfer-learning mechanism without scoped tail.','No downstream task or benchmark is explicitly named.'),
(19,'U','Deep CNNs perform DGA detection.','For supplies a direct mechanism-to-task link.'),
(21,'U?U?','DL and depthwise convolutions support segmentation; their ordinal-classification roles are underspecified.','Keep ordinal classification pairs unresolved instead of spreading the segmentation claim.'),
(22,'-','Only hierarchical inconsistency detection is in scope.','An image segmentation series is input, not a named method or benchmark.'),
(23,'-','Only translation task is identified.','Continual training is not an additional named METHOD in the frozen inventory.'),
(24,'U','Planning neural network generates Chinese poetry.','With explicitly connects network and generation.'),
(25,'UU','EmoGen and diffusion family generate emotional image content.','Both system name and instrument are linked to the same generation task.'),
(29,'-','FL and encryption are both mechanisms.','No METHOD-to-TASK/DATASET pair; do not reinterpret FL as a task.'),
(30,'U','ML predicts FPGA routing congestion.','Based supplies direct prediction mechanism evidence.'),
(31,'U','RL reoptimization supports SLA-aware cloud query processing.','With links the full optimization instrument to query processing.'),
(32,'U','Fine-tuned LLMs are used for translation.','Diversity is a factor, not a separate target or dataset.'),
(34,'U','CNN estimates musical key.','Using is explicit instrument evidence.'),
(35,'U','CNNs segment agricultural fields from satellite images.','Satellite images are modality input, not a named evaluation dataset.'),
(37,'UU','LLM agents do georelating, explained as locating events.','Task name and literal operational explanation both receive the stated agents.'),
(38,'U','Spiking networks evolved for temporal pattern recognition.','Robustness adjectives do not change the explicit recognition use.'),
(41,'UU','Mask R-CNN and Retinex are combined for road hazard detection.','Both explicit combined instruments serve the detection task.'),
(42,'-','Hybrid index is the sole method.','Linked data is not a named benchmark or computational task here.'),
(44,'??U','PiDiViT is explicitly for detection; standalone patterns and ViT only meet.','Do not project the named composite use onto all constituent mentions.'),
(45,'UU','LLMs and GPT-3.5 play story creation games.','Experiments with the model identifies game-playing use, not a dataset relation.'),
(46,'U','Learnable pixel clustering segments images.','For is direct target evidence despite unsupervised setting.'),
(47,'U','Music Transformer generates long-structure music.','Colon expansion explicitly states model output operation.'),
(49,'-','Only recurrent networks, no scoped tail.','Long sequences are unnamed input, not a benchmark.'),
(50,'U','L-inf-dist networks are used for robustness certification.','Using explicitly names the instrument, unlike a bare protected object.'),
(51,'-','Both subtraction approach and neural speech-enhancement composition are METHODS.','No nested enhancement TASK is invented from the frozen composite.'),
(52,'UE','ML detects breast cancer and is applied on the named Wisconsin dataset.','On the named diagnostic dataset is explicit experimental application evidence.'),
(53,'-','OSP, expanded scheduling approach and ML are methods.','Method-to-method performance improvement is out of scope.'),
(54,'U','ML estimates electric vehicle driving range.','With explicitly connects the instrument and estimation.'),
(55,'U','Deep RL is for multi-agent simulation.','Floor field cutout is an unnamed input representation.'),
(57,'U','Memory-synapse spiking recurrent network performs decision making.','For links the entire hardware-qualified mechanism.'),
(58,'NN','The delayed-coupling networks are the studied source of neuronal activity, not the reconstruction instrument.','By attractor reconstruction in networks separates the operation from the observed system; preserve fixed TASK types.'),
(61,'UU','LEOnto and LDA support ontology enrichment.','Using LDA is the stated instrument for the named enrichment approach.'),
(62,'UUUU','Named GaitForeMer and Transformers use forecasting pretraining and severity estimation.','Both training task and downstream task are explicit; this is use, not DATASET evaluation.'),
(63,'U','LSTM networks perform text classification.','Hyperparameter evaluation is about task use, not an EVALUATED_ON dataset.'),
(64,'U','Voltage-based ML allocates consumption among phases.','For explicitly names the electrical distribution task.'),
(65,'-','Contract design and multi-task FL are both methods.','No new application task inferred from vehicular context.'),
(66,'U','Random target embeddings support continuous-output translation.','For provides the translation use link.'),
(69,'-','Diffusion spectral representation and RL are methods.','No downstream task or named benchmark; method composition excluded.'),
(70,'UU','LiveClip and deep RL support mobile short-form streaming.','With names the method for the streaming approach.'),
(71,'U','Neural architectures enhance asthma prediction.','EHR is generic material, not an additional named dataset.'),
(72,'-','Hybrid quantum-classical network only.','No scoped relation tail.'),
(73,'UU','HLNet and its hierarchical neural model forecast time series.','Named approach and expansion share the explicit forecasting target.'),
(75,'U','Neural architectures identify Arabic dialect.','For explicitly states the use.'),
(77,'-','One composite precoding method.','Cell-free massive MIMO is deployment context, no scoped tail.'),
(79,'U','Neural network approach selects warehouses.','An approach to the selection task is explicit instrument evidence.'),
(80,'U','Attentive deep network classifies multivariate time series.','Which learns explains the mechanism for the stated classification.'),
(81,'-','Only mining knowledge graphs task.','No identifiable method is supplied in the title.'),
(83,'U','Deep learning reconstructs thermal images.','Using is explicit instrument evidence.'),
(85,'U','ML techniques detect offensive and hate speech.','For Detecting is the task use; unnamed tweets are not DATASET.'),
(86,'U','Sketch-guided diffusion synthesizes faces.','For directly names the synthesis target.'),
(87,'U','Sparse autoencoder networks classify pulses.','Based On directly binds mechanism and classifier task.'),
(88,'U','Generative AI models are evaluated for image-text modification use.','Task performance evaluation remains USED_FOR, not dataset evaluation.'),
(89,'U','Tongue-LiteSAM segments tongue images.','For names the segmentation use; zero-shot is a regime.'),
(90,'UU','JFSP-ViT and its expanded Transformer grade retinopathy.','Name and architecture are explicitly for the grading task.'),
(91,'U','ML models are explored for soil nutrient prediction.','Review context limits scientific claims but title still states the method use.'),
(92,'U','Radiomics ML classifies transcriptome subtypes from MRI.','For classifying supplies the full target and input context.'),
(93,'U','Spatial-attention Transformer identifies strawberry disease.','For links the full transformer module to identification.'),
(95,'U','Sentence representation supports entity linking.','Based on supplies explicit mechanism evidence.'),
(97,'-','All LightNN/network mentions are methods.','Comparative network families are not a scoped TASK tail.'),
(99,'U','Capsule-unified neural framework serves graphical programming.','For supplies a directed application link.'),
(100,'U','Graph CNNs perform graph-to-sequence learning.','For explicitly links the architecture and operation.'),
(101,'-','Momentum and network are methods.','Training is not a separately frozen TASK span.'),
(102,'-','Hyperbolic network only.','No scoped tail.'),
(103,'UU','RL and flexible policy iteration control robotic knee.','By policy iteration supplies the second stated control instrument.'),
(105,'U','Cross-modal progressive comprehension segments referring images.','Via explicitly names the mechanism.'),
(108,'U','3D CNN with IoU loss performs crop mapping.','For names the mapping operation, satellite images remain unnamed input.'),
(111,'-','Fine-tuned Transformer only.','Representational clusters are observations, not a scoped task.'),
(112,'U','Graph deep learning explores high-level synthesis design space.','For explicitly names the operation.'),
(114,'-','Transfer learning only in frozen inventory.','Ensembles are not an additional TASK span.'),
(115,'U','Cross-modal causal reasoning performs event-level VQA.','For is direct question-answering instrument evidence.'),
(117,'UUUU','Local_INN and invertible networks support map representation and localization.','With connects both stated operations to the same identifiable mechanism.'),
(118,'U','Sim-to-real deep RL performs UAV obstacle avoidance.','Based is explicit method-to-task evidence.'),
(119,'-','AutoTransfer, AutoML and GNN are methods.','An application to a network is method-to-method and outside schema.'),
(121,'UU','DAM-Net and differential-attention Transformers detect floods.','Using explicitly connects architecture and SAR flood detection.'),
(123,'UU','KoBigBird and Transformer serve Korean language understanding.','The named transformation is for understanding, not a protection task.'),
(124,'-','VCoder, encoders and LLMs are methods.','No scoped tail; do not turn LLM beneficiary into a TASK.'),
(125,'UU','Dialogue simulation and LLMs solve subjective tasks.','Through dialogue simulation for LLMs describes a reasoning procedure for the stated task.'),
(126,'-','One semantic-augmented vision Transformer.','No scoped tail.'),
(127,'-','Representation-learning method only.','Road networks are objects, not a named dataset or TASK span.'),
(128,'-','Audio-visual QA task only.','Overcoming bias is generic study description, no named method.'),
(129,'U','Calibrated LLMs answer binary questions.','For directly names the question-answering use.'),
(131,'UU','LaMoD and latent diffusion generate myocardial strain.','Model name and expanded architecture have the same target.'),
(136,'-','LLM only; competition is an event.','Do not force event name into a benchmark.'),
(137,'?','Dataset is proposed for bioacoustic ML, but no actual evaluation on it is stated.','Dataset-for-method is not proof of EVALUATED_ON; preserve rare-class uncertainty.'),
(138,'UU','Echo state networks and transfer learning learn chaotic attractors.','Using and with directly bind both instruments to attractor learning.'),
(139,'UU','ML and microwave sensing support oils classification.','Using dielectric properties and sensing names the input/instrument route.'),
(140,'U','Program-analysis augmented LLMs generate test code.','Using explicitly binds model and organization-specific code task.'),
(142,'-','SemCSE, embeddings and LLM are methods.','Summaries and abstracts are input material, not named benchmarks.'),
(144,'UU','LLMs and blockchain are integrated for medical-supply negotiation.','Transparent coordination describes the same negotiation mechanism context.'),
(145,'UU','KASportsFormer and anatomy-enhanced Transformer estimate pose.','Both model mentions are explicitly for the full pose target.'),
(146,'??N','Retrieval assists the recognizer; title does not say ALLabel or active learning themselves perform retrieval.','Recognizer is a beneficiary of Using retrieval; reverse usage is negative, other component roles unresolved.'),
(147,'UU','A2FM and agent foundation model do tool-aware hybrid reasoning.','For directly names reasoning target for both mentions.'),
(149,'UU','Plasticine and diffusion translate medical images.','For states the application of both named and expanded model.'),
(153,'U','Deep networks detect resonance responses.','Using explicitly supplies the instrument.'),
(154,'U','ML analyzes Java syntactic constructs.','With provides direct analysis instrument evidence.'),
(155,'-','Only hidden ontology error detection is identified.','Contextual knowledge is not a frozen identifiable METHOD.'),
(158,'UN','ML controls diabetes; parallel calorie measurement is not stated to be produced by ML.','And separates calorie-measurement technique from the ML algorithm; no reverse use inferred.'),
(159,'-','One RL-driven personalized FL composite.','No nested method or TASK fabricated.'),
(160,'U','Deep learning segments medical images.','Using states the instrument even in a survey title.'),
(161,'UU','MAM and multipath attention perform image recognition.','Name and expansion explicitly share recognition target.'),
(162,'U','Energy-conservation neural network analyzes structural dynamics.','For states the application.'),
(164,'UU','Entropy and chaotic optimization both segment images.','Based on both named methods directly supplies instrument evidence.'),
(165,'U','Model-based recurrent network resolves manipulator redundancy.','For states the full constrained-robot target.'),
(166,'U','Depth-imaging augmented binarized network predicts stock direction.','For directly names the prediction use.'),
(167,'??','Conjunction and recommendation subtitle do not establish either directed DL use.','Do not make KG construction or recommendations a positive merely from co-occurrence.'),
(168,'U','Ensemble ML predicts coronary disease.','Integrating data with ensemble ML supports the stated prediction task.'),
(169,'-','CTNRL and representation-learning expansion are methods.','No separately identified scoped tail.'),
(170,'U','Dual-aligned meta-transfer learning diagnoses faults.','For supplies use; few-shot/cross-domain are regimes.'),
(173,'-','GPL-GNN, prompt learning and GNN are methods.','Method composition is not a directed pair in this schema.'),
(174,'UU','DiffLense and conditional diffusion restore gravitational-lensing data.','For binds both model mentions to super-resolution; unnamed data not benchmark.'),
(176,'U','Federated CNN composite detects chest diseases from x-rays.','For explicitly links full composite to detection.'),
(179,'U','ML identifies plants using herbarium specimens.','For supplies the task link; specimens are input rather than named DATASET.'),
(180,'U','Recurrent spiking network recognizes spatiotemporal patterns.','With explicitly states the pattern recognizer.'),
(181,'U','Deep learning predicts patient retinopathy progression.','Predicts is a direct mechanism predicate.'),
(182,'U','Deep learning predicts electrical load.','Based On states instrument of the prediction system.'),
(183,'U','Regressor/backprop neural composite detects moving objects.','For links the entire composite to ADAS detection.'),
(184,'-','ML family only.','Intelligent applications are too generic for a frozen TASK.'),
(185,'-','ML only.','Computer architecture is a field, not a scoped TASK.'),
(186,'-','Phrase-aligned neural translation is one METHOD.','No overlapping translation TASK invented.'),
(188,'-','FL only.','Wireless constraints are setting, not a TASK or named dataset.'),
(189,'U','Heuristic-augmented video-language models answer video questions.','For explicitly links the model composite to VQA.'),
(190,'U','Hybrid CNN/RNN mechanism performs first-break picking.','Using explicitly supplies the full combined network instrument.'),
(191,'UU','Graph attention and VAE-Transformer fuse spectral images.','Via names both mechanisms for the fusion operation.'),
(193,'U','Classifier-guided diffusion reconstructs missing seismic traces.','With directly supplies the reconstruction instrument.'),
(194,'-','Electrical discharge localization task only.','Electrical transformer is equipment, not a neural model.'),
(195,'-','Transformers and RL are methods.','Survey setting supplies no scoped relation tail.'),
(196,'-','Supertwisting neural network only.','Robot manipulators are hardware objects, no TASK span invented.'),
(197,'U','Causal-disentangled representation learning performs domain generalization.','For is direct use evidence for the fixed full mechanism.'),
(198,'U','Diffusion colorizes line drawings.','Through states the method for the colorization task.'),
(199,'U','Neural network estimates bio-cyber interface parameters.','With directly connects network and estimation.'),
]


def main():
    snapshot = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_10'
    dataset = ROOT / 'kg_datasets/dblp/course_v4_weak'
    output = ROOT / 'kg_datasets/dblp/course_v4_runs/test_relation_labels_20261006_17'
    target = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_11'
    if output.exists() or target.exists():
        raise FileExistsError('Preserve RE test labels and receipts; no overwrite')
    assert c.file_sha256(snapshot / 'manifest.json') == 'fc70d7865c59791dc48bc5947e54bd5e07c20cc1a08eb755fe6fdb0f009f3e09'
    assert c.file_sha256(ROOT / 'annotations/course_v4/re_test_selection_20261006.json') == 'e4010d162f525221de7da30cf4c412892564a1da894d1271a72f1ddfa1893978'
    verify_files(snapshot)
    receipts = c.read_jsonl(snapshot / 'receipts.jsonl')
    tests = [r for r in receipts if r['reference']['split']=='test']
    expected = {i for i,r in enumerate(tests) if c.eligible_tasks(r,r['reference'])['ner']}
    assert len(tests)==200 and len(expected)==144 and len(DECISIONS)==len(expected)
    assert {r[0] for r in DECISIONS}==expected
    labels = {'U':'USED_FOR','N':'NO_RELATION','E':'EVALUATED_ON','?':'UNRESOLVED'}
    generated,comments=[],{}
    for i,codes,reason,review_reason in DECISIONS:
        receipt=tests[i]; response=copy.deepcopy(receipt['annotation'])
        pairs=list(c.candidate_pairs(response['entities']))
        assert (codes=='-' and not pairs) or (len(codes)==len(pairs) and set(codes)<=set(labels))
        assert reason.strip() and review_reason.strip()
        response['reviewOfSha256']=None
        response['relationStatus']='unresolved' if '?' in codes else 'complete'
        response['relationReason']=reason if '?' in codes else ''
        response['relations']=[{'head':head,'tail':tail,'label':labels[code],'reason':reason,
            'evidence':None if code=='?' else {'start':0,'end':len(receipt['reference']['text']),'text':receipt['reference']['text']}}
            for (head,tail),code in zip(pairs,codes if codes!='-' else '')]
        response['notes']=f'RE-only first pass; frozen NER parent content SHA256 {receipt["contentSha256"]}. '+reason
        assert not c.validate_response(response,receipt['reference'])
        generated.append(response); comments[response['sampleId']]=review_reason
    output.mkdir(exist_ok=False)
    import shutil
    shutil.copyfile(Path(__file__),output/'authored_decisions.py')
    c.write_jsonl(output/'generation_responses.jsonl',generated)
    import_results(dataset,output/'generation_responses.jsonl',output/'generation',provider='codex_session',model='unknown_session_model')
    initial=c.read_jsonl(output/'generation/receipts.jsonl')
    reviewed=[]; judgments=[]
    for receipt in initial:
        response=copy.deepcopy(receipt['annotation']); sid=response['sampleId']
        response['reviewOfSha256']=receipt['contentSha256']
        response['notes']+=' Candidate-visible same-session RE self-review: '+comments[sid]
        reviewed.append(response)
        judgments.append({'sampleId':sid,'verdict':'confirmed','reason':comments[sid],'reviewOfSha256':receipt['contentSha256']})
    c.write_json(output/'review_judgments.json',{'provider':'codex_session','model':'unknown_session_model',
        'round':'candidate_aware_ai_review','generationResponsesSha256':c.file_sha256(output/'generation_responses.jsonl'),'judgments':judgments})
    c.write_jsonl(output/'review_responses.jsonl',reviewed)
    import_results(dataset,output/'review_responses.jsonl',output/'review',provider='codex_session',model='unknown_session_model',previous=output/'generation/receipts.jsonl')
    replacements={r['reference']['sampleId']:r for r in c.read_jsonl(output/'review/receipts.jsonl')}
    merged=[replacements.get(r['reference']['sampleId'],r) for r in receipts]
    assert len(merged)==908
    for before,after in zip(receipts,merged):
        if before['reference']['split']!='test': assert before==after
        for key in ('entities','groupMentions','entityStatus','entityReason'):
            assert before['annotation'][key]==after['annotation'][key]
    c.write_jsonl(output/'assembled_receipts.jsonl',merged)
    c.write_json(output/'parent_bindings.json',{'parentSnapshot':str(snapshot.relative_to(ROOT)),
        'parentManifestSha256':c.file_sha256(snapshot/'manifest.json'),'RESelectionSha256':c.file_sha256(ROOT/'annotations/course_v4/re_test_selection_20261006.json'),
        'scope':'144 fixed-NER-eligible test papers RE judgments; 56 frozen NER-incomplete test receipts inherited, not treated as negative',
        'allNEREntitiesAndStatusesIdentical':True,'trainDevReceiptsIdentical':True,'humanGold':False,'independentAnnotator':False,
        'prior200TestNERLabelsPreservedInParentSnapshot':True,'newDocumentsAnnotated':0})
    assemble(dataset,[output/'assembled_receipts.jsonl'],target)
    c.write_json(output/'manifest.json',{'kind':'AI_authored_RE_test_labels_on_frozen_NER_entities',
        'filesSha256':{p.relative_to(output).as_posix():c.file_sha256(p) for p in sorted(output.rglob('*')) if p.is_file()},
        'scriptSha256':c.file_sha256(Path(__file__)),'parentManifestSha256':c.file_sha256(snapshot/'manifest.json'),
        'modelCallExecutedByExporter':False,'notice':'Semantic labels and comments are literal Codex session decisions. Export only materializes them. Inherited NER is not newly independent verification.'})
    print(json.dumps(json.loads((target/'summary.json').read_text(encoding='utf-8')),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
