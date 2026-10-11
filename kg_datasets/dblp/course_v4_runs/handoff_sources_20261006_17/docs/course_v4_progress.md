# 课程 v4 实施进度（2026-10-06）

## 最新17：冻结关系测试与严格pipeline

144篇固定NER可用test题名完成RE首轮及同会话自复核，138篇完整/6篇关系未决，56篇原NER未决继续隔离；无新论文，累计仍908篇。新11数据RE642条（343/162/137），test132用途/1评估/4负例，train/dev不变，实体边界不改。NER test导出annotation哈希随新关系改变，原09/10和NER成绩保留，不宣称新test文件逐字节不变。

先封数据，固定15的epoch3执行一次真实CUDA RE测试；dev162对回放一致，权重不改。参考实体下正micro99.25%，严格NER→RE正micro60.07%（P58.57/R61.65），模块2错、pipeline51篇差异均保留；pipeline复用原NER09预测，未重跑NER test。覆盖138/200=69%、EVALUATED_ON仅1，AI参考非gold，不能称整体可靠。338项回归，新增图12，旧15图保留。详见[关系最终测试与错误报告](course_v4_relation_test.md)。下一步Neo4j可追溯候选事实与应用，尚未验收。

## 历史16：复核与缺口修复（不新增训练/标注）

修复七类加载、真实无标签推理、NER评分、证据绑定、最终测试CLI和来源日期问题；334项全项目回归及额外CPU契约检查通过。实际冻结NER167篇dev、RE14/15各162条dev回放预测一致，数据/权重/选择锁不变，未重跑最终test。新增两张历史结果重渲染截图，旧13图保留；RE最终测试、pipeline与Neo4j应用仍未完成。详情与证据见[审计记录](course_v4_audit.md)。下文数字与覆盖率保留各历史轮次含义，不当成本轮新训练成绩。

已完成数据准备、累计908篇AI判断、冻结NER训练/测试与六组累计RE开发训练；RE测试候选已冻结，关系最终测试、端到端pipeline和应用尚未完成。用户无需手工标注。历史15新增实体对表示训练及图9，未新增标注；本轮16仅审计修复，不覆盖历史。

## 历史15：实体对表示对照与RE候选冻结

固定10数据、训练侧逆频率损失及三类macro选型，只将pooled CLS改为有方向的头尾开始标记向量拼接；真实GPU完成6轮/258步，选epoch3，编码器/1536维分类头更新，保存重载一致。dev正micro F1=99.05%、三类macro=77.56%，负例正确3/5（14为1/5）、总错误3条（14为5条）；但EVALUATED_ON召回由2/2降为1/2、正macro降为83.01%。全部剩余错误保留，不能只展示micro高分。

满足运行前声明的有限dev门槛，已生成[RE测试选择锁](../annotations/course_v4/re_test_selection_20261006.json)，权重和配置固定；下一步完成关系test标注和只读评估，不继续针对dev堆模型。此前NER已看过这些test题名，不能称全新文本盲测；RE test关系标签尚未产生，未用于选型。NER仍原冻结权重74.37%，908篇AI判断/505条已有关系输入不变。

328项回归与额外CPU模型契约检查通过，训练入口语句覆盖94.77%、新模型100%（不等于语义准确率/完整分支覆盖）。新增图9真实Edge结果截图，旧12图保留。详见[完整对照报告](course_v4_relation_entity.md)及[证据索引](course_v4_report_evidence.md)。最终RE/NER→RE端到端及Neo4j尚未完成。

## 历史14：角色补样与三类macro选型

25篇原train待首轮完成两轮AI判断，23确认/2修订；20篇NER可用、17篇关系可用，净增16 USED_FOR和12 NO_RELATION。5篇实体未决/8篇关系未决保留；QuixBugs部分明确评估判断未拆出训练。10快照累计908篇（508/200/200），NER输入728篇（417/167/144），关系505条（343/162/0），train负例12→24、EVALUATED_ON仍3。dev/test逐字节与09相同，原883份凭据未改；1092篇train待首轮。NER未重训，其最终测试仍74.37%。

12/13/14分别未加权、train逆频率加权、加权且三类macro选型，各6轮/258步。前两组按原正macro仍选第1轮，与类型基线相同；14选第2轮，负例正确1/5，另1条正例漏报，正micro F1=98.42%、三类macro=75.66%，比基线三类macro66.14%提高但总体错误仍5条。13/14梯度日志及各轮指标实测完全一致，仅选型与保存checkpoint不同，不能声称训练算法或多seed稳定性提高。角色信号有限，未晋级为确证图谱事实。

325项全项目回归通过；关系入口同源码单元与14真实训练合并语句覆盖94.46%，不是语义准确率。修复截图导出旧计数常量，新增图8真实Edge截图、全部权重/源码/错误/来源，旧11图保留。详见 [角色补样与选型报告](course_v4_relation_roles.md)和[证据索引](course_v4_report_evidence.md)。test关系零标签、未评估，端到端及Neo4j仍未完成。

## 历史11：关系模型开发与类别平衡对照

保持09数据快照，315train/162dev实体对来自247/113篇题名。两个SciBERT头尾标记分类模型分别真实GPU训练6轮/240步：10未加权、11按train逆频率加权，其余参数相同；各按dev正关系macro选epoch1，编码器/分类头实际更新，保存重载一致。两组选中模型dev正micro F1=98.43%、macro F1=99.21%，但162条预测均与类型多数基线相同，5条NO_RELATION全部误报。权重不同、误报相同，不把训练链路成功当模型质量验收。EVALUATED_ON仅3条train/2条dev，100%不是稳定泛化证明。

320项全项目回归通过；关系入口单元与同源码11真实训练合并语句覆盖94.28%，不是模型准确率。新增真实Edge结果可视化截图（非终端或Neo4j），保存逐轮/逐步日志、全部预测与5条错误、两组权重/源码清单。详见 [关系开发报告](course_v4_relation_development.md)及[证据索引](course_v4_report_evidence.md)。累计883篇、477条关系输入及NER最终74.37%不变，无新增标注或RE test成绩。下一步只补train侧角色区分/稀有类并记录新版，再冻结RE做模块与端到端测试；不因dev高分提前导入确证图谱事实。

## 最新09：测试队列封存与一次性NER评估

测试批次073–080共200篇两轮AI判断：198确认/2修订，144篇完整可用、56篇未决隔离。只完成NER任务，全部关系明确未处理，不改成NO_RELATION。累计883篇两轮判断（483/200/200），708篇NER输入（397/167/144），train/dev逐条与训练时08相同。实体/关系未决174/367、并列挑战7；1117篇待首轮均为train。已有关系仍477条（315/162/0），EVALUATED_ON仅3/2/0，RE未ready。

先锁定dev所选epoch4及权重哈希，后封存test标签，再做CUDA只读测试。原167篇dev预测重载完全一致；144篇test无截断全部对齐通过，P/R/F1=73.44%/75.32%/74.37%，同子集词典F1=25.27%，71篇差异与56篇排除原因全部保存。DATASET仅2个，F1=50%不代表稳定泛化。200篇全部判断≠200篇全部评估；72%覆盖、同会话AI参考和选择偏差明确披露。

09当时310项回归通过。新增真实浏览器测试结果可视化图（不是原始终端或Neo4j画面），来源/页/PNG哈希与拍摄时间封存。详情见 [最终NER测试报告](course_v4_ner_test.md)和[证据索引](course_v4_report_evidence.md)。此NER版封存，不根据test改规范/标签/权重；后续关系进展见上方最新11，最终RE/端到端及Neo4j仍未完成。NER流程完成不等于四项实验全部完成。

## 历史08：候选训练、dev选型和报告图

019批25篇首轮与AI自复核完成，24确认/1修订；累计653确认/30修订，483 train / 200 dev / 0 test。118篇实体未决、167篇关系未决、4篇并列挑战按任务隔离；来源仍为AI伪标签，不是独立盲审或人工gold。

| split | 两轮判断篇数 | NER可用 | 关系样本 | METHOD / TASK / DATASET |
|---|---:|---:|---:|---|
| train | 483 | 397 | 315 | 460 / 346 / 12 |
| dev | 200 | 167 | 162 | 208 / 148 / 3 |
| test | 0 | 0 | 0 | 0 / 0 / 0 |
| 合计 | 683 | 564 | 477 | 668 / 494 / 15 |

515篇满足关系导出条件（357/158），实际有实体对的文本导出477条：USED_FOR455/EVALUATED_ON5/NO_RELATION17。1317篇待首轮（train1117/test200）；01–07原样保留。

564篇无截断对齐通过。真实GPU训练397篇train，167篇dev选checkpoint；6轮/300步，第4轮严格实体P/R/F1=73.73%/76.60%/75.14%，同划分642词组基线F1=27.83%。编码器与分类头更新，保存重载预测一致，76篇dev错误全部保留。DATASET dev支持仅3，不宣称稳定泛化。完整步骤/各轮/错误见 [实验二候选训练报告](course_v4_ner_development.md)，五图见 [报告证据索引](course_v4_report_evidence.md)。

304项全项目回归通过；NER入口单元与真实候选训练合并覆盖90.43%，导出器单元与真实导出合并84.39%，不是语义准确率。实际运行developmentTrainingStarted=true/testEvaluated=false，封存数据summary不修改；本轮没做最终test，也未重复整套6轮训练来证明权重复现。

## 历史07快照与报告截图

训练 017/018 各 25 篇完成首轮与候选可见 AI 自复核：47 条确认、3 条修订，累计 629/29；两个批次与此前 608 篇无重复，不移动 split。修订将不确定的隐私激励机制、共享误读对象的 Detection/Diagnosis 边界、攻击对象与复合模型的重叠边界保留未决，原判断仍保留，不凑负例。累计实体/关系未决为 110/156 篇，3 篇并列 METHOD 挑战仍隔离；没有独立盲审或人工 gold。

| split | 两轮 AI 判断篇数 | NER 可用篇数 | 关系样本条数 | METHOD / TASK / DATASET 跨度 |
|---|---:|---:|---:|---|
| train | 458 | 380 | 297 | 438 / 327 / 12 |
| dev | 200 | 167 | 162 | 208 / 148 / 3 |
| test | 0 | 0 | 0 | 0 / 0 / 0 |
| 合计 | 658 | 547 | 459 | 646 / 475 / 15 |

501 篇满足关系导出条件（343/158），有实体对的文本实际导出 459 条：USED_FOR 438、EVALUATED_ON 5、NO_RELATION 16。本轮净增 42 篇 NER 输入、32 条关系样本；DATASET/EVALUATED_ON 未新增，仍不足。新版 [course_v4_training_inputs_07](../kg_datasets/dblp/course_v4_training_inputs_07/manifest.json) 保留 1342 条待首轮（train 1142、test 200），旧 01–06 未覆盖。未决不生成空负例。

547 篇 train/dev 的真实 tokenizer 预检通过，最长 33/32 token，拒绝 0。609 词组的训练词典 dev micro F1=27.29%，比 06 的 27.44% 略降，未把补标数量增加当模型成绩提升。测试题名未用于补词典或规范设计。

4 张 PNG 展示最新数据、历史真实冒烟曲线、训练内模型预测和修订证据，已逐张检查并绑定源页面哈希。数据使用 07，模型仍是 06 的 24 篇冒烟，未冒称新版本重训；截图不是终端或 Neo4j 界面的仿制。302 项回归通过，141 个运行目录的 787 个封存输出、7 个累计版本共 61 个文件及 21 个原有输入未漂移。可直接引用的图片、图注与复现步骤见 [报告证据索引](course_v4_report_evidence.md)。

## NER 训练链路已实际验证

阶段 3 的历史 06 版本已建立独立 Python 3.12/CUDA 训练环境，下载固定版本 SciBERT 并核对上游权重哈希；当时 338 篇 train 与 167 篇 dev 全部通过真实 tokenizer 对齐检查，没有截断或静默剔除。该版本训练跨度词典的 dev 严格实体 micro F1 为 27.44%；历史07预检见上节，最新08候选训练见本文开头。

RTX 4060 上两次 fresh run 均完成 24 篇 train-only、120 步真实微调：token loss 从 2.143906 降至 0.000197605，训练内 46 个实体严格 F1=1.0；编码器和分类头确实更新，保存后重载预测相同。两次样本、逐步日志、预测和权重哈希全部相同。这是过拟合冒烟，不是测试准确率，不能与不同数据上的词典 dev 成绩直接比较；其中 DATASET 只有 1 个跨度。

规范结果为 `ner_smoke_20261006_02`；实际运行 `trainingStarted=true`、`formalTrainingStarted=false`、`testEvaluated=false`，不改写数据导出 summary 中的封存状态。初次运行 01 与其源码保留，内部指标范围命名与无效 coverage 参数的问题通过新版本纠正，没有覆盖旧证据。具体模型选择、网络结构、步骤、真实指标、依赖与限制见 [实验二训练链路报告素材](course_v4_ner_smoke.md)。

## 数据准备已完成

从现有 20000 篇 DBLP 人工智能候选文献出发，按论文组固定划分后选出 2000 篇题名：训练 1600、验证 200、测试 200，共 80 个每批 25 篇的匿名标注任务。387 篇历史已暴露候选及其同组成员锁定在训练侧（共 388 篇）；12 对已知近重复放在同一 split，跨 split 论文组为 0。近重复启发式并非穷尽检测，人工智能标题规则也不是人工确认的领域金标准。

旧版本、原始数据和旧交付包没有被本轮流程覆盖。21 个清单内原始输入文件的 SHA-256 与建队列时一致。旧 20 篇 AI 候选仍保留为未决首轮材料，不自动算入已复核训练标签。

队列校验实跑结果：`valid=true, documents=2000`。来源、划分、契约与输出文件哈希见 [队列清单](../kg_datasets/dblp/course_v4_weak/manifest.json)。这是封存版本，其 summary 不作为后续动态进度。

## 历史 06：累计 608 篇 AI 判断

本轮新增 **320 篇**：训练题名 007–016 共 245 篇、验证题名 070–072 共 75 篇，共十三批。原 007/009/014 分别排除已在数据集优先批次处理的 1/2/2 篇，形成 24/23/23 篇匿名子批次，其余各 25 篇；与此前 288 篇无重复 ID，不新增论文或移动划分。累计训练/验证为 408/200 篇两轮判断，验证队列已全量处理，但不是全部标签都已裁决或可训练。此前 066/067 排除 CG-Bench、LIDC-IDRI 的记录继续保留。未读取测试题名来设计规范或补词典。当前训练样本受顺序和此前稀有类别优先处理影响；完整验证队列的未决样本排除也会产生选择偏差，不能称为人工 gold 或无偏评测结论。

全部 608 篇保留初次判断与候选可见 AI 自复核：582 条确认、26 条修订。本轮 320 条中 308 条确认、12 条修订：保留探索任务的 Interactive 场景，完整记录 LXMERT 表示学习机制与 GNN-based 图算法；将 Memory Load Value Predictor 归入完整复合 METHOD，移出 Data-efficient 评价修饰；将知识迁移题名中的技术子问题归回 TASK；补全 Landslide 评估模型构建任务；不确定的 Polar Representations、概念建模、Child FER 与 The last Dance 角色保留未决；ZipAR 的基础任务不含自回归推理设定。当前 102 篇实体未决、141 篇关系未决、3 篇共享中心词并列挑战文本仍保留并按任务隔离。确认比例不是语义准确率。

两轮判断均由当前 Codex 会话 AI 完成，来源为 `codex_session / unknown_session_model`。复核看到了首轮候选，不是独立盲审、独立模型验证或真人 gold。编译/导入脚本仅定位并验证明确写下的 AI 决定，不自行生成语义判断。

| 划分 | 两轮判断（篇） | NER 输入（篇） | DATASET 跨度 | 关系输入（条） | EVALUATED_ON（条） |
|---|---:|---:|---:|---:|---:|
| train | 408 | 338 | 12 | 265 | 3 |
| dev | 200 | 167 | 3 | 162 | 2 |
| test | 0 | 0 | 0 | 0 | 0 |
| 合计 | 608 | 505 | 15 | 427 | 5 |

可用实体跨度共 1048 个：METHOD 599、TASK 434、DATASET 15。466 篇满足关系导出条件（train 308、dev 158），实际有实体对的文本合计导出 427 条：USED_FOR 408、EVALUATED_ON 5、NO_RELATION 14。关系条件已通过的零候选文本不产生关系负例。train/dev 的实体类别覆盖分别为 METHOD 391/208、TASK 286/148、DATASET 12/3；关系类别覆盖分别为 USED_FOR 253/155、EVALUATED_ON 3/2、NO_RELATION 9/5。本轮净新增 274 篇可用 NER 输入、214 条关系输入；实体与关系导出条件独立，不能将两类数量相加当论文数。

EVALUATED_ON 来自明确的比较或性能/benchmarking 语境，不仅靠 using/on：两个 MNIST 方法比较、PTB-XL benchmarking、LIDC-IDRI accuracy，以及本轮 MIHBench 明确用于衡量多模态大模型的多图幻觉。MIHBench 的模型是被评估/缓解幻觉的对象，不倒置成幻觉缓解算法；这条 scoped NO_RELATION 保留原文理由。数据集创建、供模型训练、一般应用到数据集、或宣称将来用于评测的题名，不自动记成已评测事实。凡无法定案的关系保持 UNRESOLVED。

同名错误也保留了处理证据：题名明确介绍深度学习框架的 MNiST 标为 METHOD，不按拼写相近的 MNIST 数据集标注；Overhead-MNIST 的资源角色不够明确，仍未决。Unimodal and Multimodal Representation Training、acoustic and state-transition models、Zero and data reuse-aware fast convolution 原文整组保存在 groupMentions，不拆造省略文字，也不进入本阶段训练。Current Transformers 的电气设备语境不误标为神经网络方法；模型生成输入、受保护对象和下游受益者的角色不倒置成直接 USED_FOR。

领域与角色边界案例继续保留：反应—扩散方程中的分离变量、积分分岔按实际数学方法/求解任务记录，不把物理扩散叫作生成式 AI；本轮 social influence diffusion 也不是生成式图像模型。人工智能题名规则可能误收非 AI 文献，不能宣称所有候选都是 AI 论文。本轮 smart transformer 是电气设备，CIMGN 是芯片处理器，不误标为算法；Gaofen、Himawari-8 是卫星来源，YouTube 是平台，不当命名数据集。显式称为 Software 的 PyTorch Geometric Signed Directed 不当算法或数据集；Flower、Hetu v2、ClioPatria 等软件工具不自动当模型。ELF-Gym、ESC-Eval、MATA、nuScenes Knowledge Graph 与 dblp Knowledge Graph 的资源角色有不明之处，保留未决，不凑 DATASET 支持数。数据增强、coresets、次级扩散模型可能提供训练材料，不自动推出它们就是检测器、分割器或识别器。

该历史版本的交付与来源：

- [累计导出进度](../kg_datasets/dblp/course_v4_training_inputs_06/summary.json)
- [累计初次快照及复核凭据](../kg_datasets/dblp/course_v4_training_inputs_06/receipts.jsonl)
- [1392 条待首轮匿名输入](../kg_datasets/dblp/course_v4_training_inputs_06/pending_generation.jsonl)
- [最新导出哈希清单](../kg_datasets/dblp/course_v4_training_inputs_06/manifest.json)
- [训练 007 首轮判断](../annotations/course_v4/batch007_generation_decisions.json)及[自复核](../annotations/course_v4/batch007_review_judgments.json)，同目录保存 008–016 各批次完整初次判断与复核文件
- [验证 070 首轮判断](../annotations/course_v4/batch070_generation_decisions.json)及[自复核](../annotations/course_v4/batch070_review_judgments.json)
- [验证 071 首轮判断](../annotations/course_v4/batch071_generation_decisions.json)及[自复核](../annotations/course_v4/batch071_review_judgments.json)
- [验证 072 首轮判断](../annotations/course_v4/batch072_generation_decisions.json)及[自复核](../annotations/course_v4/batch072_review_judgments.json)

未标注的 1392 篇仍是待首轮（train 1192、dev 0、test 200），不生成空标准答案；已首轮但未决的文本不重复回到待首轮队列。最新待首轮 ID 唯一、与累计 608 份凭据的交集为 0，字段仍仅有 sampleId/text/textSha256。按 MLE 工作流维持来源、固定划分与按任务隔离，批量扩大但未加调度框架或新依赖；脚本只复用组装步骤排除已记录的论文并导出匿名输入，没有自动补语义或自动批准复核。

此前累计 288 篇快照保存在 `course_v4_training_inputs_05`：train/dev 163/125 篇两轮判断，231 篇实体输入、213 条关系输入、1712 条待首轮。累计 188 篇快照保存在 `course_v4_training_inputs_04`：train/dev 113/75 篇两轮判断，155 篇实体输入、139 条关系输入、1812 条待首轮；累计 90 篇快照保存在 `course_v4_training_inputs_03`：76 篇实体输入、70 条关系输入、1910 条待首轮。这些历史导出以及 01/02 均未改写。

## 首批 25 篇历史快照

初次判断和第二轮自复核均由当前 Codex 会话 AI 完成，来源为 `codex_session / unknown_session_model`。第二轮看到了初次候选：不是独立盲审、独立模型验证或真人 gold。编译与导入脚本没有调用外部模型，只处理实际保留下来的 AI 决定。

25 条复核中 23 条确认、2 条修订；2 条修订将有歧义的实体判断保留为未决，而非强行定类。其中一条还撤回了过于确定的关系判断，保留 UNRESOLVED。最终 6 篇实体未决、7 篇关系未决，未决不当负例。

| 训练输入 | 实际导出与类别覆盖 |
|---|---|
| NER | 19 篇；METHOD 25 个，TASK 17 个，DATASET 0 个 |
| 关系 | 18 篇满足关系导出条件，其中有实体对的文本导出共 19 条；USED_FOR 18 条、NO_RELATION 1 条、EVALUATED_ON 0 条 |
| 验证、测试 | 首批快照中各 0 篇完成两轮标注，尚不能评估 |

首批快照中，存在两轮明确检查后未发现三类实体的文本，可作为范围内负例；当时未标注的 1975 篇记作 pending，不生成空标签冒充负例。关系导出条件与实体导出条件独立，关系未决不会阻塞已完成实体样本。

实际来源与结果：

- [初次 AI 语义判断](../annotations/course_v4/batch001_generation_decisions.json)
- [AI 自复核确认与修订](../annotations/course_v4/batch001_review_judgments.json)
- [内容绑定的初次快照与复核记录](../kg_datasets/dblp/course_v4_runs/batch001_review/receipts.jsonl)
- [首批导出历史进度](../kg_datasets/dblp/course_v4_training_inputs_01/summary.json)
- [首批导出历史清单](../kg_datasets/dblp/course_v4_training_inputs_01/manifest.json)

## 验证证据

最新全项目304项通过，[08 XML](../kg_datasets/dblp/course_v4_runs/tests_20261006_round08_final.xml)与[08核对记录](../kg_datasets/dblp/course_v4_runs/verification_20261006_round08.json)保留。历史07为302项，[07 XML](../kg_datasets/dblp/course_v4_runs/tests_20261006_round07_final.xml)与[07核对记录](../kg_datasets/dblp/course_v4_runs/verification_20261006_round07.json)不覆盖。更早训练链路轮299项、六模块合并95.17%/训练入口91.55%/核心course_weak100%均仅对应当时源码，不冒称本轮覆盖率。

- [训练链路历史 pytest XML](../kg_datasets/dblp/course_v4_runs/tests_20261006_round06_verified.xml)
- [单元与真实运行合并覆盖率](../kg_datasets/dblp/course_v4_runs/coverage_ner_combined_20261006.json)
- [训练链路历史哈希及重复运行核对](../kg_datasets/dblp/course_v4_runs/verification_20261006_ner.json)：当时130 个运行目录共 720 个清单内输出、6 个累计导出、21 个原有输入均未漂移；24 篇及 120 步的梯度样本 ID 均核对为选定 train 样本。

此前回归暴露并修复了编译任务及导入初次快照时“先读文件、后记录哈希”的检查窗口：现在先记哈希、读取处理后再比较，变化时拒绝输出。首批的初次与复核响应在修复后重放，SHA-256 分别与原响应逐字一致；旧记录未改写。此前补标轮的 127 个批次/重放目录共 679 个清单内输出文件、6 个累计导出版本共 52 个文件通过哈希核对；21 个原有输入未漂移，已标注论文组跨 split 为 0。当时 278 项测试实跑 11.13 秒，失败/错误/跳过均为 0，以下是该补标轮的历史记录，不含后来新增的训练脚本与独立依赖。

- [本轮 pytest 结果 XML](../kg_datasets/dblp/course_v4_runs/tests_20261006_round05_final.xml)
- [本轮数据流程覆盖率 JSON](../kg_datasets/dblp/course_v4_runs/coverage_20261006_round05_final.json)
- [队列、文件哈希和导出计数核对](../kg_datasets/dblp/course_v4_runs/verification_20261006_round05.json)
- [复现命令与输入条件](course_v4_runbook.md)

哈希用于发现内容漂移，不认证 AI 身份、不证明语义正确，也不构成防恶意篡改签名。

## 下一步及报告表述

继续完成剩余队列的 AI 首轮判断和自复核，优先推进剩余训练数据，保持已锁定的论文组划分；验证队列已处理，未决记录不改成空负例；测试标签按既定规范一次生成、封存，不拿测试结果调参。类别不足时如实报告，必要时在固定划分内另建补充版本，不能把“ECG”“新闻语料”等普通输入材料强行改成命名数据集。DATASET/EVALUATED_ON 分别为 15/5，仍偏少；dev 的 NO_RELATION 为 5 条，仍不足保证学习效果，test 尚无标签。数据快照的 nerTrainingReady、relationTrainingReady 仍为 false；封存 trainingStarted=false 不作为实时运行状态。冒烟已经实际训练，但不能宣称正式留出评估已完成。

实体候选训练与dev选型已实际完成；下一步继续补标并封存测试参考、一次性test评估，之后训练关系模型并测端到端pipeline，最后确认目标数据库并导入模型候选/证据，实现检索应用。详见 [分阶段计划](course_v4_plan.md)。

报告可以写“已完成领域预处理、固定划分、AI弱监督标注、GPU候选模型训练与dev选型”；不能写“人工金标准”“独立双盲验证”“测试准确率100%”或“实体抽取完整实验已完成”。75.14%明确称为AI参考标签下的dev选型F1，不是test成绩。
