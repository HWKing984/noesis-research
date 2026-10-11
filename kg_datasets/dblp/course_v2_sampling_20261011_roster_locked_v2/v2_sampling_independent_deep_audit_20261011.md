# V2 选样与训练负例筛查：独立深度审核

审核日期：2026-10-11  
审计材料：`v2_sampling_audit_20261011.zip`、`course_v2_sampling_20261011.md`、`selected_metadata_review.csv`、`negative_review_queue.csv`。  
审核边界：审查上传的离线证据、源代码快照、样本元数据及训练侧唯一负例候选；没有读取新评测摘要、调用模型、访问生产 Neo4j 或取得人工 gold 标签。

## 1. 审核结论

**选样数据与可复现性：通过。** 压缩包自带只读验证在独立解压目录返回 `status=passed`；从封存网页列表、历史排除元数据、固定种子重新得到 `3,654 → 3,579 → dev 20 + test 20`。新的验证和测试仅是元数据预锁，不是内容/标注准入。

**发现一处应在模型研究前修复的训练成员锁定缺口（P1）。** `course_v2_sampling.py:prelock(folder, train, excluded, aliases)` 接受调用方传入的任意无冲突 train 名单；`validate_lock` 也以该名单自身为依据重建，没有与封存的 12 篇训练身份逐项或哈希对照。在本次只读反例测试中，`train=0`、`train=1`（来自已封存候选总体的真实 ID `2502.00003`）、`train=13` 均获得 `pending_content_binding` 且能通过 `validate_lock`。这不构成现有固定包发生训练/测试泄漏的证据（原包锁确为 train12/dev20/test20，且 `evaluationAuthorized=false`），但不足以保证未来调用方不悄然更改训练成员。

**负关系证据：仍未具备训练准入。** `pooling → MNIST` 有架构层面的明确否定“pooling is not used”，但不是针对“pooling 是否在 MNIST 上被评测”的明确关系否定；保持 `UNRESOLVED` 是合理的，不能升格成训练用 `NO_RELATION`。可接受负例仍为零。

## 2. 实际复现的校验与数据结果

从 ZIP 安全解压后在包根目录执行：

```powershell
python -I -B kg_datasets/dblp/course_v2_sampling_20261011_final/source_snapshot/scripts/prepare_v2_sampling.py --verify kg_datasets/dblp/course_v2_sampling_20261011_final
```

返回：

```json
{
  "status": "passed",
  "sourceListingCount": 3654,
  "eligiblePopulationCount": 3579,
  "metadataMembers": 40,
  "counts": {"train": 12, "dev": 20, "test": 20},
  "samplingFrameLocked": true,
  "contentBindingCompleted": false,
  "acceptedNegativePairs": 0,
  "trainingAuthorized": false,
  "evaluationAuthorized": false,
  "semanticIndependenceProven": false
}
```

封存来源网页分别含 2,000/1,654 条；排除后 3,579，57 条因历史可规范化身份重合排除，18 条因历史题名精确归一相同而保守隔离。`selected_metadata_review.csv` 的 40 个 `(arxivId, split)` 与正式 `selected_members.json` 完全对应；均为 `2502.*`，dev 与 test 各 20；`sourceURL` 与该 ID 一致。正式 `evaluation_lock.json` 的 dev/test 全部没有 `textSha256`，符合仅元数据阶段。`negative_review_queue.csv` 与 ZIP 正式目录中的同名文件字节一致。

`outputs/v2_sampling_20261011_checks/checks.xml` 保存 58 条互不重复的 pytest 测试用例记录、无失败，但本次没有重跑 58 项 pytest；**实际重新执行的是便携验证器**，不应把父包 239 项也算成本轮重新运行。

## 3. 额外审查：两个版本的样本变化

首版总体 3,597，修订版因增加题名隔离降为 3,579。重新对比两个真实清单：两版各有 40 个身份，**只有 5 个身份重合，35 个身份不同**；两版重合的 5 个仍落在相同 dev/test 划分。首版选出的 40 个没有命中后来增加的 18 条题名隔离对象。

因此：

1. 本次重新抽样确实实质改变了评测成员，而不只是对原清单做安全过滤。
2. 修订发生在读取新摘要及模型预测前，且两版均保留，是可解释的版本化规则变更，**不能直接认定为测试泄漏或挑选有利数据**。
3. 正式报告必须明确只采用 `_final` 清单，保留首版成员及修订时点；不要混用两版结果。

额外对修订版 40 篇题名与历史 20,000 条书目的归一标题进行了近似字符串匹配。基于本次 `rapidfuzz.fuzz.ratio` 的最高候选相似度约 74.42，没有发现 ≥80 的匹配。这不能排除译名、改题、会议/期刊扩展版、语义近重复，也不是来源权威身份核验。

## 4. P1：训练成员集合未被正式绑定

相关函数位于正式 ZIP：

- `source_snapshot/scripts/course_v2_sampling.py::prelock`
- `source_snapshot/scripts/course_v2_sampling.py::validate_lock`

当前 `prelock` 的关键流程是复算选样成员，然后调用 `admission.prelock(train + selected, ...)`。其入口仅检查 `train` 行的 `split=='train'`，没有比较输入训练成员与原 `evaluation_lock.json` 封存的 12 篇身份。

在独立只读反例中，基于包内的真实 `historical_exclusions.jsonl` 和 `identity_alias_index.json`，以下各调用均被接受：

| 传入训练集合 | 返回的拆分统计 | `validate_lock` |
|---|---|---|
| 原 12 篇 | train12/dev20/test20 | 通过 |
| 空训练集合 | dev20/test20 | **通过** |
| 非封存的真实元数据身份 `2502.00003` | train1/dev20/test20 | **通过** |
| 原 12 篇加 `2502.00003` | train13/dev20/test20 | **通过** |

所有这些都继续保留 `evaluationAuthorized=false`；故这里是**训练版本/溯源的准入绑定缺口**，不是现存生产泄漏。

**建议修复：** 为当前实验额外锁定规范训练论文身份集合（及训练数据版本 SHA），在正式 `prelock`/`validate_lock` 时将输入训练名单与锁逐项比对；训练数据若扩充，必须先明确升级协议版本和训练身份锁，不能自动沿用旧实验的评测选型。添加空训练、额外训练、替换训练及原12正常通过的四类回归用例。若通用库有意允许任意 train，则应在调用它的“正式实验入口”实施该锁，而非强行限制通用库 API。

## 5. 唯一负关系候选的语义裁决

候选：`arXiv:2008.10400`，`pooling (METHOD, e10) → MNIST (DATASET, e1)`，建议标签 `NO_RELATION`，当前 `pending_scope_adjudication`，`candidateEligible=false`，`trainingAuthorized=false`。

- 明确证据：摘要说所述 CNN 结构 **没有采用 pooling**，可以否定“该报告模型的卷积层含 pooling”。
- **不能推出**：独立方法实体 pooling 从未在 MNIST 数据集上评价，或 pooling 在论文/任务中的任何使用均被排除。
- 原 Schema 中 `EVALUATED_ON` 要求方法与数据集之间可归属的评测证据。架构中不用某组件，并不足以确认一个方法—数据集的全局无评测事实。

**裁决建议：维持 `UNRESOLVED`，暂不接受为负例。** 不要因为当前 RE 缺负例，就把一个作用域模糊的候选强行纳入三分类训练。12 篇的筛查“仅发现 1 个待议候选”与当前证据相符，不意味着全库没有负例。

## 6. 评测方法学的实际限制

- 固定总体只代表 **2025 年 2 月 cs.AI 官方列表在历史身份/同题名保守排除后的有限总体**；不代表全部 DBLP、全年 arXiv 或整个学术 AI 领域。
- 从 3,579 中无放回均匀取 40，样本设计合理且可复现；每个单独 dev/test 的设计纳入概率为 20/3579。**各 20 篇仍然过少，不能保证出现足够的 `DATASET`、`EVALUATED_ON`、明确负例**，不能保证以后满足稀有类护栏。
- 40 篇未读摘要、未标注、未绑定准确 UTF-8 文本哈希，不能称完整可评分参考集；当前官方来源 GET 的保存副本也不能单独证明所有 arXiv 版本、会议/期刊版本和近重复均已排除。
- 现在训练侧仅有 85 条已判正例候选、0 条可靠负例、599 条未决候选；仍不适合按原普通 `USED_FOR/EVALUATED_ON/NO_RELATION` 三分类任务直接启动正式对照训练。

## 7. 最小修复与停止条件

| 优先级 | 工作 | 验收标准 |
|---|---|---|
| P1 | 当前训练成员身份与训练数据版本锁 | `train12` 正常；替换/添加/删除训练成员拒绝或要求明确重版 |
| P1 | 维持 `pooling→MNIST` 未决 | 不导出为负例、不误用为验证真值 |
| P1 | 新 dev 正文与参考标注 | 固定身份不变；准确摘要字节哈希、来源/近重复复核、实体完整标注和可评分关系参考 |
| P1 | 确立 RE 监督目标 | 获得不同论文的强证据负例，或正式转为兼容部分标签的训练方案；不将未决关系作负例 |
| P2 | 测试集封存和长尾挑战集 | test 只用于最终盲测；挑战集另建另报；报告样本支持、覆盖率和置信区间/不确定性 |

**审核状态建议：** `sampling_metadata_lock_verified_train_roster_binding_pending_negative_supervision_missing_not_training_ready`。

整体上，这轮选样工作可以保留，不必重采数据或推翻固定总体。可以开始新 dev 数据的正式来源与语义标注，但还没有达到新 SciBERT NER+RE 正式训练和可比较评估的准入标准。
