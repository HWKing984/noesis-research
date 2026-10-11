# V2四篇实体完整性修订

AI同会话补标与自查，非独立人工金标准。所有新增关系对未决；5条争议负例仅隔离导出，不改标签。

## 2008.10400

http://arxiv.org/abs/2008.10400v2

### 全文与提及

We report that a very high accuracy on the MNIST test set can be achieved by using simple convolutional neural network (CNN) models. We use three different models with 3x3, 5x5, and 7x7 kernel size in the convolution layers. Each model consists of a set of convolution layers followed by a single fully connected layer. Every convolution layer uses batch normalization and ReLU activation, and pooling is not used. Rotation and translation is used to augment training data, which is frequently used in most image classification tasks. A majority voting using the three models independently trained on the training data set can achieve up to 99.87% accuracy on the test set, which is one of the state-of-the-art results. A two-layer ensemble, a heterogeneous ensemble of three homogeneous ensemble networks, can achieve up to 99.91% test accuracy. The results can be reproduced by using the code at: https://github.com/ansh941/MnistSimpleCNN

逐句核对网络、卷积层/全连接层、归一化/激活/池化、旋转/平移、增广目标和三种集成描述；旧8提及保留。单数convolution layer选第三个字面出现，避免与两处复数层重叠。 3x3/5x5/7x7 kernel size是参数；accuracy是指标；training/test set未额外命名数据集。pooling虽被否定仍是方法提及，不能由NER推出正关系。通用models和GitHub路径不是独立实体。

| ID | 类别 | 原文 | 偏移 | 原有/新增 |
|---|---|---|---|---|
| e1 | DATASET | MNIST | 43:48 | 原有 |
| e2 | METHOD | convolutional neural network | 90:118 | 原有 |
| e3 | METHOD | CNN | 120:123 | 原有 |
| e4 | METHOD | convolution layers | 205:223 | 新增 |
| e5 | METHOD | convolution layers | 257:275 | 新增 |
| e6 | METHOD | fully connected layer | 297:318 | 新增 |
| e7 | METHOD | convolution layer | 326:343 | 新增 |
| e8 | METHOD | batch normalization | 349:368 | 原有 |
| e9 | METHOD | ReLU activation | 373:388 | 原有 |
| e10 | METHOD | pooling | 394:401 | 新增 |
| e11 | METHOD | Rotation | 415:423 | 新增 |
| e12 | METHOD | translation | 428:439 | 新增 |
| e13 | TASK | augment training data | 451:472 | 新增 |
| e14 | TASK | image classification | 507:527 | 原有 |
| e15 | METHOD | majority voting | 537:552 | 原有 |
| e16 | METHOD | two-layer ensemble | 722:740 | 原有 |
| e17 | METHOD | heterogeneous ensemble | 744:766 | 新增 |
| e18 | METHOD | homogeneous ensemble networks | 776:805 | 新增 |

候选对：12 → 45；新对全部未决。

## 2501.02474

http://arxiv.org/abs/2501.02474v1

### 全文与提及

Remote sensing object detection is particularly challenging due to the high resolution, multi-scale features, and diverse ground object characteristics inherent in satellite and UAV imagery. These challenges necessitate more advanced approaches for effective object detection in such environments. While deep learning methods have achieved remarkable success in remote sensing object detection, they typically rely on large amounts of labeled data. Acquiring sufficient labeled data, particularly for novel or rare objects, is both challenging and time-consuming in remote sensing scenarios, limiting the generalization capabilities of existing models. To address these challenges, few-shot learning (FSL) has emerged as a promising approach, aiming to enable models to learn new classes from limited labeled examples. Building on this concept, few-shot object detection (FSOD) specifically targets object detection challenges in data-limited conditions. However, the generalization capability of FSOD models, particularly in remote sensing, is often constrained by the complex and diverse characteristics of the objects present in such environments. In this paper, we propose the Generalization-Enhanced Few-Shot Object Detection (GE-FSOD) model to improve the generalization capability in remote sensing FSOD tasks. Our model introduces three key innovations: the Cross-Level Fusion Pyramid Attention Network (CFPAN) for enhanced multi-scale feature representation, the Multi-Stage Refinement Region Proposal Network (MRRPN) for more accurate region proposals, and the Generalized Classification Loss (GCL) for improved classification performance in few-shot scenarios. Extensive experiments on the DIOR and NWPU VHR-10 datasets show that our model achieves state-of-the-art performance for few-shot object detection in remote sensing.

逐句核对背景deep learning/FSL、FSOD任务及别名、主模型、三个组件和两个数据集。补背景方法family；不从组件for后的输出/指标名词推断新的操作任务，不自动把模型评测分配给组件。 multi-scale features/feature representation、region proposals是特征或输出名词，本批不把它们改写成提取/生成任务；classification performance/generalization capability是指标/能力。learn new classes描述FSL定义，不再从泛化定义发明一个与FSOD并列的任务名称。remote sensing单独为领域，UAV imagery为模态，非DATASET。

| ID | 类别 | 原文 | 偏移 | 原有/新增 |
|---|---|---|---|---|
| e1 | TASK | Remote sensing object detection | 0:31 | 原有 |
| e2 | TASK | object detection | 259:275 | 原有 |
| e3 | METHOD | deep learning | 304:317 | 新增 |
| e4 | TASK | remote sensing object detection | 362:393 | 原有 |
| e5 | METHOD | few-shot learning | 682:699 | 原有 |
| e6 | METHOD | FSL | 701:704 | 原有 |
| e7 | TASK | few-shot object detection | 845:870 | 原有 |
| e8 | TASK | FSOD | 872:876 | 原有 |
| e9 | TASK | object detection | 899:915 | 原有 |
| e10 | TASK | FSOD | 997:1001 | 原有 |
| e11 | METHOD | Generalization-Enhanced Few-Shot Object Detection | 1181:1230 | 原有 |
| e12 | METHOD | GE-FSOD | 1232:1239 | 原有 |
| e13 | TASK | FSOD | 1306:1310 | 原有 |
| e14 | METHOD | Cross-Level Fusion Pyramid Attention Network | 1366:1410 | 原有 |
| e15 | METHOD | CFPAN | 1412:1417 | 原有 |
| e16 | METHOD | Multi-Stage Refinement Region Proposal Network | 1472:1518 | 原有 |
| e17 | METHOD | MRRPN | 1520:1525 | 原有 |
| e18 | METHOD | Generalized Classification Loss | 1571:1602 | 原有 |
| e19 | METHOD | GCL | 1604:1607 | 原有 |
| e20 | DATASET | DIOR | 1701:1705 | 原有 |
| e21 | DATASET | NWPU VHR-10 | 1710:1721 | 原有 |
| e22 | TASK | few-shot object detection | 1793:1818 | 原有 |

候选对：110 → 121；新对全部未决。

## 2501.06756

http://arxiv.org/abs/2501.06756v2

### 全文与提及

With advancements in physical power systems and network technologies, integrated Cyber-Physical Power Systems (CPPS) have significantly enhanced system monitoring and control efficiency and reliability. This integration, however, introduces complex challenges in designing coherent CPPS, particularly as few studies concurrently address the deployment of physical layers and communication connections in the cyber layer. This paper addresses these challenges by proposing a framework for robust sensor placement to optimize anomaly detection in the physical layer and enhance communication resilience in the cyber layer. We model the CPPS as an interdependent network via a graph, allowing for simultaneous consideration of both layers. Then, we adopt the Log-normal Shadowing Path Loss (LNSPL) model to ensure reliable data transmission. Additionally, we leverage the Fiedler value to measure graph resilience against line failures and three anomaly detectors to fortify system safety. However, the optimization problem is NP-hard. Therefore, we introduce the Experience Feedback Graph Diffusion (EFGD) algorithm, which utilizes a diffusion process to generate optimal sensor placement strategies. This algorithm incorporates cross-entropy gradient and experience feedback mechanisms to expedite convergence and generate higher reward strategies. Extensive simulations demonstrate that the EFGD algorithm enhances model convergence by 18.9% over existing graph diffusion methods and improves average reward by 22.90% compared to Denoising Diffusion Policy Optimization (DDPO) and 19.57% compared to Graph Diffusion Policy Optimization (GDPO), thereby significantly bolstering the robustness and reliability of CPPS operations.

逐句核对两层目标、LNSPL传输、谱韧性测量、EFGD策略生成、扩散/梯度/反馈机制及对比算法。补两个明确操作目标和三个技术方法提及；保留所有旧实体，不将Fiedler指标变方法，不把整体韧性目标转移为EFGD直接用途。 Fiedler value是谱指标，不将计算指标本身当算法。NP-hard是复杂度，CPPS是研究系统对象，18.9%/reward是指标。three anomaly detectors和framework是未命名指代。开头system monitoring/control效率描述领域背景，不拆孤立control；设计/部署挑战不是独立命名任务。expedite convergence和higher reward是优化效果，不另造应用任务。

| ID | 类别 | 原文 | 偏移 | 原有/新增 |
|---|---|---|---|---|
| e1 | TASK | robust sensor placement | 488:511 | 原有 |
| e2 | TASK | anomaly detection | 524:541 | 原有 |
| e3 | TASK | enhance communication resilience | 568:600 | 新增 |
| e4 | METHOD | Log-normal Shadowing Path Loss | 756:786 | 原有 |
| e5 | METHOD | LNSPL | 788:793 | 原有 |
| e6 | TASK | reliable data transmission | 811:837 | 原有 |
| e7 | TASK | measure graph resilience against line failures | 886:932 | 新增 |
| e8 | METHOD | Experience Feedback Graph Diffusion | 1061:1096 | 原有 |
| e9 | METHOD | EFGD | 1098:1102 | 原有 |
| e10 | METHOD | diffusion process | 1132:1149 | 新增 |
| e11 | TASK | generate optimal sensor placement strategies | 1153:1197 | 原有 |
| e12 | METHOD | cross-entropy gradient | 1227:1249 | 原有 |
| e13 | METHOD | experience feedback mechanisms | 1254:1284 | 新增 |
| e14 | METHOD | EFGD | 1391:1395 | 原有 |
| e15 | METHOD | graph diffusion methods | 1456:1479 | 新增 |
| e16 | METHOD | Denoising Diffusion Policy Optimization | 1530:1569 | 原有 |
| e17 | METHOD | DDPO | 1571:1575 | 原有 |
| e18 | METHOD | Graph Diffusion Policy Optimization | 1600:1635 | 原有 |
| e19 | METHOD | GDPO | 1637:1641 | 原有 |

候选对：40 → 78；新对全部未决。

## 2312.03556

https://arxiv.org/abs/2312.03556

### 全文与提及

Face inpainting is important in various applications, such as photo restoration, image editing, and virtual reality. Despite the significant advances in face generative models, ensuring that a person's unique facial identity is maintained during the inpainting process is still an elusive goal. Current state-of-the-art techniques, exemplified by MyStyle, necessitate resource-intensive fine-tuning and a substantial number of images for each new identity. Furthermore, existing methods often fall short in accommodating user-specified semantic attributes, such as beard or expression. To improve inpainting results, and reduce the computational complexity during inference, this paper proposes the use of Parallel Visual Attention (PVA) in conjunction with diffusion models. Specifically, we insert parallel attention matrices to each cross-attention module in the denoising network, which attends to features extracted from reference images by an identity encoder. We train the added attention modules and identity encoder on CelebAHQ-IDI, a dataset proposed for identity-preserving face inpainting. Experiments demonstrate that PVA attains unparalleled identity resemblance in both face inpainting and face inpainting with language guidance tasks, in comparison to various benchmarks, including MyStyle, Paint by Example, and Custom Diffusion. Our findings reveal that PVA ensures good identity preservation while offering effective language-controllability. Additionally, in contrast to Custom Diffusion, PVA requires just 40 fine-tuning steps for each new identity, which translates to a significant speed increase of over 20 times.

逐句核对背景生成family、任务短称、微调两次、PVA/扩散主方法、cross-attention/denoising/encoder组件、训练数据和全部对比模型。两处裸inpainting不与旧长任务跨度重叠，encoder重复提及分别保存；CelebAHQ-IDI仍不产生评测标签。 virtual reality是应用领域；facial identity、beard/expression是对象/属性；parallel attention matrices是张量，不是额外具名算法。added attention modules是已述组件的泛化指代，不另当独立方法名称。identity resemblance、language-controllability/speed是效果/属性；identity preservation作为明确研究目标单独保留。HTTP/题名不补正文实体。

| ID | 类别 | 原文 | 偏移 | 原有/新增 |
|---|---|---|---|---|
| e1 | TASK | Face inpainting | 0:15 | 原有 |
| e2 | TASK | photo restoration | 62:79 | 原有 |
| e3 | TASK | image editing | 81:94 | 原有 |
| e4 | METHOD | face generative models | 153:175 | 新增 |
| e5 | TASK | inpainting | 250:260 | 新增 |
| e6 | METHOD | MyStyle | 347:354 | 原有 |
| e7 | METHOD | fine-tuning | 387:398 | 新增 |
| e8 | TASK | inpainting | 597:607 | 新增 |
| e9 | METHOD | Parallel Visual Attention | 706:731 | 原有 |
| e10 | METHOD | PVA | 733:736 | 原有 |
| e11 | METHOD | diffusion models | 758:774 | 原有 |
| e12 | METHOD | cross-attention module | 836:858 | 新增 |
| e13 | METHOD | denoising network | 866:883 | 新增 |
| e14 | METHOD | identity encoder | 949:965 | 新增 |
| e15 | METHOD | identity encoder | 1008:1024 | 新增 |
| e16 | DATASET | CelebAHQ-IDI | 1028:1040 | 原有 |
| e17 | TASK | identity-preserving face inpainting | 1065:1100 | 原有 |
| e18 | METHOD | PVA | 1131:1134 | 原有 |
| e19 | TASK | face inpainting | 1185:1200 | 原有 |
| e20 | TASK | face inpainting with language guidance | 1205:1243 | 原有 |
| e21 | METHOD | MyStyle | 1298:1305 | 原有 |
| e22 | METHOD | Paint by Example | 1307:1323 | 原有 |
| e23 | METHOD | Custom Diffusion | 1329:1345 | 原有 |
| e24 | METHOD | PVA | 1372:1375 | 原有 |
| e25 | TASK | identity preservation | 1389:1410 | 新增 |
| e26 | METHOD | Custom Diffusion | 1491:1507 | 原有 |
| e27 | METHOD | PVA | 1509:1512 | 原有 |
| e28 | METHOD | fine-tuning | 1530:1541 | 新增 |

候选对：77 → 180；新对全部未决。
