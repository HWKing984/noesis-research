# 人工智能文献标注规范 v3-candidate

用于下一轮真实人工试标，尚未冻结。机器字段契约为schemas/annotation_v3.schema.json，候选边界政策为resources/boundary_rules_v3.json，记录同时绑定二者哈希。旧v2保留用于复现，不再与新进度混用。

本规范使用构造示例讲解，不展示20篇压力测试的逐篇AI答案。盲标者必须未看过AI答案；已经读过答案的人可以复核或裁决，但不能把自己的结果称为该20篇的独立盲标。

## 1. 任务与来源

NER识别METHOD、TASK、DATASET；DOMAIN是独立的论文级多标签，不进入BIO。研究目标是通过方法、任务、数据集提及及书目关系定位候选参考文献；NER不证明论文实际使用某数据集，更不证明论文支持某一论点。

题名是当前唯一文本单位，Unicode字符[start,end)，连续、平面、不重叠。不能补缺失单词、改原文或直接拼摘要。标题未知词必须检查，词典零命中不等于没有实体。结构化作者/年份/场馆解析不是神经NER成果。

初始候选来源分为draft_dictionary_v3、ai_suggestion；实际人员新加的实体标为human。initialDraftProvenance保存初始包来源，与后续人工复核状态分开：真实人员确认AI候选时，不应抹掉AI初始来源。AI定性confidence不是校准概率，不用它自动生成gold。

## 2. METHOD：有中心、有范围的最大方法短语

标具体方法、模型、算法和可辨识技术族。保留改变其结构、组合、训练范式的技术限定，如层级/多视图/深度/逆向/无模型/分布式；不包含一般评价词或非词汇化的approach/method/algorithm/technique载体词。中心是方法，不能把for/via/using后的任务或独立论元吞进实体。

X-based Y、X-driven Y形式在X限定以Y为中心的方法结构/优化机制时，标整体composite；如果是两个完整并列方法或显式关系句，则各自标。语义不足时保留待裁决，不能仅凭连接词自动断言。

构造示例：`Efficient Bayesian-guided Neural Encoder for Spanish Document Classification`可提出`Bayesian-guided Neural Encoder`作为composite METHOD；Efficient是评价修饰，for后的任务另标。平面BIO不重复标内部Neural Encoder；需要父方法族时在人工实体链接层处理，不能从NER自动生成技术组成关系。

命名模型/系统需要上下文技术指称：构造例`LumenNet: A Hierarchical Encoder for Speech Recognition`中的LumenNet可作命名METHOD候选，后面的方法族在另一次出现位置也可标。大写、冒号、连字符本身不证明类型。

## 3. TASK：下游任务与明确技术子问题

TASK包括具体下游任务及技术子问题/操作目标。feature fusion、prompt design、topic identification、ontology alignment属于本项目允许的任务概念；泛称analysis/study/research或单独ontology/knowledge graph不属于TASK。若以后收窄为仅benchmark任务，需要升级政策版本及重标，不能私自混用。

保留对象、语言、模态、应用场景和问题对象数量/结构等限定：构造例`Spanish Document Classification`比`Classification`更具体。评价、效果、资源/训练设定和目标性质默认不并入基础任务跨度，并保留在原文及notes。当前明确口径：Human-Like、Low-Resource、few-shot、Controllable、Disentangled、Safe、Interpretable、Robust默认不并入基础TASK。

这是一致性导向的候选项目政策，不是声称这些属性毫无意义；如果查询需要设定条件，可后续单独设计属性字段或用原题名检索。上下文中某词已是约定任务/模型正式名称的组成部分时，先记录例外待裁决，不机械剪词。

实体概念类型与句法角色分离。某任务在当前标题里充当辅助技术，不能为了套METHOD→TASK关系就把它改成METHOD。术语具体定义模糊、同一操作可能被当方法的案例必须记录，交由真实人员裁决。

## 4. DATASET与表示类方法

DATASET包括明确命名的数据集、评测集及基准套件，保留必要版本号；dataset/benchmark泛称不标。构造例`EvalSuite-X: A Benchmark for Visual Reasoning`可提出EvalSuite-X为DATASET候选，但还需真实语境核验。ARC、PubMed等同形词不能仅凭词典确认为数据集。

表示方案有明确技术限定或是具体技术对象时可以提出METHOD；泛称features/embeddings/representations及Color Features默认不标，不能把所有特征都扩成方法。物理transformer器件不标AI方法；数学/算法diffusion可标，但PDE扩散与生成式扩散不得仅凭同名自动合并。

## 5. mentionForm：single / composite / coordinated

single：单一名称或普通完整技术提及，不等于已完成规范实体链接。

composite：完整方法短语保留显式结构/组合限定，仍是一个连续NER跨度，不重复标内部嵌套方法。只有明确复合结构才用，不按单词数机械判定。

coordinated：多个成员共享中心词，原文省略了部分中心词的连续并列提及。构造例`Word, Sentence and Document Encoders`整体标一个coordinated，不虚构`Word Encoders`的原文跨度，不在NER中拆成三个缺词实体。

coordinated不是单一规范方法，当前不参与个体METHOD→TASK/DATASET候选。它只能保留为可追溯提及，后续若要解析成员，必须另有明确的省略解析和证据方案。不把整组的关系自动传播到每个成员。

## 6. 关系范围及未决项

本轮只考虑同标题、非coordinated端点的METHOD→TASK（USED_FOR）及METHOD→DATASET（EVALUATED_ON）。TASK→TASK技术依赖不在范围；无范围内候选不代表标题或论文没有其他关系。范围外不标NO_RELATION，也不改实体类型迁就关系模式。

USED_FOR要求方法用于任务的文字断言；EVALUATED_ON要求明确评测于命名数据集的文字依据，共现或on不够。范围内明确负例NO_RELATION须有理由和覆盖两端的证据；UNRESOLVED须说明原因，不能当负例训练。

只有实际复核实体、覆盖本轮所有合法候选、没有未裁决项时，才可确认relation_review。页面采用完整题名为证据单元；证据跨度有效只是结构要求，不等于语义已证明。实体或mentionForm编辑使实体/关系复核失效并清空关系。

## 7. 不可变数据与三项复核

可编辑字段只有entities、relations、domains、entity_review、relation_review、domain_review、notes。其余全部字段、嵌套来源、分区、初始候选来源及schema/政策哈希对独立reference锁定。不能拿待检查进度自身当reference。

entity_review、relation_review、domain_review分别确认；draft/unresolved不是gold。reviewed声明必须来自实际人员，带时区时间及human_reviewed来源，不能用AI替代。校验器检查声明与结构，不能认证人类身份或保证语义正确。

实体改变使实体与关系状态失效；领域改动只影响领域；notes改动后三项重确认。初始AI来源保留不动：真实人员删除重标可产生human跨度，但初始来源历史不能抹掉。确认实体不会自动确认关系。

## 8. 20篇与后续200篇流程

未看过AI逐篇答案的真实人员先打开pilot20_blind_review.html，20篇内嵌原文、空entities/domains/relations/notes；独立标注后经常导出，刷新前必须导出。检查使用pilot20_blind_reference.jsonl，而不是200篇reference，因此现在可以完整复核20篇包。

只有用于讲解/候选复核时才打开pilot20_ai_review.html。它带AI候选及理由，不能作为独立盲标。若有两名真实人员，两人各拿独立空白副本；比对、裁决后才能称人工标注。单人就如实记录单人复核。

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/annotation_v3.py '实际20篇进度.jsonl' --reference kg_datasets/dblp/ner_v3/pilot20_blind_reference.jsonl
# 仅当完整20篇经过实际人工实体复核后：
& '.\.venv-validation\Scripts\python.exe' scripts/annotation_v3.py '实际20篇进度.jsonl' --reference kg_datasets/dblp/ner_v3/pilot20_blind_reference.jsonl --entity-gold
```

领域、关系分别使用--domain-gold、--relation-gold，不存在含混的--gold。比较真实A/B进度使用compare_entity_annotations_v3.py；严格跨度一致性不是模型F1，全无实体返回null。当前v3仍是candidate，即使结构及人工声明通过，training_ready仍为false。

真实20篇边界问题解决后再推进完整200篇；这批20篇、200篇试标和100篇定向候选均限训练侧，不进入dev/test。20篇是刻意选出的困难边界样本，不估计自然总体准确率。回归测试检查政策一致性、字段/来源约束，不证明AI建议正确。

## 9. 正式训练前仍需完成

真实人工试标与裁决、低频名称/论文族补样、近重复审核、标题或摘要文本单位选择、冻结模式和独立分组划分尚未完成。原有19份摘要仍只是合法来源候选，不直接拼到title-only参考文件。作者主页消歧在最终合作网络和KG集成前完成；实体识别最多生成MENTIONS，不能自动生成数据集使用事实或无出处全局关系。

旧v2进度不能直接导入v3；已有真实人工编辑须单独保留并显式迁移，不静默重置、改版本或冒称初始AI候选为人类答案。
