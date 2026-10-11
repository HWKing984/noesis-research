# 第49轮：补充开发参考已封存，暂缓新训练，转向系统终验

2026-10-09。不要求用户手工标注；采用实际AI初标与同会话复核，仍不是独立人工金标准。本轮按机器学习流程技能先锁来源与分母、保留未知和失败，不以部分标签或工程通过证明模型可靠。报告完整撰写继续暂停。

## 补充开发数据实际完成

获取新原文前固定8篇外部语言模型相关论文，官方arXiv HTML采集8/8成功。按arXiv ID及规范题名拒绝与20,000篇书目、旧train/dev和原始划分元数据重叠；保留test只读取文件哈希及已有身份元数据，没有消费摘要内容、标注或推理。来源有定向选择偏差，不是随机代表性样本，也不是最终测试集。

- 实体抽取参考：7篇严格BIO往返通过；109个实体提及（METHOD55、TASK39、DATASET15）。Sentence-BERT的共享词头并列保留为group，整篇NER/RE隔离，不拆造原文缺失名称。
- 关系参考：88个明确对（USED_FOR70、EVALUATED_ON14、NO_RELATION4）；合格NER范围478个候选对中的390个仍未决，不填成负例。隔离论文的140个候选对不混入这一分母。
- 14条评测参考仅来自3篇论文，9条集中于同一DeBERTa摘要；按半数据/单模型/集成配置及提及位置归属，不解释为14次独立实验。
- BART架构短语内部的machine translation记为WITHIN_ENTITY，后面独立翻译任务照常保留；原文拼写、LaTeX文本不改，不从题名补正文未出现的模型名称。

[锁定合同](../resources/course_abstract_dev_supplement_v1.json)、[成功采集清单](../kg_datasets/dblp/course_abstract_supplement_sources_20261008_49_runtime/manifest.json)、[实际AI判断](../annotations/course_v4/abstract_supplement_decisions_20261009_49.json)、[同会话复核](../annotations/course_v4/abstract_supplement_reviews_20261009_49.json)、[复核产物统计](../kg_datasets/dblp/course_abstract_supplement_reviewed_20261009_49/summary.json)均保留。新增8篇是独立dev资产，未合并进训练输入或生产图；书目仍20,000篇。

## 为什么没有继续盲目训练

新切片完整关系文档为0/8，完整EVALUATED_ON支持0；旧dev仍完整7/19、完整EVALUATED_ON0。正文不足以对全部METHOD×TASK/DATASET实体对明确判定，不能通过把未知改负、删去困难文档或只评价14条正例来制造高分。

因此本轮没有新模型拟合、预测或P/R/F1，也没有最终test、模型替换、图谱写入或可靠性晋级。最近真实训练仍是46轮，47/48候选未晋级；旧分数和生产31配置原样。完成本次固定8篇补充后，当前课程系统采用已封存的候选检索版本进入终验；摘要高可靠升级单独保留为未解决项，不继续无限追加标注/训练轮次，不声称这些缺陷已经解决。

## 核验与真实留痕

[完整工程回归](../kg_datasets/dblp/course_v4_runs/tests_20261009_round49_complete.xml)378项通过，零失败/错误/跳过；命令墙钟161.66秒，JUnit161.589秒。使用D盘进程隔离tmp；C默认tmp的历史rename问题未修。新增封存审核和运行诊断另实际执行断言检查，不把它们冒充模型准确率或新增pytest项。

[机器核验](../kg_datasets/dblp/course_v4_runs/verification_20261009_round49.json)重新核对来源SHA、8份初标/复核链、序列标签、关系行和数量，`passed=true`但`qualityPromotionPassed=false`。两张实际Edge结果页截图已查看：[补充开发标注](evidence/20261009_round49/09_annotation_expansion.png)、[配置归属与弃权边界](evidence/20261009_round49/04_traceability.png)，[时间/来源/SHA](evidence/20261009_round49/captures.json)封存。这是保存产物的浏览器渲染，不是训练终端或在线应用成功截图。

失败也保留：初次用验证环境采集时缺transformers，在任何摘要请求前停止，改用已有训练环境，未安装新依赖或覆盖[失败目录](../kg_datasets/dblp/course_abstract_supplement_sources_20261008_49/failure.json)。首个新增测试夹具缺publicationId，被真实测试拒绝；[失败JUnit](../kg_datasets/dblp/course_v4_runs/tests_20261008_round49_targeted.xml)保留，修复后回归通过。首次证据审核把UTC记录误等同于单调计时配置15.1秒，被间隔检查拒绝；[失败说明](../kg_datasets/dblp/course_v4_runs/round49_evidence_preparation_failure.json)保留。原始UTC最短15.092014秒，所有间隔满足保存robots的15秒底线，但不能证明每次达到15.1秒配置裕量；审核公开全部实际间隔，采集合同、脚本和请求记录未改。

## 在线终验：当前运行环境阻塞，不是成功验收

本轮开始7474/7687/8765均未监听。定位用户已有的AI-Literature-KG实例后，尝试一次隐藏的console启动：服务器确实达到Started并监听7474/7687，但只读`neo4j-admin server license`明确返回`No license is accepted`，Java23提示unsupported、要求21或25。目录owner不同只是警告，ACL有Authenticated Users修改权限，不能认定它是启动根因；旧日志中的锁冲突也不是本次失败原因。

没有代用户接受任何许可、安装JDK、修改Java配置/ACL或导入数据，没有输入密码或继续数据库查询。对本轮拥有的启动console发出Ctrl-C，日志确认Stopped后才关闭空闲启动器；检查7474/7687/8765均已停止监听。

原始[启动stdout](../kg_datasets/dblp/course_v4_runs/neo4j_console_20261009_round49.stdout.log)、[stderr](../kg_datasets/dblp/course_v4_runs/neo4j_console_20261009_round49.stderr.log)及[实际只读诊断记录](../kg_datasets/dblp/course_v4_runs/runtime_environment_20261009_round49.json)保存。CLI的许可状态不是对用户全部授权权益的结论，不据此要求购买或代选许可。用户需要先从Neo4j Desktop正常启动该实例；如界面要求许可确认，由用户确认。若仍有Java提示，再按Desktop实际错误处理，不能承诺GUI一定自动解决。

## 剩余有限收尾

1. 恢复实例的合法、受支持运行环境；应用采用既有31图配置，不重新入库、不强推新模型。
2. 做一次真实在线只读验收：图版本/节点关系计数、中文检索、作者身份、论文详情与证据、合作/方法多跳、候选清单和实际导出；保存桌面/移动端截图。
3. 若以上通过，冻结课程“可追溯候选文献检索系统”交付版本和启动说明。剩余模型误差、未决身份/概念、缺引用网络等如实列为限制，不改称高可靠知识事实或自动引用决策系统。完整报告由用户以后单独写。

本轮仅数据/工程留痕完成，在线终验与高可靠模型升级均未完成；不将运行环境阻塞混成模型质量结论。
