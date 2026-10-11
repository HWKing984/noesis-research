# V2：训练名单锁修复与固定 dev20 原文准备

日期：2026-10-11。此文是工作记录，不是最终课程报告。

## 结论与当前入口

独立审核发现的训练名单绑定缺口已修复。固定 dev20 的官方摘要全部采集成功，20/20，0失败；未获取 test20 正文。训练和评测仍未获准，没有新模型或新 F1。AI 标注与用户提供的独立审核不称为独立人工金标准。

当前正式元数据包：`kg_datasets/dblp/course_v2_sampling_20261011_roster_locked_v2`。

当前开发原文包：`kg_datasets/dblp/course_v2_dev_sources_20261011`；`dev_review.csv` 有完整摘要、身份、官方来源、官方标识字段与 UTF-8 文本 SHA，可直接审核。

正式入口为 `course_v2_sampling.prelock/validate_lock/bind_content/finalize`；每次先验证 `course_v2_training_roster`。新增 `generic_prelock` 仅保留元数据工具能力，不作为正式实验准入入口，也不能跳过正式内容绑定/最终门禁。旧封存包使用各自代码快照，只重放历史，不作为新实验入口。

## 1. 训练身份与数据版本锁

- 在代码中固定审核过的上游 manifest SHA：`a48a65f4f86e499e2dd7e06bb3361cabc810493110c33f478c027475af64db94`，不由调用方提供所谓可信名单。
- 验证上游的原12篇 `split_lock.json`、六个核心 JSONL、身份映射与历史排除文件的字节哈希。
- `training_roster_lock.json` 绑定规范身份、组ID、原文SHA及全部允许的身份字段，另保存六个核心文件组成的 `trainingDataVersionSha256`。名单重排可接受，修改、缺失、重复或添加成员不可接受。
- 正式预锁的 `samplingFrame` 额外记录 roster 版本/哈希与训练数据版本哈希。修改协议字符串为 v1 不能绕过正式训练锁。
- 扩充训练数据必须显式建立新训练版本和审核锚点，不能沿用当前门禁偷偷加入论文。
- 这是受控工作区中的版本漂移检测，不是能抵抗操作者重写全部代码和记录的数字签名。

实际真实总体反例复验：原12篇通过；空名单、替换为真实 `2502.00003`、增加到13篇、删除到11篇均拒绝。形式/文件锁通过不代表这12篇已有可靠负例或语义认证。

## 2. 不重新抽样、不修改旧标签

当前 dev/test40 身份文件与上一正式 `_final` 清单字节相同。仍是官方 cs.AI 2025年2月固定列表3,654、历史身份排除57、题名保守隔离18、剩余3,579，固定种子20261011，dev20/test20、挑战0。

原六个训练 JSONL 与上游保持字节一致。`pooling→MNIST` 旧候选保留原样；当前裁决保存在独立 `negative_adjudication.json`：维持 `UNRESOLVED`，`adjudicated_not_admitted`，不得导出 `NO_RELATION`。审核原文及其SHA也随包保存。

“架构没采用 pooling”不是独立方法 pooling 与 MNIST 间的评测否定。当前训练侧仍为85条已判正例候选、0可靠负例、599未决，不能声称补齐负例监督。

## 3. 固定 dev20 原文采集

- 只请求锁定的20个dev身份，使用官方 `/abs/ID` 页面，串行请求间隔至少3.2秒，超时15秒；不调用模型，不读取新test正文，不因失败换身份。
- 20/20成功，0失败；20份原始页面、20条摘要、请求日志、文本和响应SHA已保存。
- 官方 `citation_title/citation_arxiv_id/citation_abstract` 必须存在且不重复；源身份和题名与锁定列表对应，HTML字符引用解码后的摘要直接作为输入文本，不改写、不用搜索片段替代。
- 官方标识字段按页面原样保存；如果未给出`v`修订号，不猜成v1，也不宣称所有来源版本已复核。
- 已检查已知历史/训练文本SHA及开发文档间的精确重复；这不能排除改写、会议/期刊扩展版等语义近重复。
- 原文采集状态是 `source_collected_pending_near_duplicate_review_and_annotation`。标注0篇；来源版本与近重复仍需复核，关系参考尚不可评分，不运行最终内容准入。

采集包保存清单、原始HTML、参考JSONL、请求记录、摘要CSV及manifest。只读验证重解析原始页面，复核固定身份、正文与SHA、请求范围、统计与未准入状态。

## 4. 实际检查与失败留痕

正式相关检查实际运行96项，全部通过（Python3.12.4，真实pytest进程）。结果：`outputs/v2_roster_20261011_checks_v2`，包含收集的测试ID、源码SHA、JUnit、日志和运行收据；runId `2d27b578-2a0d-42e3-b1f4-be59fcb06369`。这些是工程检查，不是96项论文语义认证，不代表模型准确率。

原先训练锁构建及94项检查也保留。第一次以隔离Python启动摘要脚本时因脚本未显式加入同目录模块路径，出现 `ModuleNotFoundError: course_v2_sampling`；该错误发生在任何网络请求/输出创建前。修复同目录导入后加上两项隔离CLI回归，重新构建当前 `_roster_locked_v2`；未覆盖首次构建，也未改旧采样包。

原 `_final` 的基础Python快照验证也实际重放通过；这不等于重新执行父包239项测试。原采样ZIP保持原SHA `90eac965619f09d6e3f6bf81596bbbb4f9a7e22620523840c89bf81695231084`；六个V1受保护文件哈希保持不变。没有访问生产Neo4j或证明当前线上健康状态。

## 5. 审核与重放

新审核包：`outputs/v2_roster_and_dev_audit_20261011_v2.zip`；其收据单独保存成员SHA、ZIP SHA、实际验证和测试运行身份。包中不含模型权重或新test内容。除只读验证依赖外，也补齐运行相关pytest所需的上游原路径/源文件与smoke夹具，避免依赖原工作区隐式文件；上一仅采样/采集验证的打包版本保留。截图是实际浏览器渲染的文件证据页，不伪装成Neo4j或训练控制台。

在项目根目录，或按相同相对路径独立解压后运行：

```powershell
python -I -B kg_datasets/dblp/course_v2_sampling_20261011_roster_locked_v2/source_snapshot/scripts/prepare_v2_sampling.py --verify kg_datasets/dblp/course_v2_sampling_20261011_roster_locked_v2
python -I -B kg_datasets/dblp/course_v2_sampling_20261011_roster_locked_v2/source_snapshot/scripts/collect_v2_dev.py --bundle kg_datasets/dblp/course_v2_sampling_20261011_roster_locked_v2 --verify kg_datasets/dblp/course_v2_dev_sources_20261011
```

`-B`防止在manifest绑定的历史快照目录内写入/重编译pyc。验证不下载、不训练、不调用模型。

## 6. 仍需完成（不是本批已完成）

封存后独立解压的736个文件SHA与同一96项pytest重放通过；Windows长解压路径曾漏解47个文件并被门禁拒绝，短目录重放通过。详见[独立重放与短路径说明](course_v2_roster_portable_replay_20261011.md)，该补充记录不改变ZIP内的历史版本。

1. 对固定dev20完成来源版本/近重复复核，完整实体标注与逐候选关系参考；维持AI标签来源记录。
2. 从不同训练论文补足强证据RE负例。不得把未决当负例，不依据dev标注挑选有利test或调整抽样。
3. 按独立流程准备test20正文和参考，封存后只用于最终评测；本批仍仅保存其元数据身份。
4. 上述条件通过后，才锁训练配置、启动受控NER/RE训练。当前训练/评测授权均为false，新指标为空。

按`ecc:mle-workflow`的数据契约与版本门禁执行：工程锁、语义标注、训练准入和模型晋级分别验收，不能互相代替。
