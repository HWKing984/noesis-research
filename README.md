# AI-Literature-KG · 人工智能文献知识图谱

## 当前正式交付：2026-10-11 冻结，2026-10-13 截止

V1 为正式系统；V2 仅保留实验，不替换生产。不再采集训练数据、启动训练或无限调参。下方历史记录保留当时状态，**不能覆盖本节交付状态**。

### 启动与验证

1. 在 Neo4j Desktop 启动 `AI-Literature-KG`，数据库 `neo4j`，HTTP `127.0.0.1:7474`。许可条款若需确认，由用户自行处理，脚本不代为接受。
2. 双击 [Start-Delivery.cmd](Start-Delivery.cmd)，输入 Neo4j 密码，保留窗口。密码不保存到文件。访问 `http://127.0.0.1:8765/`。
3. 双击 [Verify-Delivery.cmd](Verify-Delivery.cmd)，验证交付文件哈希、正式图谱、实时检索与多跳图。

正式启动仅使用 `resources/course_graph_quality_v3_runtime.json`，graphId 为 `ai-literature-63686318d85cccb07afb`。不要用历史默认图谱或 V2 权重替代正式版本。数据库不可用会失败，不用离线数据冒充成功。已有图谱不重复导入；新库使用现有图谱限定导入器，不删除其他图谱。

新机器需 Python 3.12+ 与支持 HTTP Query v2 的 Neo4j；首次启动安装 `requirements-validation.txt`。训练环境不是启动检索应用的前提。已安装模型依赖时可执行 `python scripts/delivery.py infer-demo --output outputs/my_demo_inference.json`，实际加载 V1 权重对五篇题名推理；输出路径必须未存在。模型依赖及真实环境版本见 `requirements-training.txt`、`docs/delivery/environment.json`。

### 本版内容

- 20,000 篇 DBLP 书目；19,999 篇完成题名抽取，1 篇超长拒绝；21,497 条候选断言。
- 正式图谱：194,597 节点、263,059 关系。中文术语检索、作者/场馆过滤、实体关系证据、局部图、2/4 跳、候选清单导出。
- [交付报告](docs/delivery/report.md)及 [HTML](docs/delivery/report.html)；[模型权重清单](docs/delivery/models.json)；[真实实验原始对比](docs/delivery/experiment_comparison.json)。
- [演示页面](docs/delivery/demo.html)：运行后访问 `http://127.0.0.1:8765/delivery-demo`。三篇摘要高亮和关系图使用 V2 **AI 辅助初标、用户逐条审核的人工参考标签**，不冒充 V1 模型摘要输出。用户已确认三篇及 Train65/Dev20 全部逐条审核，见 [人工审核来源确认](docs/delivery/human_review_confirmation.json)。
- [图谱导入核验](docs/delivery/neo4j_import_verification.json)、[五篇实际模型推理](docs/delivery/v1_actual_inference.json)、[演示操作文稿](docs/delivery/demo_script.md)。视频、截图和逐文件 SHA-256 清单位于 `docs/delivery`。
- 提交包：`outputs/AI-Literature-KG_20261013_FINAL.zip`，含五份实际 V1/V2 权重、配置、tokenizer、处理数据、源码、实验日志及演示证据；另有 ZIP 收据。旧审核 ZIP 不含权重，不能代替本包。

### 指标必须按任务范围区分

| 版本与任务 | P | R | F1 | 范围 |
|---|---:|---:|---:|---|
| V1 题名 NER | 73.44% | 75.32% | 74.37% | 历史人工复核参考测试 144/200 篇 |
| V1 题名端到端 RE | 58.57% | 61.65% | 60.07% | 历史人工复核参考测试 138/200 篇 |
| V2 摘要 NER | 58.41% | 66.22% | 62.07% | Dev20 人工复核参考 |
| V2 摘要 RE 条件范围 | 12.46% | 42.17% | 19.24% | 361/974 对已裁决，37.06% 覆盖 |

V2 完整 Pipeline F1 为 **null**；以上不是统一排行榜。V1/V2 已裁决标签按用户确认作为人工复核金标准；这不证明第二人独立复核、盲测或全库预测正确。合法 BIO NER 62.87% 与加权 RE 对照均为已暴露 dev 实验，没有正式 test20 成绩、没有上线。V1 另有不同留出队列 F1 44.28%，不能隐去低分只报最佳历史成绩。F1 不等于准确率或全库边正确率。

### 已知风险及延期项

V1 提供带证据的候选文献检索，不是可靠科研事实认证。摘要负例辨别弱、长尾类别不足、9,062 个作者署名未决、概念仅受控词表归一；无真实引用网、全文证据或自动确定参考文献能力。P2 研究全部延后。压缩包不含密码、虚拟环境、Neo4j 安装程序或封存 test20 正文，不能声称裸机离线免安装。

原始结果中的 AI_reference、humanGold=false 等字段保留当时记录，由新增来源确认说明补充，不改标签或重算分数。原视频与部分截图录于本次来源更正前，其旧措辞以当前确认说明为准。

历史 README 完整保留在 [历史记录](docs/archive/README_history_frozen_20261011.md)，其当时状态不覆盖当前交付说明。历史部分研究路径没有收入精简提交包。研究训练脚本保留源码，但完整历史来源及预训练基座未一起打包；交付阶段禁止重训。
