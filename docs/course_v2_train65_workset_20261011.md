# V2：实际训练原文交付与首批10篇补标

这是数据进度说明，不是完整课程报告，也不代表V2训练准入通过。

## 原训练数据已经找到

源目录：`kg_datasets/dblp/course_diverse_train_roles_20261010_56_final`。

- 原文来源70篇；65篇进入旧NER输入，5篇保留旧隔离记录。
- V2已修订12篇全部属于65篇；逐篇arXiv身份、原文及UTF-8 SHA完全一致。
- 对照固定dev20/test20身份，65篇身份交集为0；与dev20原文SHA交集为0。这里没有独立证明语义近重复完全不存在。
- 本批65篇是新的标注工作集，不扩大或重签原12篇正式训练身份锁。

## 交付文件

目录：`kg_datasets/dblp/course_v2_train65_workset_20261011`。

| 文件 | 内容 |
|---|---|
| `train65_sources.jsonl` | 完整65篇原摘要、身份、来源URL、文本SHA |
| `source70_inventory.jsonl` / `quarantine5_sources.jsonl` | 原70篇库存、另列5篇旧隔离来源 |
| `legacy_ner65_unreviewed.jsonl` / `legacy_relation_inventory_unreviewed.jsonl` / `legacy_receipts70.jsonl` | 旧AI标签及收据，单独保存，不自动继承到新监督 |
| `batch10_decisions.json` / `batch10_entity_changes.json` | 逐篇明确的AI判断及相对旧实体的新增/撤回账本 |
| `batch10_ner_candidates.jsonl` | 新增10篇完整实体候选，仍为AI弱标签 |
| `batch10_relation_ledger.jsonl` | 新实体集合重建411个合法对：25正例候选、386未决 |
| `ner22_candidates.jsonl` / `relation_positive_candidates.jsonl` | 复用12篇加新增10篇的合并候选，不是正式准入数据 |
| `ner_encoded.jsonl` / `relation_encoded.jsonl` | 本地冻结SciBERT BIO与实体标记实际编码，未拟合模型 |
| `pending43_sources.jsonl` | 下一批待复核43篇完整原文 |
| `train65_review.html` / `train65_review.csv` | 原文审核入口，HTML高亮新增10篇实体、展示候选关系证据 |
| `dev_intake/` | 外部dev20原始草稿及结构核对结果；不参与训练编码 |

压缩包：`outputs/v2_train65_sources_and_batch10_20261011.zip`，640,130字节。

SHA-256：`2e97459d8ca7a438ad095f8c33311081719ac22c49106773b6caf4458fba5efb`。

## 本次实际补标

| 训练论文arXiv身份 | 实体数 | 合法关系对 | 接受的正关系候选 |
|---|---:|---:|---|
| 1704.04683 / RACE | 6 | 0 | 0 |
| 1705.03551 / TriviaQA | 11 | 18 | 用途1、评测1 |
| 1809.09600 / HotpotQA | 14 | 0 | 0 |
| 1903.00161 / DROP | 12 | 0 | 0 |
| 1903.10676 / SciBERT | 11 | 30 | 用途3 |
| 1909.03546 / DyGIE++ | 15 | 50 | 用途7 |
| 1909.07755 / SpERT | 11 | 30 | 用途2 |
| 2010.12812 / 简单流水线实体与关系抽取方法 | 16 | 63 | 用途1、评测3 |
| 2308.03279 / UniversalNER | 32 | 220 | 用途7 |
| 1906.06127 / DocRED | 18 | 0 | 0 |

表中方便识别论文的名称不作为模型输入；正文未出现的方法名称没有补为实体。

新10篇：METHOD50、TASK74、DATASET22，共146个实体；USED_FOR21、EVALUATED_ON4，共25条提及级正关系候选。

复用后22篇：METHOD149、TASK132、DATASET42，共323个实体；USED_FOR89、EVALUATED_ON21，共110条提及级正关系候选。21条评测关系来自7篇论文，仍不足以保证稀有类别泛化。共享原文证据的别名/重复提及不能当作独立事实。

部分数据集摘要没有具名或可识别的具体方法端点，因此合法关系对为0。这不意味着没有知识，而是本Schema无法用缺失的方法实体组成关系。未从题名或常识补模型名字，也不把论文内部描述的负样本训练当作本数据标签。

## dev20接收情况

逐篇比对固定来源身份与文本SHA，275实体无非法偏移/重叠，54正关系引用与证据匹配；单独上传CSV/HTML与ZIP内版本逐字节一致。未执行ZIP内Python脚本。

按所列实体枚举834个合法METHOD→TASK/DATASET对，仅54正对已提出；780对仍未裁决或未决。其中1对有显式UNRESOLVED示例，其余不能假定为NO_RELATION。

该检查是结构核验，不是穷尽语义审核，不准正式F1。dev内容没有回流训练；test只用了固定身份元数据，没有获取/读取正文。

## 已执行的验证与未完成事项

22个NER输入通过现有`encode_row`及严格BIO往返检查，110个正关系通过现有`encode_pair`及实体标记检查；均未截断、无编码隔离。33个输出文件SHA、输入绑定、压缩包CRC及包内对应字节已逐项通过。

实际浏览器打开审核HTML，DOM核对65个论文章节、146处新实体高亮；页面截图已返回到本次会话。浏览器工具的文件保存被其配置的路径权限拒绝，因此没有声称生成项目内PNG文件；压缩包交付不受影响。

沿用`ecc:mle-workflow`的数据版本与隔离原则：源数据/旧标签/新候选分开；只复用现有编码器，不新增训练架构或准入平台。

仍未完成：

1. 43篇旧训练摘要的V2语义复核，直接使用已交付原文继续补标。
2. 当前宽口径Schema的可靠负例仍为0。不能用缺少表达、组件角色不同、训练集用途或类型合法性制造负例；普通三分类RE未准入。
3. dev20实体完整性与全部合法关系对还待裁决；不足以选择正式模型或计算完整Pipeline指标。
4. 最终test参考标签仍未准备，保持正文封存。

本批没有新训练、模型推理、F1或生产替换。下一批继续实际标注，不新增一套审核系统。
