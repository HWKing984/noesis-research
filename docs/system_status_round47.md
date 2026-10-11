# 第47轮：合法BIO解码的冻结对照，未通过晋级

2026-10-08。在[固定合同](../resources/course_abstract_decoder_v1.json)下复用第46轮选中的NER/RE权重，只推理同16篇已暴露摘要dev，比较argmax与既有合法BIO解码器；没有重新训练、改标签或使用保留测试。argmax实体与关系预测逐项重现第46轮结果。

| 同范围指标 | 原46 argmax | 47合法BIO |
|---|---:|---:|
| 非法BIO转移 | 65 | 0 |
| NER严格跨度/类别F1（184参考实体） | 70.84% | 69.84% |
| 完整流程P / R / F1（7篇，84参考正关系） | 29.59% / 59.52% / 39.53% | 25.91% / 59.52% / 36.10% |
| 预测正关系 / 命中 / 错报 | 169 / 50 / 119 | 193 / 50 / 143 |

合法序列不等于正确实体，扩大错误端点反而增加关系候选。本轮明确拒绝合法BIO候选，不修改生产图或模型。指标相对于AI参考标签，完整EVALUATED_ON参考仍0、覆盖7/19，不代表独立最终测试或全图准确率。

[运行清单](../kg_datasets/dblp/course_v4_runs/abstract_decoder_development_20261008_47/manifest.json)保存原始logits、两种预测、逐token变化与错报/漏报记录。D盘隔离临时目录下[375项回归](../kg_datasets/dblp/course_v4_runs/tests_20261008_round47_workspace_temp.xml)通过（命令墙钟160.08秒）；C默认tmp历史rename问题未修。第47/48轮共同由[第48轮机器核验](../kg_datasets/dblp/course_v4_runs/verification_20261008_round48.json)及[实际结果截图](evidence/20261008_round48/02_training.png)封存。截图是保存结果的浏览器可视化，不是原始训练终端截图。

后续结构性弃权实验见[第48轮当前状态](system_status_round48.md)，不要将本轮合法BIO结果作为上线默认配置。
