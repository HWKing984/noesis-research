# V2摘要标注：TASK与用途角色边界 v1

此页明确现有宽口径，不把AI标签提升为人工金标准，不改变METHOD/TASK/DATASET及USED_FOR/EVALUATED_ON/NO_RELATION Schema。

## TASK判定

TASK是原文明确表达的研究操作或研究目标，**不限于论文最终应用**。保留最短完整、连续且不与已有实体重叠的字面表达；不从题名、URL或常识补正文缺失文字。

| 情形 | 判定与例子 | 不得推导 |
|---|---|---|
| 应用操作 | face inpainting、remote sensing object detection是TASK | 模型所有组件都执行该应用 |
| 训练/数据处理操作 | augment training data是TASK；Rotation/translation为METHOD | 增广方法直接提高MNIST分数或执行所有分类任务 |
| 代理训练目标 | future clip order ranking是TASK，关系标training_proxy | 训练目标等于已验证的下游能力 |
| 具技术对象的研究目标 | identity preservation作为面部修补的身份保持目标是TASK；enhance communication resilience作为通信韧性目标是TASK | 效果目标与数据集评测关系等价 |
| 性能数值/属性 | F1 score、accuracy、speed increase、classification performance、generalization capability不是独立TASK | 为提高指标而臆造新操作实体 |
| 输出/中间表示 | region proposals、multi-scale feature representation本批按输出/表示名词排除；只有明确表达生成/提取操作时另审对应动作跨度 | 将名词改写成正文没有的generate/extract |
| 领域/模态/泛化定义 | remote sensing、virtual reality、UAV imagery不单独标TASK；learn new classes这类宽泛定义短语不新增具名研究任务 | 背景领域等于一个操作，泛化定义必然构成独立任务节点 |

identity preservation的含义是保持身份这个研究目标；“good”质量修饰不纳入跨度。它不是某个数值指标的名称。本批只确认PVA被明确归属到该目标，不据此断言其真正效果优秀。augment training data同样保留字面动作和对象，不补写论文没有的data augmentation同义名称。

## USED_FOR归属与角色

只有原文明示主体用于/执行/达成该操作或目标，才能接受候选。类型合法或句内共现不够；整体模型评测不传递给组成部分。

- `downstream_application`：方法的应用/目标，例如PVA ensures identity preservation。
- `component_operation`：组件的明确操作，例如algorithm utilizes a diffusion process to generate placement strategies。这里源句直接赋予扩散过程生成策略的操作；不继承整体EFGD的韧性、检测或性能结论。
- `training_proxy`：训练操作/目标。增广操作另存`taskSubRole=training_augmentation`；它不是新增模型标签或新顶层角色。
- `background_method_use`：背景方法类别与用途的明示联系，例如deep learning在remote sensing object detection中的success；不是GE-FSOD的组件或评测主体。

“直接执行者不同”不证明间接用途被否定。5个旧角色对比负例继续隔离；UNRESOLVED不是NO_RELATION，训练数据不是评测数据。跨句关系必须同时展示谓词、先行句和归属解释；共指链仍是AI解释，不等于独立语义认证。
