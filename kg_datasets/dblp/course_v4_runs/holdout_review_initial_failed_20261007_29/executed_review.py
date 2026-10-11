"""Explicit same-session candidate-aware judgments; not an independent reviewer or model call."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_weak as c

# Each indexed judgment was authored after reviewing the preserved first pass.
# A revision is fully expanded below before use by the existing review expander.
CONFIRMATIONS = [
    (0,'Physical sensor object excluded; complete NARX network name retained.'),
    (1,'Review wording still explicitly links learning to automated test generation.'),
    (2,'Named framework and model family are METHODs, not an invented comparison task.'),
    (3,'CT scans are input; detection and learning spans and direction are correct.'),
    (4,'gcca is the means for both the explicit representation subtask and disease-analysis goal.'),
    (5,'Full feature-based self-representation mechanism and SAR detection context retained.'),
    (6,'Coordinated mushroom-species task and two explicit means are nonoverlapping.'),
    (7,'The named application is explicitly for automated discovery.'),
    (8,'Metric alias and descriptive metric both refer to text-to-image evaluation.'),
    (9,'Privacy/helpfulness perceptions do not identify another operational task.'),
    (10,'Knowledge graph embedding for fault detection has explicit syntax.'),
    (11,'Reaction-diffusion is physical, so no AI diffusion label is added.'),
    (12,'Ontology-driven planning representations are an explicit planning means.'),
    (13,'Graphene context and tree-based algorithm structure are complete.'),
    (14,'Load monitoring based on learning is explicit.'),
    (15,'Socio-technical augmented-democracy boundary remains unresolved.'),
    (16,'Method alias and graph-network architecture are explicit for video QA.'),
    (17,'Full transformer-based graph architecture is not split into nested methods.'),
    (18,'Twitter is unnamed input, not a DATASET.'),
    (19,'LIGO is an observatory; both denoising means target the specified wave-noise removal.'),
    (20,'Coordinated cross-property analysis still lacks a stable specific task boundary.'),
    (21,'Wearable context is part of cough detection, excluding generic system.'),
    (22,'Physical memory arrays are not method/dataset labels.'),
    (24,'Complete deep-learning Mobile-Net composite is correctly retained.'),
    (25,'Missing-view setting excluded; graph network is used for classification.'),
    (26,'Prompt-recovery target models remain inside the complete task, not nested.'),
    (27,'Both RL and graph representation explicitly support timetable rescheduling.'),
    (28,'Language-specific NLP target present, no resource name invented.'),
    (29,'Full multi-agent RL mechanism and MANET routing context retained.'),
    (30,'Reasoning task and three explicit means are present; every scoped pair judged.'),
    (31,'Dust detection context retained and generic method excluded.'),
    (32,'Detector alias and feature-selection/learning components are explicitly specified.'),
    (33,'Code-smell prevalence does not name a classifier or detection operation.'),
    (34,'Full tire-production forecasting object retained.'),
    (35,'Reviewed use for health prediction is explicit; unnamed databases excluded.'),
    (36,'Generation subtask and concept-discovery goal are both explicitly connected.'),
    (37,'Contiguous asymptotic ensemble and oscillometric estimation context retained.'),
    (38,'Framework robustness study supplies no independently named operational task.'),
    (39,'Average treatment effect is part of the inference target.'),
    (40,'Modern is generic; CNN for smoke detection remains explicit.'),
    (41,'Alternative versus composite training regimes remains an unresolved boundary issue.'),
    (42,'Both named system and latent diffusion means support makeup customization.'),
    (43,'IoT botnet-identification context retained, no traffic dataset invented.'),
    (44,'Surveillance and live CCTV context remain in the concrete crime-detection target.'),
    (45,'Named benchmark is clear but introduction is not explicit evaluated-on evidence.'),
    (47,'Shared system head preserved as a group challenge, not a method endpoint.'),
    (48,'LiDAR is a sensor; layer-based mechanism is explicitly for the stated tasks.'),
    (49,'Prefix sharing is the specified LLM-inference mechanism, not DATASET.'),
    (50,'Minimax kernel learning has explicit proximal causal-inference application.'),
    (51,'Value-iteration architecture retained as a composite method.'),
    (52,'Relational-bias composite is a method without a separate task.'),
    (53,'Distillation is defense means; networks are protected targets, preserving role negative.'),
    (54,'Robot scene-understanding context retained; vision is a modality.'),
    (55,'Full feature-interaction graph architecture and multimodal medical task retained.'),
    (56,'Temperature/material qualification belongs to the physical evaluation target.'),
    (57,'Analysis for networks does not determine method versus target role.'),
    (59,'Transfer models are pruned objects, not named pruning means.'),
    (60,'Bayesian inference explicitly uncovers latent model themes; target is not nested.'),
    (61,'Federated vector-quantization phrase remains ambiguous; no invented relation.'),
    (62,'Distillation is explicitly for CNN design and federated-learning target.'),
    (63,'Swarm ensemble explicitly targets federated learning.'),
    (64,'Parallelism mechanism and wireless federated-learning context retained.'),
    (65,'Cross attention and instrument-aware RL have independent complete names.'),
    (66,'Tracking-method/task ambiguity remains honestly unresolved.'),
    (67,'Actor ontology is a representation; generic modeling is not another task.'),
    (68,'Question does not resolve a positive use assertion or successful elimination.'),
    (69,'Motion-capture datasets are not named benchmarks.'),
    (70,'Image synthesis and downstream segmentation are explicit goals for both means.'),
    (72,'Bibliometric research is study framing, not a concrete operational task.'),
    (73,'Feedback learning is explicitly to improve the target networks, not nested.'),
    (74,'Full microscopy task and transformer framework are nonoverlapping.'),
    (75,'Complex-product planning target and enhanced RL architecture retained.'),
    (76,'Transformers are extraction sources, not extraction means: role negative.'),
    (77,'Occupancy maps are input context, not named DATASET.'),
    (78,'Independent BERT occurrence 1 and the five other model names do not overlap.'),
    (79,'Named package and neural means explicitly solve differential equations.'),
    (80,'Filtered-observation mechanism is explicitly for model-based multi-agent RL.'),
    (81,'Source-code representation is the target; structure/context are generic inputs.'),
    (83,'F-measure supplies the selection/feedback mechanism, not a named dataset.'),
    (84,'KG-based XAI composite explicitly targets process analysis.'),
    (86,'Latent graph prediction is the stated means for representation learning.'),
    (87,'Named exam clear; an introduced exam for LLMs is not evaluated-on evidence.'),
    (88,'Privacy and Byzantine mechanism modifiers form one complete composite.'),
    (89,'QAT and LLM are method classes; no method-method relationship invented.'),
    (90,'Model family is part of the transferability-evaluation object, not nested.'),
    (91,'ECG context retained; two-level CNN and interval-difference means are explicit.'),
    (92,'Entire neural anchoring mechanism retained.'),
    (93,'Two complete interpretability means have no omitted shared head.'),
    (94,'Task-versus-model interpretation of contextualized translation remains unresolved.'),
    (95,'Named pooling is for a model class; no concrete task invented.'),
    (96,'Medical segmentation target clear; training settings are not dataset names.'),
    (97,'Safety shield explicitly targets the RL-navigation problem.'),
    (99,'Network role in the ensemble simulation example remains unresolved.'),
    (100,'Era wording is not an explicit LLM recommendation-use assertion.'),
    (101,'SAR classification and deep learning are explicit, casing preserved.'),
    (102,'Dysarthric speech context retained; interpretable is general qualification.'),
    (103,'Frame-selection operation is not literally supplied; boundary unresolved.'),
    (104,'Translation tools are a technical family, not an unspecified dataset.'),
    (105,'Evolution and network classes identified; trend/challenge is generic framing.'),
    (106,'Creative homogeneity is a studied property, not an operational target.'),
    (107,'Knowledge representation and textual hierarchy explicitly support disambiguation.'),
    (108,'Vision transformer and L2 regularization both explicitly support action recognition.'),
    (109,'Alpha, DBI, transformer and zero-day detection literals are exact and nonoverlapping.'),
    (110,'Corrected/suppressed properties do not identify definite preprocessing algorithms.'),
    (111,'Generative denoising diffusion is explicitly for healthy-tissue inpainting.'),
    (112,'Transfer learning and two named mechanisms explicitly support atomistic simulation.'),
    (113,'Cognitive tasks and framework unnamed; retain only clear spiking network.'),
    (114,'Transportation systems is a domain, not a concrete task verb/object.'),
    (115,'Bidirectional inference architecture is complete and explicitly for saliency.'),
    (116,'Adversarial training mechanism retained with graph network.'),
    (117,'Multicast and RL explicitly target wireless holographic streaming.'),
    (118,'Information-principle composite is one method, without downstream task.'),
    (119,'Agent/model/learning names identified, no operational task invented.'),
    (120,'Intention mechanism belongs to method; online fake-news detection target retained.'),
    (121,'Named target output is record-linkage data, not an identified DATASET.'),
    (122,'Twitter context retained with medication-effect extraction.'),
    (123,'Quantizers explicitly target low-bit LLM compression.'),
    (125,'Full optimization-based deep architecture is kept, no nested spans.'),
    (126,'Reasoning and multimodal model are both explicit detection means.'),
    (127,'Online mechanism and HEVC context retained; fast is generic qualification.'),
    (128,'Fire behavior study supplies no explicit prediction/detection operation.'),
    (129,'No-reference mechanism and pretrained audio networks target artifact detection.'),
    (130,'Full circuit initialization target retained; QAOA not duplicated as a nested method.'),
    (131,'Piecewise physical constraints and equation class retained.'),
    (132,'Architectural implication is study framing, not a task.'),
    (133,'Autoencoder is the specified deep model for road partitioning.'),
    (134,'KEEP explicitly names integration and embedding goals; clinical data not named.'),
    (135,'Quantum/interpretable model qualification retained in the architecture.'),
    (136,'Full attack target retained; no attacker means is named or nested.'),
    (138,'Self-supervised diffusion mechanism and attention are explicit recognition means.'),
    (139,'Surrogate method explicitly optimizes the draft tube.'),
    (141,'Cloud classification uses the explicit unsupervised learning method.'),
    (142,'Prior-knowledge learning is one composite without downstream task.'),
    (143,'Named HiGFA, guidance and diffusion all explicitly support augmentation.'),
    (144,'Robot/human context target is explicit for both model and ontology means.'),
    (145,'Rehabilitation posture target and neural method are exact.'),
    (146,'Early-stage disease qualifier is important target context.'),
    (147,'Model-development guidelines are for the explicit drug-prediction task.'),
    (148,'URLLC multi-connectivity target is explicitly enhanced using RL.'),
    (149,'User sequential-behavior modeling is the explicit neural target.'),
    (150,'RL environment states intended robot-task use, not demonstrated success.'),
    (151,'Annotator metadata is an input; supervised models support prediction.'),
    (154,'Collaboration and RL explicitly support remote intervention.'),
    (155,'Phi is hijacking means; multimodal models are hijacking targets.'),
    (156,'Destination prediction with transformers is explicit; data setting unnamed.'),
    (157,'Self-play and model classes identified; no method-method edge invented.'),
    (158,'Shared model-based system head remains a group challenge.'),
    (159,'Independent probabilistic model mechanism and small-data QA target retained.'),
    (160,'Long motor/controller boundary and direct operation roles remain unresolved.'),
    (161,'Constitutive learning is the specified model-discovery means.'),
    (162,'Signature investigation is generic, no missing detection verb invented.'),
    (163,'Graph network is explicitly used for domain adaptation.'),
    (164,'Indicator-selection deep time-series composite explicitly serves both tasks.'),
    (165,'Named system and neural means explicitly support joint compression/retrieval.'),
    (166,'Full adversarial adaptation architecture explicitly targets NER.'),
    (167,'Amino-acid modality retained with IDR classification; both means explicit.'),
    (168,'Color guidance in diffusion is explicitly applied to low-bitrate compression.'),
    (169,'Evolution study does not resolve whether the model is architecture-search means.'),
    (170,'Grammar templates are explicitly for ontology/model verbalisation.'),
    (171,'Translation is explicitly to inform asylum seekers; MaTIAS is a project.'),
    (172,'Coordinated network-analysis/control roles remain unresolved.'),
    (173,'Clifford algebra supplies the explicit graph-embedding representation.'),
    (174,'Only Image Transformer is named.'),
    (175,'Multirobot problems is a generic domain, not a specific target operation.'),
    (176,'Soft-mask mechanism belongs to the full neural method.'),
    (177,'Platform modifier coordination remains ambiguous, no forced individual roles.'),
    (178,'Fused task/model/components remain ambiguous under nonoverlap constraint.'),
    (179,'Electronics health/life targets are complete and explicitly served by pipeline.'),
    (180,'Positional prompt tuning explicitly targets 3D representation.'),
    (181,'LLM-driven augmentation explicitly addresses the financial-sentiment data gap.'),
    (182,'Model and named ontology explicitly support cyber-plan standardization.'),
    (183,'QA model is comparison baseline, not stated semantic-parsing means.'),
    (184,'Named denoiser and learning family explicitly serve density-map denoising.'),
    (185,'Policy gradient explicitly aligns LLMs; sequence scores are signals.'),
    (186,'Urdu language retained with sentiment target; deep learning method exact.'),
    (187,'Both YOLOv8 version and prompt-optimized SAM explicitly serve infrared tasks.'),
    (188,'Named annotation collaboration and LLM participation explicitly serve training.'),
    (189,'Full decoding/constraint optimization target includes code-generation context.'),
    (190,'TU-VDN alias and formal dataset name exact; no method means no evaluated-on edge.'),
    (191,'Human cognitive learning is not mislabeled as an AI model.'),
    (192,'Azerbaijani language context retained with classification.'),
    (193,'Pretrained prompt-tuning mechanism explicitly supports chemical-protein extraction.'),
    (194,'Underwater localization-fusion context is the explicit neural target.'),
    (195,'Preference and multi-objective qualifiers form one learning method.'),
    (196,'Wireless intrusion target and deep-learning means are exact.'),
    (197,'Social trust study supplies no concrete computational prediction target.'),
    (198,'Complete convolutional framework explicitly serves subpixel mapping.'),
    (199,'Both AI and agent explicitly support automation and the expense-processing case.'),
]


def main():
    runs = ROOT / 'kg_datasets/dblp/course_v4_runs'
    generation = runs / 'holdout_generation_decisions_20261007_29_fixed.json'
    source = json.loads(generation.read_text(encoding='utf-8'))
    assert c.file_sha256(generation) == 'fbdbe55a851e5872e1f151206597439e0638dbb5cc0d81f8ff0574d17d278c33'
    decisions = source['decisions']
    revisions = {}
    # Explicit boundary corrections: a bare linking suffix is not an identified mechanism.
    for i, entity_index, replacement in [(23,0,'Machine Learning'),(58,1,'Jump-Start Reinforcement Learning'),
                                         (82,0,'Deep Reinforcement Learning'),(85,1,'Deep Learning'),
                                         (124,0,'Machine Learning'),(152,0,'Deep Learning')]:
        d = copy.deepcopy(decisions[i]); d['entities'][entity_index]['text'] = replacement
        revisions[i] = (d, 'Remove the dangling based/-based connector before an independent task; retain the full identified learning mechanism.')
    d = copy.deepcopy(decisions[46])
    d.update(entities=[{'label':'METHOD','text':'LLM'},{'label':'TASK','text':'Code Translation'}],
             entityStatus='complete',entityReason='',relationStatus='complete',relationReason='',
             relations=[{'head':'e1','tail':'e2','label':'USED_FOR','reason':'LLM-based explicitly states the means for code translation.'}],
             notes='The based connector separates identified LLM family and code-translation task; evaluation framing does not invalidate this use relation.')
    revisions[46] = (d, 'Resolve the literal LLM and Code Translation boundaries without the linking suffix; explicit based syntax supports use.')
    for i in (71,137,140,153):
        d = copy.deepcopy(decisions[i])
        d.update(relationStatus='unresolved',relationReason='The contextual in/for setting does not conclusively determine target versus method use.')
        for pair in d['relations']:
            pair.update(label='UNRESOLVED',reason='The title identifies a setting or analyzed system, but does not conclusively rule in or rule out method use.')
        revisions[i] = (d, 'Downgrade contextual role negatives to UNRESOLVED; no relation is not justified solely by missing explicit means wording.')
    d = copy.deepcopy(decisions[83]); d['entities'][0]['text'] = 'positive feedback method based on F-measure value'
    d['entities'] = [d['entities'][0],d['entities'][2]]
    d['relations'] = [{'head':'e1','tail':'e2','label':'USED_FOR','reason':'The whole F-measure-based feedback mechanism is explicitly for saliency detection.'}]
    revisions[83] = (d, 'Keep the full contiguous feedback composite and remove its nested metric component; one method endpoint.')
    d = copy.deepcopy(decisions[98]); d['entities'] = [d['entities'][0],d['entities'][2]]
    d['relations'] = [{'head':'e2','tail':'e1','label':'USED_FOR','reason':'Communication with ADMM explicitly improves the vertical federated-learning task.'}]
    revisions[98] = (d, 'Efficient Communication is generic activity/performance wording, not a separate identified technique; ADMM is the explicit means.')
    d = copy.deepcopy(decisions[99]); d['entities'][0]['text'] = 'ensemble simulation'
    revisions[99] = (d, 'Remove generic approach suffix while retaining the ensemble simulation mechanism; preserve unresolved network role.')
    judgments = [{'sampleId':decisions[i]['sampleId'],'verdict':'confirmed','reason':reason} for i,reason in CONFIRMATIONS]
    judgments += [{'sampleId':decisions[i]['sampleId'],'verdict':'revised','reason':reason,'replacement':d} for i,(d,reason) in revisions.items()]
    assert len(judgments) == len({j['sampleId'] for j in judgments}) == 200
    order = {d['sampleId']:i for i,d in enumerate(decisions)}
    judgments.sort(key=lambda j:order[j['sampleId']])
    output = runs / 'holdout_review_judgments_20261007_29.json'
    if output.exists(): raise FileExistsError('Preserve actual candidate-aware judgments')
    c.write_json(output, {'provider':'current_codex_session','model':'unknown_session_model',
        'round':'candidate_aware_ai_review','generationDecisionsSha256':c.file_sha256(generation),'judgments':judgments})
    print(json.dumps({'judgments':len(judgments),'confirmed':len(CONFIRMATIONS),'revised':len(revisions),'independentReviewer':False}))


if __name__ == '__main__': main()
