# 实验四：候选事实图谱与文献检索应用（2026-10-07，轮次18）

## 当前结论

已完成可校验图谱导出、幂等导入代码、只读检索API与页面；当前**尚未完成真实入库和成功检索验收**。用户截图确认实例 `AI-Literature-KG` 为 RUNNING，实例版本2026.08.0，目标业务数据库为 `neo4j`，而非实例名。HTTP发现接口正常，认证查询返回401。真实导入失败凭据已保存，提交批次为0；没有创建约束、写入节点或清空用户数据，也未修改账户、密码、实例配置。

本轮不训练、不重新执行NER/RE最终测试、不修改AI标签和旧模型权重。复用轮次17冻结pipeline预测，而不是用AI参考实体或模块测试结果假扮端到端抽取。

## 1. 要解决的问题及用途

面向人工智能文献检索和候选参考文献发现：普通书目检索提供标题、作者、年份、场馆；题名中提取的方法、任务、数据集提及及候选关系提供更细的检索入口，并能够回溯到原始题名及抽取版本。例如按方法BERT与任务classification联合查找候选论文，再查看作者、场馆、DOI和预测证据。

此系统不能替代阅读论文、判断结论是否支持写作论点或决定“必须引用哪篇”。DBLP本版没有CITES数据，因此不展示引用网络、被引次数或从引用关系计算的推荐。标题规则筛选的20,000篇不等于全部人工智能领域文献，也不等于20,000篇都完成了神经网络抽取。

## 2. 数据规模与来源分层

当前唯一有效导入包：[course_v4_graph_20261007_18_final清单](../kg_datasets/dblp/course_v4_graph_20261007_18_final/manifest.json)。图谱ID为 `ai-literature-2fd435585d2db5c94e0a`。总计96,616个内容节点、109,790条关系；成功导入时另有1个CourseGraph控制节点。

| 节点 | 数量 | 来源与含义 |
|---|---:|---|
| Publication | 20,000 | DBLP结构化XML解析的书目，不是神经NER输出 |
| Person | 72,694 | 规范化作者姓名，未完成同名消歧或别名解析 |
| Venue | 3,205 | DBLP中的会议/期刊字段 |
| Concept | 272 | 模型提及的大小写规范化字符串；类型METHOD/TASK/DATASET，不进行语义别名合并 |
| Mention | 305 | 138篇题名上的冻结NER预测，保留字面跨度与来源 |
| Assertion | 140 | 冻结NER→RE的正向候选断言，139条USED_FOR、1条EVALUATED_ON |

| 关系 | 数量 | 解释 |
|---|---:|---|
| AUTHORED | 88,762 | 作者→文献，保留作者顺序 |
| PUBLISHED_IN | 19,998 | 文献→场馆；两篇缺失不捏造场馆 |
| MENTIONS | 305 | 文献→预测提及 |
| DENOTES | 305 | 提及→字符串概念 |
| SUPPORTED_BY | 140 | 候选断言→作为题名证据来源的文献；不是已证实结论 |
| HAS_HEAD / HAS_TAIL | 各140 | 断言→头/尾提及，保留方向和实体边界 |

138篇题名、148个模型候选实体对；8个NO_RELATION不写成正向事实。62篇评估未决仍排除；不把未决当作负例。原始Topic规则CSV保持不变，本轮不导入ABOUT，以免与神经网络关系混淆；不创建无来源的CITES、EDITED、PART_OF。

原始关系约定中的方法→任务或方法→数据集，在实际存储中使用带证据的Assertion节点表达：

```text
Publication ─MENTIONS→ Mention ─DENOTES→ Concept
Assertion ─SUPPORTED_BY→ Publication
Assertion ─HAS_HEAD→ 方法Mention
Assertion ─HAS_TAIL→ 任务/数据集Mention
```

Assertion保存predicate、candidate状态、model_prediction来源、原始题名、Unicode字符偏移（通过端点Mention）、标题哈希、NER/RE权重哈希、冻结运行清单哈希、三类分数。confidence为未校准softmax分数，不是事实正确率。模型预测错误不会因高分而自动升级为确定事实。

## 3. 预处理检查与本轮修复

导出前校验轮次17冻结运行清单及其全部文件、canonical references与书目标题绑定；校验节点唯一性、边端点存在、关系ID唯一、预测实体原文跨度、方向/类型、概率有限且归一、模型输出标签与argmax一致。生成包保存输入和输出SHA256；导入前再次核验文件和计数。

实际发现一个旧数据限制：`journals/corr/abs-2412-20086` 的署名中，第2和第5位均规范化为Min Zhang（题名MAFT: Efficient Model-Agnostic Fairness Testing for Deep Neural Networks via Zero-Order Gradient Search.）。两个署名是否同一真人，本轮不能判断；关系ID加入position，保留两条署名，不静默去重。Person仍标记normalized_name_not_disambiguated，未来有DBLP主页标识再另建消歧版本。

初次18导出因为重复关系校验失败，文件保留；18_ready为中间校验版；加入明确modelApplied标记后的18_final为当前版本。前两者不导入、不当作课程最终包。模型未检测到实体，与未对该论文执行模型抽取，在页面分别提示。

## 4. 导入流程与失败状态

1. 核验包及计数；密码来自交互输入或进程级环境变量，不作为CLI参数写进源码、包、报告。
2. 先执行只读连通性查询；认证失败立即停止，保存failed凭据，不自动修改密码。
3. 成功连接后仅建立CourseNode和CourseGraph的唯一ID约束。使用CoursePublication等隔离标签和graphId，避免与已有用户节点混合。
4. 每500行参数化UNWIND/MERGE；节点、关系有稳定ID，作者顺序参与关系ID。只在新建时写属性，不使用DELETE、DROP或数据库重置。
5. 所有批次提交后，逐类型核对Neo4j实际计数与包清单；完成才把CourseGraph状态设为completed。中途失败保留已提交批次，使用新凭据文件重试同包，不覆盖旧失败记录。应用拒绝尚未完成导入的图谱。
6. 当前真实记录：[导入尝试1](../kg_datasets/dblp/course_v4_runs/graph_import_20261007_18_attempt1.json)：Neo4j HTTP401、batchesCommitted=0、liveDatabaseImported=false。没有数据库写入成功证据。

本地客户端使用已安装版本支持的Query API `/db/{database}/query/v2`，检查响应中的errors，不把202接收状态当作查询成功；所有用户筛选条件作为Cypher参数。接口依据[Neo4j Query API官方说明](https://neo4j.com/docs/query-api/current/query/)，不依赖旧版已弃用的transactional HTTP API。

## 5. 应用功能与边界

[应用源码](../scripts/course_graph.py)与[页面](../resources/course_literature.html)复用已有Python环境、标准库HTTP服务，不额外安装Web框架或图可视化库。服务器仅监听127.0.0.1，检查Host、无CORS、无任意Cypher入口，页面数据通过textContent显示；模型/书目链接只允许HTTP(S)。这是本地课程演示，不是已经部署、开放公网或多人使用的服务。

| 接口 | 作用与约束 |
|---|---|
| GET /api/health | 检查真实Neo4j与当前图谱completed状态；未就绪503 |
| GET /api/publications | q、author、venue、method、task、dataset、year筛选；limit1–100，offset0–20000；稳定排序、hasNext |
| GET /api/publication?id=... | 查看书目、署名顺序、场馆、模型提及、候选断言、原始证据及哈希，生成非正式参考文献草稿 |

无效/重复/未知参数400，文献不存在404，连接/认证/导入未就绪503；内部异常500，不暴露密码或内部查询详情。失败不回退到本地JSON伪装数据库结果。姓名搜索不能消除作者身份歧义；方法/任务/数据集检索只覆盖候选模型输出，未命中不等于全文不存在。当前method与task/dataset条件作用于同一条断言，task和dataset不能同时匹配一个尾实体。

## 6. 真实检查、截图与局限

按API设计技能统一验证、分页和HTTP失败语义；按Python测试技能先保存RED再实现与修复，新增7项检查覆盖模型来源/跨度/负例、参数边界、HTTP响应错误、真实导出及篡改、导入幂等与失败状态、只读HTTP合同、成功返回的合成接口检查。合成成功场景明确不算真实Neo4j成功验收。

[全套回归](../kg_datasets/dblp/course_v4_runs/tests_20261007_round18_all.xml)：345项通过，0失败/错误/跳过。[新应用代码覆盖率](../kg_datasets/dblp/course_v4_runs/coverage_graph_20261007_18_final.json)：264/294语句，89.80%；不是完整分支覆盖，也不是所有关键路径或真实数据库兼容性已验证。

按browser-qa技能实际打开本地应用、提交检索检查失败提示、Tab检查焦点、年份2010原生校验、清空表单；真实375/768/1440 CSS视口的DOM检查无水平溢出。实际网络主页200、图标204、health/search503符合当前认证失败，控制台的503资源错误已披露，不声称网络全绿。

Lighthouse snapshot：[原始报告](evidence/20261007_round18_retry/lighthouse.json)，Accessibility100、Best Practices100、SEO75（缺少meta description）、Agentic Browsing100，26通过/1失败。此自动分数不代表完整WCAG通过：只检查了局部键盘行为，未进行屏幕阅读器验收；Core Web Vitals未测。无视觉基线，视觉回归结论INCONCLUSIVE；因认证失败，整体成功查询交付DO NOT SHIP / 未验收。

实际截图（均为当前失败状态，不冒充入库成功截图）：

- [桌面应用1440截图](evidence/20261007_round18_retry/app_1440.png)：真实已安装Edge；[拍摄记录](evidence/20261007_round18_retry/captures.json)。
- [768视口原始Chrome截图](evidence/20261007_round18_retry/chrome_app_768.jpg)、[375移动视口原始Chrome截图](evidence/20261007_round18_retry/chrome_app_375.jpg)：真实设备视口，原生JPEG质量30，已检查移动图文字与完整布局；[DOM与保存记录](evidence/20261007_round18_retry/browser_dom.json)。
- Edge按窗口375截图实际被裁切，不能作为移动布局通过证据；该失败/不适用素材保留，不放入报告主图。第一次PowerShell5抓图因ToHexString不支持失败，已改为兼容的BitConverter；失败拍摄记录仍保留于round18目录。

已知模型错误完整保留：唯一EVALUATED_ON预测把NeurIPS识别为DATASET，不能将该查询结果作为论文真实使用数据集的证明。pipeline F1仍为60.07%，DATASET低频、AI参考、69%测试覆盖及题名证据限制继承[冻结关系测试报告](course_v4_relation_test.md)。本轮未将模型应用于全部20,000篇，不提高或重报模型成绩。

## 7. 接下来执行与复现

先在Neo4j Desktop中对AI-Literature-KG点击Connect，使用用户名neo4j尝试登录目标neo4j数据库，并执行 `RETURN 1 AS connected;`。RUNNING证明实例在运行，不能证明给定密码有效。当前凭据被服务器拒绝；需要确认实际用户名/密码，不重新创建数据库、不擅自重置密码。当前本地页面为 `http://127.0.0.1:8765/`，仍显示未就绪。

确认可登录后，从项目目录执行以下命令；密码会在终端隐藏输入。不要将密码写到脚本或截图。新输出文件名避免覆盖第一次失败凭据：

```powershell
& '.\.venv-validation\Scripts\python.exe' scripts/course_graph.py verify
& '.\.venv-validation\Scripts\python.exe' scripts/course_graph.py check --database neo4j --user neo4j
& '.\.venv-validation\Scripts\python.exe' scripts/course_graph.py import --database neo4j --user neo4j --output kg_datasets/dblp/course_v4_runs/graph_import_20261007_18_attempt2.json
& '.\.venv-validation\Scripts\python.exe' scripts/course_graph.py serve --database neo4j --user neo4j
```

当前8765演示进程使用原先被拒绝的凭据；如需新凭据，先停此演示进程再启动，不能仅刷新网页更新进程内密码。实际后续验收：核对节点/关系计数，重复导入新凭据检查不增量；标题检索、作者/场馆/年份检索、方法-任务联合筛选、数据集候选误报展示、未知文献404和无结果提示、证据/哈希回溯、参考文献草稿；再拍真实成功页面和Neo4j查询界面。完成这些前不写“实验四已全部完成”。

重现检查：

```powershell
& '.\.venv-validation\Scripts\python.exe' -m pytest tests/test_course_graph.py -q --cov=course_graph --cov-report=term-missing
& '.\.venv-validation\Scripts\python.exe' -m pytest tests -q
```

无需新模型、容器、前端构建系统或依赖；未来有已测性能瓶颈、公开部署或新模型版要求时再扩展。
