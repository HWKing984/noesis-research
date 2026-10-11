# DBLP人工智能文献：v3边界修订与试标包

工程准备包，不是实验二最终训练成果。实体为METHOD/TASK/DATASET，领域独立；新增mentionForm与不可变初始来源。当前全部候选仍为draft，模式未冻结，真实人工完成数0，未训练模型。

## 从20篇真实人工试标开始

先读docs/annotation_guidelines_v3.md，再打开kg_datasets/dblp/ner_v3/pilot20_blind_review.html。此页20篇原文没有AI答案、实体、领域、关系或备注。标注者必须未看过AI逐篇答案；看过答案的人可复核/裁决，但不能算这组的独立盲标。

每几条导出JSONL，刷新会丢失未导出的修改。20篇页使用pilot20_blind_reference.jsonl，不能用200篇reference或把进度自身当reference。完成实体不等于完成领域/关系。

pilot20_ai_review.html是带AI候选和理由的讲解/复核页，不是盲标。source_review目录原样保留用户三份AI评审材料及哈希；原始46跨度未改写，按本版候选口径整理为45跨度（第6篇合并组合方法），均非人工gold。低频候选与这20篇均只能进入训练侧。

## 新边界与兼容性

机器契约唯一来源为schemas/annotation_v3.schema.json；候选边界政策为resources/boundary_rules_v3.json，每条记录绑定二者哈希。METHOD取方法内部的最大连续技术短语；TASK包含技术子问题、保留对象/语言等限定；共享中心词并列保存为coordinated提及，不能自动拆成规范个体或传播关系。

本轮关系只覆盖非coordinated METHOD→TASK/DATASET。TASK→TASK依赖在范围外，不是负例；“确认关系”只表示范围内候选复核。无候选不代表论文没有关系。NER只能支持MENTIONS，不能证明使用数据集。

v3进度与旧v2不兼容：多了mentionForm、boundaryRulesSha256和initialDraftProvenance，AI来源不能改成人类初始来源。旧版页面/数据/ZIP保留，旧人工进度不得静默转换。当前200篇包中20篇是AI候选，其他180篇仍沿用不完整词典草稿；没有宣称通用预标注准确率提高。

## 校验、复标与环境

Python3.13/Windows及本机隔离环境已验证；训练环境另建。本包不含Python或浏览器二进制，重建依赖使用根目录实际验证锁：

```powershell
python -m venv .venv-validation
& '.\.venv-validation\Scripts\python.exe' -m pip install -r requirements-validation.lock.txt
& '.\.venv-validation\Scripts\python.exe' -m pytest tests -q --cov=annotation_v3 --cov=prepare_revision_v3 --cov-branch --cov-report=term-missing
node tests/test_review_v3.cjs '实际Playwright模块路径'
```

结构检查和三个gold范围分开：

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/annotation_v3.py '实际20篇进度.jsonl' --reference kg_datasets/dblp/ner_v3/pilot20_blind_reference.jsonl
# 完整20篇经过真实人工实体复核后才使用：
& '.\.venv-validation\Scripts\python.exe' scripts/annotation_v3.py '实际20篇进度.jsonl' --reference kg_datasets/dblp/ner_v3/pilot20_blind_reference.jsonl --entity-gold
& '.\.venv-validation\Scripts\python.exe' scripts/compare_entity_annotations_v3.py '实际A.jsonl' '实际B.jsonl' --reference kg_datasets/dblp/ner_v3/pilot20_blind_reference.jsonl
```

关系/领域另用--relation-gold、--domain-gold。结构与声明检查不能认证真实人工身份或语义正确；candidate模式的training_ready永远false。双人一致性不是模型F1，没有第二人就记录单人复核，不虚构分数。

本包包含生成脚本、三份原始评审、独立旧reference、schema/政策、测试、页面，可复建新输出目录：

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/prepare_revision_v3.py --previous-data kg_datasets/dblp/ner_v3/legacy_reference --review-dir kg_datasets/dblp/ner_v3/source_review --output kg_datasets/dblp/ner_v3_rebuilt
```

20篇回归使用候选政策及AI建议做结构/一致性断言，不是独立正确性评测。测试输出应无skip；浏览器测试只使用内存合成标注者，未改真实JSONL。解压复测复用本机隔离依赖及Playwright，不是另一台电脑的新装验收。

## 来源与封存

沿用两批共19份真实摘要来源候选：10份DBLP直连arXiv中9题名匹配、1待核验；另9篇外部基准论文与arXiv种子匹配。仍未加入标题标注或宣称属于DBLP子集。API描述性元数据按[arXiv条款](https://info.arxiv.org/help/api/tou.html)为CC0，不延伸到所有PDF/正文。使用摘要前先升级文本单位、查重并人工复核。

12对近重复仍待实际裁决；作者主页消歧仍待完成。完整原始XML和20,000篇CSV不在小包中，重跑全量来源审计需要原始大文件。不要把本包测试通过等同数据语义/模型/Neo4j产品验收。

ZIP内manifest.json绑定每个文件；整ZIP哈希在同级AI-Literature-KG-v3-export-manifest.json，不放进ZIP自身。独立解压复测证据单独保存replay-evidence，不修改封存ZIP。本包保留旧v1/v2页面仅用于回归，当前工作入口是v3。
