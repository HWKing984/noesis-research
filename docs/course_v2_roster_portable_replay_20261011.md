# V2审核包：独立解压重放补充记录

这是封存ZIP之后的验证记录，不修改ZIP内的文件、旧manifest或标签。

审核包：`outputs/v2_roster_and_dev_audit_20261011_v2.zip`。

- SHA-256：`8940c2c2026511ab0aad01cf4259d5ca852934b36b3ec6c3175632935c053e08`。
- 大小12,942,118字节，736个成员；ZIP CRC、每个成员SHA及独立短目录解压后的全部736个文件SHA通过。
- 独立目录中实际再次运行同一96项工程测试，全部通过，runId `85c43eb6-28fc-4ff4-8733-9affe54da7ec`。不统计为192个独立检查；不是论文语义金标准或模型准确率。
- 独立短目录中的基础Python采样验证器、dev原文验证器均实际返回通过；仍未授权训练/评测、dev20未标注、test正文请求0。
- 收据：`outputs/v2_roster_portable_replay_20261011.json`。
- 独立pytest日志、JUnit、ID清单和运行收据：`outputs/v2_roster_independent_checks_20261011`。

## Windows解压限制及真实失败

首次把包解压到较长的用户临时目录，Windows `Expand-Archive` 没有解出47个深层文件，缺失路径长度均超过常见260字符限制。两个只读验证器均因缺文件拒绝通过；没有忽略缺文件、删除清单条目或改manifest让它通过。

改用短目录 `D:/Temp/kg-6eaff9e8` 解压，全部文件SHA检查与两项便携验证通过。建议审核时使用如 `D:/kg-review` 这类短目录，不要直接解压到长的下载/聊天附件嵌套目录。已有目录不要覆盖；选空的新目录即可。

执行命令见主工作记录 `course_v2_roster_and_dev_20261011.md`。只读验证须使用 `-I -B`；pytest重跑需要有pytest的Python环境，不需要模型权重、GPU或联网。相关测试所需的上游原路径和smoke夹具已随包提供。

当前工程身份锁修复与原文采集验收通过，仍不代表V2正式训练准入：dev语义/来源版本/近重复复核、完整标签、可靠训练负例及test独立参考均需继续。
