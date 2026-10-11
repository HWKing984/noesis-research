# V2 身份隔离修复与不可评状态

这是本批工程工作记录，不是课程最终报告，也不是新模型实验。只落实最新独立审核中的身份隔离与评价默认通过问题；不扩论文、不改标签、不训练、不推理、不修改V1。

## 本轮修复范围

1. `arXiv:`/`ARXIV:`大小写前缀及版本先归一，封住两条前缀绕过。
2. 编码式DBLP键转成同一arXiv论文身份，封住审计中的`1708.00052`跨来源绕过。
3. 哈希绑定的原书目链接补充命名式DBLP键映射；新增实际`Abdelsamea15 → 1511.00111`绕过回归。
4. 论文组、publicationId、文本SHA及跨版本检查继续有效；新评测缺可校验身份、来源冲突、非法编号或携带正文时阻断。身份格式通过不代表论文真实存在。
5. 缺正参考、缺明确负参考、参考不完整或覆盖不足，返回`not_evaluable`及null指标；稀有来源支持不足不默认晋级。

旧`finalize_v2_supervision.py`保留原字节，仅重放历史上游。当前新生成入口为[身份修复生成器](../scripts/harden_v2_identity.py)，当前准入入口为[规范身份与评价检查](../scripts/course_v2_identity.py)，具体边界见[契约说明](course_v2_identity_scope_v1.md)。不能把旧冻结检查器重新拿来接收新验证/测试成员。

## 真实映射覆盖率

读取原有`processed_ai/publications.csv`的身份和来源链接，未采集新论文或解析新测试正文。完整CSV作为哈希绑定的公开历史元数据随复核包交付，不作为新标注或训练输入。

| 历史书目映射 | 行数 |
|---|---:|
| 历史书目 | 20,000 |
| 有规范arXiv映射 | 5,425 |
| 从编码DBLP键得到 | 5,253 |
| 额外由来源URL得到 | 172 |
| 编码键和URL一致的行 | 1,540，属于5,253的子集 |
| 暂无arXiv映射 | 14,575 |
| 冲突/非法来源隔离行 | 0 |

全部历史排除来源记录仍为20,138行，其中5,563行有规范arXiv身份，去重后5,454个arXiv身份；不同来源重复行保留，不把20,138行宣传为独立论文数。未归一的14,575条保留原publicationId/groupId；这不证明它们没有arXiv版本，也不证明会议/期刊版本或近重复都已隔离。

## 数据和模型保持

12篇摘要、177实体、684候选关系对保持；68用途、17评测、0明确负例、599未决保持。85正例候选、11来源论文、29支持组和3条精细共指均不变。

`references / generation_receipts / reviewed_receipts / relation_ledger / ner_candidates / re_candidates`六个JSONL与父包逐字节相同，所有候选继续`trainingAuthorized=false`。仅历史排除身份和split_lock增加规范身份字段；12篇仍锁train，新dev/test/challenge成员均为空。

本轮依照ML数据准入检查，把缺证和缺覆盖明确保留为阻断状态，未把AI自查升级为人工gold。

## 参考完整性状态，不是模型成绩

| 训练侧参考 | 正例 | 明确负例 | 未决 | 候选总对 | 正例来源论文 | 已判覆盖 |
|---|---:|---:|---:|---:|---:|---:|
| USED_FOR | 68 | 0 | 495 | 563 | 11 | 12.08% |
| EVALUATED_ON | 17 | 0 | 104 | 121 | 5 | 14.05% |

两类均为`not_evaluable`：缺明确负例、整篇参考不完整、已判覆盖不足。`EVALUATED_ON`另有`insufficient_source_support`；10篇仅是实际工程护栏，不是统计显著性结论。TP/FP/FN/Precision/Recall/F1全部为null，没有0分或默认通过，没有新验证/测试分数。

## 检查及失败记录

[首次身份预检](../outputs/v2_identity_guard_preflight_20261010.xml)：73项通过。随后加入更严格的元数据检查，第一次完整V2回归204通过/1失败：[保留失败记录](../outputs/v2_identity_guard_verified_20261010.xml)。原因是排除清单拒绝了合法`split`字段；已改为允许合法拆分元数据、继续拒绝正文和缺身份记录。

第二次完整V2回归203通过/2失败：[第二次记录](../outputs/v2_identity_guard_final_20261010.xml)。发现8条已暴露补充开发记录原本只有合法arXiv编号，而没有publicationId/groupId；对历史排除记录强制双字段过严。已允许它们按可校验规范论文身份加入排除集合，不猜填缺失字段；空身份仍阻断，新评测成员仍要求完整publication/group字段。

最终完整V2回归[205项全部通过](../outputs/v2_identity_guard_accepted_20261010.xml)，耗时183.29秒；其中继承132项，本轮73项，不累计重复运行次数。[定向复验](../outputs/v2_identity_guard_recheck_20261010.xml)73项通过。

基础Python3.14在`-I`隔离模式下实际离线重放通过**116类数据约束**，其中父版94类、本批22类。校验重新计算全部别名、覆盖率、身份变换、6个隔离用例、参考状态、统计及源绑定；不依赖torch/jsonschema。不把116类约束与205项测试累加当成语义认证。

正式包内六个标签/收据/导出JSONL与父包SHA相同，源CSV、独立审计和源快照绑定通过。本机生成前后6个V1保护文件哈希匹配；这不是重新连接Neo4j的在线健康验证。

解压进入新包目录后运行：

```powershell
python -I source_snapshot/scripts/harden_v2_identity.py --verify .
```

这是可移植文件复核，不是全工程重训环境；未提供模型权重或新增评测原文。安装的Edge已真实渲染1280×2300结果页，PNG为107,059字节，已目视核对；来源页和图片SHA均与`captures.json`匹配，不能当成训练现场或Neo4j画面。

新包manifest SHA-256：`841195e01bd90e964e2cb4456d664cd6bf535148a24813c4f855512dd35a524c`。生成后再次核对全部当前输入SHA、6个V1保护文件、6个数据文件守恒及通过JUnit205项，均一致。

## 复核入口与下一步

正式新包位于`kg_datasets/dblp/course_v2_identity_guard_20261010`，包含原始来源CSV、规范别名索引、覆盖率、实际绕过回归、空的新评测锁、参考完整性状态、全部父包和受控源码。旧包不覆盖。

- [全部复核包](../outputs/v2_identity_guard_audit_20261010.zip)：新目录及本批工作记录、两次失败与通过XML。
- [身份覆盖率](../kg_datasets/dblp/course_v2_identity_guard_20261010/identity_coverage.json)及[6个真实规则重放](../kg_datasets/dblp/course_v2_identity_guard_20261010/identity_regression.json)：四个原绕过、一个原拒绝控制、一个合成未暴露控制；合成控制不代表真实论文，也未进入评测成员。
- [参考不可评状态](../kg_datasets/dblp/course_v2_identity_guard_20261010/evaluation_readiness.json)：不是模型预测结果。
- [真实数据结果截图](../kg_datasets/dblp/course_v2_identity_guard_20261010/09_annotation_expansion.png)：安装的Edge实际渲染，非仿制训练/数据库界面。

完整复核仍需要**同一作用域下的明确负例，以及先锁定真正独立的新验证/测试元数据**。本轮不改变未决/负例定义、不自动采集新评测、不训练。格式、源码和哈希检查不是语义准确率；未证明全量跨版本/语义近重复隔离。
