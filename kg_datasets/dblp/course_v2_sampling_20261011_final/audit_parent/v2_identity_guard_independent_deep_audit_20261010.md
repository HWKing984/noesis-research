# V2 身份隔离修复包独立深度审核报告

审核对象：`v2_identity_guard_audit_20261010.zip`、`course_v2_identity_guard_20261010.md`、页面截图。审核对象为 V2 数据与协议快照，不含实时 Neo4j、生产模型权重或完整训练环境。

## 总结

**工程数据快照：通过。已知 4 个跨来源身份绕过：修复并独立复现。真实新评测数据准入：有条件，不建议立即开放最终验收。V2 训练：未准备好。**

独立解压后，在包根目录调用 `python -I source_snapshot/scripts/harden_v2_identity.py --verify .`，返回 `status=passed`、`assertionCategories=116`。116 是数据约束类别，不是独立 116 次语义标注检验。包内正式 JUnit 实际含 205 个独立 `(classname,name)` 测试用例，未报告失败、错误或跳过；此次没有在完整本地项目环境重跑全部 205 项测试。

独立以 SHA-256 比较 `references.jsonl`、`generation_receipts.jsonl`、`reviewed_receipts.jsonl`、`relation_ledger.jsonl`、`ner_candidates.jsonl`、`re_candidates.jsonl` 与包内父版本：**六文件逐字节相同**。12 摘要/177 实体/684 候选对保持，68 `USED_FOR` +17 `EVALUATED_ON` + 0 `NO_RELATION` +599 `UNRESOLVED` = 684。85 条正例仍未授权训练。新 dev/test/challenge 成员均为空；没有新 F1 或实时生产状态证明。

## 已确认修复

1. arXiv 前缀混合大小写、大小写大写的同 ID（如 `arXiv:2107.03374v2`）被识别为历史曝光论文并拒绝。
2. DBLP `journals/corr/abs-1708-00052` 与 arXiv `1708.00052` 匹配；历史来源 URL 映射 `journals/corr/Abdelsamea15` 与 `1511.00111` 的回归结果也正确拒绝。
3. 重算历史书目 20,000 行、已知 arXiv 映射 5,425 行（编码 5,253，额外 URL 172）、未映射 14,575 行；不是 20,000 篇独立 arXiv 论文。历史排除记录 20,138 行，其中有规范 arXiv 身份 5,563 行，去重后 5,454 个 ID。
4. 训练侧 `USED_FOR` 68/563（12.08%）和 `EVALUATED_ON` 17/121（14.05%）的部分参考状态正确标记为 `not_evaluable`，0 明确负例；TP、FP、FN、P、R、F1 均为 `null`。这不是模型性能结果。

## 新发现 P1-A：构建前 JUnit 验收可以接受伪造的极简通过 XML

受影响：`source_snapshot/scripts/harden_v2_identity.py` 的 `passing_junit()`。

函数仅要求至少一个 `testcase`、没有失败/错误/跳过且存在一个 `classname=tests.test_v2_identity_guard` 的测试用例。独立构造的 XML 在 `testsuite tests="205"` 时实际只含一个虚构成功测试用例；调用 `passing_junit()` 返回 `1`，没有拒绝。

影响：构建前“已执行完整测试”的证据入口不足，不能用这一步单独证明 205 项测试真实完成。**这不意味着当前提供的正式 205 条 JUnit 记录系伪造，亦不推翻独立成功的 116 类数据约束检查。**

修复建议：校验应与固定测试标识清单和源码哈希绑定，检查 JUnit 实际 testcase 数及预期集合、运行时元数据；更可靠的是由受控构建命令执行测试并直接读取其结果，而不是信任任意外部成功 XML。增加“仅含 1 个伪测试”“报告总数与实际用例不符”回归。

## 新发现 P1-B：最终测试准入没有强制提供文本哈希

受影响：`source_snapshot/scripts/course_v2_identity.py` 的 `validate_partition()`。

新 dev/test/challenge 只强制 `publicationId`、`groupId` 及能够形成 `canonicalArxivId`，没有强制 `textSha256`。实际载入随包提供的 20,138 条历史排除记录后，执行以下对照：

- 已曝光 `arXiv:2107.03374V3`：**拒绝**，理由 `Exposed paper cannot enter new evaluation`。
- 已曝光 `1511.00111`：**拒绝**，理由同上。
- 未被历史排除表覆盖的合成 `2610.88888`，没有 `textSha256`：**准入**，返回 `{'test': 1}`。
- 同样合成 arXiv 身份，提供与历史训练记录匹配的 `textSha256`：**拒绝**，理由同上。

影响：文本哈希冲突校验仅能覆盖提交了哈希的候选；若没有哈希，就不能称其经过文本层面隔离。该实验使用合成身份和历史哈希，**不是已发生泄漏的证据**，也不是正式新论文已真实存在的验证。

修复建议：采用“先锁元数据候选，再获取原文并计算哈希，最后放行评测”的两阶段接口。预锁阶段允许缺 SHA，但标记 `pending_content_binding`；最终入库 dev/test/challenge 应强制文本哈希、来源认证及近重复复核。对保留测试正文的独立性保护与哈希核验可在受控导入后进行，不以模型预测指导纳入样本。

## P2：代表性评测的抽样框需要明确

20,000 条历史书目中 14,575 条缺可知 arXiv 映射；当前新评测准入要求可校验 arXiv 身份。因此未来若只从可映射候选中抽样，就只能代表**该受限子集**，不能把结果直接称为覆盖全部 DBLP 文献的代表性评测。项目记录已承认 DOI/会议/期刊版本与语义近重复未充分打通；建议选用受限子集时明确抽样框，或在新的身份归一方案成熟后扩展其他来源。

## 实体关系与统计方面未发现新阻断

- 12 篇、177 实体、684 对未变动，六份核心标签及证据 JSONL 与父版的 SHA 相同。
- 85 正例、11 来源论文、29 支持组不等于 85 个独立科研事实。
- 对训练侧的标签覆盖率报告正确，明确负例为 0；不可将这些训练参考统计解释为模型性能。
- `evaluation_readiness` 有 0 负例、未决参考时给出 `not_evaluable`，不产生虚假 F1。
- 新验证、测试成员目前为零，评测协议冻结并不意味着真实评测数据冻结。

## 准入意见

| 范围 | 结论 |
| --- | --- |
| 封存数据完整性、旧标签保持 | 通过 |
| 已发现的 arXiv / DBLP 别名绕过 | 修复通过 |
| 训练侧评测不可评状态 | 通过 |
| JUnit 测试执行证明门槛 | 需修复 P1-A |
| 实际新评测集的最终内容绑定 | 需修复 P1-B |
| 全领域独立性与抽样代表性 | 尚未证明 |
| V2 普通三分类关系训练 | 尚不可准入：缺合格负例 |
| 实时生产、模型 F1、人工 Gold | 此次不验证 |

**建议状态**：`identity_guard_regression_passed_evaluation_admission_requires_content_binding_not_training_ready`。先修两处小而明确的准入问题，不要开启无界限的大规模重新审标或模型训练。
