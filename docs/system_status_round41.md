# 第41轮：评测归属显式撤回与原文证据修复

2026-10-08。按MLE工作流先锁定来源与关系口径，再核对完整原文、逐对判断并实际同会话复核；只修标签，不训练或评分。完整课程报告继续暂停。

## 本轮变化

锁定39轮train58篇和40轮dev19篇，检查其中全部15篇含既有`EVALUATED_ON`的摘要（train12/dev3），共69个旧跨度对：65保持、3撤回至`UNRESOLVED`、1仅扩张证据。未按模型分数选篇，没有新增来源或替换文档。

只有下列两篇发生变化，生成新的初标及一次实际同会话复核收据；另外75份旧收据原样继承。**15篇原文判断不等于15份新复核收据，也不构成独立人工gold。**旧39/40标签包、NER字段、论文组、源文本及以前未决对全部保留各自版本。

| 源文 / 实体对 | 动作 | 原因 |
|---|---|---|
| train `2107.03374`，e4→e5：production version of Codex→HumanEval | EVAL撤回为未决 | 题名/摘要中的production版本与后文报告测量的特定Codex配置不能泛化互换；不证明其从未使用该benchmark |
| dev `1904.04163`，e14→e16：knowledge distillation→Penn Treebank | EVAL撤回为未决 | 原文测量组合配置，单个组件边丢失必要组合归属 |
| 同篇e15→e16：trust regularization→Penn Treebank | EVAL撤回为未决 | 同上，不反推组件没有贡献或不可评测 |
| train `2107.03374`，e9→e5：repeated sampling→HumanEval | 仅扩张摘录 | 原证据`[202,454)`扩至`[202,640)`，补入“Using this method”测量句；label和reason原样 |

`EVALUATED_ON`表示文中报告被测的方法、模型或评测协议配置与benchmark，**不强制独立消融，不蕴含因果改善、高性能或训练使用**。直接报告的完整模型/协议、实际被比较的基线可以保持；撤回针对丢失必需组合、配置或版本的归属，不是统一将组件关系判负。

新入口`review_eval_attribution.py`复用既有候选对、收据验证、行生成和严格编码；不改封存编译器。每个旧EVAL恰好检查一次，单独审计台账保留旧/新完整pair及SHA、上游收据SHA、原文摘录和本轮理由。未知不补成`NO_RELATION`；重复、漏覆盖、错split/来源/旧收据、假摘录和非EVAL替换均拒绝。

## 当前数据与尚存缺口

| 项目 | train | dev |
|---|---:|---:|
| 原队列 / NER可用 / NER隔离 | 58 / 50 / 8 | 19 / 16 / 3 |
| 明确关系对：旧39/40→本41 | 268→267 | 335→333 |
| USED_FOR / EVALUATED_ON / NO_RELATION | 183 / 58 / 26 | 259 / 8 / 66 |
| 未决对 / 全部合格NER候选 | 1578 / 1845 | 99 / 432 |
| 明确对覆盖率 | 14.47% | 77.08% |
| 完整关系文档 / 队列 | 6 / 58 | 7 / 19 |
| 完整文档覆盖率 | 10.34% | 36.84% |
| 完整文档的EVALUATED_ON参考 | 2 | **0** |

完整dev7篇仍为107对（84用途/23明确负例，含1篇真正零候选文档），无法评估完整pipeline的benchmark关系能力。保留8篇训练隔离，不为提高覆盖放行歧义；重复名称仍是相关跨度对，不是独立实验。开发集早已用于选择，此次源文判断未查看预测，仍不能称独立盲测。

本轮未重训、未推理、未重评分旧预测，**没有新Precision、Recall或F1**。35/36/37轮分数保留原输入和分母，不套用267/333对或7篇新范围。保留19篇摘要test无语义读取、标注、分词或推理；无数据库写入、服务重启、新线上验收或晋级。31轮图、2万篇书目和线上模型保持不变，`qualityPromotionPassed=false`。

## 检查与留痕

66篇合格NER摘要严格BIO往返通过；600个明确关系对标记编码通过，最大train333/dev306 tokens，无静默截断。NER内容/状态不变，修订文档的行收据元数据变化，不声称NER行字节相同。

正式全回归**369项通过，114.87秒，零失败/错误/跳过**。新增唯一回归覆盖全部旧值/新值绑定、三撤回/一证据扩张、NER与其他75收据不变、编译行守恒及非法决策拒绝；工程通过不是语义准确率或模型效果验收。

合同：[course_abstract_eval_attribution_v1.json](../resources/course_abstract_eval_attribution_v1.json)。数据：`kg_datasets/dblp/course_abstract_eval_attribution_reviewed_20261008_41`。逐对审计为`attribution_inspections.jsonl`，变化为`quality_actions.jsonl`；实际AI判断/复核在`annotations/course_v4/abstract_eval_attribution_*_20261008_41.json`。

```powershell
# 重放到不存在的新目录；不覆盖当前或历史快照，也不自动训练。
& '.\.venv-training\Scripts\python.exe' scripts/review_eval_attribution.py --decisions annotations/course_v4/abstract_eval_attribution_decisions_20261008_41.json --reviews annotations/course_v4/abstract_eval_attribution_reviews_20261008_41.json --output kg_datasets/dblp/NEW_EVAL_ATTRIBUTION_REVISION
& '.\.venv-validation\Scripts\python.exe' -m pytest tests/test_eval_attribution_revision.py -q
```

本轮证据入口：[机器核验](../kg_datasets/dblp/course_v4_runs/verification_20261008_round41.json)、[归属审计截图](evidence/20261008_round41/09_annotation_expansion.png)、[版本/摘录证据截图](evidence/20261008_round41/04_traceability.png)。原页、源文件和PNG分别保留哈希；机器核验只有在实际拍摄与文件检查通过后才封存。证据页展示实际JSON/JSONL/XML产物，不是训练现场、模型预测或Neo4j界面。

下一步：明确锁定修订后的训练输入、dev比较范围与预先声明护栏，通过薄适配接入新合同；旧训练入口拒绝新合同，不猴补封存脚本。稀有支持、完整pipeline覆盖和独立参考仍不足，不能因清理三条标签立即宣布可靠性解决。
