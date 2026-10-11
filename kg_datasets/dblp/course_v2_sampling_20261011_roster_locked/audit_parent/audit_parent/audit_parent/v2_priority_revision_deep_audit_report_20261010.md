# V2 优先语义修订：独立深度审核报告

审核日期：2026-10-10  
审核对象：`v2_priority_revision_audit_20261010.zip` 与 `course_v2_priority_revision_20261010.md`  
审核范围：**离线文件结构与导出守恒、变更账本、指定新增关系的语义、共指证据的可解释性、训练准入条件**。不包含生产实例登录、模型训练、完整仓库重建或人工金标准验证。

## 总体判定

- **数据工程/可重放约束：通过。** 在独立工作目录运行 `python -I source_snapshot/scripts/verify_v2_priority_bundle.py .`，返回 `status=passed`，61 个类别的约束断言通过。这是工程约束，不能当作语义正确率。
- **本轮 5 条正关系新增：有条件接受，未发现必须撤回的明确错误。** 它们分别代表训练操作、背景方法用途、组件操作、研究目标；应持续保留 `taskRole` 与 `taskSubRole` 审计信息。
- **3 条共指证据补充：形式校验通过，但推断强度需显式分层。** SQuAD 的模型成绩归属和 Codex 的 HumanEval 归属属于可辩护的语篇解释，不是所有端点/关系都在一个局部句子中直接出现。
- **普通 RE 三分类训练：暂不准入。** 可导出的 `NO_RELATION=0`，599→594 的未决收缩没有改变这一事实；V2 完整新评测与模型选型协议尚未固定。

## 1. 独立计算与文件约束

| 指标 | 上版 | 本版 | 核对 |
|---|---:|---:|---|
| 论文、实体、候选对 | 12/177/684 | 12/177/684 | 一致 |
| USED_FOR | 63 | 68 | +5 |
| EVALUATED_ON | 17 | 17 | 不变 |
| NO_RELATION | 5 | 5 | 均隔离 |
| UNRESOLVED | 599 | 594 | -5 |
| 正例候选导出 | 80 | 85 | +5 |
| 正例来源论文（并集） | 11 | 11 | 已修正旧版误写 |
| 支持组 | 25 | 29 | +4，不是+5 |
| 大小写敏感字面组合 | 50 | 55 | +5 |
| 忽略大小写字面组合 | 49 | 54 | +5 |

- 逐项核对本版 `relation_ledger.jsonl` 与 `audit_parent/relation_ledger.jsonl`：标签变化限于预定义的 **5 对**。共 **3 对**仅增加共指支持元数据；共 8 对涉及标签或支持变更。
- 5 条新正例证据偏移均匹配摘要；均在合法 `METHOD → TASK` 范围内，且有审核角色。
- 所有 85 条正例导出 `trainingAuthorized=false`；所有 5 条 `NO_RELATION` 均未进入正例导出、也未被冒充普通负例；594 条未决未转负例。
- `check_history/priority_checks.xml` 标记 98 tests、0 failures、0 errors、0 skipped，属于打包的历史测试结果；**未在此容器中重跑这套依赖仓库的 pytest**。
- 离线校验只保证 ZIP 内数据与其中的哈希及来源约束自洽；不能独立确认线上模型、Neo4j、V1 文件即时状态。包内的保护记录与其父版相同，但不是对线上状态的新测量。

## 2. 五条新增关系逐项裁决

| arXiv | 关系 | 独立语义意见 | 限定条件 |
|---|---|---|---|
| `2008.10400` | `e11 Rotation → e13 augment training data` | **接受** | 文中明确用 Rotation 与 translation 增广训练数据；两条共享一组证据，不构成两个独立实验 |
| `2008.10400` | `e12 translation → e13 augment training data` | **接受** | `training_proxy` + `training_augmentation` 合理；不推断 MNIST 评测关系 |
| `2501.02474` | `e3 deep learning → e4 remote sensing object detection` | **有条件接受** | 原文直接表明背景深度学习方法在该任务上取得成功；这是广义背景方法，不是 GE-FSOD 特定成果 |
| `2501.06756` | `e10 diffusion process → e11 generate optimal sensor placement strategies` | **接受** | 句中 `utilizes a diffusion process to generate` 支持组件用途；不继承整体算法的其他任务和效果 |
| `2312.03556` | `e24 PVA → e25 identity preservation` | **接受，保留宽口径 TASK 说明** | `ensures good identity preservation` 明确支持源文作者宣称的方法目标，不证明实际效果优秀 |

此外，对照了对应论文的 arXiv 摘要页：
- https://arxiv.org/abs/2008.10400
- https://arxiv.org/abs/2501.02474
- https://arxiv.org/abs/2501.06756
- https://arxiv.org/abs/2312.03556

## 3. 共指补证逐项审核

### `1606.05250`：`logistic regression → Stanford Question Answering Dataset / SQuAD`

- 两个别名对应同一个基准事实，不是独立的两项评测。
- `which achieves an F1 score of 51.0%` 的语法先行词确为 logistic regression model；数据集语境通过前文介绍的 SQuAD 与 `the dataset` 延续。
- **中等语义风险：** 原文没有在模型成绩句写出“on SQuAD”，归属需要依赖摘要上下文；目前的解释是合理推断，不能描述为显式局部评测谓词。

### `2107.03374`：`repeated sampling → HumanEval`

- `this method` 的先行内容是 repeated sampling，语法关联清楚。
- `our problems` 对 HumanEval 的指代符合前文 benchmark 语境，但仍属语篇解析判断；如将来使用严格句内显式证据标准，应单独设定 `context_inferred` 而非悄悄视为 direct。
- 现有说明正确阻止将该结果归属于生产版本 Codex 或泛化 GPT 方法类别。

### 结构粒度问题（建议修正，不阻断现阶段封存）

目前 `coreferenceEvidence[].anaphorSpan` / `antecedentSpan` 多采用**整个句子**，而不只是实际回指词或实体，例如：
- SQuAD 的 `anaphorSpan` 长 147 字符，实际触发词是 `the dataset`；`antecedentSpan` 长 277 字符，实际实体为 SQuAD。
- HumanEval 的 `anaphorSpan` 长 79 字符；同一句里有 `this method` 与 `our problems` 两种不同的回指。

这些跨度在字面上正确，却缺少精细的 `triggerSpan` 与 `resolvedEntitySpan`。建议将整句保留为 `contextSpan`，另记录最小触发跨度、目标实体 ID 和推断层级 `direct / alias / discourse_inferred`，以免后续统计或自动校验把“句子存在”误作“共指正确”。

## 4. 容易被整体计数掩盖的训练风险

### P0：仍然没有可用的训练负例

- `684` 个候选中 `594` 个为 `UNRESOLVED`（86.84%），`5` 个旧 `NO_RELATION` 仍争议隔离（0.73%），只有 `85` 个正例获准候选导出（12.43%）。
- 在现有三分类 `USED_FOR / EVALUATED_ON / NO_RELATION` 设置下，若直接把这 85 对作为普通监督训练数据，模型几乎不能学习何时拒绝关系。**没有充分负例是训练准入阻断项，而非格式问题。**
- 不能将未决强行降为负例；应先固定完整 `NO_RELATION` 语义（否定用途 vs 缺少语句证据），只对明确可判的候选进行标注，或单独研究部分标注/正未标注训练方案。

### P1：正例高度相关，不能按 85 项独立样本宣传

- `85` 个提及级正例只有 `29` 个证据支持组，覆盖 `11` 篇不同论文。
- `2503.03790:g1` 的 DDCSR→CSR 占 `20` 个提及对；`2501.02474:g1` 的 GE-FSOD→FSOD 占 `10` 对，仅两个证据组就占 30/85（35.29%）。
- 下一阶段应先在**论文组层面分割训练/验证/测试**，再在训练中控制同一 `supportGroup` 过度重复；报告提及级与支持组级结果，避免虚假的样本独立性与跨拆分泄漏。

### P1：USED_FOR 采用宽口径，须统一评测责任

当前模型标签同时容纳 `background_method_use`、`training_proxy`、`component_operation`、`downstream_application`。符合本轮契约，但它们并非同一种严苛程度的学术事实。需在标注和错误分析时保留角色分层，尤其区分“该论文主模型用途”和“背景知识里的方法用途”。不要把审核用角色字段作为预测阶段的外生 oracle 特征。

### P2：`coreferenceEvidence` 可改为双层跨度

保留整句来源证据，新增小跨度触发词、明确的 referent、指代类型、基于句内/跨句/语篇推断的证据级别。对此轮 3 条已补证关系做增强即可，不必回滚已有关系或反复重审全部材料。

## 5. 源码与重放能力界限

- 受控快照 `train_course_relation.py` 中 `encode_pair` 将实体标记插入原摘要，读入的模型输入主要为 `text/head/tail` 位置与训练标签；`taskRole/coreferenceEvidence` 并未直接拼进特征。**该静态源码支持“审核元数据不直接成为模型输入”的设计，但本审计未在真实 SciBERT 权重上重跑模型特征测试。**
- 便携校验器确实核查实体偏移、收据关系、候选全集、变化白名单与导出授权标志；它无法通过摘要字面跨度判断科研语义是否成立。
- 98 项测试 XML 从包内读取，记录为通过；此前失败和缺失 JUnit 的生成问题有所留痕，不应把历史修复当新模型表现提升。

## 6. 建议下一批的明确准入条件

1. **先处理 NO_RELATION 作用域与明确负例来源**。统一否定的是“在给定证据范围内无该关系”，还是“明确属于不同职责/非直接执行者”。对 5 条争议负例按统一关系定义复核，不能为凑数强制转正或转负。
2. **保留五条本次正例**，不用重跑本批。优先提升具有不同论文来源、不同谓词表达、不同主体的监督支持，而不是增加同一支持组的别名组合。
3. **给 3 个共指提及对补最小触发跨度与推断强度**。SQuAD 两个别名共用同一事实链；HumanEval 的两个回指分开表示。
4. **锁未来的独立数据拆分**：按 publication/group 去重，暴露的 12 篇仅用于 train-side；代表性评测与稀有类别挑战集分开，新最终测试保持盲测。
5. 所有 V2 导出在新协议签署前继续 `trainingAuthorized=false`。不得把本轮 85 条候选作为正式三分类训练已准备好的证明。

## 最终结论

**“优先语义裁决与证据链补充”这一工作包：有条件通过。** 五条新增正例的语义可接受，变更与来源在当前提供的审计包中自洽；没有证据显示旧 V1 模型或测试成绩在本包中被改写。**“V2 模型训练准入”：不通过。** 主阻断项仍是统一关系定义下可用的显式负例为零，新的独立评测与模型选择方案未冻结。

请勿把“61 类离线断言通过”“98 个历史测试记录通过”或“85 条正例候选”解读为模型准确率、独立语义金标准或生产无回归证明。
