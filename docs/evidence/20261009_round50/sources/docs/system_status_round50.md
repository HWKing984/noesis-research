# 第50轮：当前候选文献检索系统完成真实在线验收

2026-10-09。用户从Neo4j Desktop启动AI-Literature-KG后，确认7474/7687可连接，恢复既有8765只读检索服务。实际数据库进程使用Desktop自带JRE21；上一轮独立CLI的Java23/许可状态不代表这次Desktop启动环境。本轮未修改全局Java、接受许可、安装依赖、重新入库或替换模型，服务保持运行供用户查看。

## 实际验收结果

| 范围 | 本轮结果 |
|---|---|
| 当前版本 | `ai-literature-ed16399925fac2a599ed`；31轮包及清单哈希与配置一致 |
| 实际图谱计数 | 文献20,000；6类节点合计194,639；关系263,059；候选断言21,497 |
| 数据库检查 | 8项只读查询；逐类节点/关系与清单相等，出边跨图谱版本计数0 |
| HTTP检查 | 综合32项 + 既有图探索脚本15项；含成功、空结果、分页、无效参数、Host/方法限制，均符合预期 |
| 中文检索 | 知识图谱、大语言模型、扩散模型、机器翻译、AAAI会议，5组中英文有序首页一致；不是比较全部分页或中文全文抽取 |
| 作者与证据 | 主页PID/身份查询、未决署名单篇隔离、署名纠正、原文跨度/SHA/模型来源、超长拒绝条目均通过 |
| 多跳界面 | 共享作者4节点/3关系/2路径；同方法63节点/62关系/30路径，明确提示另有路径；不是引用关系或整库全图 |
| 真实导出 | 实际点击加入清单和原生下载按钮，保存1篇书目、1条候选断言及来源证据JSON、参考文献草稿TXT |
| 工程回归 | 本轮378项通过，零失败/错误/跳过，墙钟136.29秒、JUnit136.218秒；D进程隔离tmp，C历史rename未修 |
| 原生Node检查 | 现有`test_course_ui.cjs`实际通过：快照导出、文本安全、清单移除/重置、陈旧查询、链接及有向路径解释 |

[综合实际响应/查询](../kg_datasets/dblp/course_v4_runs/application_acceptance_20261009_50_final.json)、[图探索15项](../kg_datasets/dblp/course_v4_runs/graph_explorer_acceptance_20261009_50.json)、[本轮JUnit](../kg_datasets/dblp/course_v4_runs/tests_20261009_round50_complete.xml)保留。首次综合验收脚本误将小写化AAAI术语与原大写字符串比较，检查失败而非查询失败；[原失败响应](../kg_datasets/dblp/course_v4_runs/application_acceptance_20261009_50.json)和[失败源码](evidence/20261009_round50/failed_application_check_source.py)保存，修正检查后另存final，没有覆盖原失败或改数据。

## 浏览器与截图

按browser-qa技能额外核验真实表单、错误年份、Tab/Enter检索与节点激活、三种屏宽及控制台/网络。浏览器观察15个请求全部200/204，无控制台错误/警告；8个输入有标签，Tab有可见焦点，2010年被原生范围校验拒绝。未做完整axe/WCAG或屏幕阅读器审计，不能宣称全面无障碍。单页缓冲LCP168ms、layout-shift累计0.03127仅为本地诊断，不是完整CLS算法或现场Core Web Vitals成绩，INP未测。

真实应用截图：[桌面节点图](evidence/20261009_round50/04_graph_desktop_round50.png)、[平板](evidence/20261009_round50/05_graph_tablet_round50.png)、[手机](evidence/20261009_round50/06_graph_mobile_round50.png)、[作者身份](evidence/20261009_round50/08_author_identity.png)、[候选清单与下载](evidence/20261009_round50/07_selection_downloads.png)。三张局部图截图与31轮同URL/屏宽/高度基线逐字节一致，页面源码也未变；不是以没有基线冒充视觉通过，也不覆盖所有界面状态。截图来自实际Edge加载真实Neo4j应用，不是离线结果页。

[真实下载JSON](evidence/20261009_round50/downloads/ai-literature-candidates.json)、[TXT草稿](evidence/20261009_round50/downloads/ai-literature-reference-drafts.txt)、[浏览器观察摘要](evidence/20261009_round50/browser_qa.json)、[原始捕获回执](evidence/20261009_round50/capture_receipt.json)保存。浏览器工具直接输出项目文件的访问检查曾拒绝，未绕过其路径检查；DOM观察改为正常内联读取，本摘要不冒充被拒绝的原始导出。键盘节点首次探针仅截取500字符漏看ID；按完整938字符JSON解析确认成功，原页面源码未改。

[封存核验](../kg_datasets/dblp/course_v4_runs/verification_20261009_round50.json)区分`liveApplicationPassed=true`和`qualityPromotionPassed=false`，绑定配置、源码快照、查询响应、回归、截图与下载文件；不复制模型权重，不触碰保留test。

## 交付边界与下一步

当前“本机可追溯候选文献检索系统”的检索→详情证据→局部/多跳图→候选清单→真实导出闭环已验收，冻结31图/原题名模型与当前只读页面作为课程工程交付版本。入口为[本地应用](http://127.0.0.1:8765/)；恢复方式见[运行说明](course_v4_runbook.md)。清单仅当前页面内存保存，刷新前需要导出；关闭服务或重启电脑后需重新启动应用。

这不是高可靠知识事实系统、正式参考文献格式生成器或自动必引决策。49轮补充dev仍完整0/8，旧摘要dev完整EVALUATED_ON0；作者未决9,064个、概念仅受控词表合并、题名抽取错误及无引用网络等未解决。没有新训练、模型质量成绩或质量晋级。高可靠摘要升级、公网/多人服务、完整无障碍及教师/用户最终验收为后续独立事项；完整报告按用户要求暂不撰写，不为工程收尾无限追加训练轮次。
