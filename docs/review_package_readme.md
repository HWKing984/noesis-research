# DBLP实体试标复核包

全部标注为自动词典草稿，需要真实人工复核。未训练模型，未测正式F1。

主试标：打开AI-Literature-KG-pilot-review.html（200篇）。

补充训练候选：打开AI-Literature-KG-rare-review.html（100篇，定向选样，不能当测试集）。

先读AI-Literature-KG-annotation-guidelines.md，填写真实标注者，修改和补漏后逐条确认。每隔几条导出JSONL，刷新前必须导出；可导入上次进度恢复。未解决的歧义保留draft。CSV只是查看副本，正式进度使用网页导出的JSONL。

本包的validation/annotation_core.py无需第三方包，Python 3.10+可运行。在解压目录按实际文件名检查：

```powershell
python validation/annotation_core.py '实际主试标进度.jsonl' --reference pilot/pilot_200.jsonl
# 所有记录真实人工复核后加--gold；原草稿会失败，这是预期行为。
python validation/annotation_core.py '实际主试标进度.jsonl' --reference pilot/pilot_200.jsonl --gold
python validation/annotation_core.py '实际稀有候选进度.jsonl' --reference rare/rare_candidates_train.jsonl
```

表格中的is_ai等判断列尚未填写，不代表筛选质量已测定。目录evidence记录本次审计/测试；不含原始1GB快照或完整Neo4j项目。文件manifest记录包内容哈希，export_manifest记录zip哈希。

本包只完成第一批材料准备，不是完整实验二最终提交结果。返回人工进度后，还需模式冻结、正式金标准、划分、深度学习训练、独立测试和课程报告补充。
