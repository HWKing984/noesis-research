# 第37轮：训练摘要扩充与数据量单因素实验

2026-10-08。按MLE流程先锁训练侧来源和原超参数，复用现有采集、逐篇AI标注/自复核、严格BIO评分和固定旧RE。**数据扩充、真实训练和对照已完成，但可靠性问题没有解决，新候选不替换现有模型。**未扩写课程报告、部署或改写保留测试。

## 数据与来源

从32轮在响应/标签前锁定的60篇train成员中，排除旧网页请求与已暴露缓存，顺序取下一批24篇。未按dev错误、稀有关键词或模型分数选择；原论文组均属于train，不触碰dev/test组。24次官方arXiv摘要页请求均成功，21篇题名匹配，3篇不一致隔离，不以成功样本补足24；原HTML、请求时间、原文、哈希和排除原因保存。

采集技能的限速/去重/留痕规则发现一个历史合规缺口：32轮网页入口用了API的3.1秒间隔，而网页robots要求15秒。本轮新入口实际按至少15.1秒单连接执行，保存robots原文与实际请求时间；旧源包/执行源码原样保留，不追改历史记录。旧 `collect_course_abstract_pages.py` 仅留作历史复现和元数据解析来源，**不要再运行它的旧采集命令**。当前入口为 `collect_train_abstracts.py`。[当前网页规则](https://arxiv.org/robots.txt)、[API规则](https://info.arxiv.org/help/api/tou.html)。

21篇逐篇AI初标和同会话自复核，实际复核补了KoPL engine别名、diffusion transformer组合跨度与GNN-based完整家族跨度。19篇通过严格token/BIO往返，2篇因领域/方法多义和同词嵌套角色保留隔离，未强制all-O。新增METHOD151 / TASK76 / DATASET9个提及；DATASET9只来自4篇/9个名称，不能冒充9个独立实验。未确定的724个关系候选全部UNRESOLVED，不作为NO_RELATION；本轮没有新增RE监督训练。

训练NER从29篇增至48篇，参考提及总METHOD362 / TASK185 / DATASET44。旧37篇训练标注、16/19篇dev参考和3篇dev隔离状态不变；累计58篇训练侧摘要自复核，48篇NER输入、10篇隔离。摘要资产由75篇增至96篇，新增21篇均对应已有DBLP书目，**图谱书目仍20,000篇**，不把摘要当新论文。教程/综述可作为本轮NER语言样本，明确不是新增原创研究成果；没有声称修复原20,000书目的非研究条目污染。

## 真实NER训练与同分母结果

新合同 `resources/course_abstract_expansion_v1.json` 在采集/新标注/训练前锁定：父合同和超参数不变、同旧题名NER初始化、seed20261008、batch2、lr2e-5、FP32 eager、6轮、按dev严格micro F1最早最佳。48篇每轮恰好覆盖一次，共144步，选epoch6；RTX4060 Laptop，训练及固定RE对照共36.75秒、峰值显存2,279,580,160字节。编码器和分类头确实改变，重载预测相同；不因结果再改超参数。

| 相同16篇/184个AI参考实体 | Precision | Recall | micro F1 | METHOD F1 | TASK F1 | DATASET F1 |
|---|---:|---:|---:|---:|---:|---:|
| 旧题名权重迁移 | 43.08% | 59.24% | 49.89% | 61.66% | 35.00% | 25.00% |
| 35轮摘要NER | 69.23% | 73.37% | 71.24% | 81.98% | 52.54% | 66.67% |
| 37轮扩充NER | 69.79% | 72.83% | 71.28% | 82.76% | 49.15% | 69.23% |

总F1仅变动约0.04百分点，不足以称为明显提高。TASK仍退化；DATASET精确率由54.17%升至81.82%，但召回由86.67%降至60.00%，不能只看F1说稀有类已解决。134个严格TP，192个预测、184个参考；非法BIO转移从55降到41，不等于语义可靠性。

| 同一5/19篇完整dev、固定旧RE | Precision | Recall | F1 | TP / 预测正例 / 参考正例 | 漏关系主因 |
|---|---:|---:|---:|---:|---|
| 旧题名NER | 8.59% | 47.83% | 14.57% | 22 / 256 / 46 | 边界24 |
| 35轮摘要NER | 24.32% | 39.13% | 30.00% | 18 / 74 / 46 | 缺失19 / 边界7 / 类型2 |
| 37轮扩充NER | 19.05% | 43.48% | 26.49% | 20 / 105 / 46 | 缺失5 / 边界21 |

没有参考实体或标签参与候选生成，标签无关的重新推理与NER dev预测一致。缺失主因减少并不等于全部修复：一些被识别的实体仍有边界错误，且预测正边/FP增多。对35轮摘要候选，召回升4.35百分点，但Precision/F1降低，拒绝替换；对旧题名NER，召回仍下降4.35百分点，超过父合同2点护栏。整体覆盖仍5/19=26.32%，含1篇零参考对，EVALUATED_ON参考正例0，晋级条件仍不满足。

评分是**已经暴露的AI开发标签诊断**，不是盲评、最终测试或独立gold。复用的历史评分函数在原始JSON部分字段仍保留 `held_out_ai_reference_agreement_not_human_gold` 默认字符串；本轮审计另存正确的 `exposed_dev_AI_reference_not_final_test` 口径，数字不改，原始运行记录不重写。不要把这些字段或数字当最终测试成绩，也不与旧60.07%题名test比较。

## 当前决定与下一步

`candidateNER=rejected_pipeline_precision_and_f1_regression`，`qualityPromotionPassed=false`。新权重和未通过结果保留，生产旧模型/31轮图、35轮摘要候选、36轮被拒RE与09/17/29封存成绩不变。19篇摘要test仍只做源包哈希完整性检查，未语义阅读、标注、分词、推理或训练；没有写数据库或重启服务，不声称新线上验收。

这次小规模实验未支持“只多加训练文献就能解决”的假设，不能据此否定所有数据扩充策略。下一步优先**训练侧跨度/角色定义和逐次出现的上下文标注**，针对方法名嵌套任务词、长任务边界和家族/研究对象区别；不根据模型预测改dev参考追分。保留未决，补有证据的完整关系dev覆盖；参考同一AI来源仍有限，独立核验可选但不能伪称已完成。新增盲评与一次性保留test评估必须等待整条pipeline和选择规则锁定。

## 复现与留痕

新输出目录必须不存在。当前入口没有final-test或自动部署参数：

```powershell
& '.\.venv-validation\Scripts\python.exe' -m pytest tests/test_expanded_abstract_ner.py -q
& '.\.venv-training\Scripts\python.exe' scripts/train_expanded_abstract_ner.py train --snapshot kg_datasets/dblp/course_abstract_expansion_inputs_20261008_37 --source kg_datasets/dblp/course_abstract_train_sources_20261008_37 --reviewed kg_datasets/dblp/course_abstract_expansion_reviewed_20261008_37 --output kg_datasets/dblp/course_v4_runs/NEW_EXPANSION_DEV
```

原文/请求：`course_abstract_train_sources_20261008_37`；AI收据：`course_abstract_expansion_reviewed_20261008_37`；输入：`course_abstract_expansion_inputs_20261008_37`；运行：`course_v4_runs/abstract_ner_expansion_development_20261008_37`（均在 `kg_datasets/dblp`）。

工程回归与逐条指标/错误重算结果见[机器核验](../kg_datasets/dblp/course_v4_runs/verification_20261008_round37.json)。[数据扩充与拒绝截图](evidence/20261008_round37/09_annotation_expansion.png)、[真实训练与类别变化截图](evidence/20261008_round37/05_development.png)是浏览器对真实产物页的截图，不是训练现场、原终端或Neo4j画面；页源、逐条错误、决策、原运行文件、执行源码及哈希同目录保留。
