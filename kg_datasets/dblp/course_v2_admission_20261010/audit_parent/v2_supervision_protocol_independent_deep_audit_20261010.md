# V2 监督协议：独立深度审计报告（2026-10-10）

## 审计范围与方法

材料：`v2_supervision_protocol_audit_20261010.zip`、`course_v2_supervision_protocol_20261010.md`、`protocol_review.csv`。
将 ZIP 解压至独立目录，执行原包只读校验程序：

```bash
cd course_v2_supervision_protocol_20261010
python -I source_snapshot/scripts/finalize_v2_supervision.py --verify .
```

实际返回 `status=passed`、`assertionCategories=94`、`RECandidatePairs=85`、`acceptedNegativePairs=0`、`evaluationInventoryLocked=false`。解析打包的 JUnit：最终 132 tests / 0 failures / 0 errors / 0 skips；历史预检 33 tests / 1 failure / 0 errors / 0 skips。外部上传的 `protocol_review.csv` 与 ZIP 内同名 CSV 字节完全一致。注意：94 类是数据约束，不是 94 项语义审计；132 项是打包的项目侧测试结果，外部只复跑了便携数据校验而未重跑完整仓库 pytest。

## 1. 通过项（本次独立重算）

- 12 篇、177 个实体、684 个候选关系保持；`USED_FOR=68`、`EVALUATED_ON=17`、`NO_RELATION=0`、`UNRESOLVED=599`。
- 相比父版，仅 5 条原 `NO_RELATION` 标签变为 `UNRESOLVED`，支持字段变化恰为 8 条（上述 5 条加 3 条共指补证）；其余关系标签无变化。父版 684 个键和本版 684 个键逐一相同。
- 85 条正例候选全部来自 11 篇论文，共 29 个支持组；`trainingAuthorized=false`。没有把 599 条未决转成负例。前两个支持组贡献 20+10=30 条提及级正例，占 85 条的约 35.3%。
- 3 条补证提及对的文本跨度匹配原摘要：`1606.05250` 中 `the dataset`、`which`；`2107.03374` 中 `this method`、`our problems`。`which` 的句内模型归属标 `direct`，关系整体仍标 `discourse_inferred`，这是恰当的区分；SQuAD 全称和缩写共享事实链。
- 5 条旧的“不同直接执行者”反例撤回合理：在当前允许背景用途、代理目标、组件操作和下游应用的宽范围关系契约下，不能仅凭直接执行者不同就证明宽口径 `NO_RELATION`。
- 12 篇被锁为 train-only；新验证、最终测试、挑战集均无成员，`evaluationInventoryLocked=false`，并未冒充新盲测结果。

## 2. 确定性的程序缺陷：未来评测隔离可以绕过（P0，需在采集评测成员前修复）

### 缺陷 A：arXiv 前缀大小写规范化不一致

文件：`source_snapshot/scripts/finalize_v2_supervision.py`，`identity()`：

```python
re.sub(r'v\d+$', '', row['arxivId'].strip().removeprefix('arxiv:'), flags=re.IGNORECASE)
```

`removeprefix` 区分大小写。用历史排除 `arxivId=2107.03374`，新测试候选 `arxivId=arXiv:2107.03374v2`，且其他身份键取不同值，实际 `validate_partition()` **错误接受**新候选，返回 `{'test': 1}`。全大写 `ARXIV:` 也能绕过；小写 `arxiv:` 对照被正确拒绝。

### 缺陷 B：DBLP arXiv 论文 ID 与 arXiv ID 没有跨来源归一

历史排除列表 20,000 条 `historical_corpus` 记录只有 publication/group 元数据，没有 arXiv ID 或文本哈希；其中 5,253 条 publication ID 包含 `corr/abs-` 或 `arxiv` 特征。

取实际排除记录 `publicationId=journals/corr/abs-1708-00052`，新测试候选 `arxivId=1708.00052`、`publicationId=arxiv:1708.00052`，并赋不同 group/text 值，实际 `validate_partition()` **错误接受**该候选。两个标识代表同一 arXiv 论文，但当前算法只比较相同字段的字符串。

建议：增加统一的 `canonicalPaperId` / `canonicalArxivId` 提取函数，把 `arxiv:YYMM.NNNNNvN`、`arXiv:...`、`journals/corr/abs-YYMM-NNNNN`、arXiv URL 等转成规范 ID；构建跨来源别名索引，避免只靠 publication/group/text 哈希的字面相等。对没有可靠规范化身份的候选应拒绝进入独立测试直至人工核验。应测试两种漏洞回归、不同版本、大小写、连字符、URL、缺失字段及真正全新论文放行。

**影响边界**：新验证/测试目前为空，因此这两处漏洞不证明已经发生泄漏；但原有“排除历史身份”自动检查不足以保证未来入选阶段正确隔离。

## 3. 协议和标注层面的未解决阻断

### 3.1 普通三分类关系模型不具备训练条件（P0，属于已披露的状态，不是新程序回归）

导出的 85 条都是 `USED_FOR` / `EVALUATED_ON` 正例，可用 `NO_RELATION=0`；其余 599 对没有被语义认证，不应自动转负。在保留普通三分类 RE 模型的前提下，当前数据不能训练出可靠的无关系边界。严格的“原文明确否定或排他”规则与宽口径 `USED_FOR` 定义自洽，但在一般学术摘要中可能极难收集丰富的负例；应在下一阶段预先决定采用可认证负例的判定与抽样方案，或修改学习目标为适当的部分标注/正例未标注范式。**不要把无证据等同于明确否定，也不要临时改变标签口径以凑数。**

### 3.2 评测协议冻结不等于评测样本封存（P0/阶段性）

`protocolFrozen=true`，但 `evaluationInventoryLocked=false`，验证、测试、challenge 分别是空列表。具体新论文总体、抽样种子、样本量、身份清单尚未生成，所以当前只能验“制度”，不能验未来的代表性、类覆盖、盲测可靠性。需要等身份标准化修复后锁定总体和成员，再读取原文与开始标注/模型选型。

### 3.3 过于集中且高度相关的正例（P1）

85 个提及级正例只有 29 个支持组、11 篇来源论文。仅两个支持组占 30/85。当前协议按同一论文/支持组每轮只抽一个提及对，是合适的未来控制措施，但还没执行；按论文级划分、防别名权重放大和逐源统计仍不可省略。

### 3.4 评测门槛将来要避免不可判定（P1）

协议要求新模型端到端验证 F1 提升 ≥0.02、逐类 TP 不下降、负例 FP 不上升。这个门槛可作为工程性筛选，但在稀有类别样本很少、验证集含 0 条有证据负例、或类别基数不同的情况下，逐类 TP/FP 条件可能不可判定或过度依赖单例。应提前规定何为可比较样本、缺少该类参考时记 `not_evaluable` 而非默认“通过”，并保存原始 TP/FP/FN 与覆盖率。验证 F1 变化不是统计显著性证明。

### 3.5 共指链不是独立人工语义认证（P1，已正确标示限制）

`which` 的模型指代相对直接；`the dataset → SQuAD`、`our problems → HumanEval`、`this method → repeated sampling` 属跨句语义解释。校验程序仅能确认字面跨度、实体 ID 和证据字段的内部一致性，不能证实跨句指代唯一正确。已保存 `discourse_inferred` 标签，不应改成 `direct`，也不宜把两个 SQuAD 提及对计作两个独立实验证据。

## 4. 下一阶段的封闭修复清单

1. **首先修复身份校验器**（大小写、DBLP/arXiv跨来源转换、缺失身份拒绝、输入规范）；将本报告两条真实绕过构造成必须拒绝的单元测试，并以实际历史排除清单做规范化覆盖率统计。
2. 保持 5 条负例撤回与 599 未决掩码不变。对有明示证据的负例进行独立复核；如始终缺少足够负例，就明确宣布普通 RE 三分类训练暂不启动，另行设计经批准的监督范式。
3. 身份检查修复后，**再**锁定新验证/最终测试/长尾 challenge 的成员、随机种子、样本量与采样框。代表性评测与稀有挑战分开报告，最终测试在模型冻结前保持不可见。
4. 新增分类评测检查：某类无正例、无明确负例或评测参考不完整时报告不可评分状态、覆盖率、排除原因；不能用总体 F1 替代稀有类别证据。
5. 只在前置条件全部满足时，以单独授权快照训练；本轮不修改 V1 生产系统。

## 5. 结论

**本次数据迁移、保守负例撤回、双层共指表达与训练禁用状态可接受。** ZIP 的 94 类数据约束确实通过，项目侧 132 项 JUnit 记录也为全通过。但隔离协议存在两处由实际构造反例证明的身份规范化缺陷，因此**不能将本版视为“新独立评测集划分器已验证可用”**。此外当前接受负例为零，新评测样本尚未锁定：保持 `not_training_ready` 是正确决策。

本审计仅检验用户提供的离线文件与代码副本。没有连接运行中的 Neo4j、没有操作生产权重、没有重跑 GPU 训练、没有人工金标准语义标注；因此不能认证在线状态或模型准确率。
