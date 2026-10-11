# 第42轮：修订摘要NER/RE真实训练与同dev对照

2026-10-08。使用41版不可变标签、独立42训练合同和薄适配入口，完成一次固定NER训练、一次固定RE训练及同dev四种交叉对照。**有真实新训练与dev成绩，但没有最终测试、模型晋级或线上更新。**完整课程报告继续暂停。

## 实际训练

输入保持train58篇队列/50篇NER/8隔离、267个明确关系对；dev19篇/16篇NER/3隔离、333个明确关系对。train1578个、dev99个未决对屏蔽，不补负例。完整pipeline只评7/19篇，含真正零候选文档；参考107对（84用途/23明确负例），EVALUATED_ON正例仍0。

| 模型 | 训练 / dev输入 | 实际轮数 / 步数 | 选择 |
|---|---:|---:|---|
| SciBERT＋BIO实体头 | 50 / 16篇 | 6 / 150 | epoch6，严格实体micro F1 |
| SciBERT＋实体标记关系头 | 267 / 333对 | 6 / 402 | epoch6，条件三类macro F1 |

沿用父合同种子20261008、lr2e-5、batch2/4、旧08/旧15初始化、deterministic FP32和严格BIO；仅train产生梯度、dev选型，没有重试或超参数搜索。整个运行140.86秒，RTX4060 Laptop GPU；编码器/分类头实际变化、checkpoint保存重载预测一致。输入、权重、实际tokenizer和执行源码前后SHA绑定，旧训练入口及历史模型不改。

## NER：总体小幅增加，稀有类明显退化

同16篇、184个AI参考实体重新推理；下表旧模型为35轮摘要NER，不是题名初始化模型。

| 严格实体指标 | 旧35 | 新42 |
|---|---:|---:|
| Precision / Recall / F1 | 69.23% / 73.37% / 71.24% | **77.50% / 67.39% / 72.09%** |
| TP / 预测 / 参考 | 135 / 195 / 184 | 124 / 160 / 184 |
| METHOD F1，参考116 | 81.98% | 83.64% |
| TASK Recall / F1，参考53 | 58.49% / 52.54% | 49.06% / 53.06% |
| DATASET Recall / F1，参考15 | **86.67% / 66.67%** | **40.00% / 46.15%** |
| 非法BIO转移 | 55 | 39 |

预测更少、Precision上升，但正确实体和Recall下降；不能只用总体F1宣称NER已全面改善。DATASET只有15个相关提及，支持有限，下降必须单列。旧08题名权重在相同摘要上的初始化迁移F1为49.89%；本轮train词典24.17%，不是上述旧35比较基线。

## RE：已判定实体对的条件模块

同333个dev已判对评分，覆盖333/432=77.08%；提供AI参考实体而非模型预测实体。正参考为259用途＋8EVAL，另外66个明确负例。

| 条件模块 | 旧15 RE重新推理 | 新42 RE |
|---|---:|---:|
| 三类macro F1 | 77.89% | 82.13% |
| 正关系P / R / F1 | 84.71% / 99.63% / 91.57% | 87.00% / 97.75% / 92.06% |
| 正关系TP / 预测 / 参考 | 266 / 314 / 267 | 261 / 300 / 267 |
| NO_RELATION Recall / F1，参考66 | 27.27% / 42.35% | 40.91% / 54.55% |

负例仍有39/66误判为用途；新模块也漏6条用途。8个EVAL均匹配，但类型多数基线也在这8对上F1=100%，数量小且重复提及相关，**不能据此证明benchmark关系泛化，更不是完整pipeline的EVAL成绩**。新同范围模块数字不能与36轮旧242对或题名最终测试直接比较。

## 完整pipeline：同7篇重新推理四种组合

旧NER为冻结35摘要NER，旧RE为冻结15题名RE；四种组合均在41版同7篇完整dev上重新推理，候选生成只使用预测实体，不用参考端点掩掉错误。

| NER / RE | Precision | Recall | F1 | TP / 预测 / 参考 |
|---|---:|---:|---:|---:|
| 旧35 / 旧15 | 31.01% | 58.33% | 40.50% | 49 / 158 / 84 |
| 新42 / 旧15 | 49.02% | 59.52% | 53.76% | 50 / 102 / 84 |
| 旧35 / 新42 | 32.45% | 58.33% | 41.70% | 49 / 151 / 84 |
| 新42 / 新42 | **50.00%** | **59.52%** | **54.35%** | 50 / 100 / 84 |

同7篇范围FP109→50、TP49→50，收益主要是少预测错误关系，Recall仅增加1.19百分点。新完整组合FP50/FN34，漏参考主因missing26、boundary8；仍不能将候选边当确定事实。FP50/100是此7篇可判定dev正预测相对于AI参考的错误比例，不能推广为2万篇总体错误率，F1也不能反推该比例。

**旧36/37轮仅5篇、46条正参考的30.00%/26.49%不能直接与本轮54.35%比较。**333/432是条件实体对覆盖，7/19=36.84%是完整文档覆盖，两者不混用。AI同会话标签且dev此前已暴露，全部为开发一致性，不是独立gold或最终测试。

## 为什么仍拒绝晋级

同范围pipeline Precision/F1与Recall回退护栏通过，DATASET参考量15也满足数量门槛；但**完整EVAL参考0＜10、文档覆盖7/19＜80%**，明确阻断。数量门槛通过不掩盖DATASET召回退化，也不等于科学可信度证明。保留既有门槛，不按新分数降低；`qualityPromotionPassed=false`、`modelPromoted=false`。

保留19篇摘要test未做语义读取、标注、分词或推理；没有生产推理、数据库写入、服务重启或新线上验收。2万篇书目、31轮图和线上旧模型原样保持。

## 工程与证据状态

模型运行已成功封存：`kg_datasets/dblp/course_v4_runs/abstract_revised_development_20261008_42`，包含初始/逐轮/最佳指标、训练日志、checkpoint、逐文预测/错误、四种组合、原始参考及源码/tokenizer哈希。模型`passed=true`不是全项目验收通过。

工程首轮全回归**369通过、1失败**：历史`test_snapshot_date_is_explicit_and_not_invented`在C盘默认临时目录rename遇到`WinError5`拒绝访问，原路径单跑仍失败。仅将pytest进程临时目录改为D盘工作区隔离目录，同一原测试**1通过、0.20秒**，随后完整回归**370通过、136.57秒，零失败/错误/跳过**。源码未改、没有skip或吞错；通过结论限定D隔离tmp，C默认路径两次失败的具体锁或ACL触发方仍未知，**不称Windows根因已修复**。

原失败`tests_20261008_round42.xml`、单跑失败`tests_20261008_round42_rename_check.xml`和D盘对照`tests_20261008_round42_rename_D_check.xml`均保留；完整通过输出为`tests_20261008_round42_workspace_temp.xml`。新增42合同/loader/gates检查覆盖递归dev口径、输入不变、未决屏蔽、错源/行/分组拒绝以及已有目录禁止覆盖。工程通过不是370项语义认证；选定NER、条件模块和四种pipeline指标从保存预测重算，不声称重新复算全部epoch或重新训练。

合同：[course_abstract_revised_training_v1.json](../resources/course_abstract_revised_training_v1.json)。数据源仍为41版`course_abstract_eval_attribution_reviewed_20261008_41`；行`contractSha256`保留父36合同，42实验/41修订合同另行绑定，不改历史行来源。

```powershell
# preflight只绑定/校验train/dev；train须不存在的新目录，不重试当前运行或改合同追分。
& '.\.venv-validation\Scripts\python.exe' scripts/train_revised_abstract_models.py preflight
# 如需原配置重现另存，不是下一轮优化或最终测试。
& '.\.venv-training\Scripts\python.exe' scripts/train_revised_abstract_models.py train --output kg_datasets/dblp/course_v4_runs/NEW_FIXED_REVISED_REPRO

# 本轮验证的D盘隔离pytest临时目录；每次全新目录/XML，不覆盖现有失败或通过证据。
& '.\.venv-validation\Scripts\python.exe' -c "import pathlib,sys,tempfile,pytest; validation_temp42=tempfile.mkdtemp(prefix='round42-validation-',dir='kg_datasets/dblp/course_v4_runs'); tempfile.tempdir=validation_temp42; sys.exit(pytest.main(['-q','--basetemp',str(pathlib.Path(validation_temp42)/'pytest'),'--junitxml',str(pathlib.Path(validation_temp42)/'regression.xml')]))"
```

证据入口：[机器核验](../kg_datasets/dblp/course_v4_runs/verification_20261008_round42.json)、[实际训练结果页](evidence/20261008_round42/02_training.png)、[误差/边界证据页](evidence/20261008_round42/04_traceability.png)。真实浏览器展示保存产物，不冒充原始终端训练现场或Neo4j界面；实际拍摄与文件检查通过后才封存机器核验。

下一步基于missing26/boundary8及FP50建立训练侧任务跨度/角色假设，检查稀有实体支持并锁定可检验修订，不立即盲训或按已见dev改超参数。C默认临时目录权限根因保留另行排查；完整EVAL评估、独立参考、8篇训练隔离和知识质量验收仍缺。
