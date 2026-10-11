# V2 实体补标与关系重建——独立深度审核（2026-10-10）

## 审核范围与结论

审核输入：`v2_entity_completion_audit_20261010.zip`、`course_v2_entity_completion_20261010.md`，并以打包的父版账本、两份 arXiv 网页、正式版数据及前一轮语义修订记录为交叉基准。核验方式：独立执行 ZIP 完整性、SHA-256、JSONL 解析、Unicode 字面偏移、实体 ID 迁移、旧关系保留、合法候选枚举、导出一致性和 JUnit XML 解析；对 26 个新增实体与若干易混淆关系做原文语义复核。非独立人工 gold，不复现模型训练、线上数据库或未打包的训练/测试分组。

**总体意见：工程重建通过；有 1 处已确认的来源篇数统计错误；没有发现旧关系在迁移时发生串接、改写或自动把未决关系转负例；实体标注与语义作用域仍有少数策略性争议。状态应继续保持 `entity_completion_and_role_export_done_negative_scope_pending_not_training_ready`。**

## A. 可独立复现的结果

| 项目 | 独立复算 | 判断 |
|---|---:|---|
| 压缩包 ZIP 完整性 | `testzip()` 无坏成员 | 通过 |
| manifest 内 SHA-256 | 33/33 个文件匹配 | 通过；manifest 自身未包含自己的哈希 |
| 论文与 NER/收据 | 各 12 篇；同一批 arXiv ID | 通过 |
| 实体 | 177 = METHOD 99、TASK 58、DATASET 20 | 通过 |
| 新增实体 | 26 = 10 + 1 + 5 + 10 | 通过 |
| 字面 offset、ID | 177/177 文本切片相等；连续 ID；无重叠 | 通过 |
| 旧实体迁移 | 151/151 字面四元组锚点可映射 | 通过 |
| METHOD × (TASK+DATASET) 全部候选 | 684；每篇与实体笛卡尔枚举一致 | 通过 |
| 父版旧候选 | 499/499，按旧实体 ID 定位完全相符 | 通过 |
| 新增候选 | 185/185 为 `UNRESOLVED` | 通过 |
| 关系标签 | USED_FOR 63、EVALUATED_ON 17、NO_RELATION 5、UNRESOLVED 599 | 通过 |
| RE 正例导出 | 80，均与账本的 `candidateEligible=true` 一一相同 | 通过 |
| 负例隔离 | 5 条 NO_RELATION 均不进入 RE 导出 | 通过 |
| 训练授权 | NER 12 行与 RE 80 行均为 `trainingAuthorized=false` | 通过 |
| 角色标签 | 下游54、组件4、训练代理3、背景2、评测不适用17 | 通过 |
| 正例证据分组 | 25（用途17、评测8） | 通过 |
| JUnit 报告 | 71=本批32+上一批23+初批16；XML中失败/错误均0 | **报告本身一致**，不是独立运行源码 |
| 既有生产资产 | 有六条 `production_protection.json` 哈希记录 | 外部没有对应生产文件，**无法重新读取生产文件验证** |

### 唯一确认的数值错误

交付说明第47行写“80对来自10篇有正例论文”，实际上：`re_candidates.jsonl` 共包含 **11 个不同 arXiv ID**；`USED_FOR` 的来源为 10 篇，`EVALUATED_ON` 来源为 5 篇，两者交集 4 篇，合并 = 11 篇。建议将报告第47行改为：**80条正例来自11篇不同论文；其中用途正例来自10篇，评测正例来自5篇**。`summary.json` 的逐类别篇数本身正确，但建议增加 `totalSourcePapersWithEligibleRE = 11` 的回归断言。

## B. 旧记录保留与迁移核验

父版 499 条 `parent_change_ledger.jsonl` 与新版 `relation_ledger.jsonl` 的 `priorHeadId/priorTailId` 一一对应。标签 `newLabel -> label` 499/499 一致；`newRelation.evidence`、理由、支持元数据与本版 499/499 一致。对应旧版的准入变化共 33 项：四篇补完文献的 28 条旧正例由不可准入变可准入；原有 5 条争议负例由准入变隔离。其余未发现无声变更。四篇取得资格的正例数分别为：2008.10400：4，2501.02474：14，2501.06756：8，2312.03556：2，总计28。

新增 185 个关系对未建立标签；这是保守防错设计，而非算法遗漏或自动语义证明。

## C. 新增实体的语义审核

- **2008.10400（+10）**：卷积层、全连接层、pooling、rotation/translation、增强操作、集成网络表达确实出现在摘要中，偏移正确。`pooling is not used` 的否定状态未被反推为正关系，做法合理。`augment training data` 标为 TASK 依赖当前契约允许研究/训练操作，建议在术语表中明确“训练数据增广操作”属于 TASK，而非仅论文的终端任务。
- **2501.02474（+1）**：背景 `deep learning` 是方法类别，但不代表 GE-FSOD 的独立组件或评测主体。新增合法；把 `multi-scale feature representation`、`region proposals` 认作结果/名词还是操作 TASK 存在粒度边界，暂不能把全文 `complete` 理解为跨规范绝对完整。
- **2501.06756（+5）**：通信韧性目标、谱韧性测量目标、diffusion process、experience feedback mechanisms、graph diffusion methods 都有字面对应；`Fiedler value` 作为指标而非 METHOD 的排除合理。注意 `diffusion process` 作为组件不自动继承 EFGD 的全部用途。
- **2312.03556（+10）**：face generative models、fine-tuning、cross-attention、denoising network、identity encoder 均有字面依据；两处独立 `inpainting` 偏移匹配。`identity preservation` 是任务目标还是效果属性，需要在当前 TASK 宽口径中明确；不能因其存在就把 `CelebAHQ-IDI` 从训练集改成评测集。

**本次对 26 处新增字面跨度没有发现明确的错字、偏移漂移或违反已给契约的确定性错误。** 但“是否应标 TASK”的边界仍属于标注策略判断，不能被偏移检查替代。

## D. 关联语义、证据与统计独立性

1. **80 条关系 ≠ 80 个独立语义事实**。它们来自11篇论文、25个来源+角色证据分组，按 `(arxivId, head字面, tail字面, label)` 去重仅49组。DDCSR一篇20条提及级用途关系共享同一证据组；GE-FSOD也有重复提及。这不是导出错误，但在训练采样、置信区间及评测拆分时必须按论文/证据组保护，不能按实体对随机打散。
2. **谓词证据不总是字面包含两端实体**。80 条中46条 `predicateSpans` 包含头尾两侧的字面，18条只包含头，16条只包含尾，34条需要别名或上下文指代连接。存在合理情形，不等于34条错误；建议对需要跳句或别名链接的标签增设 `coreferenceEvidence` 或 `antecedentSpans`，避免只显示直接谓词句却无法解释关系来源。
3. **具体示例**：`1606.05250` logistic regression → Stanford Question Answering Dataset / SQuAD 的当前证据切片主要是模型取得 F1 的句子，未显式包含数据集名称；归属依赖摘要前文唯一数据集定义。`2107.03374` repeated sampling → HumanEval 需要从前文“our problems”的指代链定位 benchmark。两项并非必然误标，但证据链应呈现先行句。
4. **新增185对中存在高优先级可复核候选**。以下目前仍正确保留为 UNRESOLVED，但摘要中存在直观用途谓词：`2008.10400 e11 Rotation → e13 augment training data`、`e12 translation → e13`；`2501.02474 e3 deep learning → e4 remote sensing object detection`（背景角色）；`2312.03556 e24 PVA → e25 identity preservation`（目标/性能边界需裁决）。`2501.06756 e10 diffusion process → e11 generate optimal sensor placement strategies` 属于组件贡献，是否满足直接归属尚需谨慎。可先复核这5条，不必审完185条才推进。
5. **负例问题未解决**。五条 source-scoped operator-role contrasts 已隔离，目前可用普通 NO_RELATION = 0。旧任务 RE 训练可能需要明确的负例监督和未决掩码，不能因为导出80条正例就声称训练集具备完整三分类训练能力。

## E. 来源与复现限制

- 两份打包原始 arXiv HTML（2010.01057 和 2503.01309）的 `citation_arxiv_id` 与 `citation_abstract` 可与对应 `references.jsonl` 原文完全比对（不仅是摘要哈希）。前述四篇补标论文的 arXiv 页面也能对上论文主题与摘要，来源身份没有明显错配。
- 旧来源元数据仍有原先的缺口：`2010.01057` 缺 `schemaVersion`、`contractSha256`、`sourceCorpusSha256`、`annotationStatus`；`2503.01309` 缺 `sourceCorpusSha256`。目前是保留缺失、不伪造，比凭空补哈希正确；独立新收据只能补充来源溯源，不等于恢复历史字段。
- 压缩包不含训练器与生成器源代码、V1 模型文件、Neo4j 实例以及真正的独立留出集。虽然 SHA 清单、71 项 JUnit 报告和运行声明一致，外部审计无法复跑测试、验明模型 feature 生成过程或证明生产环境文件未变。前期失败的 `preflight JUnit` 也未打包，因此无法独立核实首次失败轨迹。
- 全部候选均带 `ai_pseudo` 且 `trainingAuthorized=false`；既有摘要训练样本已暴露，不允许直接充作 V2 最终独立测试集。

## F. 建议修复优先级（严格限定工作量）

| 级别 | 动作 | 验收标准 |
|---|---|---|
| **P0** | 修正“80对来自10篇”→11篇，并补来源篇数测试 | summary、Markdown、测试一致 |
| **P0** | 保持5争议负例隔离，不默认 UNKNOWN 为 NO_RELATION | 普通可训练负例仍为0，直到证据型重新裁决 |
| **P1** | 按合同补 `TASK` 操作/目标/效果的边界例子，特别是 identity preservation / augment training data | 一页完整标注准则，对同类表达口径统一 |
| **P1** | 复核首批5条新候选中的直接谓词与背景/组件角色 | 有逐条证据才迁移标签，无证据保持 UNRESOLVED |
| **P1** | 为跨句共指关系补辅助证据锚点 | 不改变标签，只改审计可追溯性 |
| **P2** | 若需要外部可重放工程验收，另外提交预检历史 XML 和受控版本的运行脚本/测试脚本 | 能复跑35类守恒与防泄漏断言，不依赖线上环境 |
| **之后** | 锁定新的 V2 训练/验证/最终测试分组和负例协议，再授权训练 | 原本12篇仍只属于 TRAIN，未解决负例不能宣称完整 RE 三分类就绪 |

### 最终状态

**工程级数据补全：通过（附一个统计修正）。语义级标签认证：条件通过，仅限复核范围。新的模型训练许可：不通过，保持 `not_training_ready`。** 没有发现需要推倒重建这批数据的证据；建议先修补这次发现的统计和证据链问题，再定向扩充真正独立的正/负监督。
