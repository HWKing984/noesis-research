# 实验二：冻结 SciBERT 的最终 NER 测试与报告材料

2026-10-06 已完成一次锁定模型的最终测试：固定 200 篇 test 队列全部完成 AI 首轮判断及候选可见自复核，144 篇完整可用、56 篇未决排除。严格实体 P/R/F1 为 **73.44% / 75.32% / 74.37%**；同划分 train 词典 F1 为 **25.27%**。这是留出论文上相对于 **AI 参考标签** 的一致性，不是人工 gold 准确率，也不是全部 200 篇的无偏成绩。

## 1 为什么 DBLP 仍需实体抽取

作者、论文、年份、场馆可以从 DBLP 结构化字段直接解析，但题名中的方法、研究任务和命名数据集需要识别原文位置与类别。实验二的输入是题名，输出为 METHOD / TASK / DATASET 的连续、不重叠 Unicode 字符跨度。后续关系模型再判断方法与任务、数据集之间的关系。识别到术语不等于论文实际采用该方法或在该数据集上评估；最终应用提供候选参考文献及原文证据，不能替代阅读文献和确认其是否支持论点。

整体采用 pipeline：题名 → SciBERT NER → 实体对关系分类 → 可追溯候选图谱 → 文献检索。书目解析、规则主题与深度学习预测分别记录来源，不把结构化字段或规则结果包装成神经网络成绩。

## 2 模型、划分与冻结顺序

SciBERT 科学英语编码器为 12 层、hidden size 768，接 7 类 BIO token 分类头：O、B/I-METHOD、B/I-TASK、B/I-DATASET。编码器和分类头在此前实际微调中均更新；损失为 token 交叉熵，特殊 token/padding 标签 -100。使用 AdamW、weight decay 0.01、梯度裁剪 1.0、batch 8、lr 5e-5、max length 128、seed 20261006。选择原因是输入为英文科学文献题名且本地有固定可核验的模型；未做架构搜索，不称全局最优。

模型固定 revision `24f92d32b1bfb0bcaf9ab193ff3ad01e87732fc1`。此前 [08 候选训练报告](course_v4_ner_development.md) 记录 397 train / 167 dev、6 epoch / 300 步；每轮仅 train 回传梯度，以 dev 严格实体 micro F1 最大、平分取较早 epoch，选择 **checkpoint_epoch_04**。dev P/R/F1=73.73%/76.60%/75.14%。

| 时点（2026-10-06，UTC / 北京时间） | 真实动作 |
|---|---|
| 01:21:53 / 09:21:53 | 08 train/dev 训练完成，dev 选中 epoch 4 |
| 01:36:16 / 09:36:16 | [锁定选择](../annotations/course_v4/ner_test_selection_20261006.json)，尚未读取本轮测试题名或评分 |
| 01:45:59 / 09:45:59 | 首轮测试判断导入凭据；此时间是导入记录，不冒称每条推理的开始时间 |
| 01:58:09 / 09:58:09 | 200 篇 AI 自复核导入，封存 09 输入 |
| 02:01:19–02:02:03 / 10:01:19–10:02:03 | 实际 CUDA 最终测试流程；总计 44.45 秒，含校验/重载/dev 一致性/词典/保存，非纯 GPU 耗时 |
| 05:32:23 / 13:32:23 | 保存结果的实际 Edge 浏览器截图；不是训练现场截图 |

固定基础权重不重新下载，测试不创建优化器、不训练、不改变权重。权重文件 SHA-256 仍为 `968a594de551a1ab77a263a725fcdf487b8c559539f7452e2edeb8cf62c8d996`。时间和哈希用于追溯、检查漂移，不是密码学认证的独立实验或语义正确性证明。

## 3 测试标注、复核与清洗

从既定匿名批次 0073–0080 各取 25 篇，恰好覆盖原有 200 篇 test，不移动 split、不增加题名。首轮只读 sampleId/text/textSha256，题名作为数据而非指令，不参考模型的测试预测。200 条具体语义判断保存后，由原有编译器机械定位原文 offset、验证契约，再导入。

第二轮为同一 Codex 会话看见首轮候选的 AI 自复核，**198 确认、2 修订**，每条都有具体理由，不是脚本自动确认。Attractor Reconstruction 由 METHOD 修为目标操作 TASK；编辑性题名中的 Signal Processing 由完整 TASK 改为领域/操作身份未决，整条隔离。初次内容和复核内容都保留。来源为 `codex_session / unknown_session_model`、`ai_pseudo`，不冒称独立盲审、独立模型或人工 gold。

测试本轮范围仅 NER。所有关系状态明确为未处理，候选对均为 UNRESOLVED；不是 NO_RELATION、不是共现关系，也没有伪造关系训练标签。

| split | 两轮判断题名 | NER 可用题名 | METHOD | TASK | DATASET | 已有关系样本 |
|---|---:|---:|---:|---:|---:|---:|
| train | 483 | 397 | 460 | 346 | 12 | 315 |
| dev | 200 | 167 | 208 | 148 | 3 | 162 |
| test | 200 | 144 | 192 | 118 | 2 | 0 |
| 合计 | 883 | 708 | 860 | 612 | 17 | 477 |

09 的 train/dev NER 输入逐条与训练时的 08 完全相同。仍有 1117 篇 train 待首轮；首批预算 2000 篇没有全部标完，也不是课程必须的标注数量。累计实体未决 174、关系未决 367、并列挑战 7。56 篇测试排除记录均保留原题名、原因、提及组及内容哈希，排除不是空负例。

歧义案例包括共享中心词并列（不补造省略文字）、TASK/METHOD 重叠、硬件加速器与方法身份不清、Disease Ontology 的本体/数据集角色不清。Electrical Transformer 明确是电力设备，未当神经 Transformer。Retraction Note 题名保留撤稿警告且未决，不作为有效研究结论。两项命名数据集为 Wisconsin diagnostic dataset 和 InsectSet459，不为凑支持数强行标其他资源。

## 4 最终评估的实际步骤

1. 验证已封存运行文件、epoch 记录和选择锁：只允许此前 dev 选择的 epoch 4，不取最后一轮、latest 或其他权重。
2. 重新验证 canonical reference、凭据和 09 summary；必须整个固定测试队列都完成复核，而非只处理容易题名便提前打分。
3. 校验 08 train/dev 与 09 完全一致，契约/类别/论文组不漂移；记录训练完成、选择锁及测试导入的时间顺序。
4. 使用 checkpoint 自带的本地 tokenizer，无远程代码；167 dev / 144 test 全部对齐通过，最长分别 32/34 token，拒绝 0、无截断、无静默过滤。
5. RTX 4060 Laptop GPU / CUDA 12.6，固定原配置、确定性 eager FP32、关闭 TF32；`eval()`、`requires_grad_(False)` 和 `no_grad()` 只读推理。CLI 不允许测试模式传入训练超参数。
6. 先对原 dev 做重载一致性检查，167 篇实体预测与历史保存结果完全相同；这不是重新选择 checkpoint。不同则拒绝进行测试推理。
7. 对 144 篇 test 一次性预测。以同一文档的 start/end/类别完全一致计 TP，计算实体级 micro/逐类 P/R/F1；非法 orphan I 丢弃并计数，不自动修成 B。
8. 保存全部参考/预测、全部 71 篇差异、56 篇排除记录；仅由固定 train 跨度生成 642 词组的词典，评估相同 test 子集，不补测试词典。
9. 再检查权重/来源哈希和所有参数无梯度；封存状态、来源源码副本、依赖、配置、结果与清单。输出已存在即拒绝覆盖，失败明确记录，不自动重试或调参。

此次 dev 预测一致性核验也验证了提取为公共推理函数后解码语义没有改变。词典用标准库 regex cache 避免反复编译同一词组，不改匹配/冲突策略。

## 5 最终结果与基线

| 模型/类别 | AI 参考数 | TP / 预测数 | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| SciBERT micro | 312 | 235 / 320 | 73.44% | 75.32% | 74.37% |
| train 词典 micro | 312 | 59 / 155 | 38.06% | 18.91% | 25.27% |
| SciBERT METHOD | 192 | 140 / 192 | 72.92% | 72.92% | 72.92% |
| SciBERT TASK | 118 | 94 / 126 | 74.60% | 79.66% | 77.05% |
| SciBERT DATASET | 2 | 1 / 2 | 50.00% | 50.00% | 50.00% |

词典 DATASET 没有预测：P=N/A、R=0、F1=0，不伪造 precision=100%。神经模型比词典 test micro F1 高约 49.10 个百分点，但只有单次 seed 和一组超参数，不是多 seed 显著性结论。测试 F1 比 dev 选型 F1 低约 0.77 个百分点，不能仅凭接近就证明无过拟合或跨领域泛化。

测试 token loss=0.665234，95 次非法 BIO 延续，71/144 篇有至少一个跨度或类别差异。实体指标不是 token accuracy；实体边界截短同时产生 FP/FN。可用覆盖率 72%，不能把未决的 28% 自动算正确，也不能把该子集指标称为整个 200 篇的成绩。

## 6 真实差异案例与限制

保存顺序中的首个差异题名：`On the Power of Graph Neural Networks and Feature Augmentation Strategies to Classify Social Networks.`。AI 参考 METHOD 为 `Feature Augmentation Strategies`，模型只预测 `Feature Augmentation`；另两实体完全匹配。这展示完整方法边界缺失，而非只选容易的成功例子。

第二例：`Multi-Modal Retrieval For Large Language Model Based Speech Recognition.`。参考保留完整 METHOD `Large Language Model Based Speech Recognition`，模型截为 `Large Language Model`。完整组合与基础模型边界仍是难点；AI 参考也可能存在体系性误差，未经独立语义核验不能把所有差异都称模型错误。

主要限制：同会话相关标注错误、未决排除的选择偏差、只有题名无摘要/全文、DATASET train/dev/test 仅 12/3/2、单组参数及单 seed、近重复检测不穷尽、规则筛 AI 候选并非人工领域金标准。代码与哈希检查不能替代这些实质质量问题。此模型版的 NER train/dev/test 流程已完成，**不意味着实验三、四或全部课程已完成**。

## 7 报告截图与原始证据

![冻结模型最终NER测试](evidence/20261006_round09/06_final_test.png)

图注：固定 200 篇测试题名全部完成 AI 首轮及自复核后，冻结 dev 所选 SciBERT epoch 4 在 144 篇完整可用题名上一次性评估；56 篇未决隔离，严格实体 P/R/F1=73.44%/75.32%/74.37%，词典同子集 F1=25.27%。DATASET 支持仅 2，结果为 AI 参考一致性。图片是已保存真实结果的实际浏览器可视化截图，不是训练现场终端或 Neo4j 界面。

- [首轮具体判断与机械导出源码](../annotations/course_v4/test_ner_generation_20261006.py)、[200条AI自复核](../annotations/course_v4/test_ner_review_judgments_20261006.json)、[初次导入](../kg_datasets/dblp/course_v4_runs/test_ner_generation_20261006_09/receipts.jsonl)、[复核及初次快照](../kg_datasets/dblp/course_v4_runs/test_ner_review_20261006_09/receipts.jsonl)。导出程序本身不调用 AI、不自动进行语义标注。
- [09统计](../kg_datasets/dblp/course_v4_training_inputs_09/summary.json)、[09清单](../kg_datasets/dblp/course_v4_training_inputs_09/manifest.json)：SHA-256 `9727dad008ab4750292e5bde3a2d8be2f68b7e2f3e1f0f3ed5ab64b4ec219fde`，旧 01–08 原样保留。
- [实际状态](../kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09/status.json)、[最终指标](../kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09/test_result.json)、[完整控制台输出](../kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09.console.log)、[推理清单](../kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09/manifest.json)：SHA-256 `0e64965da7f521cebded4bf01afc6cfe3d40aeb84685bec5e1fce9d56d1a1602`。
- [全部144篇预测](../kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09/test_predictions.jsonl)、[71篇差异](../kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09/test_errors.jsonl)、[56篇排除原因](../kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09/excluded_test_titles.jsonl)、[词典指标](../kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09/dictionary_test_metrics.json)、[dev重载核验](../kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09/dev_reload_check.json)。
- [310项全项目回归](../kg_datasets/dblp/course_v4_runs/tests_20261006_round09_evidence.xml)：失败/错误/跳过均为 0，XML 34.162 秒；包含全队列门槛、选中权重绑定、不可覆盖/显式失败、从预测重算截图分数等。不是 310 条语义人工检查。
- [源页与来源副本清单](evidence/20261006_round09/manifest.json)、[实际拍摄时间/Edge版本/PNG哈希](evidence/20261006_round09/captures.json)、[图注索引](evidence/20261006_round09/report_figures.md)、[全链路核对](../kg_datasets/dblp/course_v4_runs/verification_20261006_round09.json)。页面完整文字、表格、差异案例和页底来源均已视觉检查；19 个页/来源文件封存、1 张 PNG。旧 08 五图、07 四图保留。

本次按 MLE 工作流先冻结 dev 选择、再封存 test 标签；PyTorch 模式确保只读推理与 dev 重载一致性，Python 测试验证输入绑定与失败/不可覆盖状态。没有新增训练/截图框架。测试运行覆盖记录只涉及最终评估路径，不能沿用旧版 08 的 90.43% 覆盖率冒称当前源码全部分支已验证。

## 8 复现与下一步

```powershell
# 本轮已执行完；不要为了改进分数重跑/更换模型。本命令仅供原样复现实验。
# --model 在 evaluate-test 模式表示已封存的 development 运行，不是基础模型目录。
& '.\.venv-training\Scripts\python.exe' -B scripts/train_course_ner.py evaluate-test --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_09 --model kg_datasets/dblp/course_v4_runs/ner_development_20261006_08 --selection annotations/course_v4/ner_test_selection_20261006.json --output kg_datasets/dblp/course_v4_runs/NEW_UNCHANGED_REPRO --device cuda
& '.\.venv-validation\Scripts\python.exe' -B -m pytest tests -q
& '.\.venv-validation\Scripts\python.exe' -B scripts/export_course_evidence.py --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_09 --final-test kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09 --tests kg_datasets/dblp/course_v4_runs/tests_20261006_round09_evidence.xml --output docs/evidence/NEW_TEST_EVIDENCE
& './scripts/capture_course_evidence.ps1' -EvidenceDirectory docs/evidence/NEW_TEST_EVIDENCE
```

固定配置来自旧运行，不接受测试调参；当前测试仅执行一次，尚未重复最终 CUDA 评估或完整 6 轮训练，不冒称重跑一致性。已完成的 dev 重载一致性与“重复训练”不同。

**NER 此版本封存，不再根据这次 test 差异修改规范、标签或权重。** 原样复现不是再次调参；测试入口没有全局禁止手工另建运行目录，行为约束须在报告/工作流程中继续遵守。未来测试启发的改进另建模型版，并预先准备未暴露的新评估集。

下一阶段先为关系任务保存独立的标注/复核修订（保留此次实体/关系未处理快照），再训练带头尾实体标记的编码器分类模型；只用 train/dev 做模型开发和选择，冻结后测参考实体下 RE 及冻结 NER→RE 端到端 pipeline。EVALUATED_ON train/dev 仅 3/2、test 尚无关系标签；不得为覆盖率强标关系或把不确定当负例，零支持须报告 N/A，必要的新留出数据在评估前独立锁定。完成关系模型后确认 Neo4j 连接及目标库，幂等导入候选事实与证据并实现检索应用，保存真实数据库/应用截图。
> 轮次16审计补充：加强评分跨度、最终测试CLI和证据覆盖/排除绑定校验；本文封存结果不变，只回放167篇dev，未再执行test推理。当前334项回归；日期勘误和AI参考/覆盖限制见[复核记录](course_v4_audit.md)。

