# V2 首批语义修订独立审核（2026-10-10）

## 结论

**结论：结构及账本一致性通过；语义审核原则上接受，5 条负例与跨粒度用途标签仍需作训练准入裁决；不能认定 training_ready。** 本审核依据用户上传的 `semantic_review.md`、`priority_adjudications.csv`、`relation_review.csv`，并与此前上传的 `references.jsonl`、`review_dossiers.jsonl` 交叉比对。未读取本地 `D:/` 项目代码、39 项测试输出或生产环境。

## 逐项复算

- 原样本：12 篇，151 个既有实体，499 个候选实体对。
- 旧标签：USED_FOR 69、EVALUATED_ON 17、NO_RELATION 16、UNRESOLVED 397。
- 新标签：USED_FOR 63、EVALUATED_ON 17、NO_RELATION 5、UNRESOLVED 414。
- 精确变更：8 个 USED_FOR→UNRESOLVED；11 个 NO_RELATION→UNRESOLVED；2 个 UNRESOLVED→USED_FOR；共 21 条变化。
- 完整性：8 篇 `complete`，4 篇 `unresolved`（2008.10400、2501.02474、2501.06756、2312.03556）。
- 准入：57 对提及级候选（43 USED_FOR、9 EVALUATED_ON、5 NO_RELATION），来自 7 篇实际含已判关系的论文；第 8 篇 2010.01057 的 66 对均未决，仅提供 NER 完整候选。
- 已准入的 57 对共使用 20 个 `supportGroup` 证据组；**证据组、提及级对与独立语义事实不是同一统计单位**。
- EVALUATED_ON 准入仅 3 篇论文；NO_RELATION 准入仅 2 篇论文。该批不足以宣称长尾关系样本支持充足。

## 独立结构检查（0 项错误）

1. 12/12 篇摘要正文与之前 `references.jsonl` 内容逐字符一致。
2. 151/151 个实体提及在正文中的 Unicode 字符偏移与字面内容相符。
3. 499/499 条新旧关系对的实体键、原标签，与之前 `review_dossiers.jsonl` 的旧候选一一对应，无遗漏/重复。
4. 21 条修改的 `labelChanged` 与 `oldLabel`、`newLabel` 一致。
5. 499 条 `candidateEligible` 与「文献实体完整且关系已判」的声明性准入规则一致；未决关系未误标为准入。
6. 所有已判关系的 `predicateEvidence` 至少是摘要原文中的准确连续文字（多片段以换行相隔）。这证明字面出处可追溯，**不证明语义关系本身必然成立**。
7. `priority_adjudications.csv` 的 12 项与全量 `relation_review.csv` 中对应条目一致。
8. 修订说明文件中逐篇正文及实体表，与之前参考文件一致。

## 待进一步裁决：按影响排序

### P0：5 条 NO_RELATION 的语义作用域

- `1903.10404`：e1/e7/e9（reinforcement learning/RL）→ e4（compress high dimensional data），共 3 条 `direct_operator_contrast`。原文区分了“负责压缩的自编码器”和“利用压缩表示训练策略的 RL”，在**直接执行压缩**的语义下可作负例；但宽泛的 USED_FOR（间接服务/用于实现）未必严格排斥该关系。
- `2503.03790`：e11（implicit learning module）→ e14（predict the 3D mesh surfaces）；e13（explicit learning module）→ e12（predict a voxel-wise intermediate surface representation），共 2 条 `direct_operator_contrast`。原文明确直接输出分工，但模块对总体 CSR 可能存在间接贡献。
- **建议**：在 V2 任务契约中明示 `USED_FOR` 是否只含“直接执行者”；若不区分，五条先作为带 `direct_operator_contrast` 的待定候选，不应不加作用域直接并入常规负样本。此项是准入风险，而不是已证实的五条错标。

### P1：METHOD 家族术语与具体实例的处理应统一

- `2107.03374`：e2 GPT → e3 Python code-writing 已撤为未决，理由是 GPT 为家族描述、能力属于 Codex。
- `1903.10404`：e3 deep neural network → e4 compress high dimensional data 仍保留正例，理由是该描述在上下文中限定自编码器实例。
- 二者并非必然矛盾：后者存在局部的 “used to compress” 限定。但建议将“局部实例描述可标注”和“泛化类别不能继承具体实例效果”写成明确规则，并在标签收据标识上下文指代范围。

### P1：背景用途与组件/代理任务的统一 RE Schema

- 新增两条 `1905.00537` pretraining / transfer learning → language understanding，证据支持背景层面方法与任务相关，但不是该篇论文自己验证的具体系统。
- `1910.12770` 的 future clip order ranking 被作为 `training_proxy`，而非未来视频预测的已实现能力；方向合理。
- `2503.03790` 的 `component_operation` 是组件的直接输出；与 `downstream_application` 不是同层级。
- **建议**：如 RE 只使用单一 `USED_FOR` 类别，至少在训练时保留 `taskRole` 并在误差分析中分层统计；如果任务规范要求的 USED_FOR 范围较窄，背景关系和代理目标应另行过滤。不要在训练代码里静默丢掉这些角色元数据。

### P1：重复提及导致独立支持被高估

- `2503.03790` 中 DDCSR → CSR 有 20 条 mention 对、只有 1 个同源证据组。
- `1606.05250` logistic regression → 两个数据集别名是一次语境下同一数据集评测，不是两次独立实验。
- `2107.03374` 三个模型各自在 HumanEval 上有分数，虽共享一个支持片段，仍为不同事实；因此也不能简单以 `supportGroup` 去重作为事实数量。
- **建议**：单独记录 `mention_pairs`、`evidence_groups`、`normalized_relation_facts` 与 `source_papers`，训练和报告不要混用。

### P2：4 篇实体未完成，隔离方案正确

- `2008.10400`：fully connected layer、rotation/translation 增强提及是否纳入 METHOD。
- `2501.02474`：deep learning methods、任务/模块粒度。
- `2501.06756`：graph resilience 等任务遗漏与粒度。
- `2312.03556`：cross-attention、identity encoder 等组件遗漏。
- 在确认完整性之前，不将这些摘要按完整 BIO 序列监督，也不将其关系对加入 V2 全文对照训练。完成后需**重新生成实体对和关系审查范围**，不能只补 BIO 边界而继续沿用旧 pair universe。

### P2：目前不能独立认定来源补证已经完成

- 本次新增上传的 3 份是审核呈现文件，不包含独立来源补证收据、新的结构化训练准入产物、39 项检查的机器输出，也不包含 V1 生产环境哈希记录。
- 前次 `references.jsonl` 中，`2010.01057` 缺少 schemaVersion、contractSha256、sourceCorpusSha256、annotationStatus；`2503.01309` 缺少 sourceCorpusSha256。本次不能从新上传的三个文件验证这些字段已经补齐；如另存了补证 receipt，建议在 V2 清单中链入路径和 SHA。

## 审核决定与下一步

1. **接受** 12 篇复核结果作为 `semantic_review_completed_with_open_issues` 的阶段性材料。
2. **暂缓** 将 5 条作用域依赖的 NO_RELATION 无差别投入普通 RE 训练；先明确 USED_FOR 直接/间接判定。
3. **保留** 四篇实体未决隔离规则；不把这批 57 个 mention 对宣称为独立、高可靠训练事实。
4. **完成** 4 篇实体完整性修正，并重新构造候选实体对（新实体可能产生新的未决对）。
5. **再锁定** 新版本训练、验证和最终盲测协议；当前材料不构成模型 F1 改善证据。

**限定语：此报告独立复现的是三个文件及上一轮样本的内容一致性和语义逻辑检查，不是 39 项原工程 CI 的重复执行，更不是独立人工金标准仲裁。**
