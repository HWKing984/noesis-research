# V1.0 课程系统演示与证据清单

2026-10-10。本文件是操作与交付清单，不是四份最终实验报告。生产模型、图谱与应用冻结；V2.0 数据研究和训练不在本次范围内。

## 本次真正复核了什么

入口：[本地应用](http://127.0.0.1:8765/)。只读健康检查为 `ready`，在用图为 `ai-literature-63686318d85cccb07afb`。

- 复用已有验收器，33项真实HTTP检查及22组离线图数据对照全部通过，包含预期的无效参数拒绝，而不是所有请求均返回200。
- 实际浏览器完成：中文检索→文献详情→加入候选清单→三种图探索→JSON/TXT下载。不是仅验证API或模拟下载。
- 1440、768、375像素三个检索视口无横向溢出、表单有标签；8张成功截图均已目视核对。此次流程未捕获JS异常或HTTP错误。
- 下载JSON为15,400字节，TXT为568字节；JSON中一篇文献、2条候选断言及graphId与在用图一致。
- 本次没有训练、标注、重启服务、重新入库或修改生产源码/运行配置。487项历史全套回归和53项训练相关检查不算本次重新执行。

## 为什么选人工智能文献领域

研究者需要先确定研究方法、任务及可能相关的论文，再阅读原文决定引用。普通书目检索能查标题和作者，但不能直接串联“方法—任务—文献”，也不便追踪同一作者或相同方法相关的其他论文。DBLP提供公开结构化书目，适合作为可追溯基础；神经网络补充题名中的方法、任务和数据集候选，Neo4j支持作者及概念路径探索。系统的意义是缩小阅读与核验范围，而不是代替阅读或自动决定必引文献。

## 演示前准备

先在Neo4j Desktop启动现有 `AI-Literature-KG` 实例。当前应用已经运行，无须重复启动；若关闭服务或重启电脑，在项目根目录的PowerShell中执行：

```powershell
Set-Location 'D:\a-open_source\neo4j'
& '.\.venv-validation\Scripts\python.exe' 'scripts/course_quality_app.py' --port 8765
```

按提示输入数据库密码，保持终端运行。不要把密码写进截图、报告或命令参数。当前配置是 `resources/course_graph_quality_v3_runtime.json`；不要改用历史 `course_graph.py serve` 或默认8766入口。

## 一条约8分钟的演示路径

1. 打开首页，说明20,000篇书目、19,999篇模型输出、1篇抽取拒绝及21,497条候选断言。强调这些数量不代表全量正确率。
2. 在“方法候选”输入 **卷积神经网络**，点击检索，展示固定中英术语展开。为便于复现本次演示，在“题名关键词”再输入 `Integrating Attention Mechanisms into Convolutional Neural Networks for Image Classification`，保留其他默认条件，可定位一篇样例。
3. 点击“查看作者、候选关系与证据”。展示5位作者、DBLP PID、场馆及DOI入口；展示3个模型提及：Attention Mechanisms、Convolutional Neural Networks、Image Classification，以及2条USED_FOR候选。展开“查看来源与模型哈希”。未校准分数0.9994不等于99.94%的事实正确概率。
4. 点击“论文局部图”，查看作者、场馆、概念、提及及候选断言。点击节点查看完整属性；长名称可从路径列表读取，而不是只看截短标签。
5. 依次切换“共享作者·2跳”和“同方法文献·4跳”，说明作者/概念提供跨论文连接，但同方法不是引用关系，也不保证论文之间有真实学术依赖。
6. 点击“加入候选文献清单”，导出JSON与TXT。JSON保留书目、实体、候选关系和来源；TXT只是非正式参考文献草稿。打开下载文件检查标题与DOI。清单仅在当前页面内存保存，刷新前必须导出。

样例ID为 `conf/seeda/VonitsanosESKM25`。也可直接打开[样例局部图](http://127.0.0.1:8765/#paper=conf%2Fseeda%2FVonitsanosESKM25&view=paper)，但直接链接不重建先前的检索条件或候选清单。

| 实际图模式 | 节点 | 关系 | 返回路径 |
|---|---:|---:|---:|
| 论文局部图 | 15 | 18 | 13 |
| 共享作者2跳 | 10 | 11 | 7 |
| 同方法4跳 | 65 | 64 | 30，另有路径未展示 |

图展示最多30条路径，不是194,597个节点的全库画面。图中的圆形布局只表示显示方式；节点距离不是语义相似度。这篇样例用于功能演示，不能作为随机准确率抽检或替代正式评价。

## 报告中的模型成绩如何写

| 结果口径 | Precision | Recall | F1 | 可评覆盖 |
|---|---:|---:|---:|---|
| 原生产NER历史题名测试 | 73.44% | 75.32% | 74.37% | 144/200篇 |
| 原生产端到端RE历史题名测试 | 58.57% | 61.65% | 60.07% | 138/200篇 |
| 扩充NER固定验证 | 79.60% | 77.16% | 78.36% | 167/200篇 |
| 扩充NER+RE固定验证 | 70.78% | 69.43% | 70.10% | 158/200篇 |

全部相对AI参考标签，不是独立人工金标准。新旧验证的对照基线分别为75.14%和66.47%，不能拿原测试74.37%/60.07%作同口径提升基线。扩充模型未通过预先锁定的稀有类别护栏，未上线；[实验冻结记录](course_delivery_frozen_20261010.md)保留完整解释。

首页还披露了另一个新增留出队列的端到端F1 44.28%、覆盖87.5%；它与上述历史测试不是同一队列，不得删除该限制、取较高分代表全部效果，或归入扩充模型的成绩。参考实体输入时RE的99.25%仅是模块成绩，不是当前端到端效果或全量候选边准确率。

四份实验的材料可以按：领域意义与采集清洗→NER标注/划分/真实训练与测试→RE实体对与Pipeline评价→Neo4j入库及应用演示组织。实验要求中的“较高精度和召回率”没有给出数值线，本项目的指标仍可能影响评分；功能验收通过不等于教师认定精度达标。

## 截图与原始证据

本次成功证据在 [20261010_v1_demo_workflow_ready](evidence/20261010_v1_demo_workflow_ready)。这些是本机Edge真实渲染的应用画面，不是Neo4j Browser窗口截图或GPU训练终端截图。

- 检索与中文展开：[桌面](evidence/20261010_v1_demo_workflow_ready/search_1440.png)、[平板](evidence/20261010_v1_demo_workflow_ready/search_768.png)、[窄屏](evidence/20261010_v1_demo_workflow_ready/search_375.png)。
- [作者、实体与关系证据](evidence/20261010_v1_demo_workflow_ready/04_detail.png)。
- [论文局部图](evidence/20261010_v1_demo_workflow_ready/05_graph_paper.png)、[作者2跳](evidence/20261010_v1_demo_workflow_ready/05_graph_coauthors.png)、[同方法4跳](evidence/20261010_v1_demo_workflow_ready/05_graph_methods.png)。
- [清单与导出](evidence/20261010_v1_demo_workflow_ready/06_selection.png)、[实际下载JSON](evidence/20261010_v1_demo_workflow_ready/ai-literature-candidates.json)、[实际下载TXT](evidence/20261010_v1_demo_workflow_ready/ai-literature-reference-drafts.txt)。
- [本次HTTP/离线对照收据](../kg_datasets/dblp/course_v4_runs/course_v1_handoff_http_20261010.json)、[浏览器截图/下载哈希和状态](evidence/20261010_v1_demo_workflow_ready/captures.json)。
- [一次扩充实验结果截图](../outputs/title_expansion_once_20261010/07_relation_development.png)、[53项历史相关检查](../outputs/title_expansion_regression_20261010.xml)、[历史NER测试](course_v4_ner_test.md)、[历史RE测试](course_v4_relation_test.md)。
- [截图与下载复核脚本](../annotations/course_v4/capture_v1_demo_20261010.ps1)复用原CDP helper，自带状态、非空图和下载内容断言；为保护证据，目录已存在时拒绝覆盖，不要直接重复运行。

失败同样留存：Chrome截图工具曾因配置工作区路径拒绝写文件；第一版Edge流程将“正在查询真实Neo4j路径”误判为已加载，空图断言阻止继续，记录在 [失败收据](evidence/20261010_v1_demo_workflow/captures.json)。随后只修正截图工具的等待条件，在独立ready目录成功完成，没有修改应用或覆盖失败记录。

## 交付边界与剩余事项

V1.0本次本机功能演示复核完成。剩余课程交付工作是用户整理四份最终报告并按此路径自行排练，不是继续模型训练。

模型可靠性没有晋级；DATASET/EVALUATED_ON仍稀少；9,062个未决署名保持隔离；概念归一仅38组受控词表，18个版本概念保留；中文仅固定术语展开。没有真实引用网络、全文证据或自动决定必引文献的能力。出版状态只据有限题名前缀，不穷举所有勘误/撤稿写法。

本次未做服务重启恢复、公网/多用户部署、完整WCAG及Core Web Vitals验收；无同场景视觉基线，视觉回归结论为INCONCLUSIVE，不把无溢出与截图可读说成完整视觉/无障碍认证。
