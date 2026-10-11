# V2 监督作用域、精细共指与评测协议冻结

本批落实最新独立审核的三项修复：统一负例作用域、细化指定3条共指记录、冻结未来评测规则。没有扩论文、训练、模型推理或修改V1；AI判断与同会话自查仍不是独立人工金标准。本文件是工作记录，不是课程最终报告。

## 结果与状态

正式目录：`kg_datasets/dblp/course_v2_supervision_protocol_20261010`。

状态：`scope_and_evaluation_protocol_frozen_missing_negatives_and_new_evaluation_not_training_ready`。

| 项目 | 上版 | 本版 |
|---|---:|---:|
| 摘要 / 实体 / 候选全集 | 12 / 177 / 684 | 不变 |
| USED_FOR | 68 | 68 |
| EVALUATED_ON | 17 | 17 |
| NO_RELATION | 5（隔离） | 0 |
| UNRESOLVED | 594 | 599 |
| 正例候选导出 | 85 | 85 |
| 正例来源论文 / 支持组 | 11 / 29 | 不变 |
| 可用普通负例 | 0 | 0 |
| 精细共指提及对 / 共享事实链 | 无双层跨度 | 3 / 2 |
| 新验证 / 新最终测试成员 | 未锁定 | 0 / 0，仍未锁定 |

所有候选仍为 `trainingAuthorized=false`。五条旧负例撤回未决并不增加可用样本，也不代表模型准确率提高。

## 负例裁决

[作用域说明](course_v2_supervision_scope_v1.md)与[唯一机器配置](../resources/course_v2_supervision_protocol_v1.json)固定整篇原摘要中的归属关系。正例继续使用明确支持的四种用途角色，不偷偷缩成“直接执行者”。负例必须有明确否定或同一口径下的排他约束。

| 原文实体对 | 本批裁决 | 源文理由 |
|---|---|---|
| `1903.10404 e1/e7/e9 → e4`，RL → compress high dimensional data | 3条NO_RELATION撤回UNRESOLVED | 原文区分autoencoder压缩与RL使用表示，但未排除宽口径的间接用途 |
| `2503.03790 e11 → e14`，implicit module → predict the 3D mesh surfaces | 撤回UNRESOLVED | 即时输出分工不等于否定间接贡献 |
| `2503.03790 e13 → e12`，explicit module → predict a voxel-wise intermediate surface representation | 撤回UNRESOLVED | 没有对应的明确否定/排他用途证据 |

原标签、连续证据、原原因和支持在父包与新账本的 `protocolPriorLabel/Evidence/Reason/Support` 保留。当前未决的关系证据为null；旧角色反例支持保留作追溯，并有 `negativeAdjudication.decision=withdraw_to_unresolved`，不得用其旧 `negativeBasis` 绕过当前未决掩码。其他679条关系标签、证据和原因不变，包括上轮5条新增正例。

[四篇受绑定AI裁决及自查](../annotations/course_v4/v2_supervision_decisions_20261010.json)记录原文SHA、上游收据SHA、实际推理与限定条件。未从缺证、共现、训练数据用途或成绩差造新负例。

## 精细共指：三对、两条事实链

| 论文 | 最小回指 | 对应提及 | 证据层级 |
|---|---|---|---|
| SQuAD | `the dataset` | e1，别名e2 | discourse_inferred |
| SQuAD | `which` | e4 logistic regression | direct：句内模型成绩归属 |
| HumanEval | `this method` | e9 repeated sampling | discourse_inferred |
| HumanEval | `our problems` | e5 HumanEval | discourse_inferred |

整句/子句保留为 `anaphorContextSpan/antecedentContextSpan`；新增 `triggerSpan`、`resolvedEntitySpan`、`resolvedEntityId`、`referentAliasIds` 和 `evidenceLevel`。`which`的局部直接归属不使数据集评测整体变成显式句内事实。

SQuAD全名与缩写共用 `coreferenceFactId`，不算两项独立科研事实。三条关系的 `relationEvidenceLevel` 均为 `discourse_inferred`；原EVALUATED_ON标签、理由和原连续证据不变。HumanEval的两个回指分别指向策略和基准，未将成绩归于生产Codex。

仅加强指定3对，不宣称所有跨句/别名关系均有精细共指。字符偏移、别名和类型一致性可程序检查，语篇解释仍有中等语义风险。

## 评测协议与真实拆分边界

机器协议固定了论文组拆分、整摘要输入、代表性评测与长尾挑战分开、盲测一次、逐类与覆盖率披露、支持组相关性控制，以及未来候选模型选择护栏。

`split_lock.json`把12篇现有论文锁为train-only。`historical_exclusions.jsonl`保存**元数据**排除记录：历史语料20,000行、旧训练摘要70行、旧摘要选择60行、补充开发身份8行。20,138行是来源记录数量，不是20,138篇独立论文；其身份可能重复。未复制或解析保留test正文，只核对其文件SHA。

新验证、测试和challenge成员均为空；`protocolFrozen=true`与`evaluationInventoryLocked=false`分别保存。下一阶段必须先锁新总体、种子、样本量和元数据，再采集评测原文/标注/查看预测，不能以本批已暴露论文填充独立测试。

元数据校验器拒绝同publication/group/arXiv版本/已知文本哈希跨拆分，也拒绝历史身份进入新评测；但它不能证明所有近重复或语义相似论文已排除。未来新数据采集后仍需近重复复核。

本批还固定未决评测的责任：部分标签不支持对所有未知预测算确定FP，也不能排除未知后宣称完整Precision。正式端到端指标须完整参考或披露不可评分分母与覆盖率。

训练重复控制只冻结为未来规则：同论文/supportGroup每轮一个提及、按预定种子轮换别名。本批没有执行采样或训练；审核角色/共指仍不作为模型真值特征。

## 已执行检查与失败留痕

[最终相关回归132项](../outputs/v2_supervision_protocol_verified_20261010.xml)全部通过：本批34项、上轮27项、完整性32项、语义修订23项、首批16项。不是全仓库测试，也不累加重复运行次数。

检查包括12篇守恒、五条撤回白名单、正例保持、收据与来源绑定、最小回指与目标实体、跨句不得标direct、版本/组/文本哈希隔离、已暴露论文拒绝进入评测、不读取测试正文、缺失JUnit不创建半成品、不可覆盖旧目录、重新签名的错误统计拒绝，以及真实SciBERT tokenizer特征不受审核元数据影响。未执行真实模型权重推理。

首轮预检32通过/1失败：篡改summary被正确拒绝，但校验器返回`summary_counts`，测试预期为`protocol_summary_counts`。统一错误类别名称后补跨句direct拒绝测试，最终132项通过。原失败XML保留：[首次预检](../outputs/v2_supervision_protocol_preflight_20261010.xml)。该修复不涉及训练效果。

已用基础Python在隔离模式实际运行便携校验，**94类数据约束通过，其中继承父版61类、新增33类**。不是94次语义认证，不能与132项pytest相加宣传。

解压后进入本版数据目录运行：

```powershell
python -I source_snapshot/scripts/finalize_v2_supervision.py --verify .
```

校验器只使用标准库；检查文件/来源/收据/导出守恒、撤回范围、双层跨度、身份锁、统计和权限标志。完整仓库pytest/生成重建仍需要未打包历史输入与本地ML环境；便携重放不代表可重训整个项目。

生成前后本机6个V1保护文件SHA均与父版相同，未改旧图、权重、应用及训练编码器；没有登录Neo4j重新验收。外部包内保护记录仅证明记录守恒，不等于线上即时证明。

[真实结果截图](../kg_datasets/dblp/course_v2_supervision_protocol_20261010/09_annotation_expansion.png)经安装的Edge实际渲染并目视核对；来源页与图片SHA见 `captures.json`。这是数据结果页，不是训练现场或Neo4j截图。

## 审核入口及下一步

- `protocol_review.csv`：8条变更/补证记录，5条标签撤回、3条证据细化。
- `relation_ledger.jsonl`：684对全账本，保留上游及本轮变化链。
- `re_candidates.jsonl`：85条原正例候选，全部无训练授权。
- `split_lock.json`：12篇训练身份与空的新评测成员。
- `source_snapshot`：受控源码、配置、规则、裁决和测试副本。

三项本批修复结束。下一阶段缺口仅是**同一作用域下的高质量负例支持，以及真正新锁定的独立评测数据**。本批不启动训练，不继续反复审已接受五条用途，不通过更改规则或把未决降负来凑样本。
