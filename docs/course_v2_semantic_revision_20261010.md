# V2 首批语义修订与来源补证

2026-10-10。本批按MLE工作流处理来源、错误归属和标签准入，不训练、不推理、不替换模型、图谱或应用。原始12篇档案保持不变；最终修订目录为 `kg_datasets/dblp/course_v2_semantic_revision_20261010_final`。

## 直接审核入口

- [逐篇审核包](../kg_datasets/dblp/course_v2_semantic_revision_20261010_final/semantic_review.md)：全部12篇摘要、151个现有实体提及、每个旧已判/新增关系的修订结果、谓词偏移、指代理由和实体完整性判断。
- [12项优先问题裁决CSV](../kg_datasets/dblp/course_v2_semantic_revision_20261010_final/priority_adjudications.csv)：保留你提供的原审核意见，另列实际头尾文本、新标签、理由与任务角色；不能把旧意见列当成当前新标签。
- [全部499对关系新旧对照CSV](../kg_datasets/dblp/course_v2_semantic_revision_20261010_final/relation_review.csv)：包括未决，UTF-8 BOM便于Excel打开；CSV证据字段含换行，必须用CSV解析器，不能按物理行计数。
- [完整更改账本](../kg_datasets/dblp/course_v2_semantic_revision_20261010_final/change_ledger.jsonl)：旧完整关系与证据、新关系、谓词片段、支持组及新旧收据SHA绑定。
- [修订AI收据](../kg_datasets/dblp/course_v2_semantic_revision_20261010_final/reviewed_receipts.jsonl)、[来源补证侧车](../kg_datasets/dblp/course_v2_semantic_revision_20261010_final/source_provenance_sidecars.jsonl)、[机器统计](../kg_datasets/dblp/course_v2_semantic_revision_20261010_final/summary.json)。

这是本会话AI逐篇阅读后判断和同会话自查，不是独立人工gold。外部审核文件保留原件，但不因其称为“独立核验”就宣称标签经过独立人工标注。

## 实际修订结果

| 类别 | 旧提及对 | 修订后提及对 |
|---|---:|---:|
| USED_FOR | 69 | 63 |
| EVALUATED_ON | 17 | 17 |
| NO_RELATION | 16 | 5 |
| UNRESOLVED | 397 | 414 |

102条旧已判全部有明确保留或撤回裁决；19条撤回为未决，原397条未决中2条得到直接背景用途证据，其余保持未决，总数仍499。没有把未知当负例，也没有新采集论文。优先队列12项中5项改标签、7项维持旧标签；维持也有本批原文理由，不是自动继承。

主要裁决：

- Codex泛称GPT不独立继承Python专门能力；“distinct production version”所指Codex不自动等同研究版，撤回其3条旧任务边。最后的广义影响讨论不单独认证任务谓词。
- repeated sampling有自己的70.2%结果及“this method/our problems”指代链，保留HumanEval关系；这不是让所有组件继承总体成绩。原文数值是论文报告，不是我们复现实验。
- deep neural network后面有明确“used to compress”定义，保留它对当前autoencoder实例的局部用途，不能宣传为全部深度网络的普遍事实。
- Skip-Clip的ranking保留为 `training_proxy`，不当作下游应用；“video future prediction”目标没有直接执行证据，撤回3条用途。ImageNet只作对比初始化不证明否定评测，撤回3条负例。CSV实际e2为self-supervised representation learning，已另列真实文本。
- VFM输入掩码与后续组件不同不充分证明否定能力，撤回6条负例；总体模型ScanNet/SceneNN评测仍不分派给组件。
- DDCSR编号组件明确分配中间／最终输出，保留2条直接操作角色反例。这是本契约的局部角色对比，**不是显式全球能力否定**；若后续改为“只有not/without等明示否定才标负例”的任务，必须重新隔离，不直接复用。
- SuperGLUE开头明确说明pretraining/transfer learning改善language understanding，新增2条 `background_method_use`。它们不是本文被测模型的实验关系，也不推出GLUE/SuperGLUE评测边。

全部85条已判候选另存精确谓词片段，本批最长244字符。原完整证据没有删除；新连续证据仍覆盖实体，必要指代说明另存，不把缩短字符数当语义可靠性证明。不同提及、不同字面组合、不同支持组、不同论文是不同计数口径。DDCSR的22条用途仍只有4种字面组合；20条DDCSR—CSR别名提及对共用一个源内支持组。

## NER完整性隔离与真实候选支持

151个已有实体提及都检查了原文、边界和类别，但“现有提及正确”不证明“原文所有实体都标全”。4篇存在具体遗漏或粒度待裁决，因此不准入完整BIO训练，也不输出为整篇已认证标签：

| 论文 | 尚需裁决 |
|---|---|
| 2008.10400 | fully connected layer、Rotation、translation等架构／增广方法遗漏候选 |
| 2501.02474 | deep learning methods及组件特征／proposal目标的粒度和完整性 |
| 2501.06756 | graph resilience操作目标、experience feedback机制等边界；Fiedler value不能自动当方法 |
| 2312.03556 | cross-attention、identity encoder等组件提及的粒度和遗漏 |

其余8篇按本次任务规范作AI完整性判断，保留90个已有实体。它们中57对关系具备候选导出条件：USED_FOR43、EVALUATED_ON9、NO_RELATION5。**57不是新增57个独立事实，也不是已执行训练准入。**4篇隔离中的28个已判候选仍保留待审，但不混入此57。

稀有类仍薄弱：可候选评测边9条只来自3篇，角色反例5条只来自2篇；统计不能证明泛化。其余414对未决保持掩码。仅凭本批定向12篇不能构成代表性最终测试。

## 来源补证

OnlineAnySeg与LUKE均找到对应历史采集请求、原始HTML、采集manifest和采集契约。重新解析原始citation metadata，核对arXiv身份及完整摘要，文本和SHA与引用完全一致。

旧采集器没有发出的schemaVersion/contractSha256/sourceCorpusSha256/annotationStatus字段仍保持缺失；侧车显式null并解释。不把采集manifest的SHA冒充sourceCorpusSha256，也不把采集契约版本当作原始标注schema。两份页面citation_arxiv_id未带版本后缀；本批锁定的是历史响应字节、采集时间与身份，不能据此猜出arXiv的具体v号。

## 验证与留痕

- [生成脚本](../scripts/review_v2_evidence_pilot.py)、[固定修订契约](../resources/course_v2_semantic_revision_v1.json)、[人工可读决策文件](../annotations/course_v4/v2_pilot_semantic_decisions_20261010.json)、[同会话自查文件](../annotations/course_v4/v2_pilot_semantic_reviews_20261010.json)。
- [39项最终相关检查](../outputs/v2_semantic_revision_final_20261010.xml)：23项本批检查＋16项准备检查，不累加重跑次数。包括12篇绑定、错误来源哈希、伪证据、非法方向、负例依据、完整旧已判覆盖、角色回归、原始页面补证、真实生成及CSV绑定、输出防覆盖。
- 第一次完整生成的JSONL读取白名单只包含首批refs、旧收据和论文组身份元数据3份；不解析dev/test正文。最后版本相同读取路径也由生成集成测试覆盖。保留test仅二进制SHA核对，不宣称正文近重复已排除。
- 6个V1保护文件、首批所有受绑定文件未变；首批身份冲突0。代码、决策、审核输入、采集页面和输出由最终manifest绑定。
- [真实结果页面截图](../kg_datasets/dblp/course_v2_semantic_revision_20261010_final/09_annotation_expansion.png)、[截图收据](../kg_datasets/dblp/course_v2_semantic_revision_20261010_final/captures.json)。这是已保存数据的浏览器渲染，不是GPU训练或Neo4j UI画面；截图已目视核对。
- [失败与修复记录](../outputs/v2_semantic_revision_failures_20261010.json)：首次pytest缺scripts导入路径导致收集失败；已按仓库既有模式修复。初次生成清单缺kind字段，截图脚本正确拒绝；修复生成端并增加测试，保留初次数据产物，在 `_final` 新目录重建，不覆盖失败记录。

未运行整个仓库测试套件、独立人工标注或新模型测试；39工程检查不证明85条候选语义正确率。

## 当前停止点与下一批

当前 `semantic_review_complete_with_entity_coverage_quarantines_not_training_ready`：完成本批既有提及与旧已判的AI语义修订，**没有完成全12篇完整NER标签验收，也没有训练许可**。

下一批限定这4篇遗漏／粒度裁决，保留现有修订版不变，另建完整性修订；随后锁训练、验证及最终测试与选型条件。不新增论文、不扩大图、不追加旧测试调参。此文是工程留痕，不是课程最终报告。
