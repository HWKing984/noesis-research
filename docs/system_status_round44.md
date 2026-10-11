# 第44轮：训练侧范围清洗、四篇准入与方法漏标修复

2026-10-08。本轮只处理训练侧标签质量：固定11篇原文范围复核，4篇旧隔离摘要重新准入，修复1处任务边界与1处方法漏标。**没有重训、dev/test推理、新F1、模型晋级或线上图更新。**沿用AI标注路线；初标和同会话自复核不是独立金标准。完整课程报告继续暂停。

## 当前数据及实际改动

| 训练侧 | 第43轮 | 第44轮最终 |
|---|---:|---:|
| 固定队列 / 合格NER / 隔离 | 58 / 50 / 8 | 58 / 54 / 4 |
| METHOD / TASK / DATASET提及 | 378 / 189 / 44 | 403 / 196 / 44 |
| 明确关系：用途 / 评测 / 负例 | 183 / 58 / 26 | 183 / 58 / 26 |
| 未决 / 全部候选实体对 | 1578 / 1845 | 1647 / 1914 |
| 完整关系文档 | 6 | 8（新增两篇真正零候选文档） |

不是新增4篇图谱文献，也不是新增两个负例。原2万条DBLP书目/第31轮生产图不变；本轮54篇新训练输入尚未用于模型训练。DATASET仍44提及、16篇论文，独立名称/上下文多样性不足没有解决。

先锁定原8篇NER隔离＋43轮其余3篇源文范围提醒，再实际逐篇读取完整训练摘要、形成初判、检查生成收据并同会话自复核。范围规则仍用原METHOD/TASK/DATASET与连续平面BIO：TASK包括有对象的计算目标/技术操作，不把裸学科或人类教育技能当计算任务；技术方法家族与泛AI领域、物理同名概念按具体上下文区分。没有从已见dev/test或模型错例挑本轮论文、短语。

四篇准入：

- `2009.03300`：只抽原文GPT-3方法。学科清单不是命名计算任务，摘要没有MMLU名称，不从题名补入。0 TASK/0 DATASET/0候选关系，是范围内真零，不伪造负例。
- `2105.15057`：12个方法提及、2个技术任务，24对全未决。原文`Deep NeuralNetworks`等拼写保留；DNN修饰语中的家族名按发生位置判断并严格BIO验证，不造名为DNN-specific的方法或推广所有子串匹配。
- `2507.22101`：6个方法、5个任务，30对全未决。未来方向中的命名家族/操作允许NER，但不证明实际采用、部署或评测；泛修饰词、指标对象与无名数据集不编成实体。
- `2312.14977`：5个方法提及，0任务/0数据集/0候选。排除物理PDE语境中的同名diffusion models及课程学科列表，不将“生成输出”等泛动作编成命名任务。

仍隔离4篇：`2404.01036`教育技能/泛GenAI范围、`1804.07461`共享头部不连续方法组、`2510.02719`未命名任务/数据与reasoning角色歧义、`2208.08611`低信息平台表述。不是删数据或强行全O。`1708.07747`的benchmarking machine learning algorithms是当前广义技术操作TASK，保留原收据；`2406.01574`并列任务短语保留，平面BIO不擅自拆成重叠实体。

## 两处实体修正与关系保护

`2510.26830` SmoothGuard：TASK从`110:119 reasoning`扩到`110:150 reasoning over textual and visual inputs`，保留对象/模态；实体ID/type与其他13实体不变。触及端点的8对逐个复判：3个基础MLLM家族用途保留、5个防御组件/框架候选仍未决，没有自动继承基础模型用途。其余关系保持原对象。

自复核另发现`2406.01574` MMLU-Pro开头漏掉`14:41 large-scale language models` METHOD。**基础44版及初标已封存，不回写**；另锁方法库存修补合同、创建新的初标与实际同会话复核。保留18个旧实体字面跨度/类型，用`(start,end,label)`重绑定新的实体ID；45个旧关系的类别、原文证据、理由完全不变。新方法产生的15对全为UNRESOLVED，不能从CoT或direct-answer的评测归属继承。

相对43版最终共6篇收据变化，52行逐行字节不变（包括43轮遥感TASK修正）。新准入54对＋新增方法15对均未知；明确267条不变，不能将未决增长解释为模型变差或更准确。本轮使用mle-workflow约束训练侧契约、标签噪声与泄漏边界，没有新增框架或依赖。

三个独立封存产物：

1. 初标：`kg_datasets/dblp/course_abstract_scope_generation_20261008_44`，5份初标收据。
2. 基础复核：`kg_datasets/dblp/course_abstract_scope_reviewed_20261008_44`，5份新复核/53继承。
3. **最终训练输入**：`kg_datasets/dblp/course_abstract_scope_inventory_reviewed_20261008_44`，另修1篇漏标，合计6新/52继承。manifest SHA：`3bbad6603684b1ea47e70ddd9193d8e037eda0d285cea7cbb84050fc21b2921f`。

行`contractSha256`仍表示父36的行序列化规则，本轮修订合同另行绑定。42版训练入口仍锁41版，不能拿新目录替换旧输入或修改封存脚本；后续须另锁实验/薄入口及资源预算。

## 验证与留痕

实际完整回归：**372通过，144.86秒，零失败/错误/跳过**，D盘进程隔离临时目录；JUnit记录144.788秒。新增一个可运行测试覆盖源文绑定、准入未知对、受影响关系必须复判、未知禁止升正、共享头部拒绝准入、库存修补跨度映射/旧证据保留与覆盖保护。目标测试1项通过1.25秒。工程检查不等于人工语义验证。

封存检查重新从58篇原收据生成训练行/全部候选，检查54篇保存offsets/labels的严格BIO往返、52行未变收据、45个旧关系与15新未知对；原训练文本不变，9个dev文件只按字节复制并核验SHA。历史模型/原始预测及保留test/生产配置按二进制哈希核验，未语义读取dev/test，未做新模型推理。C默认临时目录历史rename/WinError5根因仍未修，不以D盘通过声称修复。

浏览器截图展示真实保存产物，**不是原始终端、训练现场或Neo4j界面的仿制**；实际查看两张PNG后封存机器核验。入口：[机器核验](../kg_datasets/dblp/course_v4_runs/verification_20261008_round44.json)、[数据清洗截图](evidence/20261008_round44/02_training.png)、[修正与保护截图](evidence/20261008_round44/04_traceability.png)、[最终统计](../kg_datasets/dblp/course_abstract_scope_inventory_reviewed_20261008_44/summary.json)、[实体ID重绑定记录](../kg_datasets/dblp/course_abstract_scope_inventory_reviewed_20261008_44/inventory_patch.json)。

```powershell
# 输入与原文绑定预检；所有输出必须是不存在的新目录，不自动重试或覆盖。
& './.venv-validation/Scripts/python.exe' scripts/review_train_entity_scope.py preflight
& './.venv-validation/Scripts/python.exe' -m pytest tests/test_train_scope_review.py -q
# 历史初标/复核入口的实际产物已保留；不重新生成或修改其判断追dev分。
# 单独库存修补入口：
& './.venv-training/Scripts/python.exe' scripts/patch_train_method_inventory.py --output kg_datasets/dblp/NEW_TRAIN_INVENTORY_PATCH
```

## 还需推进

优先补训练侧DATASET的独立论文/名称/上下文多样性及有证据的正/负关系，剩余4篇隔离只在原文歧义可解时准入；不能用新的NER数量证明稀有类已修复。随后锁定使用本轮最终快照的单一训练实验、同范围对照和稀有召回护栏，当前新标签没有收益成绩。已有42轮完整dev EVALUATED_ON=0、覆盖7/19仍阻断可靠性；保留test19篇不消费。

独立参考、模型泛化、概念/作者长尾消歧仍未解决；`qualityPromotionPassed=false`、`modelPromoted=false`。没有写库、服务重启或新线上验收；仍为31图/旧题名模型。完整课程报告不在本轮扩写。
