# 第45轮：补充四篇训练基准，增加独立DATASET来源

2026-10-08。完成四篇新训练来源的采集、整篇AI初标、实际同会话自复核、合并输入及严格编码；**没有训练、模型推理、新F1、晋级或线上图更新**。沿用mle-workflow的身份隔离、原文绑定与未知遮罩约束；标签不是独立人工gold，完整课程报告继续暂停。

## 实际增加了什么

| 训练侧 | 第44轮 | 第45轮 |
|---|---:|---:|
| 全队列 / 合格NER / 隔离 | 58 / 54 / 4 | 62 / 58 / 4 |
| METHOD / TASK / DATASET提及 | 403 / 196 / 44 | 405 / 218 / 55 |
| 含DATASET的独立论文 | 16 | 20 |
| DATASET字面名称（未同义归一） | 27 | 31 |
| 明确关系：用途 / 评测 / 负例 | 183 / 58 / 26 | 184 / 61 / 26 |
| 未决 / 全部候选实体对 | 1647 / 1914 | 1659 / 1930 |
| 完整关系文档 | 8 | 11（新增3篇真实零候选） |

所有旧267关系原样保留。新增4条明确关系为1用途/3评测，**评测只来自TriviaQA这一篇**，不是三个独立试验，更不是新增四篇完整评测论文。新增12对继续未决，没有填负例。

新增DATASET字面名：RACE、TriviaQA、HotpotQA、DROP；SQuAD是已有名称在另一独立论文中的新语境。数据多样性有实际增加，但四篇都属于阅读理解/问答基准，不能据此证明跨领域泛化已解决。重复提及数与独立论文数分别披露。

## 选择、采集与标注

在新页面/标签产生前锁定四个arXiv ID及参考题名；使用已有2万篇规范化题名/ID身份元数据、论文组划分及旧train身份做重叠拒绝检查，没有将已存在dev/test论文强制划为train。匹配未发现，不意味着语义近重复检测穷尽。只扫描身份元数据，不语义消费dev/test摘要或标签。

这是**定向训练补充**，而非独立、代表性评测样本。没有按已见dev/test错误、模型分数或测试稀有名称挑选。四篇不是DBLP子集成员，专用于train；书目20,000篇及31轮生产图不变。摘要资产由96→100篇，其中DBLP对应87篇、外部训练来源9→13篇。

仅请求官方arxiv.org `/abs` citation元数据，复用已有下载/解析/标注/复核函数；保存原HTML、robots、原文SHA、题名/ID及请求日志，不下载全文/PDF。当前[robots规则](https://arxiv.org/robots.txt)要求通用爬虫间隔15秒；程序按单调时钟等待至少15.1秒，保存的墙钟请求间隔为15.100272/15.098972/15.109734秒，均超过15秒（墙钟与单调时钟的毫秒差异不隐去）。四请求全部成功并题名匹配，169–219 tokens，无截断、失败替换或自动重试。

| 源论文 | 新实体 | 局部关系判断 |
|---|---|---|
| [RACE · 1704.04683](https://arxiv.org/abs/1704.04683) | DATASET3 / TASK3 | 未命名state-of-the-art模型不造METHOD；零候选 |
| [TriviaQA · 1705.03551](https://arxiv.org/abs/1705.03551) | DATASET5 / TASK3 / METHOD2 | 局部3评测/1用途，12未决 |
| [HotpotQA · 1809.09600](https://arxiv.org/abs/1809.09600) | DATASET2 / TASK6 | QA任务缩写不是命名模型；零候选 |
| [DROP · 1903.00161](https://arxiv.org/abs/1903.00161) | DATASET1 / TASK10 | 报告的系统/新模型未命名，不造方法端点；零候选 |

同会话AI判断：TriviaQA明确给出feature-based classifier与neural network两种局部baseline家族。单数从句“performs well on SQuAD”支持network的局部评测/reading comprehension用途，不能套给classifier；随后两种方法23%/40%与human80%的对比支持最后TriviaQA提及的两条评测断言。其他12对未决，包括classifier→SQuAD；没有报告该方法表现不是负例。仍是AI对原文的解释，不宣称独立核验正确。

RACE中的学生理解/推理能力不当模型任务；HotpotQA不从题名借入multi-hop短语，Wikipedia来源不当评测集。DROP的addition/counting/sorting明确是对段落/问题输入执行的计算操作，保留English与paragraph对象限定；semantic parsing/numerical reasoning作为技术任务，不造同名方法。URL保护、不连续/重叠处理与既有平面BIO规则不变。

## 输入、验证与失败留痕

来源：`course_abstract_benchmark_sources_20261008_45`；初标：`course_abstract_benchmark_generation_20261008_45`；复核：`course_abstract_benchmark_reviewed_20261008_45`。**最终训练输入**：`kg_datasets/dblp/course_abstract_benchmark_inputs_20261008_45`，manifest SHA `efbd9c2fc1f1e89f7cfc2cc59ec2df239e534f763d07a4a38b92d9464016e167`。

58行旧收据逐行字节不变，旧267条关系和原训练原文不改；9个dev文件只复制原始字节并核对SHA。58篇BIO实际严格往返并按保存offsets/labels重算通过；271关系对均实际标记编码，最长333 tokens，小于512，无静默截断。最终行`contractSha256`仍指父36行序列化规则，45轮数据合同独立绑定。

完整工程回归：**373通过，234.89秒，零失败/错误/跳过**，D盘进程隔离临时目录；JUnit记录234.534秒。新增一个可运行检查覆盖四源/训练范围、别名ID和规范化题名碰撞拒绝、重复种子及覆盖保护；目标测试1项通过0.86秒。工程测试不等于人工语义验证。C默认tmp历史rename问题仍未修。

一次流程顺序失误：复核进程尚未封存时提前请求snapshot，入口因缺`manifest.json`拒绝，未写目标输出；错误单独留痕。没有伪造manifest、覆盖或重启复核；等待原进程实际完成后才继续成功构建。失败记录：[precondition failure](../kg_datasets/dblp/course_v4_runs/round45_snapshot_precondition_failure.json)。

证据核验重新解析四个原HTML、核对题名/ID/Unicode原文/生成与实际复核收据、所有合并行/BIO/未决对、旧收据/关系及dev字节，截图来自真实保存产物，**不是原始终端、训练现场或Neo4j界面的仿制**。两PNG实际检查后才封存。[机器核验](../kg_datasets/dblp/course_v4_runs/verification_20261008_round45.json)、[数据支持截图](evidence/20261008_round45/02_training.png)、[关系证据截图](evidence/20261008_round45/04_traceability.png)、[最终统计](../kg_datasets/dblp/course_abstract_benchmark_inputs_20261008_45/summary.json)。

```powershell
# 只读预检与源/身份检查；历史目录不可覆盖，不能重复旧采集来追分。
& './.venv-validation/Scripts/python.exe' scripts/expand_train_benchmarks.py preflight
& './.venv-validation/Scripts/python.exe' -m pytest tests/test_train_benchmark_expansion.py -q
# 新输入仍不能直接塞给42版训练入口；需另锁新实验和资源预算。
```

## 下一步

本轮补到了独立DATASET训练论文，但完整dev仍EVALUATED_ON=0/覆盖7/19、独立参考与长尾支持仍不足。下一步另锁单一模型对照、固定同范围开发分母、稀有召回护栏与资源预算，使用新版标签检验是否改善，不改封存入口或反复用已见dev调分；19篇保留test不消费。当前没有新模型收益成绩。

4篇NER隔离、模型泛化、概念/作者长尾消歧仍待解决；`qualityPromotionPassed=false`、`modelPromoted=false`。没有写库、服务重启或新线上验收，仍31图/旧题名模型；课程完整报告不扩写。
