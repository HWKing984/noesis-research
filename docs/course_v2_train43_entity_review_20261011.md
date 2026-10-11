# V2 剩余43篇训练摘要：实体源文复核候选

本批已逐篇阅读43篇训练摘要及旧实体列表，生成实际修订工作集，不只是增加审核规则。采用同会话AI弱监督复核，不冒充人工或独立金标准；没有训练、模型推理、新F1、生产模型替换或test正文访问。

## 当前交付

- 最终数据目录：`kg_datasets/dblp/course_v2_train43_entity_review_20261011_final/`。
- [逐篇高亮审核页](../kg_datasets/dblp/course_v2_train43_entity_review_20261011_final/train43_entity_review.html)：43篇原文、实体偏移、修改列表、原标注对照及逐篇判定原因。
- [完整下载包](../outputs/course_v2_train43_entity_review_20261011_final.zip)。ZIP SHA-256：`42981581410fe7c5dd6739dbdaa0da47c99577cf0ef6e0370e1bccc684eac743`。
- [逐条实体CSV](../kg_datasets/dblp/course_v2_train43_entity_review_20261011_final/train43_entity_review.csv)。JSONL和更改账本同时包含在包内。
- 显式复核决定：`annotations/course_v2/train43_entity_review_20261011.json`；本地重建入口：`scripts/review_train43_entities.py`。不会执行上传ZIP内的脚本。

初次编译目录 `course_v2_train43_entity_review_20261011/` 保留为中间记录，其中4条受影响关系尚未完成回判；本次最终交付以带 `_final` 的目录和ZIP为准。既有文件没有覆盖或删除。

## 实际变化

| 项目 | CoT修复后的父包 | 本批最终候选 |
|---|---:|---:|
| 训练摘要 | 65 | 65 |
| 本批逐篇源文复核 | 待处理43篇 | 43篇完成一次AI阅读复核 |
| 实体 | 841 | 940 |
| METHOD / TASK / DATASET | 481 / 289 / 71 | 521 / 346 / 73 |
| 正关系候选 | 176 | 175 |
| 合法关系对 | 2,646 | 3,367 |
| 未决关系对 | 2,470 | 3,192 |
| 明确负例 | 0 | 0 |

36篇有实体变化，7篇在本次阅读后保留原实体。变更账本实际记录101次新增、25次边界/类别修订、2次删除；其余22篇NER记录逐字段保持原值。25次修订不全部是类别变化，也不等于25项独立科研事实。

代表性决定：

- 补齐Transformer model、transformer models、模型/算法后缀，修复仅保留局部技术词的边界；删除transfer learning-based中不完整的语法后缀。
- 将reinforcement learning、hybrid annotation保留为方法；将policy learning、generating synthetic training data按当前原文中的操作/目标归为任务。
- 新增字面可定位的时序表示、后验概率估计、知识库构建、查询处理、特征提取等操作。技术类别、具体操作、领域、指标与中间表示分别判断，不由词典统一批量猜标签。
- 移除“measure a text model's multitask accuracy”指标评价标签及“predicting the outputs”过于泛化的任务标签。保留相应原始实体/关系记录，未改成负例。
- TREC Incident Streams和IS新增为命名评测基准/track的DATASET候选，不声称增加了两项独立数据集，也未自动生成评测关系。
- 不从已知论文标题补MMLU、Cora等正文缺失名字；保留LTSMs、precessing等原文拼写。不标URL内名字、未知数据集及模型输出为实体事实。

平面不重叠规则意味着含方法名的动作跨度不能同时内嵌第二个实体。审核JSONL记录了逐篇原因及被已有/更长跨度覆盖的候选，不把这些跳过项声称为自动语义认证。

## 关系如何同步

新增/修改实体后按当前实体全集重建所有METHOD→TASK/DATASET对。未重新判定的对均为UNRESOLVED，不能进普通负例训练。

4条旧正例的端点受修改影响，其中3条已重新阅读原文后同步边界：Transformer model→股票价格预测、verifiers→完成正确性判断、RLQP→tune parameters。RLQP仍保留跨句归属证据与discourse_inferred标识，不伪装成同句直接证据。

剩余1条Neural Networks→predicting the outputs因尾实体删除而隔离于 `train65_relations_deferred.jsonl`，不是NO_RELATION，也不宣称科学事实不成立。原176条正例中的175条作为弱监督候选保留（142 USED_FOR、33 EVALUATED_ON）；本批没有增加新正关系。CoT e13→MMLU-Pro e15的修复保持。

## 验证与限制

最终包的文件SHA、父包输入绑定、65篇身份/原文SHA/字符偏移、实体不重叠、175条关系端点/类型/证据与3,367对全集一致性均复核通过。训练身份与固定dev/test元数据无交集；没有读取test正文。

复用项目真实本地SciBERT tokenizer及现有编码函数，65篇NER严格BIO往返和175条RE实体标记通过；最大350/354 tokens，小于512，无截断。最初预检遇到特殊token的-100标签及未注册保留标记两处检查脚本配置差异，修正忽略位并复用现有 `prepare_tokenizer` 后重跑通过。这不是模型训练或准确率评测。

浏览器已实际打开最终审核页、读取页面内容，并通过原生图片附件展示真实页面截图。截图写入两个本地候选路径均被浏览器工具自身的工作区限制拒绝，故不声称PNG已落盘；页面和下载包可直接打开审核。

本批关闭的是“剩余43篇尚未做整篇AI源文阅读复核”这一工作项，不保证不存在语义争议或漏标。所有trainingAuthorized、formalF1Authorized仍为false，referenceComplete不升为独立金标准。既有12篇正式训练身份锁没有扩写，65篇仍是单独的训练侧弱监督工作集。

下一步集中完成新增/暂缓训练关系和固定dev20的实体、全候选关系裁决；普通RE负例仍需按已有宽口径找到明确否定证据。若该语料无法支持可靠负例，应单独决定监督任务方案，不能静默放宽NO_RELATION定义。最终训练另行授权，V1保持冻结。
