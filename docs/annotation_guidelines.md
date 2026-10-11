# 人工智能文献实体抽取：试标规范 v1-candidate

此文件是待试标验证的候选规范，不是已冻结模式。DBLP的作者、年份、场馆等已有字段通过结构化解析获得；实验二的深度学习任务是从真实论文标题识别方法、任务、命名数据集与应用领域。

## 1. 为什么这样做

题名关键词检索常常不能区分“用了什么方法”“做什么任务”“在哪个领域应用”。抽取这些实体后，可以按任务查论文、比较方法、按数据集寻找可比研究，再结合作者和场馆形成候选参考文献。最终是否引用必须阅读原文，标题不足以证明实验效果或论点支持。

## 2. 标注对象和边界

只标标题中实际出现的文字，不补写摘要、不展开未出现的缩写、不按Topic标签猜实体。原文固定为CSV中的标题，位置为Unicode字符数，不是UTF-8字节数或JavaScript UTF-16长度；start包含、end不包含，必须满足 `text[start:end] == entity.text`。

| 标签 | 标什么 | 不标什么 |
|---|---|---|
| METHOD | 有明确技术含义的方法、算法、模型，包括标题实际出现的机器学习/强化学习等技术族 | our method、novel approach等无指称描述；电力变压器不能因transformer同形而标AI方法 |
| TASK | 明确要完成的任务，如object detection、question answering、knowledge graph completion | 单独的data、study、research；Knowledge Graph等仅作研究对象时不自动标为任务 |
| DATASET | 命名数据集或基准语料，包括版本、必要后缀，如CIFAR-10、FB15k-237 | dataset、benchmark、training data等未命名泛称；同形地名不能自动当数据集 |
| DOMAIN | 明确应用场景/行业，如medical imaging、autonomous driving、remote sensing | 泛称real world；仅有AI、computer science等范围过宽词语 |

优先完整且必要的最小指称：Graph Neural Networks完整标METHOD，不另嵌套Neural Networks；visual question answering完整标TASK，不另标question answering。别把整个“Graph Neural Networks for …”包成一个实体。

- 冠词、标点、作者评价词一般排除；技术名称内部的连字符、数字、版本号保留。
- 标注单数/复数原样，不在标注层做归一化；标注只存原文，别名归一化是后续步骤。
- 并列实体分别标；共享中心词的不连续表达，不能跨越非实体词拼接：标可独立解释的连续片段并记录歧义。
- 同一缩写两次出现分别标；缩写和全称同时出现分别标，括号一般不包进实体。
- 没有实体的标题必须经人工核对后保留空列表。词典无命中不等于确实无实体。
- 不确定边界或类别时先写notes并保持draft；不为增加实体数量强行归类。

构造的教学例句（不是DBLP数据或实验结果）：

`Graph Neural Networks for Node Classification on Cora`

标METHOD=`Graph Neural Networks`，TASK=`Node Classification`，DATASET=`Cora`。不能仅凭“on Cora”就认定报告了某项实验效果。

`A Transformer-Based Model for Medical Image Segmentation`

可以标METHOD=`Transformer`；TASK考虑完整的`Medical Image Segmentation`。若DOMAIN会与TASK重叠，首版平面模式优先完整TASK，在notes记录领域信息缺失，不额外建立嵌套实体。若此类情况很多，试标后统一修订模式，不能逐条临时变更规则。

## 3. 试标流程

1. 用浏览器打开同目录的pilot_review.html，填写真实姓名/标注者编号。
2. 每条检查预标注；点击色块可删除，鼠标选中原文后选择类别并添加，记录歧义。
3. 确认整条标题的遗漏、边界、类别都已核对，再点击“确认本条人工复核”。空实体标题也需点击确认。
4. 经常导出JSONL。网页刷新会丢失未导出的编辑；重新打开后可导入上次导出的JSONL。
5. 对不确定记录保留draft，不把自动预标注或仅浏览过的数据标成reviewed。
6. 命令行对导出的JSONL执行结构与原文一致性检查；全部复核后再使用--gold检查。结构校验不能证明语义标注正确，也不验证真实标注者身份。

pilot_review.csv仅是便于表格查看的副本；正式回传使用网页导出的JSONL。实体每次增删后关系下标可能变化，网页会清空已有关系，需重新检查。

## 4. 关系抽取衔接：Pipeline

先抽实体，再对有证据的实体对判断关系。NER输出只能支持“论文提及实体”，不能直接生成方法效果、引用或实验关系。

| 关系 | 方向 | 必须核对 |
|---|---|---|
| USED_FOR | METHOD → TASK | 文字明确说方法用于任务；不等于已成功解决 |
| EVALUATED_ON | METHOD → DATASET | 有实验/评测的明确文字依据；只出现数据集名称不足 |
| APPLIED_TO | METHOD → DOMAIN | 方法实际应用于所述领域有明确依据 |
| NO_RELATION | 同上述候选方向 | 对该候选对明确作过判断，不能把所有未标关系视为负例 |

首批网页只复核实体，自动关系为空。关系试标后续单独开展：head/tail为entities数组的0起始下标，evidence保存原文start/end/text且覆盖两个实体。证据结构有效不代表语义必然正确。例格式：

```json
{"head":0,"tail":1,"label":"USED_FOR","evidence":{"start":0,"end":45,"text":"Graph Neural Networks for Node Classification"}}
```

这段示例的下标和证据位置必须用实际记录重新验证，不能复制进其他论文。

## 5. 金标准与数据划分

200篇为跨主题/年份/类型的目的性试标，每个已知重复论文组至多一篇，不是代表整个AI领域的随机调查。全部保留训练侧，不进入独立测试侧。当前重复分组仅依据规范化标题和可恢复DOI，不保证找到所有近重复版本。

正式阶段目标1500—2000篇，由人工时间和类别支持数决定。按论文/重复组划分，约70/15/15；试标限定训练，测试冻结后不得参与词典补充、模式修订、超参数选择或挑选随机种子。验证/测试需独立人工金标准。

记录每类实体数量、零实体标题比例、关系可判定性和歧义。DATASET/DOMAIN过少时，先补充训练候选或有来源的真实摘要，必要时在冻结之前调整类别并说明理由。不能训练后删困难类别来抬高F1。

## 6. 状态与结果诚实性

- draft_dictionary_v1：词典预标注，全部draft，尚未人工确认；覆盖率/零命中率仅说明词典输出。
- human_reviewed：真实人工复核后记录reviewer和带时区的reviewed_at。
- --gold只检查声称的状态字段及结构。人工真实性、语义一致性仍靠实际复核记录。
- 在正式金标准、训练与独立测试完成前，不报告真实模型P/R/F1，不声称满足高精度/召回率。
- 当前基础图谱不含CITES；DBLP标题不是完整文献内容，参考文献推荐只是候选发现。
