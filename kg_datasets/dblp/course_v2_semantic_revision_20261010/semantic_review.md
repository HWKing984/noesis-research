# V2 首批语义修订审核包

AI原文复核与同会话自查，非独立人工gold。仅摘要训练侧；不训练、不覆盖旧数据。

## 2008.10400

来源：http://arxiv.org/abs/2008.10400v2

### 摘要原文

We report that a very high accuracy on the MNIST test set can be achieved by using simple convolutional neural network (CNN) models. We use three different models with 3x3, 5x5, and 7x7 kernel size in the convolution layers. Each model consists of a set of convolution layers followed by a single fully connected layer. Every convolution layer uses batch normalization and ReLU activation, and pooling is not used. Rotation and translation is used to augment training data, which is frequently used in most image classification tasks. A majority voting using the three models independently trained on the training data set can achieve up to 99.87% accuracy on the test set, which is one of the state-of-the-art results. A two-layer ensemble, a heterogeneous ensemble of three homogeneous ensemble networks, can achieve up to 99.91% test accuracy. The results can be reproduced by using the code at: https://github.com/ansh941/MnistSimpleCNN

### 实体审核

完整性状态：unresolved。Eight existing mentions have supported names/types and literal boundaries. However, fully connected layer, Rotation and translation are explicit architecture/augmentation omission candidates. Do not claim exhaustive NER or label these unreviewed spans O.

| ID | 类别 | 原文提及 | 偏移 |
|---|---|---|---|
| e1 | DATASET | MNIST | 43:48 |
| e2 | METHOD | convolutional neural network | 90:118 |
| e3 | METHOD | CNN | 120:123 |
| e4 | METHOD | batch normalization | 349:368 |
| e5 | METHOD | ReLU activation | 373:388 |
| e6 | TASK | image classification | 507:527 |
| e7 | METHOD | majority voting | 537:552 |
| e8 | METHOD | two-layer ensemble | 722:740 |

### 关系复核（包含全部旧已判项、新增项和撤回项）

- `e2 convolutional neural network → e1 MNIST`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：CNN is the immediately defined abbreviation of convolutional neural network; the first sentence directly names MNIST and the measured models.

  谓词证据 [0:132]：We report that a very high accuracy on the MNIST test set can be achieved by using simple convolutional neural network (CNN) models.

- `e3 CNN → e1 MNIST`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：CNN is the immediately defined abbreviation of convolutional neural network; the first sentence directly names MNIST and the measured models.

  谓词证据 [0:132]：We report that a very high accuracy on the MNIST test set can be achieved by using simple convolutional neural network (CNN) models.

- `e7 majority voting → e1 MNIST`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：The test set refers back to MNIST in the opening sentence. This is the separately reported ensemble inference strategy's result, not batch-normalization/ReLU component scores.

  谓词证据 [535:719]：A majority voting using the three models independently trained on the training data set can achieve up to 99.87% accuracy on the test set, which is one of the state-of-the-art results.

- `e8 two-layer ensemble → e1 MNIST`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：The contiguous experiment discusses the MNIST test set and reports a distinct two-layer ensemble result; preserve that explicit paragraph-local dataset chain.

  谓词证据 [720:846]：A two-layer ensemble, a heterogeneous ensemble of three homogeneous ensemble networks, can achieve up to 99.91% test accuracy.

保留未决说明：Components and the generic image-classification context do not acquire test/capability edges by co-occurrence. Entity omissions block this document's NER and paired training export.

同会话自查：Re-read the first MNIST sentence and both separately reported ensemble scores. Their dataset chain is explicit; do not transfer scores to normalization/activation. Existing spans are sound but identified architecture/augmentation omissions block exhaustive NER admission.

## 2501.02474

来源：http://arxiv.org/abs/2501.02474v1

### 摘要原文

Remote sensing object detection is particularly challenging due to the high resolution, multi-scale features, and diverse ground object characteristics inherent in satellite and UAV imagery. These challenges necessitate more advanced approaches for effective object detection in such environments. While deep learning methods have achieved remarkable success in remote sensing object detection, they typically rely on large amounts of labeled data. Acquiring sufficient labeled data, particularly for novel or rare objects, is both challenging and time-consuming in remote sensing scenarios, limiting the generalization capabilities of existing models. To address these challenges, few-shot learning (FSL) has emerged as a promising approach, aiming to enable models to learn new classes from limited labeled examples. Building on this concept, few-shot object detection (FSOD) specifically targets object detection challenges in data-limited conditions. However, the generalization capability of FSOD models, particularly in remote sensing, is often constrained by the complex and diverse characteristics of the objects present in such environments. In this paper, we propose the Generalization-Enhanced Few-Shot Object Detection (GE-FSOD) model to improve the generalization capability in remote sensing FSOD tasks. Our model introduces three key innovations: the Cross-Level Fusion Pyramid Attention Network (CFPAN) for enhanced multi-scale feature representation, the Multi-Stage Refinement Region Proposal Network (MRRPN) for more accurate region proposals, and the Generalized Classification Loss (GCL) for improved classification performance in few-shot scenarios. Extensive experiments on the DIOR and NWPU VHR-10 datasets show that our model achieves state-of-the-art performance for few-shot object detection in remote sensing.

### 实体审核

完整性状态：unresolved。All21 existing mentions have valid supported categories: FSOD in descriptive task positions is TASK, whereas the full GE-FSOD model name and its abbreviation are METHOD. The explicit deep learning methods occurrence and component feature/proposal objectives need a completeness/boundary decision; withhold full-sequence NER admission.

| ID | 类别 | 原文提及 | 偏移 |
|---|---|---|---|
| e1 | TASK | Remote sensing object detection | 0:31 |
| e2 | TASK | object detection | 259:275 |
| e3 | TASK | remote sensing object detection | 362:393 |
| e4 | METHOD | few-shot learning | 682:699 |
| e5 | METHOD | FSL | 701:704 |
| e6 | TASK | few-shot object detection | 845:870 |
| e7 | TASK | FSOD | 872:876 |
| e8 | TASK | object detection | 899:915 |
| e9 | TASK | FSOD | 997:1001 |
| e10 | METHOD | Generalization-Enhanced Few-Shot Object Detection | 1181:1230 |
| e11 | METHOD | GE-FSOD | 1232:1239 |
| e12 | TASK | FSOD | 1306:1310 |
| e13 | METHOD | Cross-Level Fusion Pyramid Attention Network | 1366:1410 |
| e14 | METHOD | CFPAN | 1412:1417 |
| e15 | METHOD | Multi-Stage Refinement Region Proposal Network | 1472:1518 |
| e16 | METHOD | MRRPN | 1520:1525 |
| e17 | METHOD | Generalized Classification Loss | 1571:1602 |
| e18 | METHOD | GCL | 1604:1607 |
| e19 | DATASET | DIOR | 1701:1705 |
| e20 | DATASET | NWPU VHR-10 | 1710:1721 |
| e21 | TASK | few-shot object detection | 1793:1818 |

### 关系复核（包含全部旧已判项、新增项和撤回项）

- `e10 Generalization-Enhanced Few-Shot Object Detection → e6 few-shot object detection`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：GE-FSOD is the explicit model alias, and FSOD is defined as few-shot object detection. Repeated task mentions refer to that same task, not independent evidence; count them within one paper/alias chain.

  谓词证据 [1151:1317]：In this paper, we propose the Generalization-Enhanced Few-Shot Object Detection (GE-FSOD) model to improve the generalization capability in remote sensing FSOD tasks.

- `e10 Generalization-Enhanced Few-Shot Object Detection → e7 FSOD`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：GE-FSOD is the explicit model alias, and FSOD is defined as few-shot object detection. Repeated task mentions refer to that same task, not independent evidence; count them within one paper/alias chain.

  谓词证据 [1151:1317]：In this paper, we propose the Generalization-Enhanced Few-Shot Object Detection (GE-FSOD) model to improve the generalization capability in remote sensing FSOD tasks.

- `e10 Generalization-Enhanced Few-Shot Object Detection → e9 FSOD`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：GE-FSOD is the explicit model alias, and FSOD is defined as few-shot object detection. Repeated task mentions refer to that same task, not independent evidence; count them within one paper/alias chain.

  谓词证据 [1151:1317]：In this paper, we propose the Generalization-Enhanced Few-Shot Object Detection (GE-FSOD) model to improve the generalization capability in remote sensing FSOD tasks.

- `e10 Generalization-Enhanced Few-Shot Object Detection → e12 FSOD`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：GE-FSOD is the explicit model alias, and FSOD is defined as few-shot object detection. Repeated task mentions refer to that same task, not independent evidence; count them within one paper/alias chain.

  谓词证据 [1151:1317]：In this paper, we propose the Generalization-Enhanced Few-Shot Object Detection (GE-FSOD) model to improve the generalization capability in remote sensing FSOD tasks.

- `e10 Generalization-Enhanced Few-Shot Object Detection → e19 DIOR`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：Our model resolves to the explicitly proposed GE-FSOD. Its named components CFPAN/MRRPN/GCL are not separately measured benchmark actors.

  谓词证据 [1672:1837]：Extensive experiments on the DIOR and NWPU VHR-10 datasets show that our model achieves state-of-the-art performance for few-shot object detection in remote sensing.

- `e10 Generalization-Enhanced Few-Shot Object Detection → e20 NWPU VHR-10`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：Our model resolves to the explicitly proposed GE-FSOD. Its named components CFPAN/MRRPN/GCL are not separately measured benchmark actors.

  谓词证据 [1672:1837]：Extensive experiments on the DIOR and NWPU VHR-10 datasets show that our model achieves state-of-the-art performance for few-shot object detection in remote sensing.

- `e10 Generalization-Enhanced Few-Shot Object Detection → e21 few-shot object detection`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：GE-FSOD is the explicit model alias, and FSOD is defined as few-shot object detection. Repeated task mentions refer to that same task, not independent evidence; count them within one paper/alias chain.

  谓词证据 [1151:1317]：In this paper, we propose the Generalization-Enhanced Few-Shot Object Detection (GE-FSOD) model to improve the generalization capability in remote sensing FSOD tasks.

- `e11 GE-FSOD → e6 few-shot object detection`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：GE-FSOD is the explicit model alias, and FSOD is defined as few-shot object detection. Repeated task mentions refer to that same task, not independent evidence; count them within one paper/alias chain.

  谓词证据 [1151:1317]：In this paper, we propose the Generalization-Enhanced Few-Shot Object Detection (GE-FSOD) model to improve the generalization capability in remote sensing FSOD tasks.

- `e11 GE-FSOD → e7 FSOD`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：GE-FSOD is the explicit model alias, and FSOD is defined as few-shot object detection. Repeated task mentions refer to that same task, not independent evidence; count them within one paper/alias chain.

  谓词证据 [1151:1317]：In this paper, we propose the Generalization-Enhanced Few-Shot Object Detection (GE-FSOD) model to improve the generalization capability in remote sensing FSOD tasks.

- `e11 GE-FSOD → e9 FSOD`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：GE-FSOD is the explicit model alias, and FSOD is defined as few-shot object detection. Repeated task mentions refer to that same task, not independent evidence; count them within one paper/alias chain.

  谓词证据 [1151:1317]：In this paper, we propose the Generalization-Enhanced Few-Shot Object Detection (GE-FSOD) model to improve the generalization capability in remote sensing FSOD tasks.

- `e11 GE-FSOD → e12 FSOD`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：GE-FSOD is the explicit model alias, and FSOD is defined as few-shot object detection. Repeated task mentions refer to that same task, not independent evidence; count them within one paper/alias chain.

  谓词证据 [1151:1317]：In this paper, we propose the Generalization-Enhanced Few-Shot Object Detection (GE-FSOD) model to improve the generalization capability in remote sensing FSOD tasks.

- `e11 GE-FSOD → e19 DIOR`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：Our model resolves to the explicitly proposed GE-FSOD. Its named components CFPAN/MRRPN/GCL are not separately measured benchmark actors.

  谓词证据 [1672:1837]：Extensive experiments on the DIOR and NWPU VHR-10 datasets show that our model achieves state-of-the-art performance for few-shot object detection in remote sensing.

- `e11 GE-FSOD → e20 NWPU VHR-10`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：Our model resolves to the explicitly proposed GE-FSOD. Its named components CFPAN/MRRPN/GCL are not separately measured benchmark actors.

  谓词证据 [1672:1837]：Extensive experiments on the DIOR and NWPU VHR-10 datasets show that our model achieves state-of-the-art performance for few-shot object detection in remote sensing.

- `e11 GE-FSOD → e21 few-shot object detection`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：GE-FSOD is the explicit model alias, and FSOD is defined as few-shot object detection. Repeated task mentions refer to that same task, not independent evidence; count them within one paper/alias chain.

  谓词证据 [1151:1317]：In this paper, we propose the Generalization-Enhanced Few-Shot Object Detection (GE-FSOD) model to improve the generalization capability in remote sensing FSOD tasks.

保留未决说明：Family FSL and GE-FSOD components are not silently assigned every abstract task or the overall model's dataset results.

同会话自查：Re-read the model introduction and both named-dataset results. Our model refers to GE-FSOD, not each component. Repeated FSOD/GE-FSOD occurrences share evidence rather than independent support. The missing deep-learning family and objective granularity require further NER coverage work.

## 2107.03374

来源：http://arxiv.org/abs/2107.03374v2

### 摘要原文

We introduce Codex, a GPT language model fine-tuned on publicly available code from GitHub, and study its Python code-writing capabilities. A distinct production version of Codex powers GitHub Copilot. On HumanEval, a new evaluation set we release to measure functional correctness for synthesizing programs from docstrings, our model solves 28.8% of the problems, while GPT-3 solves 0% and GPT-J solves 11.4%. Furthermore, we find that repeated sampling from the model is a surprisingly effective strategy for producing working solutions to difficult prompts. Using this method, we solve 70.2% of our problems with 100 samples per problem. Careful investigation of our model reveals its limitations, including difficulty with docstrings describing long chains of operations and with binding operations to variables. Finally, we discuss the potential broader impacts of deploying powerful code generation technologies, covering safety, security, and economics.

### 实体审核

完整性状态：complete。All10 mentions are source-supported; GPT remains a method-family mention, not an independently evaluated Python-specialized actor. The second Codex occurrence describes a distinct production version, not an automatic alias of the measured research model. GitHub Copilot is a product name, outside this extraction schema.

| ID | 类别 | 原文提及 | 偏移 |
|---|---|---|---|
| e1 | METHOD | Codex | 13:18 |
| e2 | METHOD | GPT | 22:25 |
| e3 | TASK | Python code-writing | 106:125 |
| e4 | METHOD | Codex | 173:178 |
| e5 | DATASET | HumanEval | 205:214 |
| e6 | TASK | synthesizing programs from docstrings | 286:323 |
| e7 | METHOD | GPT-3 | 371:376 |
| e8 | METHOD | GPT-J | 391:396 |
| e9 | METHOD | repeated sampling | 437:454 |
| e10 | TASK | code generation | 889:904 |

### 关系复核（包含全部旧已判项、新增项和撤回项）

- `e1 Codex → e3 Python code-writing`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：Its refers to introduced Codex, not to every GPT model or the separately mentioned production version.

  谓词证据 [0:139]：We introduce Codex, a GPT language model fine-tuned on publicly available code from GitHub, and study its Python code-writing capabilities.

- `e1 Codex → e5 HumanEval`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：Our model is the introduced Codex; GPT-3 and GPT-J have separate named results. Zero success is still evaluation, not NO_RELATION.

  谓词证据 [202:410]：On HumanEval, a new evaluation set we release to measure functional correctness for synthesizing programs from docstrings, our model solves 28.8% of the problems, while GPT-3 solves 0% and GPT-J solves 11.4%.

- `e1 Codex → e6 synthesizing programs from docstrings`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：All three named tested systems attempt the benchmark's explicit synthesis task; USED_FOR does not require successful answers on every task item.

  谓词证据 [202:410]：On HumanEval, a new evaluation set we release to measure functional correctness for synthesizing programs from docstrings, our model solves 28.8% of the problems, while GPT-3 solves 0% and GPT-J solves 11.4%.

- `e1 Codex → e10 code generation`：**USED_FOR → UNRESOLVED**；角色 `unresolved`。

  理由：The final code-generation occurrence is in a broad impacts discussion; do not make a new local capability assertion from that discussion alone.

- `e2 GPT → e3 Python code-writing`：**USED_FOR → UNRESOLVED**；角色 `unresolved`。

  理由：GPT is an appositional family descriptor; the specialized capability pronoun refers to introduced Codex, not independently to generic GPT.

- `e4 Codex → e3 Python code-writing`：**USED_FOR → UNRESOLVED**；角色 `unresolved`。

  理由：This Codex mention is explicitly a distinct production version. The abstract does not separately establish its equivalence to the research actor or the same task predicates.

- `e4 Codex → e6 synthesizing programs from docstrings`：**USED_FOR → UNRESOLVED**；角色 `unresolved`。

  理由：This Codex mention is explicitly a distinct production version. The abstract does not separately establish its equivalence to the research actor or the same task predicates.

- `e4 Codex → e10 code generation`：**USED_FOR → UNRESOLVED**；角色 `unresolved`。

  理由：This Codex mention is explicitly a distinct production version. The abstract does not separately establish its equivalence to the research actor or the same task predicates.

- `e7 GPT-3 → e5 HumanEval`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：Our model is the introduced Codex; GPT-3 and GPT-J have separate named results. Zero success is still evaluation, not NO_RELATION.

  谓词证据 [202:410]：On HumanEval, a new evaluation set we release to measure functional correctness for synthesizing programs from docstrings, our model solves 28.8% of the problems, while GPT-3 solves 0% and GPT-J solves 11.4%.

- `e7 GPT-3 → e6 synthesizing programs from docstrings`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：All three named tested systems attempt the benchmark's explicit synthesis task; USED_FOR does not require successful answers on every task item.

  谓词证据 [202:410]：On HumanEval, a new evaluation set we release to measure functional correctness for synthesizing programs from docstrings, our model solves 28.8% of the problems, while GPT-3 solves 0% and GPT-J solves 11.4%.

- `e8 GPT-J → e5 HumanEval`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：Our model is the introduced Codex; GPT-3 and GPT-J have separate named results. Zero success is still evaluation, not NO_RELATION.

  谓词证据 [202:410]：On HumanEval, a new evaluation set we release to measure functional correctness for synthesizing programs from docstrings, our model solves 28.8% of the problems, while GPT-3 solves 0% and GPT-J solves 11.4%.

- `e8 GPT-J → e6 synthesizing programs from docstrings`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：All three named tested systems attempt the benchmark's explicit synthesis task; USED_FOR does not require successful answers on every task item.

  谓词证据 [202:410]：On HumanEval, a new evaluation set we release to measure functional correctness for synthesizing programs from docstrings, our model solves 28.8% of the problems, while GPT-3 solves 0% and GPT-J solves 11.4%.

- `e9 repeated sampling → e5 HumanEval`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：This method explicitly refers to repeated sampling; our problems refers to HumanEval problems in the preceding result sentence. The strategy receives its own reported result, unlike an unevaluated architectural component.

  谓词证据 [411:560]：Furthermore, we find that repeated sampling from the model is a surprisingly effective strategy for producing working solutions to difficult prompts.

  谓词证据 [561:640]：Using this method, we solve 70.2% of our problems with 100 samples per problem.

- `e9 repeated sampling → e6 synthesizing programs from docstrings`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：Working solutions and our problems resolve to the immediately stated program-synthesis benchmark task. This is explicit strategy operation, not abstract-level task inheritance.

  谓词证据 [411:560]：Furthermore, we find that repeated sampling from the model is a surprisingly effective strategy for producing working solutions to difficult prompts.

  谓词证据 [561:640]：Using this method, we solve 70.2% of our problems with 100 samples per problem.

保留未决说明：Preserve all other unknown pairs. No benchmark edges for the distinct production actor or generic GPT, and no absence negatives.

同会话自查：Re-read all Codex clauses: distinct production version is not certified equivalent to the research actor. GPT apposition and final societal-impact discussion do not establish additional specialized capabilities. Repeated sampling has its own reported score and explicit this-method/our-problems chain, so retain it rather than reject every reviewed case.

## 1606.05250

来源：http://arxiv.org/abs/1606.05250v3

### 摘要原文

We present the Stanford Question Answering Dataset (SQuAD), a new reading comprehension dataset consisting of 100,000+ questions posed by crowdworkers on a set of Wikipedia articles, where the answer to each question is a segment of text from the corresponding reading passage. We analyze the dataset to understand the types of reasoning required to answer the questions, leaning heavily on dependency and constituency trees. We build a strong logistic regression model, which achieves an F1 score of 51.0%, a significant improvement over a simple baseline (20%). However, human performance (86.8%) is much higher, indicating that the dataset presents a good challenge problem for future research.
  The dataset is freely available at https://stanford-qa.com

### 实体审核

完整性状态：complete。The full dataset name and SQuAD are distinct supported occurrences/aliases. Logistic regression is the named method. Dependency/constituency trees are analysis representations without a separately named parsing method; Wikipedia is article provenance, not the evaluated named benchmark here.

| ID | 类别 | 原文提及 | 偏移 |
|---|---|---|---|
| e1 | DATASET | Stanford Question Answering Dataset | 15:50 |
| e2 | DATASET | SQuAD | 52:57 |
| e3 | TASK | reading comprehension | 66:87 |
| e4 | METHOD | logistic regression | 444:463 |

### 关系复核（包含全部旧已判项、新增项和撤回项）

- `e4 logistic regression → e1 Stanford Question Answering Dataset`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：The sole dataset being presented/analyzed is Stanford Question Answering Dataset (SQuAD); which directly attaches the reported score to logistic regression.

  谓词证据 [426:563]：We build a strong logistic regression model, which achieves an F1 score of 51.0%, a significant improvement over a simple baseline (20%).

- `e4 logistic regression → e2 SQuAD`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：The sole dataset being presented/analyzed is Stanford Question Answering Dataset (SQuAD); which directly attaches the reported score to logistic regression.

  谓词证据 [426:563]：We build a strong logistic regression model, which achieves an F1 score of 51.0%, a significant improvement over a simple baseline (20%).

- `e4 logistic regression → e3 reading comprehension`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：The preceding dataset definition identifies reading comprehension as the scored task. No model/task name is imported from the title.

  谓词证据 [426:563]：We build a strong logistic regression model, which achieves an F1 score of 51.0%, a significant improvement over a simple baseline (20%).

保留未决说明：All three scoped pairs have source-local evidence; the two dataset aliases are not independent benchmark studies.

同会话自查：Re-read the whole SQuAD abstract; the logistic model's relative clause supplies the score and the sole presented dataset/task supplies its antecedent. Dataset aliases are one experimental context, not two independent evaluations.

## 2501.06756

来源：http://arxiv.org/abs/2501.06756v2

### 摘要原文

With advancements in physical power systems and network technologies, integrated Cyber-Physical Power Systems (CPPS) have significantly enhanced system monitoring and control efficiency and reliability. This integration, however, introduces complex challenges in designing coherent CPPS, particularly as few studies concurrently address the deployment of physical layers and communication connections in the cyber layer. This paper addresses these challenges by proposing a framework for robust sensor placement to optimize anomaly detection in the physical layer and enhance communication resilience in the cyber layer. We model the CPPS as an interdependent network via a graph, allowing for simultaneous consideration of both layers. Then, we adopt the Log-normal Shadowing Path Loss (LNSPL) model to ensure reliable data transmission. Additionally, we leverage the Fiedler value to measure graph resilience against line failures and three anomaly detectors to fortify system safety. However, the optimization problem is NP-hard. Therefore, we introduce the Experience Feedback Graph Diffusion (EFGD) algorithm, which utilizes a diffusion process to generate optimal sensor placement strategies. This algorithm incorporates cross-entropy gradient and experience feedback mechanisms to expedite convergence and generate higher reward strategies. Extensive simulations demonstrate that the EFGD algorithm enhances model convergence by 18.9% over existing graph diffusion methods and improves average reward by 22.90% compared to Denoising Diffusion Policy Optimization (DDPO) and 19.57% compared to Graph Diffusion Policy Optimization (GDPO), thereby significantly bolstering the robustness and reliability of CPPS operations.

### 实体审核

完整性状态：unresolved。All14 retained mentions are supported; CPU/power-system terminology and CPPS are not neural methods or datasets. The explicit objective measure graph resilience against line failures and experience feedback mechanisms require omission/granularity decisions. Fiedler value is a spectral measure, not automatically METHOD. Withhold exhaustive BIO supervision.

| ID | 类别 | 原文提及 | 偏移 |
|---|---|---|---|
| e1 | TASK | robust sensor placement | 488:511 |
| e2 | TASK | anomaly detection | 524:541 |
| e3 | METHOD | Log-normal Shadowing Path Loss | 756:786 |
| e4 | METHOD | LNSPL | 788:793 |
| e5 | TASK | reliable data transmission | 811:837 |
| e6 | METHOD | Experience Feedback Graph Diffusion | 1061:1096 |
| e7 | METHOD | EFGD | 1098:1102 |
| e8 | TASK | generate optimal sensor placement strategies | 1153:1197 |
| e9 | METHOD | cross-entropy gradient | 1227:1249 |
| e10 | METHOD | EFGD | 1391:1395 |
| e11 | METHOD | Denoising Diffusion Policy Optimization | 1530:1569 |
| e12 | METHOD | DDPO | 1571:1575 |
| e13 | METHOD | Graph Diffusion Policy Optimization | 1600:1635 |
| e14 | METHOD | GDPO | 1637:1641 |

### 关系复核（包含全部旧已判项、新增项和撤回项）

- `e3 Log-normal Shadowing Path Loss → e5 reliable data transmission`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：The full name and LNSPL are explicitly the model adopted for the named transmission objective.

  谓词证据 [737:838]：Then, we adopt the Log-normal Shadowing Path Loss (LNSPL) model to ensure reliable data transmission.

- `e3 Log-normal Shadowing Path Loss → e8 generate optimal sensor placement strategies`：**NO_RELATION → UNRESOLVED**；角色 `unresolved`。

  理由：Different transmission and placement roles do not explicitly exclude a component's contribution to placement. No object/operator or mutually partitioned output contrast sufficient for a factual negative is stated.

- `e4 LNSPL → e5 reliable data transmission`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：The full name and LNSPL are explicitly the model adopted for the named transmission objective.

  谓词证据 [737:838]：Then, we adopt the Log-normal Shadowing Path Loss (LNSPL) model to ensure reliable data transmission.

- `e4 LNSPL → e8 generate optimal sensor placement strategies`：**NO_RELATION → UNRESOLVED**；角色 `unresolved`。

  理由：Different transmission and placement roles do not explicitly exclude a component's contribution to placement. No object/operator or mutually partitioned output contrast sufficient for a factual negative is stated.

- `e6 Experience Feedback Graph Diffusion → e1 robust sensor placement`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：EFGD and its repeated exact name refer to the introduced placement algorithm. Robust sensor placement is its explicitly stated problem context, not anomaly detection assigned to every component.

  谓词证据 [1033:1198]：Therefore, we introduce the Experience Feedback Graph Diffusion (EFGD) algorithm, which utilizes a diffusion process to generate optimal sensor placement strategies.

- `e6 Experience Feedback Graph Diffusion → e8 generate optimal sensor placement strategies`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：EFGD and its repeated exact name refer to the introduced placement algorithm. Robust sensor placement is its explicitly stated problem context, not anomaly detection assigned to every component.

  谓词证据 [1033:1198]：Therefore, we introduce the Experience Feedback Graph Diffusion (EFGD) algorithm, which utilizes a diffusion process to generate optimal sensor placement strategies.

- `e7 EFGD → e1 robust sensor placement`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：EFGD and its repeated exact name refer to the introduced placement algorithm. Robust sensor placement is its explicitly stated problem context, not anomaly detection assigned to every component.

  谓词证据 [1033:1198]：Therefore, we introduce the Experience Feedback Graph Diffusion (EFGD) algorithm, which utilizes a diffusion process to generate optimal sensor placement strategies.

- `e7 EFGD → e8 generate optimal sensor placement strategies`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：EFGD and its repeated exact name refer to the introduced placement algorithm. Robust sensor placement is its explicitly stated problem context, not anomaly detection assigned to every component.

  谓词证据 [1033:1198]：Therefore, we introduce the Experience Feedback Graph Diffusion (EFGD) algorithm, which utilizes a diffusion process to generate optimal sensor placement strategies.

- `e10 EFGD → e1 robust sensor placement`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：EFGD and its repeated exact name refer to the introduced placement algorithm. Robust sensor placement is its explicitly stated problem context, not anomaly detection assigned to every component.

  谓词证据 [1033:1198]：Therefore, we introduce the Experience Feedback Graph Diffusion (EFGD) algorithm, which utilizes a diffusion process to generate optimal sensor placement strategies.

- `e10 EFGD → e8 generate optimal sensor placement strategies`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：EFGD and its repeated exact name refer to the introduced placement algorithm. Robust sensor placement is its explicitly stated problem context, not anomaly detection assigned to every component.

  谓词证据 [1033:1198]：Therefore, we introduce the Experience Feedback Graph Diffusion (EFGD) algorithm, which utilizes a diffusion process to generate optimal sensor placement strategies.

保留未决说明：Do not assign overall placement/anomaly tasks to gradient, comparator algorithms or transmission components without their own predicate; the two old negatives become unresolved.

同会话自查：Re-read the LNSPL transmission clause and EFGD placement clause. Retain their direct positive predicates, but different component purposes do not suffice to deny LNSPL involvement in placement. Two negatives become unknown; identified missing objectives block exhaustive NER.

## 1903.10404

来源：https://arxiv.org/abs/1903.10404

### 摘要原文

In autonomous embedded systems, it is often vital to reduce the amount of actions taken in the real world and energy required to learn a policy. Training reinforcement learning agents from high dimensional image representations can be very expensive and time consuming. Autoencoders are deep neural network used to compress high dimensional data such as pixelated images into small latent representations. This compression model is vital to efficiently learn policies, especially when learning on embedded systems. We have implemented this model on the NVIDIA Jetson TX2 embedded GPU, and evaluated the power consumption, throughput, and energy consumption of the autoencoders for various CPU/GPU core combinations, frequencies, and model parameters. Additionally, we have shown the reconstructions generated by the autoencoder to analyze the quality of the generated compressed representation and also the performance of the reinforcement learning agent. Finally, we have presented an assessment of the viability of training these models on embedded systems and their usefulness in developing autonomous policies. Using autoencoders, we were able to achieve 4-5 $\times$ improved performance compared to a baseline RL agent with a convolutional feature extractor, while using less than 2W of power.

### 实体审核

完整性状态：complete。All10 mentions are supported; reinforcement learning and RL are method-family mentions. Embedded GPU is hardware, not METHOD/DATASET. Compress high dimensional data is the explicitly defined operation. Singular/plural autoencoder occurrences are preserved, not counted as independent experiments.

| ID | 类别 | 原文提及 | 偏移 |
|---|---|---|---|
| e1 | METHOD | reinforcement learning | 154:176 |
| e2 | METHOD | Autoencoders | 270:282 |
| e3 | METHOD | deep neural network | 287:306 |
| e4 | TASK | compress high dimensional data | 315:345 |
| e5 | METHOD | autoencoders | 664:676 |
| e6 | METHOD | autoencoder | 816:827 |
| e7 | METHOD | reinforcement learning | 926:948 |
| e8 | METHOD | autoencoders | 1121:1133 |
| e9 | METHOD | RL | 1216:1218 |
| e10 | METHOD | convolutional feature extractor | 1232:1263 |

### 关系复核（包含全部旧已判项、新增项和撤回项）

- `e1 reinforcement learning → e4 compress high dimensional data`：**NO_RELATION → NO_RELATION**；角色 `direct_operator_contrast`。

  理由：For this source-scoped compression operation, autoencoders are the representation producer; RL agents/policy learning consume the representations. This object-versus-operator contrast does not assert RL can never compress data.

  谓词证据 [145:269]：Training reinforcement learning agents from high dimensional image representations can be very expensive and time consuming.

  谓词证据 [270:405]：Autoencoders are deep neural network used to compress high dimensional data such as pixelated images into small latent representations.

  谓词证据 [406:514]：This compression model is vital to efficiently learn policies, especially when learning on embedded systems.

- `e2 Autoencoders → e4 compress high dimensional data`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：The relative predicate used to compress explicitly qualifies this autoencoder deep-network instance; it is not a universal statement about all deep neural networks. Later autoencoder mentions refer to that same model family.

  谓词证据 [270:405]：Autoencoders are deep neural network used to compress high dimensional data such as pixelated images into small latent representations.

- `e3 deep neural network → e4 compress high dimensional data`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：The relative predicate used to compress explicitly qualifies this autoencoder deep-network instance; it is not a universal statement about all deep neural networks. Later autoencoder mentions refer to that same model family.

  谓词证据 [270:405]：Autoencoders are deep neural network used to compress high dimensional data such as pixelated images into small latent representations.

- `e5 autoencoders → e4 compress high dimensional data`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：The relative predicate used to compress explicitly qualifies this autoencoder deep-network instance; it is not a universal statement about all deep neural networks. Later autoencoder mentions refer to that same model family.

  谓词证据 [270:405]：Autoencoders are deep neural network used to compress high dimensional data such as pixelated images into small latent representations.

- `e6 autoencoder → e4 compress high dimensional data`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：The relative predicate used to compress explicitly qualifies this autoencoder deep-network instance; it is not a universal statement about all deep neural networks. Later autoencoder mentions refer to that same model family.

  谓词证据 [270:405]：Autoencoders are deep neural network used to compress high dimensional data such as pixelated images into small latent representations.

- `e7 reinforcement learning → e4 compress high dimensional data`：**NO_RELATION → NO_RELATION**；角色 `direct_operator_contrast`。

  理由：For this source-scoped compression operation, autoencoders are the representation producer; RL agents/policy learning consume the representations. This object-versus-operator contrast does not assert RL can never compress data.

  谓词证据 [145:269]：Training reinforcement learning agents from high dimensional image representations can be very expensive and time consuming.

  谓词证据 [270:405]：Autoencoders are deep neural network used to compress high dimensional data such as pixelated images into small latent representations.

  谓词证据 [406:514]：This compression model is vital to efficiently learn policies, especially when learning on embedded systems.

- `e8 autoencoders → e4 compress high dimensional data`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：The relative predicate used to compress explicitly qualifies this autoencoder deep-network instance; it is not a universal statement about all deep neural networks. Later autoencoder mentions refer to that same model family.

  谓词证据 [270:405]：Autoencoders are deep neural network used to compress high dimensional data such as pixelated images into small latent representations.

- `e9 RL → e4 compress high dimensional data`：**NO_RELATION → NO_RELATION**；角色 `direct_operator_contrast`。

  理由：For this source-scoped compression operation, autoencoders are the representation producer; RL agents/policy learning consume the representations. This object-versus-operator contrast does not assert RL can never compress data.

  谓词证据 [145:269]：Training reinforcement learning agents from high dimensional image representations can be very expensive and time consuming.

  谓词证据 [270:405]：Autoencoders are deep neural network used to compress high dimensional data such as pixelated images into small latent representations.

  谓词证据 [406:514]：This compression model is vital to efficiently learn policies, especially when learning on embedded systems.

保留未决说明：The convolutional feature extractor's compression capabilities are not established by its comparator role; retain that pair unresolved.

同会话自查：Re-read the definition: used to compress explicitly qualifies the described autoencoder deep-network instance. Retain this locally scoped family predicate, not a universal claim. The compression operator versus consuming RL/policy role supports scoped contrasts; a comparator feature extractor remains unresolved.

## 2503.03790

来源：https://arxiv.org/abs/2503.03790

### 摘要原文

Diffusion MRI (dMRI) plays a crucial role in studying brain white matter connectivity. Cortical surface reconstruction (CSR), including the inner whiter matter (WM) and outer pial surfaces, is one of the key tasks in dMRI analyses such as fiber tractography and multimodal MRI analysis. Existing CSR methods rely on anatomical T1-weighted data and map them into the dMRI space through inter-modality registration. However, due to the low resolution and image distortions of dMRI data, inter-modality registration faces significant challenges. This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data. DDCSR consists of two major components, including: (1) an implicit learning module to predict a voxel-wise intermediate surface representation, and (2) an explicit learning module to predict the 3D mesh surfaces. Compared to several baseline and advanced CSR methods, we show that the proposed DDCSR can largely increase both accuracy and efficiency. Furthermore, we demonstrate a high generalization ability of DDCSR to data from different sources, despite the differences in dMRI acquisitions and populations.

### 实体审核

完整性状态：complete。All17 mentions are supported. dMRI/T1/WM describe modality/tissue, not named benchmark datasets. Predict a voxel-wise intermediate surface representation and predict the 3D mesh surfaces are explicit module objectives, not the voxel/mesh research objects alone.

| ID | 类别 | 原文提及 | 偏移 |
|---|---|---|---|
| e1 | TASK | Cortical surface reconstruction | 87:118 |
| e2 | TASK | CSR | 120:123 |
| e3 | TASK | fiber tractography | 239:257 |
| e4 | TASK | multimodal MRI analysis | 262:285 |
| e5 | TASK | CSR | 296:299 |
| e6 | METHOD | inter-modality registration | 385:412 |
| e7 | METHOD | inter-modality registration | 485:512 |
| e8 | METHOD | DDCSR | 601:606 |
| e9 | TASK | CSR | 641:644 |
| e10 | METHOD | DDCSR | 670:675 |
| e11 | METHOD | implicit learning module | 728:752 |
| e12 | TASK | predict a voxel-wise intermediate surface representation | 756:812 |
| e13 | METHOD | explicit learning module | 825:849 |
| e14 | TASK | predict the 3D mesh surfaces | 853:881 |
| e15 | TASK | CSR | 925:928 |
| e16 | METHOD | DDCSR | 964:969 |
| e17 | METHOD | DDCSR | 1082:1087 |

### 关系复核（包含全部旧已判项、新增项和撤回项）

- `e8 DDCSR → e1 Cortical surface reconstruction`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e8 DDCSR → e2 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e8 DDCSR → e5 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e8 DDCSR → e9 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e8 DDCSR → e15 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e10 DDCSR → e1 Cortical surface reconstruction`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e10 DDCSR → e2 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e10 DDCSR → e5 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e10 DDCSR → e9 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e10 DDCSR → e15 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e11 implicit learning module → e12 predict a voxel-wise intermediate surface representation`：**USED_FOR → USED_FOR**；角色 `component_operation`。

  理由：The numbered component statement assigns the intermediate-output task directly to the implicit module.

  谓词证据 [670:882]：DDCSR consists of two major components, including: (1) an implicit learning module to predict a voxel-wise intermediate surface representation, and (2) an explicit learning module to predict the 3D mesh surfaces.

- `e11 implicit learning module → e14 predict the 3D mesh surfaces`：**NO_RELATION → NO_RELATION**；角色 `direct_operator_contrast`。

  理由：Within the explicitly partitioned module-output roles, the implicit module's immediate output is the intermediate surface, while the explicit module predicts the mesh. This is not denial of the implicit module's overall contribution to CSR.

  谓词证据 [670:882]：DDCSR consists of two major components, including: (1) an implicit learning module to predict a voxel-wise intermediate surface representation, and (2) an explicit learning module to predict the 3D mesh surfaces.

- `e13 explicit learning module → e12 predict a voxel-wise intermediate surface representation`：**NO_RELATION → NO_RELATION**；角色 `direct_operator_contrast`。

  理由：The same explicit partition assigns intermediate surface prediction to the implicit module, not the explicit final-mesh predictor. Only that immediate-output scope is negated.

  谓词证据 [670:882]：DDCSR consists of two major components, including: (1) an implicit learning module to predict a voxel-wise intermediate surface representation, and (2) an explicit learning module to predict the 3D mesh surfaces.

- `e13 explicit learning module → e14 predict the 3D mesh surfaces`：**USED_FOR → USED_FOR**；角色 `component_operation`。

  理由：The numbered component statement assigns the final mesh-output task directly to the explicit module.

  谓词证据 [670:882]：DDCSR consists of two major components, including: (1) an implicit learning module to predict a voxel-wise intermediate surface representation, and (2) an explicit learning module to predict the 3D mesh surfaces.

- `e16 DDCSR → e1 Cortical surface reconstruction`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e16 DDCSR → e2 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e16 DDCSR → e5 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e16 DDCSR → e9 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e16 DDCSR → e15 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e17 DDCSR → e1 Cortical surface reconstruction`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e17 DDCSR → e2 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e17 DDCSR → e5 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e17 DDCSR → e9 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

- `e17 DDCSR → e15 CSR`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：CSR is explicitly defined as Cortical surface reconstruction; exact repeated DDCSR and CSR mentions refer to one actor/task. All20 mention pairs share one source/alias-chain support, not20 independent studies.

  谓词证据 [543:669]：This work proposes a novel end-to-end learning framework, DDCSR, which for the first time enables CSR directly from dMRI data.

保留未决说明：No EVALUATED_ON is invented for unnamed data sources; registration and module components do not inherit all dMRI downstream analyses.

同会话自查：Re-read the numbered two-component definition: immediate intermediate and final mesh outputs are explicitly partitioned. Retain direct component edges and source-scoped contrasts, without denying overall contribution. All repeated DDCSR/CSR pairs share one support group.

## 1910.12770

来源：https://arxiv.org/abs/1910.12770

### 摘要原文

Deep neural networks require collecting and annotating large amounts of data to train successfully. In order to alleviate the annotation bottleneck, we propose a novel self-supervised representation learning approach for spatiotemporal features extracted from videos. We introduce Skip-Clip, a method that utilizes temporal coherence in videos, by training a deep model for future clip order ranking conditioned on a context clip as a surrogate objective for video future prediction. We show that features learned using our method are generalizable and transfer strongly to downstream tasks. For action recognition on the UCF101 dataset, we obtain 51.8% improvement over random initialization and outperform models initialized using inflated ImageNet parameters. Skip-Clip also achieves results competitive with state-of-the-art self-supervision methods.

### 实体审核

完整性状态：complete。All9 mentions are supported; future clip order ranking is an explicit training proxy, video future prediction is its intended objective, and action recognition is the downstream task. e2 is self-supervised representation learning, not the literal Skip-Clip name. No entity/type change is needed to distinguish task roles.

| ID | 类别 | 原文提及 | 偏移 |
|---|---|---|---|
| e1 | METHOD | Deep neural networks | 0:20 |
| e2 | METHOD | self-supervised representation learning | 168:207 |
| e3 | METHOD | Skip-Clip | 281:290 |
| e4 | TASK | future clip order ranking | 374:399 |
| e5 | TASK | video future prediction | 459:482 |
| e6 | TASK | action recognition | 596:614 |
| e7 | DATASET | UCF101 | 622:628 |
| e8 | DATASET | ImageNet | 742:750 |
| e9 | METHOD | Skip-Clip | 763:772 |

### 关系复核（包含全部旧已判项、新增项和撤回项）

- `e2 self-supervised representation learning → e4 future clip order ranking`：**USED_FOR → USED_FOR**；角色 `training_proxy`。

  理由：The introduced self-supervised approach is locally named Skip-Clip, and the deep model is explicitly trained for ranking. This is permitted as a training-objective edge, not a demonstrated downstream video-generation capability.

  谓词证据 [268:483]：We introduce Skip-Clip, a method that utilizes temporal coherence in videos, by training a deep model for future clip order ranking conditioned on a context clip as a surrogate objective for video future prediction.

- `e2 self-supervised representation learning → e5 video future prediction`：**USED_FOR → UNRESOLVED**；角色 `unresolved`。

  理由：Ranking is a surrogate objective for video future prediction. The source does not demonstrate direct future-video prediction as a separate performed task; keep intended-goal versus executed-proxy uncertainty.

- `e2 self-supervised representation learning → e6 action recognition`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：Our method and the introduced self-supervised approach refer to Skip-Clip, whose features explicitly transfer to the stated downstream action-recognition task.

  谓词证据 [592:762]：For action recognition on the UCF101 dataset, we obtain 51.8% improvement over random initialization and outperform models initialized using inflated ImageNet parameters.

- `e2 self-supervised representation learning → e7 UCF101`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：UCF101 is the explicitly evaluated downstream dataset for the proposed method; the named self-supervised approach and repeated Skip-Clip are local aliases of that actor, not every self-supervised model.

  谓词证据 [592:762]：For action recognition on the UCF101 dataset, we obtain 51.8% improvement over random initialization and outperform models initialized using inflated ImageNet parameters.

- `e2 self-supervised representation learning → e8 ImageNet`：**NO_RELATION → UNRESOLVED**；角色 `unresolved`。

  理由：ImageNet supplies comparator initialization parameters; this is not an explicit denial of evaluation on ImageNet. Training/comparator use alone cannot become NO_RELATION.

- `e3 Skip-Clip → e4 future clip order ranking`：**USED_FOR → USED_FOR**；角色 `training_proxy`。

  理由：The introduced self-supervised approach is locally named Skip-Clip, and the deep model is explicitly trained for ranking. This is permitted as a training-objective edge, not a demonstrated downstream video-generation capability.

  谓词证据 [268:483]：We introduce Skip-Clip, a method that utilizes temporal coherence in videos, by training a deep model for future clip order ranking conditioned on a context clip as a surrogate objective for video future prediction.

- `e3 Skip-Clip → e5 video future prediction`：**USED_FOR → UNRESOLVED**；角色 `unresolved`。

  理由：Ranking is a surrogate objective for video future prediction. The source does not demonstrate direct future-video prediction as a separate performed task; keep intended-goal versus executed-proxy uncertainty.

- `e3 Skip-Clip → e6 action recognition`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：Our method and the introduced self-supervised approach refer to Skip-Clip, whose features explicitly transfer to the stated downstream action-recognition task.

  谓词证据 [592:762]：For action recognition on the UCF101 dataset, we obtain 51.8% improvement over random initialization and outperform models initialized using inflated ImageNet parameters.

- `e3 Skip-Clip → e7 UCF101`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：UCF101 is the explicitly evaluated downstream dataset for the proposed method; the named self-supervised approach and repeated Skip-Clip are local aliases of that actor, not every self-supervised model.

  谓词证据 [592:762]：For action recognition on the UCF101 dataset, we obtain 51.8% improvement over random initialization and outperform models initialized using inflated ImageNet parameters.

- `e3 Skip-Clip → e8 ImageNet`：**NO_RELATION → UNRESOLVED**；角色 `unresolved`。

  理由：ImageNet supplies comparator initialization parameters; this is not an explicit denial of evaluation on ImageNet. Training/comparator use alone cannot become NO_RELATION.

- `e9 Skip-Clip → e4 future clip order ranking`：**USED_FOR → USED_FOR**；角色 `training_proxy`。

  理由：The introduced self-supervised approach is locally named Skip-Clip, and the deep model is explicitly trained for ranking. This is permitted as a training-objective edge, not a demonstrated downstream video-generation capability.

  谓词证据 [268:483]：We introduce Skip-Clip, a method that utilizes temporal coherence in videos, by training a deep model for future clip order ranking conditioned on a context clip as a surrogate objective for video future prediction.

- `e9 Skip-Clip → e5 video future prediction`：**USED_FOR → UNRESOLVED**；角色 `unresolved`。

  理由：Ranking is a surrogate objective for video future prediction. The source does not demonstrate direct future-video prediction as a separate performed task; keep intended-goal versus executed-proxy uncertainty.

- `e9 Skip-Clip → e6 action recognition`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：Our method and the introduced self-supervised approach refer to Skip-Clip, whose features explicitly transfer to the stated downstream action-recognition task.

  谓词证据 [592:762]：For action recognition on the UCF101 dataset, we obtain 51.8% improvement over random initialization and outperform models initialized using inflated ImageNet parameters.

- `e9 Skip-Clip → e7 UCF101`：**EVALUATED_ON → EVALUATED_ON**；角色 `not_applicable`。

  理由：UCF101 is the explicitly evaluated downstream dataset for the proposed method; the named self-supervised approach and repeated Skip-Clip are local aliases of that actor, not every self-supervised model.

  谓词证据 [592:762]：For action recognition on the UCF101 dataset, we obtain 51.8% improvement over random initialization and outperform models initialized using inflated ImageNet parameters.

- `e9 Skip-Clip → e8 ImageNet`：**NO_RELATION → UNRESOLVED**；角色 `unresolved`。

  理由：ImageNet supplies comparator initialization parameters; this is not an explicit denial of evaluation on ImageNet. Training/comparator use alone cannot become NO_RELATION.

保留未决说明：Deep neural networks in the introductory annotation-bottleneck sentence do not inherit proposed-model tasks. Explicitly mask intended-goal and comparator-dataset pairs.

同会话自查：Re-read training-by-ranking as a surrogate objective and the UCF101 action-recognition result. Keep ranking only as training_proxy; do not assert demonstrated future-video prediction. ImageNet comparator initialization is not evidence denying evaluation, so all three old negatives become unknown. Queue e2 names a local approach description, not literal Skip-Clip.

## 1905.00537

来源：http://arxiv.org/abs/1905.00537v3

### 摘要原文

In the last year, new models and methods for pretraining and transfer learning have driven striking performance improvements across a range of language understanding tasks. The GLUE benchmark, introduced a little over one year ago, offers a single-number metric that summarizes progress on a diverse set of such tasks, but performance on the benchmark has recently surpassed the level of non-expert humans, suggesting limited headroom for further research. In this paper we present SuperGLUE, a new benchmark styled after GLUE with a new set of more difficult language understanding tasks, a software toolkit, and a public leaderboard. SuperGLUE is available at super.gluebenchmark.com.

### 实体审核

完整性状态：complete。All8 mentions are supported: pretraining and transfer learning are explicit method families, GLUE/SuperGLUE are named benchmarks, and language understanding is the stated task. No model name, metric or software toolkit is invented as METHOD.

| ID | 类别 | 原文提及 | 偏移 |
|---|---|---|---|
| e1 | METHOD | pretraining | 45:56 |
| e2 | METHOD | transfer learning | 61:78 |
| e3 | TASK | language understanding | 143:165 |
| e4 | DATASET | GLUE | 177:181 |
| e5 | DATASET | SuperGLUE | 482:491 |
| e6 | DATASET | GLUE | 522:526 |
| e7 | TASK | language understanding | 560:582 |
| e8 | DATASET | SuperGLUE | 636:645 |

### 关系复核（包含全部旧已判项、新增项和撤回项）

- `e1 pretraining → e3 language understanding`：**UNRESOLVED → USED_FOR**；角色 `background_method_use`。

  理由：This sentence explicitly connects the two method families to the language-understanding task. It is a background methodological claim, not this paper's measured model result; no benchmark evaluation edge is inferred.

  谓词证据 [0:172]：In the last year, new models and methods for pretraining and transfer learning have driven striking performance improvements across a range of language understanding tasks.

- `e2 transfer learning → e3 language understanding`：**UNRESOLVED → USED_FOR**；角色 `background_method_use`。

  理由：This sentence explicitly connects the two method families to the language-understanding task. It is a background methodological claim, not this paper's measured model result; no benchmark evaluation edge is inferred.

  谓词证据 [0:172]：In the last year, new models and methods for pretraining and transfer learning have driven striking performance improvements across a range of language understanding tasks.

保留未决说明：GLUE/SuperGLUE descriptions do not establish a specific method's scored benchmark result. The later task mention defines a new benchmark, not another demonstrated capability for each method.

同会话自查：Re-read the opening sentence linking pretraining and transfer learning to language-understanding improvements. Two direct background-method uses are supported, but no measured method-specific GLUE/SuperGLUE score is supplied. All benchmark pairs remain unknown.

## 2312.03556

来源：https://arxiv.org/abs/2312.03556

### 摘要原文

Face inpainting is important in various applications, such as photo restoration, image editing, and virtual reality. Despite the significant advances in face generative models, ensuring that a person's unique facial identity is maintained during the inpainting process is still an elusive goal. Current state-of-the-art techniques, exemplified by MyStyle, necessitate resource-intensive fine-tuning and a substantial number of images for each new identity. Furthermore, existing methods often fall short in accommodating user-specified semantic attributes, such as beard or expression. To improve inpainting results, and reduce the computational complexity during inference, this paper proposes the use of Parallel Visual Attention (PVA) in conjunction with diffusion models. Specifically, we insert parallel attention matrices to each cross-attention module in the denoising network, which attends to features extracted from reference images by an identity encoder. We train the added attention modules and identity encoder on CelebAHQ-IDI, a dataset proposed for identity-preserving face inpainting. Experiments demonstrate that PVA attains unparalleled identity resemblance in both face inpainting and face inpainting with language guidance tasks, in comparison to various benchmarks, including MyStyle, Paint by Example, and Custom Diffusion. Our findings reveal that PVA ensures good identity preservation while offering effective language-controllability. Additionally, in contrast to Custom Diffusion, PVA requires just 40 fine-tuning steps for each new identity, which translates to a significant speed increase of over 20 times.

### 实体审核

完整性状态：unresolved。All18 existing spans are supported; comparison systems MyStyle/Paint by Example/Custom Diffusion are methods, not datasets. CelebAHQ-IDI is explicitly training data. Named cross-attention and identity encoder components merit an omission/granularity decision before full BIO supervision; existing entities are preserved, not advertised as exhaustive.

| ID | 类别 | 原文提及 | 偏移 |
|---|---|---|---|
| e1 | TASK | Face inpainting | 0:15 |
| e2 | TASK | photo restoration | 62:79 |
| e3 | TASK | image editing | 81:94 |
| e4 | METHOD | MyStyle | 347:354 |
| e5 | METHOD | Parallel Visual Attention | 706:731 |
| e6 | METHOD | PVA | 733:736 |
| e7 | METHOD | diffusion models | 758:774 |
| e8 | DATASET | CelebAHQ-IDI | 1028:1040 |
| e9 | TASK | identity-preserving face inpainting | 1065:1100 |
| e10 | METHOD | PVA | 1131:1134 |
| e11 | TASK | face inpainting | 1185:1200 |
| e12 | TASK | face inpainting with language guidance | 1205:1243 |
| e13 | METHOD | MyStyle | 1298:1305 |
| e14 | METHOD | Paint by Example | 1307:1323 |
| e15 | METHOD | Custom Diffusion | 1329:1345 |
| e16 | METHOD | PVA | 1372:1375 |
| e17 | METHOD | Custom Diffusion | 1491:1507 |
| e18 | METHOD | PVA | 1509:1512 |

### 关系复核（包含全部旧已判项、新增项和撤回项）

- `e10 PVA → e11 face inpainting`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：The sentence directly credits this PVA occurrence with both named tasks. Introductory applications and other model/components do not automatically receive these two predicates.

  谓词证据 [1102:1346]：Experiments demonstrate that PVA attains unparalleled identity resemblance in both face inpainting and face inpainting with language guidance tasks, in comparison to various benchmarks, including MyStyle, Paint by Example, and Custom Diffusion.

- `e10 PVA → e12 face inpainting with language guidance`：**USED_FOR → USED_FOR**；角色 `downstream_application`。

  理由：The sentence directly credits this PVA occurrence with both named tasks. Introductory applications and other model/components do not automatically receive these two predicates.

  谓词证据 [1102:1346]：Experiments demonstrate that PVA attains unparalleled identity resemblance in both face inpainting and face inpainting with language guidance tasks, in comparison to various benchmarks, including MyStyle, Paint by Example, and Custom Diffusion.

保留未决说明：PVA-to-CelebAHQ-IDI remains unresolved: the source states training modules/encoder, not evaluated PVA on that dataset. Entity omission review blocks this document's full-sequence training admission.

同会话自查：Re-read the PVA experiment sentence and explicit training of modules/encoder on CelebAHQ-IDI. Retain the two direct task occurrences, no training-to-evaluation inference. Architectural omission candidates mean existing spans alone do not certify complete BIO supervision.

## 2503.01309

来源：https://arxiv.org/abs/2503.01309

### 摘要原文

Online zero-shot 3D instance segmentation of a progressively reconstructed scene is both a critical and challenging task for embodied applications. With the success of visual foundation models (VFMs) in the image domain, leveraging 2D priors to address 3D online segmentation has become a prominent research focus. Since segmentation results provided by 2D priors often require spatial consistency to be lifted into final 3D segmentation, an efficient method for identifying spatial overlap among 2D masks is essential - yet existing methods rarely achieve this in real time, mainly limiting its use to offline approaches. To address this, we propose an efficient method that lifts 2D masks generated by VFMs into a unified 3D instance using a hashing technique. By employing voxel hashing for efficient 3D scene querying, our approach reduces the time complexity of costly spatial overlap queries from $O(n^2)$ to $O(n)$. Accurate spatial associations further enable 3D merging of 2D masks through simple similarity-based filtering in a zero-shot manner, making our approach more robust to incomplete and noisy data. Evaluated on the ScanNet and SceneNN benchmarks, our approach achieves state-of-the-art performance in online, zero-shot 3D instance segmentation with leading efficiency.

### 实体审核

完整性状态：complete。All15 mentions are supported; 2D masks and 3D instance objects are not separately TASK unless the source explicitly names an operation. VFMs are method-family occurrences, voxel hashing and filtering are component operators. OnlineAnySeg is not inserted from title or URL because no such name occurs in this abstract.

| ID | 类别 | 原文提及 | 偏移 |
|---|---|---|---|
| e1 | TASK | Online zero-shot 3D instance segmentation | 0:41 |
| e2 | METHOD | visual foundation models | 168:192 |
| e3 | METHOD | VFMs | 194:198 |
| e4 | TASK | 3D online segmentation | 253:275 |
| e5 | TASK | 3D segmentation | 422:437 |
| e6 | TASK | identifying spatial overlap among 2D masks | 463:505 |
| e7 | METHOD | VFMs | 704:708 |
| e8 | METHOD | hashing technique | 744:761 |
| e9 | METHOD | voxel hashing | 776:789 |
| e10 | TASK | 3D scene querying | 804:821 |
| e11 | TASK | 3D merging of 2D masks | 968:990 |
| e12 | METHOD | similarity-based filtering | 1006:1032 |
| e13 | DATASET | ScanNet | 1135:1142 |
| e14 | DATASET | SceneNN | 1147:1154 |
| e15 | TASK | online, zero-shot 3D instance segmentation | 1221:1263 |

### 关系复核（包含全部旧已判项、新增项和撤回项）

- `e2 visual foundation models → e10 3D scene querying`：**NO_RELATION → UNRESOLVED**；角色 `unresolved`。

  理由：VFMs produce the input masks and other components perform subsequent operations, but this is not an explicit partition excluding VFM involvement in those operations. Conservatively withhold the six source-local negatives instead of inferring incapability or no contribution.

- `e2 visual foundation models → e11 3D merging of 2D masks`：**NO_RELATION → UNRESOLVED**；角色 `unresolved`。

  理由：VFMs produce the input masks and other components perform subsequent operations, but this is not an explicit partition excluding VFM involvement in those operations. Conservatively withhold the six source-local negatives instead of inferring incapability or no contribution.

- `e3 VFMs → e10 3D scene querying`：**NO_RELATION → UNRESOLVED**；角色 `unresolved`。

  理由：VFMs produce the input masks and other components perform subsequent operations, but this is not an explicit partition excluding VFM involvement in those operations. Conservatively withhold the six source-local negatives instead of inferring incapability or no contribution.

- `e3 VFMs → e11 3D merging of 2D masks`：**NO_RELATION → UNRESOLVED**；角色 `unresolved`。

  理由：VFMs produce the input masks and other components perform subsequent operations, but this is not an explicit partition excluding VFM involvement in those operations. Conservatively withhold the six source-local negatives instead of inferring incapability or no contribution.

- `e7 VFMs → e10 3D scene querying`：**NO_RELATION → UNRESOLVED**；角色 `unresolved`。

  理由：VFMs produce the input masks and other components perform subsequent operations, but this is not an explicit partition excluding VFM involvement in those operations. Conservatively withhold the six source-local negatives instead of inferring incapability or no contribution.

- `e7 VFMs → e11 3D merging of 2D masks`：**NO_RELATION → UNRESOLVED**；角色 `unresolved`。

  理由：VFMs produce the input masks and other components perform subsequent operations, but this is not an explicit partition excluding VFM involvement in those operations. Conservatively withhold the six source-local negatives instead of inferring incapability or no contribution.

- `e9 voxel hashing → e10 3D scene querying`：**USED_FOR → USED_FOR**；角色 `component_operation`。

  理由：The for predicate directly assigns scene querying to voxel hashing; this complexity claim is not a named-benchmark evaluation of that component.

  谓词证据 [763:922]：By employing voxel hashing for efficient 3D scene querying, our approach reduces the time complexity of costly spatial overlap queries from $O(n^2)$ to $O(n)$.

- `e12 similarity-based filtering → e11 3D merging of 2D masks`：**USED_FOR → USED_FOR**；角色 `component_operation`。

  理由：Through filtering explicitly supplies the named mask-merging operation.

  谓词证据 [923:1117]：Accurate spatial associations further enable 3D merging of 2D masks through simple similarity-based filtering in a zero-shot manner, making our approach more robust to incomplete and noisy data.

保留未决说明：ScanNet/SceneNN evaluate the unnamed overall approach, not voxel hashing, VFMs or filtering separately. All component-to-benchmark pairs remain unresolved.

同会话自查：Re-read input-mask generation, voxel-hashing querying, filtering-based merging and the final overall-approach benchmark score. Retain the two direct predicates. The text does not explicitly partition away VFM contribution, so six old negatives are withdrawn; all separately unmeasured component-benchmark pairs stay unknown.

## 2010.01057

来源：https://arxiv.org/abs/2010.01057

### 摘要原文

Entity representations are useful in natural language tasks involving entities. In this paper, we propose new pretrained contextualized representations of words and entities based on the bidirectional transformer. The proposed model treats words and entities in a given text as independent tokens, and outputs contextualized representations of them. Our model is trained using a new pretraining task based on the masked language model of BERT. The task involves predicting randomly masked words and entities in a large entity-annotated corpus retrieved from Wikipedia. We also propose an entity-aware self-attention mechanism that is an extension of the self-attention mechanism of the transformer, and considers the types of tokens (words or entities) when computing attention scores. The proposed model achieves impressive empirical performance on a wide range of entity-related tasks. In particular, it obtains state-of-the-art results on five well-known datasets: Open Entity (entity typing), TACRED (relation classification), CoNLL-2003 (named entity recognition), ReCoRD (cloze-style question answering), and SQuAD 1.1 (extractive question answering). Our source code and pretrained representations are available at https://github.com/studio-ousia/luke.

### 实体审核

完整性状态：complete。All17 mentions are supported and complete under the named-method/task/dataset scope. Wikipedia is corpus provenance, not the named evaluation dataset. The proposed model is unnamed in the abstract body; LUKE occurs only in title/URL and is not fabricated as a literal METHOD endpoint.

| ID | 类别 | 原文提及 | 偏移 |
|---|---|---|---|
| e1 | METHOD | bidirectional transformer | 187:212 |
| e2 | METHOD | masked language model | 413:434 |
| e3 | METHOD | BERT | 438:442 |
| e4 | TASK | predicting randomly masked words and entities | 462:507 |
| e5 | METHOD | entity-aware self-attention mechanism | 588:625 |
| e6 | METHOD | self-attention mechanism | 654:678 |
| e7 | METHOD | transformer | 686:697 |
| e8 | DATASET | Open Entity | 968:979 |
| e9 | TASK | entity typing | 981:994 |
| e10 | DATASET | TACRED | 997:1003 |
| e11 | TASK | relation classification | 1005:1028 |
| e12 | DATASET | CoNLL-2003 | 1031:1041 |
| e13 | TASK | named entity recognition | 1043:1067 |
| e14 | DATASET | ReCoRD | 1070:1076 |
| e15 | TASK | cloze-style question answering | 1078:1108 |
| e16 | DATASET | SQuAD 1.1 | 1115:1124 |
| e17 | TASK | extractive question answering | 1126:1155 |

### 关系复核（包含全部旧已判项、新增项和撤回项）

保留未决说明：All66 pairs remain unresolved. The proposed model's five dataset results do not independently evaluate its transformer/BERT/attention components. A new pretraining task inspired by BERT does not mean original BERT predicts both words and entities.

同会话自查：Re-read all seventeen spans and five named datasets. The evaluated actor is an unnamed proposed model; neither title/URL nor component architecture names create a literal LUKE endpoint. Preserve all66 unknown pairs and the source-boundary distinction.
