# 第59轮训练源 TASK 边界复核（AI候选，不是标签修改）

日期：2026-10-10。复核者：Codex AI；同会话源文本判断，`independentHumanGold=false`。

## 范围与结果

只解析 `course_diverse_train_roles_20261010_56_final/references.jsonl` 和 `reviewed_receipts.jsonl` 的70条训练来源；65条满足完整NER资格。未解析任何开发集、开发预测、测试标注或预留测试内容，未执行模型推理或训练，未修改已封存文件。

读取摘要侧现行约定和52轮生成/自复核规则：TASK包含有明确对象的计算子操作及连续复合任务；原始Unicode跨度；保留具体任务限定；不从题名引入摘要不存在的实体。题名v3规则不能直接替代现行摘要契约，不统一扩成最大句段，也不机械删去已有few-shot等限定。

本次未找到可以无条件自动修改的“同文已标完整TASK在另一处被标成更短同词组”错误。用每篇完整NER训练来源的已标TASK字面词组逐一匹配同文所有出现位置（忽略大小写），检查其他已标TASK是否严格落在完整词组内部：结果为0条。这是有界的字面一致性检查，不能证明所有训练标签语义正确，也不会覆盖缺失实体或近义表达。

以下仅保留3篇源文本绑定的范围裁决候选：1篇可在后续另行裁决，2篇暂缓；第59轮三者均不修改，不进入新训练标签。不为凑数量制造第四处错误。

来源绑定：

- 快照manifest SHA256：`b45ac3019819f67a56e33abc68b8d5a1115fe4b251b0f3d8d47d6dd5e77aa4e8`
- references SHA256：`84c8b8b51d1cc8d951f23cae1fec365855719bfd7b4e33216c6900b0fb053972`
- reviewed_receipts SHA256：`2ad552219bdf753d23152dad461aa8014a205f4ed05d26ff034478a16bd91281`

70条来源/receipt逐条校验：`split=train`、源文本SHA256及`validate_receipt`全部通过。以下before/after均检查原文精确Unicode切片、有效跨度和与其他实体不重叠；尚未生成新receipt或将候选纳入训练。

## A. 可进一步单独裁决：异质变化检测限定

- arxivId：`2303.17448`
- sampleId：`sample-ec29ee1c93f8281fc505`
- entityId：`e5`
- textSha256：`3e3f6fb322df501ee4ccc9e4b392a7ab167a585d6b88679a90763bed4877e940`
- upstreamReceiptSha256：`f71c6b79816a21fa643956acd88f761d13e18fcd39d5b9f1e912445b6ffdf7f5`
- 原句 `[131:260]`：

> In the past decade, the heterogeneous CD problem has significantly benefited from the development of deep neural networks (DNNs).

```json
{
  "before": {"entityId":"e5","start":169,"end":171,"text":"CD","label":"TASK"},
  "afterCandidate": {"entityId":"e5","start":155,"end":171,"text":"heterogeneous CD","label":"TASK"}
}
```

理由：此句明确将异质变化检测作为问题对象；`heterogeneous`限定输入的异质性，能够与一般CD任务区分，不是结果好坏评价。若采用“此处保留明确任务领域限定”的局部裁决，155:171是唯一连续原文候选；不加入泛称`problem`，不吞入方法或后续谓词。

反证与限制：同文另一完整字面出现`heterogeneous CD`位于666:682，而e15也只标680:682的`CD`。因此不能宣称已有一处完整标注、另一处截短。e15所在`knowledge-data-driven heterogeneous CD method`具有方法容器语境，本次不顺手更改。此项仍是需要显式裁决的任务范围候选，而不是确定的标注程序bug。

受影响候选对11条：2条已知、9条UNRESOLVED。已知关系必须在新receipt中实际重判，不能将旧序列化端点/receipt哈希原封不动当作新事实。

现有head端点：e6=`{"entityId":"e6","start":232,"end":252,"text":"deep neural networks","label":"METHOD"}`；e7=`{"entityId":"e7","start":254,"end":258,"text":"DNNs","label":"METHOD"}`。当前tail端点为上述before；候选after仅供后续显式裁决。

```json
[
  {
    "head":"e6","tail":"e5","label":"USED_FOR",
    "evidence":{"start":131,"end":260,"text":"In the past decade, the heterogeneous CD problem has significantly benefited from the development of deep neural networks (DNNs)."},
    "reason":"The sentence explicitly assigns deep neural networks and its immediately defined DNNs abbreviation as an approach benefiting the local heterogeneous change-detection task."
  },
  {
    "head":"e7","tail":"e5","label":"USED_FOR",
    "evidence":{"start":131,"end":260,"text":"In the past decade, the heterogeneous CD problem has significantly benefited from the development of deep neural networks (DNNs)."},
    "reason":"The sentence explicitly assigns deep neural networks and its immediately defined DNNs abbreviation as an approach benefiting the local heterogeneous change-detection task."
  }
]
```

源头复核意见：若单独接受候选，此完整原句仍明确支持两个方法别名对异质CD目标的局部USED_FOR；两条关系是同一句、同一方法的相关提及，不是两份独立实验。其余9条继续未知，不扩大至其他CD提及、灾害监测或土地管理。

## B. 暂缓：物理层是否属于任务实体范围

- arxivId：`2501.06756`
- sampleId：`sample-f5ba3a152aa16ff91eb2`
- entityId：`e2`
- textSha256：`d82bb4791d31a9035b37c9ed2601f856aceffd271242d8ef9f797b15e79ff4be`
- upstreamReceiptSha256：`3fe7a1967ab814a85deabe9ed9e0ac1d897d24f452b9c72590196e4a9f801d96`
- 原句 `[421:620]`：

> This paper addresses these challenges by proposing a framework for robust sensor placement to optimize anomaly detection in the physical layer and enhance communication resilience in the cyber layer.

```json
{
  "before": {"entityId":"e2","start":524,"end":541,"text":"anomaly detection","label":"TASK"},
  "afterCandidate": {"entityId":"e2","start":524,"end":563,"text":"anomaly detection in the physical layer","label":"TASK"}
}
```

支持候选的理由：原句区分物理层异常检测与网络层通信韧性，完整介词短语可表达任务场景。

暂缓理由：`in the physical layer`也可被解释为任务发生位置/独立上下文，不必属于实体边界；源头不存在相同完整词组一长一短的既有标注对照。没有预先确定这种后置位置修饰的范围政策，不能因为短语连续就自动扩长。

受影响候选对10条，全部UNRESOLVED。若未来显式接受范围变更，仅重新绑定实体端点和新receipt；不能从这句强行将10条关系填成正例或负例。目前不改。

## C. 暂缓：PET后置模态限定

- arxivId：`2506.16934`
- sampleId：`sample-766c7e9d5eff9ef242fd`
- entityId：`e4`
- textSha256：`f80060e4f093ba762bdc95c2706db381dda9a180e1064e81c626072b16a71e89`
- upstreamReceiptSha256：`60e606f203ac73e6b544c9030d65281569fd4f39918728af442fdf6a0f8d3209`
- 原句 `[657:798]`：

> To the best of our knowledge, this is the first attempt to use texture condition and multi-latent space for tracer separation in PET imaging.

```json
{
  "before": {"entityId":"e4","start":765,"end":782,"text":"tracer separation","label":"TASK"},
  "afterCandidate": {"entityId":"e4","start":765,"end":797,"text":"tracer separation in PET imaging","label":"TASK"}
}
```

支持候选的理由：同文e3为634:655的`PET tracer separation`，此句明确提供相同PET模态。

暂缓理由：两处字面词组不同；后置`in PET imaging`是否并入TASK需要显式范围政策，不能将语义近似直接当作原标注错误。此轮保持原跨度，不以既有模型开发错误作裁决依据。

受影响候选对7条，全部UNRESOLVED。若未来接受变更，仍需新receipt与端点再生成，7条关系保持未知。目前不改。

## 明确保留的易误判案例

- `1909.03546`的对象明确的文本跨度枚举、上下文捕获及实体消歧目标已被52规则明确纳入TASK；不能仅因它们是内部操作就机械删除。
- `1903.00161`的`Discrete Reasoning Over the content of Paragraphs`虽与DROP缩写有关，原句是`which requires ...`计算目标语境，旧receipt已有实际自复核理由。此轮没有足够的新证据强改为DATASET；若要重新裁决，须明确多义表述的flat标注优先级。
- `1903.07107`的`reinforcement learning-type problems`属于边界/本体范围歧义，不仅凭方法名称子串将整个短语改为METHOD。

此记录只提供训练源裁决依据，没有证明模型改善、独立评估可靠性或项目已完成。
