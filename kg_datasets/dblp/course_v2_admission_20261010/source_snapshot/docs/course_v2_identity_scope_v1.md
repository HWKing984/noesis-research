# V2 身份隔离与不可评状态契约 v1

本轮仅修复独立审计发现的身份绕过和评价默认通过风险，不增加论文、不改标签、不训练、不推理、不修改V1。`finalize_v2_supervision.py`及既有上游档案保持封存，只用于重放历史记录；新准入调用`course_v2_identity.validate_partition(assignments, excluded, aliases)`。

## 身份边界

arXiv编号格式依照[官方编号说明](https://info.arxiv.org/help/arxiv_identifier.html)：现代编号从0704开始，1412以前四位序号，1501开始五位序号；月份01–12，序号非零，版本号从v1开始。编号允许大小写不同的`arXiv:`前缀，去除版本后按同一论文身份隔离。仅接受ASCII数字。

可识别现代编号、arXiv官方abs/pdf链接、`journals/corr/abs-YYMM-NNNNN`编码键，以及哈希绑定的原有书目CSV中明确提供的arXiv链接。不从命名式DBLP键猜测编号；冲突来源或非法编号隔离。缺少可校验arXiv身份的新dev/test/challenge记录拒绝准入。2007年前旧编号暂不支持，遇到即阻断，不能静默忽略。

书目CSV按既有分号URL数组规则拆分。公开历史题名属于源元数据，不是新增标注或新测试正文。历史排除清单保留原publicationId/groupId/来源并增加canonicalArxivId/canonicalPaperId；原有论文组、文本哈希和版本隔离继续生效。重复排除来源行保留，行数不等于独立论文数。

shortcut: 已知arXiv别名不是完整跨会议/期刊、DOI或语义近重复去重；未来建立新评测成员前需要额外审查真实身份和近重复。格式通过不是论文存在证明。合成回归控制样本不进入数据或评测成员。

## 评价边界

没有正参考、没有明确负参考、参考不完整或已判覆盖不足时，状态必须为`not_evaluable`，指标TP/FP/FN/P/R/F1为null，不产生虚构0分或默认通过。未决对不转换为NO_RELATION。

用于正关系的来源论文少于10篇时，额外标为`insufficient_source_support`，不能自动通过升级。10篇只是保守工程护栏，不代表统计显著性或泛化充分性。即使参考完整、支持达到护栏，仍需冻结的可比预测与参考文件，不能默认晋级。

本轮`evaluation_readiness.json`只检查训练侧参考是否完整，不是验证/测试评分；新dev/test/challenge成员仍为0。85个已接受正例及599未决全部保持，不将AI同会话复核称为独立人工gold。

## 调用与复核

`harden_v2_identity.py`是本轮唯一生成入口，生产生成要求提供已完成且通过的身份回归JUnit；拒绝覆盖已有目录。原始CSV、独立审计、全部上游、源代码和测试快照一并保存，标准库`--verify`重新计算别名、覆盖率、隔离用例、参考状态及数据守恒，不依赖ML环境。

最终没有新训练/准确率成绩。结构与哈希校验不构成语义正确率、完整防泄漏或在线生产健康的证明。
