# V2 第一批独立数据核验报告

核验对象：`course_v2_evidence_pilot_20261010.md`、`references.jsonl`、`review_dossiers.jsonl`。仅审核上传文件；原始仓库、训练文件、原始收据和外部 SHA 锁清单未作为输入。

## 结论

**可进入逐篇语义复核（prepared_not_training_ready），不可直接准入新训练。** 12篇档案的结构、实体原文偏移和引用关系均通过独立脚本检查。语义关系仍为旧 AI 标签，存在特定角色、关系归属和负例界限值得复核；无证据宣布任何预测指标改善。

## 独立程序检查

- 两个 JSONL 文件各 12 行，解析全部成功；12 个 sampleId、publicationId、groupId、arxivId、textSha256 均唯一，两个文件的对应 reference 内容逐字段完全一致。
- 12/12 摘要的 UTF-8 SHA-256 与 textSha256 匹配。
- 151/151 实体的 [start,end) Unicode 字符偏移与原文子串匹配；无实体 ID 重复、原文跨度重叠。
- 499/499 对的头尾 ID、mention 复制、关系方向与实体类别均通过；候选对与每篇 METHOD × (TASK + DATASET) 笛卡尔积一一对应，无漏对、无重复 ID 组合。
- 所有非 UNRESOLVED 关系具有 evidence，其 evidence 的原文 offset 都精确对应摘要原文，且覆盖两个实体原文提及；397 条 UNRESOLVED 都未伪造 evidence。
- 12 篇均为 train/abstract，reviewStatus=pending_source_semantics，trainingAdmitted=false。

## 数量复算

- 论文：12；实体：151（METHOD 79，TASK 52，DATASET 20）。
- 候选对：499；旧已判 102（USED_FOR 69，EVALUATED_ON 17，NO_RELATION 16）；UNRESOLVED 397（79.56%）。
- 102 条旧已判的证据范围中，58 条长于 400 字符；这不是 offset 错误，但证据往往过长，不利于人工确认最小支持语句。

| 行号 | arXiv | 分层 | 实体 | USED_FOR | EVALUATED_ON | NO_RELATION | UNRESOLVED | 准入 |
|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 | 2008.10400 | evaluation_positive | 8 | 0 | 4 | 0 | 8 | 否 |
| 2 | 2501.02474 | evaluation_positive | 21 | 10 | 4 | 0 | 96 | 否 |
| 3 | 2107.03374 | evaluation_positive | 10 | 10 | 4 | 0 | 10 | 否 |
| 4 | 1606.05250 | evaluation_positive | 4 | 1 | 2 | 0 | 0 | 否 |
| 5 | 2501.06756 | explicit_negative | 14 | 8 | 0 | 2 | 30 | 否 |
| 6 | 1903.10404 | explicit_negative | 10 | 5 | 0 | 3 | 1 | 否 |
| 7 | 2503.03790 | explicit_negative | 17 | 22 | 0 | 2 | 48 | 否 |
| 8 | 1910.12770 | explicit_negative | 9 | 9 | 3 | 3 | 5 | 否 |
| 9 | 1905.00537 | dataset_unresolved | 8 | 0 | 0 | 0 | 12 | 否 |
| 10 | 2312.03556 | dataset_unresolved | 18 | 2 | 0 | 0 | 75 | 否 |
| 11 | 2503.01309 | dataset_unresolved | 15 | 2 | 0 | 6 | 46 | 否 |
| 12 | 2010.01057 | dataset_unresolved | 17 | 0 | 0 | 0 | 66 | 否 |

## 发现与建议

1. **元数据不齐。** 第 12 行 `2010.01057` 缺少 schemaVersion、contractSha256、sourceCorpusSha256、annotationStatus；第 11 行 `2503.01309` 缺少 sourceCorpusSha256。需从原始侧车清单补证；若无法追溯，不可填写臆测值。
2. **证据范围偏宽。** 58/102 已判关系的 evidence 超过 400 字符。建议另存更短的最小支持句及指代链，不覆盖原偏移/旧证据。
3. **实体提及重复不等于独立论文证据。** 例如 `2503.03790` 的 22 条 USED_FOR 仅来自 4 种不同的字面头尾组合；应按提及级与规范实体/论文级分别计数，避免分配权重时把重复别名当独立样本。
4. **优先人工/独立复核的语义边界。** 见 `v2_semantic_review_queue.csv`，其中只是核验候选（未宣布已确认错误）：`2107.03374` 泛称 GPT、推断策略；`1903.10404` 类别词 deep neural network；`1910.12770` 代理训练目标与 USED_FOR 方向；`2503.01309` 直接执行者与 NO_RELATION 范围。
5. **保持未决。** `2312.03556` 的 CelebAHQ-IDI 在摘要明确是训练数据，不能自动推出 EVALUATED_ON；`2503.01309`/`2010.01057` 的总体模型评测不能直接赋给组件标签。

## 尚不能核实

- 缺少原始训练/验证/测试元数据，因此不能独立重跑论文组隔离、近重复排除或“只读训练白名单”的检查。
- 缺少 upstreamReceipt 原文件、契约 JSON、源 manifest、生产文件、JUnit XML 和首次失败收据，因此不能验证这些被引用文件的哈希和检查结果。
- 文档声称 65 篇摘要、787 实体与总计 2,357 对等历史库存，上传文件只包含其中 12 篇；这部分只能列为来源报告，不能独立重算。
- 原文自洽性和部分 arXiv 页面可抽查，但还需要按具体版本追溯全量收集链与出版身份。

## 建议验收门槛

修复或解释元数据缺失；逐篇复核 12 篇实体边界/类别/文献角色及候选关系；给定最小证据与实体指代规则；生成有修订记录的 V2 收据；完整重跑 offset/schema/训练集隔离检查；仍保留未决为未决，且独立确定验证和最终测试方案。期间不修改 V1 生产文件。
