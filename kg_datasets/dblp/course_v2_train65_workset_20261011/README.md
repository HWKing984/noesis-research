# V2 train65 原始训练摘要与实际补标

完整原文：`train65_sources.jsonl`（65篇）；70篇来源与5篇旧隔离记录也保留。

本批复用已修订12篇，另逐篇补标10篇；剩余43篇见 `pending43_sources.jsonl`。旧标签/收据以legacy命名单独保存，不能自动当作新V2标签。

新增实体与关系见 `batch10_ner_candidates.jsonl`、`batch10_relation_ledger.jsonl`；最直观的审核入口是 `train65_review.html`。关系只接受有原文证据的候选正例，未决不变成负例。

已通过本地冻结SciBERT tokenizer生成BIO和实体标记输入，见 `ner_encoded.jsonl` 和 `relation_encoded.jsonl`。这是输入可编码检查，不是模型训练。没有新增F1。

12篇原训练身份锁保持不变；65篇是独立标注工作集，不是绕过原准入规则的正式训练锁。dev20上传包仅做结构性检查且单独归档；test20只使用身份元数据，不读取正文。

所有新旧AI标签均不是独立人工金标准。当前没有合格负例、dev覆盖不完整，普通三分类RE仍不准入。
