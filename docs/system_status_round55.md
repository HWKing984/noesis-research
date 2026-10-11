# 第55轮：检索修复与真实应用验收

2026-10-09。按审计顺序完成应用正确性优先项；不是模型质量升级，不编写完整课程报告。

## 已完成

- 联合查询改为同一论文、同一方法概念下分别匹配TASK与DATASET尾端，允许不同实体提及；不要求同一尾节点有两个类型。按方法汇总尾端，避免嵌套重复关联扫描。
- 方法/任务/数据集默认精确名称及受控别名匹配；保留显式子串模式并提示会混入其他模型。题名、作者、场馆仍为原有模糊检索。
- 增加题名前缀信号提示和过滤：默认隐藏14条撤稿/通知信号，9条更正类可单独检索；原始记录和断言没有删除。无信号也显示“未经独立核验”，不伪装出版商认证。
- 详情、图谱中的论文属性、候选清单、JSON及TXT导出保留文献状态提示。状态是应用派生字段，不是改写DBLP或训练标签。
- 8765和8766均启动修复后的质量应用，使用51包 `ai-literature-2ba355fe96d011524e55`；旧31图与默认导入配置保留，未重入库。
- 更正Agent历史提案中从F1推导错误边比例的表述。当前主入口以本页为准，旧轮次页面不是实时状态。

## 实际验证

Python testing技能指导先补11个失败用例，再实施修复；随后相关23项通过。全套402项回归通过（494.56秒），0失败/错误/跳过；运行期间优化了查询，最终查询版本另重跑13个直接相关用例通过，并完成以下真实数据库验收。因此全套结果与最终查询重验分开记录，不把旧进程的导入缓存冒充最终查询的全套运行。

- 19项真实HTTP检查通过，7组查询与已校验离线图逐项对照ID、排序、分页状态；包括3组任务+数据集、GPT-4精确/模糊、CNN中英文。
- GPT-4精确搜索返回1篇；显式子串返回4篇，含MiniGPT-4/GeoGPT4V/GPT4EAD。精确模式不把这些当同一概念。
- 联合实例：`neural reranking` / `subjective quality of machine translation` / `naist` 返回 `conf/aclwat/NeubigMN15`。
- 默认撤稿标题查询无结果，显式包含/仅信号可找回；详情和局部图有警示。错误枚举、越权graphId、注入式文本都按约定处理。
- 浏览器真实表单操作确认精确/模糊、联合查询、默认隐藏/显示14条、详情警示、加入清单、JSON与TXT导出内容警示。导出内容已检查，本次未独立核对原生下载文件落盘。
- Browser QA技能要求三尺寸及失败说明：最终CDP实测1440/768/375视口全部无横向溢出、输入/选择器具备label、实际联合结果可见、无捕获到的页面异常或HTTP错误。保存全页截图并目视检查；没有视觉基线，视觉回归为INCONCLUSIVE，不声称完整WCAG或INP达标。
- 图包哈希再次核验通过，节点/关系未改。服务当前就绪不等于开机自启，关闭进程后仍需重新启动。

## 未掩盖的失败

首版真实联合请求返回503（客户端有20秒请求时限），未将其当空结果；保留 `search_repair_acceptance_20261009.json`。改为单次分组查询后最终19项通过，最慢约4.01秒，单次本机耗时不是性能SLA；首个503未独立获取Neo4j服务端根因日志，不断言唯一原因。

浏览器连接器截图未及时返回，未计为成功。原Edge `--window-size` 截图的375宽图出现裁切，保存在 `20261009_search_repair`，不作为手机布局通过证据。最终改用CDP强制真实视口并测量宽度，另存 `20261009_search_repair_cdp`，不覆盖初次图片。

## 使用与复现

推荐打开 http://127.0.0.1:8765/ ，8766为同一修复版本的另一入口。Neo4j先启动；如应用停止，在项目目录执行下列命令并交互输入数据库密码，保持终端运行：

```powershell
.venv-validation/Scripts/python.exe -B scripts/course_quality_app.py --port 8765
```

另一个终端可用 `--port 8766` 启动第二入口。不要用 `course_graph.py serve` 作为当前应用入口：它保留旧查询用于历史复现，且其源码哈希被训练流水线绑定。本轮在既有质量应用中修复运行时查询，而不是破坏历史训练/导出契约。`resources/course_graph_runtime.json` 仍是历史31包；当前质量应用读取 `resources/course_graph_quality_runtime.json`。

## 证据

- 实现：`scripts/course_quality_app.py`、`resources/course_literature.html`。
- 新测试：`tests/test_course_search_repair.py`。
- 只读验收：`annotations/course_v4/check_search_repair_20261009.py`；已存在的最终输出拒绝覆盖，重验须另选输出名。
- 最终接口记录：`kg_datasets/dblp/course_v4_runs/search_repair_acceptance_20261009_final.json`。
- 全套回归：`kg_datasets/dblp/course_v4_runs/tests_search_repair_20261009.xml`。
- 最终截图：`docs/evidence/20261009_search_repair_cdp/captures.json`及三个PNG；脚本 `annotations/course_v4/capture_search_repair_20261009.ps1` 包含真实查询与视口断言，拒绝覆盖证据。

## 下一步

系统查询优先缺陷已修。模型仍需跨论文NER边界/关系角色与完整开发支持，之后按冻结方案训练比较、满足门槛才做最终测试。概念长尾与9,062次未决署名仍待有证据地解决。未训练、未读取保留测试正文、未替换权重、未重写标签/图谱；不能据402项工程回归宣称模型可靠。
