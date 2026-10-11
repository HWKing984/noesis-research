# V2 训练65 + 验证20：摘要表达关系审核包

这是 AI 原文复核工作集；保留旧版本，不训练、不读 test20、不修改生产。

新的 NO_RELATION 只表示完整摘要范围内经逐篇裁决未表达该关系；它与旧版“必须明确否定”不是同一个任务口径。未决项不作负例。

先打开 review85.html；negative_review.csv 可集中审核负例；relation_review.csv 含全部候选对。JSONL 可供现有 SciBERT 编码函数直接读取。

65 篇训练身份已经在本实验 train_members.json 中固定，dev20 与既有固定名单一致。旧12篇身份锁未改；这里是新的65篇实验快照，不声称旧锁自动批准了新增论文。

NER 实体列表已排序并通过实际 BIO 往返编码；RE 已判样本均通过实际实体标记编码，无截断、无权重加载。

## 评测边界

每个候选对都有裁决：正例、摘要范围负例或不确定掩码。裁决完成不等于所有参考确定。仍有掩码时，只能报告已裁决范围的条件分数、覆盖率、未知预测数和完整总体上下界，不能报告完整端到端 F1。

test20 正文仍封存。先审核/接受本快照，再启动一次探索性训练；AI 参考不是独立人工金标准，编码通过不意味着语义正确或模型准确率提升。

## 统计

```json
{
  "version": "whole_abstract_expressed_relation_v2_review_20261011",
  "labelSource": "AI source-read weak reference pending user acceptance",
  "trainingExecuted": false,
  "modelWeightsLoaded": false,
  "newF1": null,
  "testBodyRead": false,
  "productionModified": false,
  "trainingAuthorized": false,
  "relationAdjudicationComplete": true,
  "historicalFiveAmbiguousPairsStillMasked": true,
  "splits": {
    "train": {
      "documents": 65,
      "entities": 941,
      "entityLabels": {
        "TASK": 348,
        "METHOD": 520,
        "DATASET": 73
      },
      "pairLabels": {
        "USED_FOR": 569,
        "UNRESOLVED": 2693,
        "EVALUATED_ON": 57,
        "NO_RELATION": 48
      },
      "legalPairs": 3367,
      "scoredPairs": 674,
      "scoredPairCoverage": 0.20017820017820018,
      "fullyScorableRelationDocuments": 10,
      "sourcesByLabel": {
        "USED_FOR": 53,
        "EVALUATED_ON": 15,
        "NO_RELATION": 16
      },
      "distinctEvidenceScopes": 207,
      "relationReferenceComplete": false
    },
    "dev": {
      "documents": 20,
      "entities": 299,
      "entityLabels": {
        "METHOD": 173,
        "TASK": 103,
        "DATASET": 23
      },
      "pairLabels": {
        "UNRESOLVED": 613,
        "USED_FOR": 261,
        "NO_RELATION": 48,
        "EVALUATED_ON": 52
      },
      "legalPairs": 974,
      "scoredPairs": 361,
      "scoredPairCoverage": 0.37063655030800824,
      "fullyScorableRelationDocuments": 1,
      "sourcesByLabel": {
        "USED_FOR": 20,
        "EVALUATED_ON": 6,
        "NO_RELATION": 14
      },
      "distinctEvidenceScopes": 76,
      "relationReferenceComplete": false
    }
  },
  "encoding": {
    "documentsPassed": 85,
    "scoredPairsPassed": 1035,
    "maxNERtokens": 350,
    "maxREtokens": 354,
    "truncation": false
  }
}
```
