# 人工智能文献标注规范 v2-candidate

本版替代v1用于下一轮试标，尚未冻结，不授权直接扩大正式标注或报告模型效果。机器契约唯一来源是schemas/annotation_v2.schema.json；网页标签、Python校验器和导出包均读取同一文件。

## 1. 任务定义与应用

NER识别METHOD、TASK、DATASET三个类别。DOMAIN改为论文级多标签分类，独立保存领域标签及原文证据，不再进入BIO序列。实体识别的结果仅支持论文MENTIONS实体；不能仅凭数据集名称生成USES_DATASET或EVALUATED_ON。

应用目标：按任务、方法、数据集提及和领域寻找候选参考文献，再查看作者、场馆、DOI及匹配证据。是否支持论点需阅读原文；作者ID和书目来源类型也需核验。标题语料只能支撑标题级任务，不能代表摘要/正文信息完整性。

## 2. 标注单位与不可变数据

原文为既有CSV题名，Unicode字符右开区间[start,end)，连续、平面、不重叠。不得改写原文、补摘要或按Topic标签猜答案。作者、年份、场馆来自结构化解析，不是深度学习NER成果。

publicationId、title、text、textKind、year、type、doi、topics、groupId、sourceCsvSha256、schemaVersion、schemaSha256、intendedSplit、samplingStratum、ambiguityFlags、textSource均不可编辑。除此之外，不允许自创字段。来源信息嵌套内容也锁定。

可编辑内容只有entities、relations、domains、三项review和notes。reference必须使用独立保存的原始包，不能拿待检查文件同时充当reference。哈希和结构不等于人为复核真实性。

## 3. METHOD边界

标技术方法、模型、算法及明确技术族；不标无指称的our method、new approach，也不把电力transformer当成Transformer架构。

完整保留能区分架构或方法的限定词，排除一般评价性词语：

| 表达 | METHOD范围 | 原因 |
|---|---|---|
| novel neural network | neural network | novel只是评价 |
| efficient graph neural networks | graph neural networks | efficient通常是效果描述，不自动当架构名称 |
| Deep Convolutional Neural Networks | 完整短语 | deep明确架构深度 |
| Siamese Neural Network | 完整短语 | Siamese区分孪生架构 |
| Vision Transformer | 完整短语 | Vision区分方法族 |
| Hierarchical Transformer | 完整短语 | hierarchical限定架构组织 |
| Multi-view Graph Convolutional Networks | 完整短语 | multi-view限定输入/组织方式 |

上述范围是候选一致规则，不靠词典命中范围决定gold。词典若只命中Neural Network，人工仍需扩展到正确完整边界。

论文命名的模型/框架名称、缩写可以标METHOD，但必须能从标题或随后核验的真实摘要确定其技术指称：RoadFormer、BEI-DETR、SwinSUNet等不能因为词典没收录而漏掉，也不能把任意大写词都当METHOD。不确定缩写是模型、数据集还是普通术语时记notes，相关复核保留unresolved/draft。

`RoadFormer: A Vision Transformer for Road Extraction`是构造教学例：可以分别标RoadFormer和Vision Transformer，二者是不同出现位置，不自动声称是同一个标准实体。全称和缩写同时出现分别按原文标，不做跨片段合并。BERT与BioBERT不能仅靠相似字串归并。

## 4. TASK与DATASET边界

TASK必须是具体任务，标完整的最小可独立解释短语，如Named Entity Recognition、Fraud Detection、Medical Image Segmentation、Multi-lingual Geoparsing。不标泛称study、analysis、research，也不将单独Knowledge Graph自动当任务。

`Medical Image Segmentation`整体标TASK；同一文字中的Medical Image也可以作为论文healthcare标签的证据。领域证据不是第二个NER实体，允许与TASK重合。

DATASET标实际命名的数据集/基准，保留必要版本/编号：CIFAR-10、FB15k-237、MMLU-Pro。dataset、benchmark等泛称不标。ARC、PubMed、COCO等同形词需查上下文，不能凭词典命中认定为数据集；“PubMed检索平台”也不必然是某个机器学习基准。

缺实体标题必须实际检查遗漏后确认。词典零命中不等于无实体；是否高质量论文、是否确实属于AI是另一项筛选质量复核。

## 5. DOMAIN：论文级标签

可选标签由schema生成；当前候选标签涵盖医疗、遥感、自动驾驶、安全、农业、能源、生物信息、金融、教育、制造及other。每个标签保存至少一段支持该判断的题名证据，同一论文可以多标签，不要求领域文字与NER跨度互斥。

一般AI方向如machine learning不是应用领域标签。不能由算法名称推断行业，不能将医疗题名中的方法效果扩大为临床效果。无法从题名确定时保持待判定；以后加入真实摘要需升级文本单位契约，不拼接无来源摘要。

领域分类与实体、关系分别复核和评估。IN_DOMAIN表达领域归属，不自动生成METHOD APPLIED_TO DOMAIN；后者若需要应另设计有证据的关系任务。

## 6. 关系候选与完整性

首版范围为同一个标题内的所有METHOD→TASK及METHOD→DATASET候选对；不是跨句摘要关系抽取。每个候选对分别人工判断：

- USED_FOR：方法明确用于任务；不是“成功解决”的效果承诺。
- EVALUATED_ON：明确有评测/实验于命名数据集的文字依据，仅出现on或数据集名称不足。
- NO_RELATION：在当前标题及预定范围内，人工判断没有此断言，保存判断理由，不等于整篇正文不存在关系。
- UNRESOLVED：上下文不足或待裁决，必须说明原因；不是负例，不能进入确定关系训练标签。

正例和明确负例保存证据字符跨度，覆盖两个实体；网页当前使用完整标题为证据单位。JSON中的head/tail是entities数组下标；实体改变后必须重新核对所有关系。

空relations不代表负例或已复核。只有实体复核完成、全部合法候选对有确定判定、没有UNRESOLVED时，才能确认relation_review；无合法候选对也要先实际复核实体。

## 7. 三项状态与gold检查

entity_review、relation_review、domain_review互相独立，状态为draft、unresolved、reviewed。reviewed要求实际人员姓名/编号、带时区时间及human_reviewed来源。未复核状态不携带已复核人员/时间声明。

三种检查分别为--entity-gold、--relation-gold、--domain-gold。关系gold还依赖实体gold及候选覆盖；领域gold不要求关系已标完。v2没有含混的--gold参数。

实体增删使实体与关系复核失效并清空关系；领域增删只使领域复核失效。修改通用notes后三项重新确认。结构有效不能证明语义正确，脚本不能认证真实人类身份。schema仍为candidate时，training_ready一律false。

## 8. 如何试标和双人复标

先用pilot_review.html（交付页为AI-Literature-KG-v2-pilot-review.html）熟悉规范。每完成几条导出JSONL，刷新会丢失未导出的修改。恢复进度使用同一版本JSONL，旧v1进度不可直接导入；若已有真实v1复核，请保留并显式人工迁移。

另外准备blind_50_a.html及blind_50_b.html：同一50篇标题，内嵌数据没有词典答案。两名实际标注者独立完成，不事先讨论逐条答案，之后比较严格跨度与类别一致性，再由实际裁决人员处理分歧。没有第二人就如实记录单人复核，不假造双人一致性。

这50篇仍属于训练侧试标，不能转入独立测试。正式dev/test从零标注并在可用条件下独立复标，不能直接复制词典结果。

## 9. 正式标注前的门槛

冻结前检查：边界规则是否可执行、低频类别名称和论文族多样性、摘要能否合法获取、筛选误命中、近重复审核、人工一致性。1500—2000是初始预算，不是必须凑满的整数。

先由训练侧试标估算实体率与不确定性，再确定测试规模和取样规则，冻结后不为凑support改测试集、用测试信息补词典或挑种子。稀有类别定向候选只进训练；可另外预注册挑战集，但不能冒充自然分布测试。

## 10. 摘要与作者身份

摘要补充保存source_url、retrieved_at、content_hash、来源论文ID、标题匹配和license/source_policy；未知许可不得自动随公开包分发。DBLP元数据的CC0不自动延伸到其他来源正文。正式NER/关系使用摘要前还需制定分句、长文本及新文本哈希契约。

作者最终应从原始DBLP完整区分大小写的名称标识映射到主页profile key，保留消歧编号和合并重定向。无法唯一确认的用未消歧作者记录，不靠归一化姓名强行合并。作者身份审核在合作网络及最终KG集成前完成，不影响先检验NER边界规范。
