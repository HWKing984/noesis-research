# DBLP人工智能文献标注：v2修订复核包

本包是候选模式和试标准备，不是模型训练/最终实验二交付。NER为METHOD/TASK/DATASET；论文级领域标签独立复核。所有真实数据仍为draft，未测模型F1。

## 开始复核

先读docs/annotation_guidelines_v2.md，再打开kg_datasets/dblp/ner_v2/pilot_review.html。先20条检验边界规则，再逐步完成200篇试标。不要因为词典零命中就确认无实体。经常导出进度，刷新前必须导出；恢复进度必须是同一版本。

如有两名真实标注者，分别使用blind_50_a.html和blind_50_b.html；内嵌数据都是空标注。同一50篇独立标完后再比较、裁决。没有第二人就如实记录单人复核，不虚构一致性。

rare_review.html是多样性受限的训练侧候选，仍未解决DATASET稀缺，不能当无偏测试。near_duplicate_review目录是候选对，需要人工判定，不能自动合并。

## 在独立环境复现

Python 3.13在Windows已验证。解压后，在项目根目录：

```powershell
python -m venv .venv-validation
& '.\.venv-validation\Scripts\python.exe' -m pip install -r requirements-validation.lock.txt
& '.\.venv-validation\Scripts\python.exe' -m pytest tests -q --cov=annotation_v2 --cov=prepare_revision_v2 --cov-branch --cov-report=term-missing
```

浏览器测试需要单独可用的Playwright及其Chromium，不包含浏览器二进制。本次使用本机已有Playwright，版本在evidence/verification.json记录：

```powershell
node tests/test_review_v2.cjs '实际已安装的playwright模块路径'
```

本包带schema、lexicon、完整scripts/tests/docs以及试标输入，能独立重跑上述测试。完整数据审计、20,000篇近重复候选重算和原始DBLP处理还需要原始大文件及完整CSV，不包含在这个小型复核包；不能把单元测试替代来源审计。

scripts/replay_review_package.py可对ZIP及外部manifest验证后，解压到新的独立目录，重跑全部Python测试和v1/v2浏览器测试，并检查加载的模块确实来自解压目录。复用本机验证依赖不是验证另一台电脑的全新安装；复测证据单独保存，不事后修改已封存ZIP。

## 校验实际进度

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/annotation_v2.py '实际主试标进度.jsonl' --reference kg_datasets/dblp/ner_v2/pilot_200.jsonl
& '.\.venv-validation\Scripts\python.exe' scripts/annotation_v2.py '实际主试标进度.jsonl' --reference kg_datasets/dblp/ner_v2/pilot_200.jsonl --entity-gold
```

领域和关系分别加--domain-gold、--relation-gold；关系需先完成实体复核、覆盖全部合法候选对、裁决UNRESOLVED。原始草稿不能通过gold检查。v2不接受含混的--gold，旧annotation_core.py只用于历史v1。

稀有候选用rare_candidates_train.jsonl作reference；盲标用blind_50_reference.jsonl。reference不能用待校验进度本身替代。比较两名实际标注者：

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/compare_entity_annotations.py '实际A进度.jsonl' '实际B进度.jsonl' --reference kg_datasets/dblp/ner_v2/blind_50_reference.jsonl
```

没有真实人工结果时，不存在真实一致性分数。全无实体时agreement报告null，而不是虚高的1。

## 来源与哈希

schema唯一来源是schemas/annotation_v2.schema.json。每条记录绑定该文件SHA-256，元数据和分区对独立reference完整锁定。网页检查不代替Python结构和语义约束检查，二者也不能认证人工身份或判断文本语义必然正确。

abstract_sources包含一次10条DBLP直连arXiv ID的API批量请求结果；9条题名匹配，1条题名变化待核验。benchmark_abstract_sources另含9篇预先核验的基准论文摘要，9条题名与arXiv种子匹配；这些使用arxiv:ID，不能声称已在DBLP的20,000篇子集中。两次请求均记录API来源、获取时间、原始Atom、许可和内容哈希，19份摘要都未加入NER、未人工标注，仅用于训练侧补样和文本单元设计试验，仍需跨来源查重和真实人工复核。

第一批较早的request/records未含新版本的分区与reference_provider字段，现用独立scope_policy.json绑定其原文件哈希、声明未来仅用于训练候选，不改写原始来源日志、不声称当时已保存这些新字段。第二批在请求和记录中直接声明。

API描述性元数据包括摘要，依[官方条款](https://info.arxiv.org/help/api/tou.html)使用CC0；此许可不适用于任意PDF/正文。标题与摘要属于不同文本单元：当前v2契约只支持标题，不允许把摘要直接塞入现有reference后继续标成同一版本。

manifest.json记录ZIP内文件哈希。最终ZIP哈希在与ZIP同级的AI-Literature-KG-v2-export-manifest.json，不放进ZIP自身；请一并保留。旧版v1不会被覆盖，旧人工进度不得静默转换为v2的reviewed。
