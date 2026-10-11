# 实验三：SciBERT 关系抽取开发实验

本文保存09数据下10/11开发结论；最新10数据与12–14角色/三类选型对照见 [角色实验报告](course_v4_relation_roles.md)。旧结果不改写为新成绩。

## 实验约定（训练前固定）

领域任务为人工智能文献的候选参考文献发现。实验二的冻结 NER 负责识别方法/任务/命名数据集；本模块判断 METHOD→TASK 的 USED_FOR、METHOD→DATASET 的 EVALUATED_ON，并识别范围内明确不成立的 NO_RELATION。UNRESOLVED 不训练，不改成负例。共现或一个 using/on 词不是关系事实。

本轮只完成参考实体下的 train/dev 开发实验，不读取 test 题名用于模型推理。原 NER 模型和09标注快照不修改；后续独立关系标注修订须保留现有未处理关系记录。实验三 PDF 要求深度学习训练、测试及基于实体抽取结果，不能以书目字段解析/规则共现代替。

数据为 `course_v4_training_inputs_09` 的既有 AI 两轮判断：train 315 条实体对来自247篇题名，dev 162条来自113篇题名；三个类别支持分别为 300/3/12 与 155/2/5。515篇关系条件通过的文本中，部分没有范围内实体对，不产生负例，因此不能称515篇训练样本或477篇论文。883篇已标注题名、708篇NER可用的统计不因本轮训练改变。

模型为固定 SciBERT 英文科学编码器（12层、768维）+ pooled CLS/dropout/3类线性分类头。使用本地固定基础模型，而非已见NER测试后的权重。全编码器与分类头微调。头实体和尾实体插入方向明确的5种标记，用已有 `[unused0]`–`[unused4]`，无词表/权重扩容；tail标记区分TASK/DATASET，训练与推理按同一契约屏蔽不可能的关系类别。此类型约束可由NER输出类别得到，不使用参考关系标签。

特征仅题名、头尾跨度与实体类别，**不将 evidence、reason、关系标签、元数据topics或split作为模型输入**。labels仅作为交叉熵目标，从网络输入中移除。原题名和端点通过Unicode切片及WordPiece边界验证，无截断或静默删样本。

预设参数：seed20261006、batch8、lr2e-5、max128、6epoch；AdamW、weight decay0.01、梯度裁剪1.0，未加权交叉熵、未过采样、无调度器。固定6轮，以**dev两个正关系类别的macro F1最大、平分取较早epoch**选择权重，不以多数类accuracy选型；报告positive micro、逐类支持、3×3混淆矩阵。初始和选中权重分别测dev，保存每步pairId/sampleId、模型与tokenizer以及全部错误。

基线为只从train统计的尾实体类型多数类（分别在METHOD→TASK和METHOD→DATASET范围内决定），不是一般的无条件多数标签。这能揭示模型是否只是依靠类型与高度不平衡；不预设神经网络必胜。dev不反传梯度，test不参与选型。选型通过和权重实际更新只证明训练/保存链路，不等于可以把候选关系当确证事实。

关键风险是误报关系使推荐文献看似支持错误论点，因此后续图谱须保留原文证据和预测来源。当前正例占绝大多数，EVALUATED_ON仅3条train来自2篇题名、2条dev来自2篇；非零support不意味着可靠。单次seed/一组参数与同会话AI伪标签不能称全局最优或人工gold。

## 当前执行状态

入口：[train_course_relation.py](../scripts/train_course_relation.py)，复用已有凭据验证、哈希封存和SciBERT环境。已完成两组真实GPU开发训练，各6轮/240步；两组所选模型都与类型多数基线持平，5条验证负例全部误报，**尚不能视为可靠语义关系模型，未晋级为确证图谱事实**。RE最终测试、NER→RE端到端评估及Neo4j应用未完成。累计标注仍883篇，没有增加论文、改写09快照或重新训练冻结NER。

MLE工作流用于固定版本、隔离train/dev/test与保留失败；PyTorch技能用于真实梯度更新及重载验证；Python测试技能用于先写失败检查，再实现入口、类别权重和证据导出。未添加训练框架或新依赖。

### 第二次开发对照的事前约定

首轮10实际完成6轮/240步，选第1轮；dev正关系micro F1=98.43%、macro F1=99.21%，却与train类型多数基线完全一致，5条NO_RELATION全部误报。不能凭该高分接受为有语义区分能力的关系模型。本现象来自已有dev，未查看任何RE test成绩。

据此在同一固定train/dev上增加**一次**标准逆频率加权交叉熵对照：仅train计数得到权重N/(3n_c)，USED_FOR/EVALUATED_ON/NO_RELATION分别0.35/35/8.75；其余seed、输入、初始化、参数、轮数和类型mask不变。验证损失仍不加权，指标可比。单次run按dev正关系macro选epoch；两种run之间先比较此macro，若平分再比较NO_RELATION recall，仍平分保留更简单的未加权模型。这是验证集超参数开发，不是反复测试调参。

若加权仍无法区分负例，不假装模型优于基线，不把候选写成确证知识；下一步补充训练侧有明确证据的负例及稀有类，或另作有记录的dev实验。保持原dev/test划分和NER冻结。RE最终test、端到端pipeline和Neo4j均尚未执行。

```powershell
# 使用不存在的新输出目录，不覆盖旧数据、NER权重或关系实验。
& '.\.venv-training\Scripts\python.exe' -B scripts/train_course_relation.py --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_09 --model kg_datasets/models/scibert_24f92d32 --output kg_datasets/dblp/course_v4_runs/NEW_RE_DEV --device cuda
& '.\.venv-validation\Scripts\python.exe' -B -m pytest tests/test_course_relation_training.py -q
```

## 实际实验流程与留痕

1. 验证20000篇分组划分与09快照哈希，再从两轮AI凭据重建train/dev实体对；导出条目须逐项相等，不信任仅有文件名或自报标签。未决、不完整实体对和关系测试队列不作为负例。
2. 每条头尾跨度验证原文和WordPiece边界，再插入方向及类别标记。315/162条全部通过，最长36/35 token，无截断、无静默删除。
3. 只由train确定类型多数基线、类别权重；固定本地SciBERT版本及seed。仅train反传；每轮315条恰好各见一次，40批，最后一批3条，6轮240步。
4. 每轮评估162条dev，按事前正关系macro F1选checkpoint，平分取较早轮。两组均选epoch1；选中权重重载后编码、预测完全一致，编码器和分类头都实际更新。`passed=true`只表示这些工程检查通过，**不是语义质量验收通过**。
5. 第一组未能区别负例，因此增加上述仅train计数的类别平衡对照；仍未改善。依既定跨实验顺序，未加权10保留为更简单的开发候选，不宣称它适合直接上线。
6. 保存两组逐步/逐轮日志、全部预测、5条错误、权重及源码；生成真实结果可视化页面，使用本机Edge截图，核对源页、PNG和来源哈希。没有拍摄伪造终端或Neo4j成功画面。

| 项目 | 未加权10 | 逆频率加权11 |
|---|---:|---:|
| train / dev实体对 | 315 / 162 | 315 / 162 |
| train / dev题名 | 247 / 113 | 247 / 113 |
| 轮数 / 更新步 | 6 / 240 | 6 / 240 |
| 初始dev loss（未加权） | 0.642625 | 0.642625 |
| 选中epoch | 1 | 1 |
| 选中dev loss（未加权） | 0.140993 | 0.143282 |
| 正关系micro P / R / F1 | 96.91% / 100% / 98.43% | 96.91% / 100% / 98.43% |
| 正关系macro F1 | 99.21% | 99.21% |
| NO_RELATION recall | 0 / 5 = 0% | 0 / 5 = 0% |
| 与类型多数基线所选预测是否逐条相同 | 是，162条 | 是，162条 |

两组为不同损失方案的开发对照，不是同配置多seed复现。全流程分别耗时80.61秒、43.87秒，含加载与保存，不能据此推断加权使训练加速；未加权与加权batch训练loss也不能直接横向比较。验证loss始终未加权。基础模型revision为`24f92d32b1bfb0bcaf9ab193ff3ad01e87732fc1`，环境Python3.12.4 / torch2.8.0+cu126 / transformers4.57.1，设备RTX4060 Laptop GPU。

### 完整逐轮选择记录

| epoch（累计step） | 10正micro F1 | 10正macro F1 | 11正micro F1 | 11正macro F1 | 两组负例recall |
|---|---:|---:|---:|---:|---:|
| 1（40） | 98.43% | 99.21% | 98.43% | 99.21% | 0% |
| 2（80） | 98.43% | 99.21% | 98.43% | 99.21% | 0% |
| 3（120） | 98.43% | 99.21% | 98.43% | 99.21% | 0% |
| 4（160） | 95.82% | 97.88% | 95.48% | 97.71% | 0% |
| 5（200） | 98.43% | 99.21% | 97.14% | 98.55% | 0% |
| 6（240） | 98.43% | 99.21% | 97.47% | 98.72% | 0% |

此处positive micro统计关系标签与实体对都匹配的正关系，NO_RELATION不进入正关系分母；负例误报计入正关系预测数。正macro只平均两个有参考支持的正类，不能掩盖负类表现。选中模型TP157、预测正关系162、参考正关系157；整体accuracy96.91%，不能与micro F1混称。

| 类别 | dev参考 / 预测 / TP | P | R | F1 |
|---|---|---:|---:|---:|
| USED_FOR | 155 / 160 / 155 | 96.88% | 100% | 98.41% |
| EVALUATED_ON | 2 / 2 / 2 | 100% | 100% | 100% |
| NO_RELATION | 5 / 0 / 0 | N/A（无预测） | 0% | 0% |

混淆矩阵行=AI参考、列=模型预测；两组所选模型和类型基线均相同：

| 参考\预测 | USED_FOR | EVALUATED_ON | NO_RELATION |
|---|---:|---:|---:|
| USED_FOR | 155 | 0 | 0 |
| EVALUATED_ON | 0 | 2 | 0 |
| NO_RELATION | 5 | 0 | 0 |

EVALUATED_ON只有2条dev，且尾实体类别已提供强先验；100%不能证明模型掌握评估语义或稀有类稳定泛化。这些成绩基于**参考实体**及同会话AI伪标签，不是最终test、人类gold或冻结NER预测实体下的端到端成绩。

## 失败案例：共现不等于方法执行任务

全部5条错误均为AI参考NO_RELATION被预测为USED_FOR，未挑选漂亮成功案例代替：

| sampleId后缀 | 题名 | 需要区分的角色 |
|---|---|---|
| c0fd77afb68c65c839e8 | Neural Network Security: Hiding CNN Parameters with Guided Grad-CAM. | Neural Network是参数被隐藏的受保护对象；直接隐藏手段是Guided Grad-CAM。 |
| 710c48d6461a108d253d | Robustness Evaluation of Text Classification Models Using Mathematical Optimization and Its Application to Adversarial Training. | Adversarial Training是评估的下游应用，不是执行该鲁棒性评估的手段。 |
| ad366be658bf5d281e54 | Cross-Dataset Data Augmentation Using UMAP for Deep Learning-Based Wind Speed Prediction. | 深度学习预测模型是增强数据的受益者；不能倒置为数据增强工具。 |
| 52e04b4842fc31291bdc | MIHBench: Benchmarking and Mitigating Multi-Image Hallucinations in Multimodal Large Language Models. | 多模态大模型是幻觉评估/缓解的对象，不能直接说其执行幻觉缓解；另一个评估实体对单独判断。 |
| 1412781f2a4ef8311aeb | Optimal Scheduling Algorithms for LLM Inference: Theory and Practice. | LLM推理是被调度对象，不是Scheduling任务的调度算法。 |

首例`pair-72cfd3d3970154ef9d3a8549`的USED_FOR输出概率0.9837775，仍是误报。softmax概率未经校准，不等于事实正确概率。当前train仅12条负例（10条METHOD→TASK、2条METHOD→DATASET），EVALUATED_ON仅3条。类别极不平衡、角色区分例少、仅有题名和AI标签相关误差均是风险；本次不能唯一证明失败原因，加权对照只证明单纯改损失没有解决问题。不能为了提高分数把已有5条负例改成正例。

## 报告截图、工程验证与复现

![图7：真实GPU关系开发结果、类型基线和误报分析](evidence/20261006_round11/07_relation_development.png)

图注：固定09输入，两个SciBERT实体对分类模型分别完成6轮/240步GPU微调。参考实体下所选dev正关系F1均98.43%，与train类型多数基线逐条相同，5条NO_RELATION全部误报；类别平衡对照未改善。图为真实保存结果的浏览器可视化截图，不是原始终端、训练现场或Neo4j界面；非最终test或端到端指标。

320项全项目回归通过，无失败/错误/跳过。关系入口8项测试包括方向、Unicode边界、实体类型mask、凭据重建、防覆盖/失败状态及train-only权重；证据导出还验证模型与基线重算、源码快照、逐轮样本覆盖和错误绑定。关系入口单元与**同源码加权11真实运行**合并覆盖280/297条语句=94.28%，17条未覆盖；不是分支全覆盖、人工语义准确率或产品验收。未把旧10源码行号的coverage混入新源码。

留痕文件：

- [未加权10清单](../kg_datasets/dblp/course_v4_runs/re_development_20261006_10/manifest.json)、[实际指标](../kg_datasets/dblp/course_v4_runs/re_development_20261006_10/development_result.json)、[逐轮](../kg_datasets/dblp/course_v4_runs/re_development_20261006_10/epochs.json)、[全部错误](../kg_datasets/dblp/course_v4_runs/re_development_20261006_10/dev_errors.jsonl)。
- [加权11清单](../kg_datasets/dblp/course_v4_runs/re_balanced_development_20261006_11/manifest.json)、[实际指标](../kg_datasets/dblp/course_v4_runs/re_balanced_development_20261006_11/development_result.json)、[逐轮](../kg_datasets/dblp/course_v4_runs/re_balanced_development_20261006_11/epochs.json)、[全部错误](../kg_datasets/dblp/course_v4_runs/re_balanced_development_20261006_11/dev_errors.jsonl)。
- [320项回归XML](../kg_datasets/dblp/course_v4_runs/tests_20261006_round11_handoff.xml)、[关系入口覆盖记录](../kg_datasets/dblp/course_v4_runs/coverage_re_combined_20261006_11.json)。
- [图7来源清单](evidence/20261006_round11/manifest.json)、[实际拍摄记录](evidence/20261006_round11/captures.json)、[图注](evidence/20261006_round11/report_figures.md)。旧07/08/09数据、权重和10张图均保留。
- [本轮全链路核验](../kg_datasets/dblp/course_v4_runs/verification_20261006_round11.json)：156个运行目录957个封存输出、9个导出版本79个文件、21个原始输入及累计11张图哈希全部通过；冻结NER权重与最终test清单不变。

两组选中权重SHA-256分别为`31a73698c92a3c6bce690f8c8d6494dea743f158a638816cdf83ed687741cf3f`与`0a6c6f0057c038395c6c71d48a829f8db3a8a3fe6d5f82578c05c9a0aff53237`，结果相同不等于没训练。运行清单内存有当时源码，10/11的代码版本有加权开关差异，各按其归档复现，不把历史源码与现在文件强行判为一致。

```powershell
# 新输出目录；保留旧结果。第二次加权对照仅增加 --balanced-loss。
& '.\.venv-training\Scripts\python.exe' -B scripts/train_course_relation.py --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_09 --model kg_datasets/models/scibert_24f92d32 --output kg_datasets/dblp/course_v4_runs/NEW_BALANCED_RE_DEV --device cuda --balanced-loss
& '.\.venv-validation\Scripts\python.exe' -B -m pytest tests -q
& '.\.venv-validation\Scripts\python.exe' -B scripts/export_course_evidence.py --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_09 --relation-development kg_datasets/dblp/course_v4_runs/re_development_20261006_10 kg_datasets/dblp/course_v4_runs/re_balanced_development_20261006_11 --tests kg_datasets/dblp/course_v4_runs/tests_20261006_round11_handoff.xml --output docs/evidence/NEW_RE_EVIDENCE
& './scripts/capture_course_evidence.ps1' -EvidenceDirectory docs/evidence/NEW_RE_EVIDENCE
```

## 下一步与完成边界

优先在既有train侧补有原文依据的角色区分负例及稀有评估类；不是合成题名充当DBLP采集，也不把UNRESOLVED强改NO_RELATION。保留旧凭据，独立任务修订明确替换ID，不重复合并或移动split；用户不需手工标注。若定向挑选train，披露选择偏差；不拿这次dev错误原题名回灌训练。

重新开发时固定并报告正类与负类指标、基线及支持，确认语义区分进展后再锁RE权重与选择记录，然后建立完整RE测试参考，报告模块及冻结NER→RE端到端成绩。随后确认Neo4j目标库、幂等导入模型候选与证据、实现检索并拍真实应用界面。当前NER封存不改，RE测试未执行、test关系零标签、图谱应用未验收；实验三尚未整体完成，更不能声称四项课程全部完成。
