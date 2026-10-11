# 课程报告截图与证据索引（2026-10-06）

## 最新16：审计修复与历史结果重渲染

[图10：冻结RE开发结果复核](evidence/20261006_round16_re/07_relation_development.png)、[图11：冻结NER结果复核](evidence/20261006_round16_ner/06_final_test.png)。两图均为实际Edge渲染、视觉检查，展示既有封存结果与334项当前回归；不是新训练/最终测试、原始终端或Neo4j界面。原13图保留，累计15图；本轮没有新增标签或模型成绩。

完整问题与残留限制见[审计记录](course_v4_audit.md)。证据：[334项回归](../kg_datasets/dblp/course_v4_runs/tests_20261006_round16_handoff.xml) → [CPU模型边界检查](../kg_datasets/dblp/course_v4_runs/re_audit_contract_20261006_16_final.json) → [真实只读dev回放](../kg_datasets/dblp/course_v4_runs/dev_audit_parity_20261006_16.json) → [图10来源](evidence/20261006_round16_re/manifest.json)/[拍摄记录](evidence/20261006_round16_re/captures.json)与[图11来源](evidence/20261006_round16_ner/manifest.json)/[拍摄记录](evidence/20261006_round16_ner/captures.json) → [全链路核验](../kg_datasets/dblp/course_v4_runs/verification_20261006_round16.json)。旧训练源码与当前修复源码分开绑定，旧成绩和冻结锁不改，不合并旧训练覆盖冒称当前代码覆盖。

## 历史15：显式实体对表示与RE候选冻结

[图9：CLS与头尾标记开发对照](evidence/20261006_round15/07_relation_development.png)，已真实Edge拍摄并视觉检查。固定10数据343/162条train/dev参考实体对，损失、种子及三类选型一致，仅分类表示变化；14为历史CLS运行、15本轮新训练6轮/258步。15选epoch3，负例正确3/5、错误3条，正micro99.05%、三类macro77.56%，但评估关系召回仅1/2。不是最终RE test、端到端、人工gold或原始训练/Neo4j界面；旧12图保留，累计13图。

完整过程及全部错误见[实体对表示报告](course_v4_relation_entity.md)。证据：[训练前约定存档](../kg_datasets/dblp/course_v4_runs/re_entity_compact_20261006_15.json) → [真实GPU训练清单](../kg_datasets/dblp/course_v4_runs/re_entity_development_20261006_15/manifest.json)/[指标](../kg_datasets/dblp/course_v4_runs/re_entity_development_20261006_15/development_result.json) → [328项回归](../kg_datasets/dblp/course_v4_runs/tests_20261006_round15_final.xml)/[额外模型契约检查](../kg_datasets/dblp/course_v4_runs/re_entity_contract_20261006_15_final.json) → [RE测试候选选择锁](../annotations/course_v4/re_test_selection_20261006.json) → [图9页面/来源哈希](evidence/20261006_round15/manifest.json)/[拍摄记录](evidence/20261006_round15/captures.json)。训练入口同源码94.77%、新模型100%是语句覆盖，不是语义或完整分支证明。NER冻结权重不变，908篇累计判断不变；下一步才做RE test与NER→RE评估。

[全链路核验](../kg_datasets/dblp/course_v4_runs/verification_20261006_round15.json)通过166个运行目录1120个封存输出、96份归档输入、10个导出版本88个文件、21个原始输入及累计13张图；dev/test与09逐字节一致、冻结NER不变，RE选择锁与训练前约定时间/哈希绑定均核对。

## 历史14：角色补样、三类macro选型及漏报代价

[图8：角色与选型对照](evidence/20261006_round14/07_relation_development.png)，真实拍摄并视觉检查。图注：10数据343train/162dev实体对来自264/113篇题名；12–14三组SciBERT各完成6轮/258步真实GPU训练。14三类macro选epoch2，负例正确1/5、另1条USED_FOR漏报，正micro F1=98.42%、三类macro75.66%，整体错误仍5条。少量角色信号不是可靠性证明；基于参考实体和AI标签，非最终RE test、端到端或人工gold。图是实际保存结果的Edge可视化截图，非原始终端或Neo4j界面。

完整选样、两轮AI判断、未决隔离、三组对照和全部错误见 [角色实验报告](course_v4_relation_roles.md)。来源：[25篇匿名选样](../kg_datasets/dblp/course_v4_runs/relation_priority002_jobs/manifest.json) → [首轮](../annotations/course_v4/relation_priority002_generation_decisions.json)/[候选可见自复核](../annotations/course_v4/relation_priority002_review_judgments.json) → [10数据清单](../kg_datasets/dblp/course_v4_training_inputs_10/manifest.json) → [12未加权](../kg_datasets/dblp/course_v4_runs/re_roles_development_20261006_12/manifest.json)/[13加权](../kg_datasets/dblp/course_v4_runs/re_roles_balanced_development_20261006_13/manifest.json)/[14三类选型](../kg_datasets/dblp/course_v4_runs/re_roles_allclass_development_20261006_14/manifest.json) → [325项回归XML](../kg_datasets/dblp/course_v4_runs/tests_20261006_round14_final.xml) → [图8来源/页面哈希](evidence/20261006_round14/manifest.json)/[拍摄记录](evidence/20261006_round14/captures.json)。新增1图，旧11图保留，累计12图；NER冻结不变。覆盖94.46%是同源码关系入口语句覆盖，不是标注准确率。

[本轮核验记录](../kg_datasets/dblp/course_v4_runs/verification_20261006_round14.json)：165个运行目录1078个封存输出、10版导出88个文件、21个原始输入和12张图均通过哈希；图8源包40个封存文件。完整报告保留新增漏报，而非只展示纠正负例。

## 历史11：关系模型开发、类型基线与全部误报

[图7：关系开发](evidence/20261006_round11/07_relation_development.png)，已真实拍摄并视觉检查。图注：固定09输入，315train/162dev实体对来自247/113篇题名；未加权与train逆频率加权SciBERT各完成6轮/240步真实GPU训练，选中dev正关系micro F1均98.43%，却与类型多数基线逐条相同，5条NO_RELATION全部误报。EVALUATED_ON dev仅2条；图为参考实体下的开发结果可视化，不是最终test、NER→RE端到端、人类gold、原始终端或Neo4j界面。尚未晋级为确证图谱事实。

完整流程、逐轮记录、两组比较、5条错误与复现见 [关系开发报告](course_v4_relation_development.md)。来源：[09数据清单](../kg_datasets/dblp/course_v4_training_inputs_09/manifest.json) → [未加权10实际训练](../kg_datasets/dblp/course_v4_runs/re_development_20261006_10/manifest.json)/[加权11实际训练](../kg_datasets/dblp/course_v4_runs/re_balanced_development_20261006_11/manifest.json) → [320项回归](../kg_datasets/dblp/course_v4_runs/tests_20261006_round11_handoff.xml) → [图7源页/来源哈希](evidence/20261006_round11/manifest.json)/[实际拍摄记录](evidence/20261006_round11/captures.json)/[图注](evidence/20261006_round11/report_figures.md)。两组权重、预测、逐步日志、各时源码和全部错误均保留；只增加1张图，旧07四图/08五图/09一图未覆盖，累计11张。

关系入口单元与同源码11实际训练合并语句覆盖94.28%，不是语义准确率。`.passed=true`表示梯度更新/保存重载等工程完整性，不能省略负例0召回而宣称质量通过。[本轮核验记录](../kg_datasets/dblp/course_v4_runs/verification_20261006_round11.json)：156个运行目录957个封存输出、9个导出版本79个文件、21个原始输入和11张图均通过哈希；新图包29个来源/页文件。下一步补train角色区分样本，再冻结RE做最终测试和端到端；NER09已经封存，图谱应用仍未完成。

## 最新09：冻结模型最终NER测试图

[图6：最终测试](evidence/20261006_round09/06_final_test.png)，已拍摄并视觉检查。可直接使用图注：固定200篇测试题名全部完成AI首轮与候选可见自复核后，冻结dev所选SciBERT epoch4，在144篇完整可用题名上一次性评估，56篇未决排除；严格实体P/R/F1=73.44%/75.32%/74.37%，同子集train词典F1=25.27%。DATASET支持仅2，指标是AI参考一致性，覆盖率72%，不是人工gold或完整200篇无偏成绩。图为真实保存结果的浏览器可视化截图，不是原始终端/训练现场/Neo4j界面。

完整步骤、冻结时间线、模型/数据/错误分析、局限和复现见 [最终NER报告](course_v4_ner_test.md)。来源：[选择锁](../annotations/course_v4/ner_test_selection_20261006.json) → [200条首轮](../annotations/course_v4/test_ner_generation_20261006.py)/[200条自复核](../annotations/course_v4/test_ner_review_judgments_20261006.json) → [09数据清单](../kg_datasets/dblp/course_v4_training_inputs_09/manifest.json) → [实际test指标](../kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09/test_result.json)/[全部预测](../kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09/test_predictions.jsonl) → [310项回归](../kg_datasets/dblp/course_v4_runs/tests_20261006_round09_evidence.xml) → [源页和来源哈希](evidence/20261006_round09/manifest.json)/[拍摄记录](evidence/20261006_round09/captures.json)。19个页面/来源文件封存，1张PNG；旧08五图/07四图保留。权重不改、dev重载预测一致，71篇差异/56篇排除原因完整保留。

图1–5按历史版本解释，不能把08未标test状态当现在状态；图6才是09冻结最终NER测试，关系开发图7见上方最新11。此NER版已封存，不用test再调参；RE最终/端到端与Neo4j应用未完成，不预写对应成功截图。

## 历史08：实体候选训练与5张报告图

019批新增25篇train两轮AI判断，24确认/1修订；累计683篇，564篇NER输入、477条关系输入、1317篇待首轮。真实397/167篇train/dev在RTX4060上完成6轮/300步，dev选择第4轮；P/R/F1=73.73%/76.60%/75.14%，同划分词典F1=27.83%，76篇dev错误全部保留。304项回归通过。完整模型结构、数据流程、训练参数、各轮结果、错误分析及重现见 [实验二候选训练报告](course_v4_ner_development.md)。

| 报告位置 | 最新图片 | 可直接使用的图注 |
|---|---|---|
| 实验二：数据准备 | [图1](evidence/20261006_round08/01_data.png) | 08快照683篇AI两轮判断，397train/167dev可用题名全部对齐通过；test未标注，未决不当负例。 |
| 实验二：链路冒烟 | [图2](evidence/20261006_round08/02_training.png) | 历史06的24篇/120步GPU过拟合冒烟回放，不是08候选模型训练曲线，100%是训练内成绩。 |
| 实验二：跨度示例 | [图3](evidence/20261006_round08/03_predictions.png) | 历史06冒烟模型在训练内两个样本上的真实跨度预测，不是dev/test泛化展示。 |
| 可追溯性 | [图4](evidence/20261006_round08/04_traceability.png) | 304项真实回归、08数据及AI未决案例；表中训练权重/输入版本仍指历史06冒烟，不能当08选中权重哈希。 |
| 实验二：训练与验证选型 | [图5](evidence/20261006_round08/05_development.png) | 08的397train/167dev真实6轮/300步候选训练，严格dev F1选择epoch4（75.14%）；同划分词典27.83%，逐类support和首个真实错误案例保留，非最终test成绩。 |

五张均是保存的真实结果的浏览器可视化截图，不是原始终端、训练现场或Neo4j界面。页内来源和限制保留，已逐张视觉检查。DATASET dev仅3个，不能声称稳定泛化；AI自复核不是人工gold或独立盲审。本次仅一组模型/超参数与6个epoch候选，没有全局最优或多seed显著性证明。

08来源：[首轮](../annotations/course_v4/batch019_generation_decisions.json)/[自复核](../annotations/course_v4/batch019_review_judgments.json) → [数据清单](../kg_datasets/dblp/course_v4_training_inputs_08/manifest.json) → [真实训练清单](../kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/manifest.json)/[选型指标](../kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/development_result.json) → [304项XML](../kg_datasets/dblp/course_v4_runs/tests_20261006_round08_final.xml) → [五图索引](evidence/20261006_round08/report_figures.md)/[页面与来源哈希](evidence/20261006_round08/manifest.json)/[拍摄记录](evidence/20261006_round08/captures.json)。[本轮核对记录](../kg_datasets/dblp/course_v4_runs/verification_20261006_round08.json)保留。

最佳权重SHA-256为968a594de551a1ab77a263a725fcdf487b8c559539f7452e2edeb8cf62c8d996，保存重载167篇预测完全相同。NER入口/导出器单元与实际运行合并覆盖90.43%/84.39%，不是模型准确率。新图包30个页面/来源文件封存并记录5张PNG，初始manifest.pending不改写，captures.completed为实际拍摄状态；原图包07不覆盖。

```powershell
& '.\.venv-validation\Scripts\python.exe' -B scripts/export_course_evidence.py --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_08 --preflight kg_datasets/dblp/course_v4_runs/ner_development_20261006_08 --smoke kg_datasets/dblp/course_v4_runs/ner_smoke_20261006_02 --smoke-snapshot kg_datasets/dblp/course_v4_training_inputs_06 --tests kg_datasets/dblp/course_v4_runs/tests_20261006_round08_final.xml --development kg_datasets/dblp/course_v4_runs/ner_development_20261006_08 --output docs/evidence/NEW_08_EVIDENCE
& './scripts/capture_course_evidence.ps1' -EvidenceDirectory docs/evidence/NEW_08_EVIDENCE
```

## 历史07：首批4张报告图与证据

本轮新增 50 篇训练题名的首轮 AI 判断及候选可见自复核，累计 658 篇；新版 `course_v4_training_inputs_07` 导出 547 篇 NER 输入、459 条关系样本，1342 篇仍待首轮。547 篇 train/dev 真实 tokenizer 对齐全部通过。302 项测试通过，失败/错误/跳过均为 0。

历史07截图共4张，已逐张检查文字、曲线和页底来源。它们是真实结果文件的浏览器可视化截图，不是原始终端、GPU训练现场或Neo4j界面。数据页对应当时07快照；训练/预测页回放06真实GPU冒烟，不能说07已重新训练。

## 可直接使用的图与图注

| 建议位置 | 图片 | 可用图注 |
|---|---|---|
| 实验二：标注、划分、输入准备 | [图1：数据处理与划分](evidence/20261006_round07/01_data.png) | 固定论文组划分下的 AI 参考标注与训练输入统计。658 篇完成两轮 AI 判断，380/167 篇 train/dev 可用 NER 题名全部通过 WordPiece 字符跨度对齐；test 尚未标注。 |
| 实验二：模型训练链路验证 | [图2：GPU 冒烟曲线](evidence/20261006_round07/02_training.png) | SciBERT 在 RTX 4060 上完成 24 篇训练内题名、120 个更新步的实际过拟合冒烟。曲线为未平滑 batch loss 的对数坐标显示，不是 dev/test 曲线；编码器与分类头更新、保存重载检查通过。 |
| 实验二：实体预测展示 | [图3：实体跨度与预测](evidence/20261006_round07/03_predictions.png) | 保存模型对两个训练内题名的真实预测回放，展示 METHOD、TASK、DATASET 的原文位置及类别，与 AI 参考跨度对照；不作为未见文献泛化演示。 |
| 实验过程：可复现性与错误分析 | [图4：版本与修订记录](evidence/20261006_round07/04_traceability.png) | 数据版本、固定模型 revision、权重哈希和真实 pytest 结果留痕；省略并列诊断任务及攻击对象边界冲突保持未决，未将它们伪造为空负例。 |

截图插入报告时，保留输入版本、范围限制与来源说明；不能把训练内 F1=100% 改成测试准确率。图2与词典 dev F1不是同一数据，不能直接比较并宣布模型优于基线。正式 NER/test、关系模型和 Neo4j 检索应用尚未完成，本轮没有这些阶段的成功截图。

## 本轮完整留痕链

1. 匿名题名：`course_v4_weak/jobs/generation/batch-0017.jsonl`、`batch-0018.jsonl`，各 25 篇，与旧 608 篇无重复，不移动 split。
2. 首轮语义判断：[017](../annotations/course_v4/batch017_generation_decisions.json)、[018](../annotations/course_v4/batch018_generation_decisions.json)；编译脚本只根据明确原文定位 Unicode offset，不生成语义答案。
3. AI 自复核：[017](../annotations/course_v4/batch017_review_judgments.json)、[018](../annotations/course_v4/batch018_review_judgments.json)。47 条确认、3 条修订；来源 `codex_session / unknown_session_model`，不是人工 gold 或独立盲审。原初次判断未覆盖。
4. 内容绑定凭据与新版导出：[07 清单](../kg_datasets/dblp/course_v4_training_inputs_07/manifest.json)、[累计凭据](../kg_datasets/dblp/course_v4_training_inputs_07/receipts.jsonl)、[进度](../kg_datasets/dblp/course_v4_training_inputs_07/summary.json)。NER 与关系分别筛选，零候选关系文本不产生负例。
5. 真实预检：[547 篇对齐结果](../kg_datasets/dblp/course_v4_runs/ner_preflight_20261006_07/preflight.json)、[新版词典 dev 指标](../kg_datasets/dblp/course_v4_runs/ner_preflight_20261006_07/dictionary_dev_metrics.json)。词典 609 词组，TP=73、预测=176、参考=359，P/R/F1=41.48%/20.33%/27.29%；较 06 的 27.44% 略降，未隐藏未改善结果，DATASET 仍无预测。
6. 冒烟训练历史：[真实每步日志](../kg_datasets/dblp/course_v4_runs/ner_smoke_20261006_02/steps.jsonl)、[预测](../kg_datasets/dblp/course_v4_runs/ner_smoke_20261006_02/smoke_predictions.jsonl)、[权重及输入清单](../kg_datasets/dblp/course_v4_runs/ner_smoke_20261006_02/manifest.json)。实际输入为 06，不用最新补标冒充重训。
7. 本轮回归：[pytest XML](../kg_datasets/dblp/course_v4_runs/tests_20261006_round07_final.xml)。测试渲染转义、Unicode 跨度、缺失/非有限训练步骤等；模拟单元用例不计为新标注或训练成绩。
8. 截图包：[可视化索引](evidence/20261006_round07/report_figures.md)、[页面及来源哈希](evidence/20261006_round07/manifest.json)、[截图时间/浏览器/PNG 哈希](evidence/20261006_round07/captures.json)、[本轮全链路核对](../kg_datasets/dblp/course_v4_runs/verification_20261006_round07.json)。141 个运行目录共 787 个清单内输出、7 个导出版本共 61 个文件、21 个原有输入以及 4 张图/源页面均通过哈希核对；论文组跨 split 为 0。

源数据/模型/测试文件副本在截图包 `sources/` 内，21 个页面与来源文件已封存；原始模型大权重不重复打包。生成时 `manifest.json` 记录截图 pending，后续实际拍摄完成状态以独立 `captures.json` 的 completed 为准，不改写初始封存状态。哈希用于发现漂移，不能认证 AI 身份或语义正确性。

## 截图生成与复现

采用 MLE 工作流技能保持版本和评估范围隔离。未安装新前端框架或绘图库，曲线直接取实际 steps.jsonl，用本地 HTML/SVG 呈现。浏览器插件能打开和检查页面，但按路径保存受插件工作区限制；不带路径的一张截图仅在会话展示。最终 4 张 PNG 使用本机已安装 Edge 的 headless 截图功能，未修改图片像素。

Edge 采用独立临时 profile、隐藏窗口，不复用用户登录态；截图命令中的 `--disable-gpu` 只控制截图浏览器渲染，与此前 PyTorch 的真实 CUDA 训练无关。截图不是此刻仍在训练的证明，训练发生时间读取原始 status/steps 文件。临时浏览器 profile 保留在 captures.json 指明的 Temp 路径，报告材料不依赖该 profile。

```powershell
# NEW 目录必须不存在；原始数据、旧版导出和截图不覆盖。
& '.\.venv-validation\Scripts\python.exe' -B scripts/export_course_evidence.py --dataset kg_datasets/dblp/course_v4_weak --snapshot kg_datasets/dblp/course_v4_training_inputs_07 --preflight kg_datasets/dblp/course_v4_runs/ner_preflight_20261006_07 --smoke kg_datasets/dblp/course_v4_runs/ner_smoke_20261006_02 --smoke-snapshot kg_datasets/dblp/course_v4_training_inputs_06 --tests kg_datasets/dblp/course_v4_runs/tests_20261006_round07_final.xml --output docs/evidence/NEW
& './scripts/capture_course_evidence.ps1' -EvidenceDirectory docs/evidence/NEW
```

需要重拍时生成新证据目录，不覆盖已有 PNG 或 captures.json。下一阶段继续补训练队列与固定规范的测试参考标签，正式 NER 用 dev 选型；之后训练关系模型、测端到端 pipeline，再截图真实 Neo4j 导入和文献查询应用。
