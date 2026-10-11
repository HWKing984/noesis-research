# integrations/external-sources

给研究 Agent 提供**摘要级证据**。知识图谱只存题名，所以任何只靠它的回答都只能说
「这篇论文存在、题名里有这些词」。这一层补上"能读的内容"。

## 为什么零第三方依赖

这是 Agent 工具的直接底座（与 `integrations/knowledge-graph/` 同级、同性质）：
多一个依赖树就会被工具层继承。所以只用标准库 —— 传输层是自带的 `urllib` + 私有
opener，不是 `httpx`。

`reference/paper-qa/src/paperqa/clients/` 里已有 `openalex.py` / `crossref.py` /
`semantic_scholar.py`，但它们（a）依赖 `httpx`/`tenacity`，（b）**只返回 metadata，
不取摘要**（`abstract` 字段一次都没用到）。因此这里复用的是**端点与查询形状**，
解析与重建另写，并在测试里对真实 API 校准。

## 来源与回退链

| 顺序 | source | 查询键 | 摘要形状 | 2026-10-10 本机实测 |
|---|---|---|---|---|
| 1 | Semantic Scholar | `DOI:<doi>` / `ARXIV:<id>` | 纯文本 `abstract` | ✅ 两个样例 DOI 均有（1293 / 1117 字符）+ venue |
| 2 | OpenAlex | `https://doi.org/<doi>` | `abstract_inverted_index`（需按位置重建） | ✅ 两个样例均有 inverted index |
| 3 | Crossref | `/<doi>` | `message.abstract`（JATS，需剥标签） | ❌ 两个样例 DOI 都是 0 长度 |

总结论：**S2 优先**。它的摘要覆盖最好，但**无 key 时共享池极小**（连续几次即 429）——
配 `EXTERNAL_S2_API_KEY` 可解除。OpenAlex 是可靠的第二源；Crossref 在会议论文上
经常没有摘要，留着是为了覆盖它有摘要的那部分。

## 身份纪律（硬约束）

匹配顺序 **DOI → 精确 arXiv ID → 明确来源标识**。

* **不提供任何按标题查询的入口** —— 标题相似度永远不能用来"认领"一条记录。
* 每个响应都要过 **DOI 一致性校验**：返回记录的 DOI 必须等于查询的 DOI（归一到小写）。
  实测 OpenAlex 对 `10.48550/arXiv.1706.03762` 会返回另一条记录（DOI
  `10.65215/2q58a426`），这条校验把这种"看起来对、其实不是"的命中直接挡掉。
* arXiv 记录常无 DOI，此时用 arXiv 的规范 DOI `10.48550/arxiv.<id>` 作为稳定 key，
  绝不出现"用空标识符记一条证据"。

## 失败语义（与全仓同一条规则）

| 情况 | 结果 |
|---|---|
| 拿到摘要 | `ExternalRecord`（`evidenceLevel=abstract`） |
| 源不可达 / 429 / 5xx / 超时 | `ExternalUnavailable` —— **调用方必须如实报失败** |
| 该源没有这条记录（404） | 记为 absent |
| 200 但结构不符、非 JSON、DOI 不一致 | 记为 unusable —— **不等于"无摘要"** |
| 该源因标识符类型不适用（如只有 arXiv id 时查 OpenAlex） | 记为 skipped —— **不等于"无摘要"** |
| 记录存在但没有摘要 | 记为 present-but-empty |
| 没有任何摘要，且**没有任何源失败** | 返回 `None`（这是有依据的结论） |
| 有任何源失败、且没拿到摘要 | `ExternalUnavailable` ——「我没查成」绝不能被说成「没有」 |

最后两行是这一层最重要的两条。它们是被真实流量打出来的：第一次跑真实查询时 S2 返回
429，而 OpenAlex/Crossref 因为拿不到 DOI 压根没被问过，却被当成"它们说没有摘要"，
于是整个查询对外表现为"这篇论文没有摘要"。**这就是本项目铁律禁止的那种伪装。**
回归用例见 `FailureSemanticsTests` 里的 `test_outage_is_not_reported_as_no_abstract` /
`test_arxiv_only_lookup_skips_doi_only_sources_instead_of_calling_them_empty`。

## 配置（全部可选）

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `EXTERNAL_SOURCES` | `semanticscholar,openalex,crossref` | 启用顺序；未知名字被丢弃 |
| `EXTERNAL_TIMEOUT` | `12` | 单请求超时（秒） |
| `EXTERNAL_CACHE_DIR` | `.data/external` | 磁盘缓存目录（JSON，按 key 哈希命名） |
| `EXTERNAL_CACHE_TTL` | `2592000`（30 天） | 缓存有效期（秒） |
| `EXTERNAL_CONTACT_MAIL` | 空 | OpenAlex / Crossref 的礼貌池地址 |
| `EXTERNAL_S2_API_KEY` | 空 | Semantic Scholar key（免费），显著放宽限流 |

安全默认：**环境代理被忽略**。传输层装 `ProxyHandler({})`（空 dict，不是 `None`——
`None` 会去读环境），所以宿主注入的 `HTTP_PROXY` 不会把公开 API 请求导向别处。
这条有单测守着，也有真实集成用例（把 `HTTP_PROXY` 指向死端口后仍必须连通）。

## 用法

```python
from metadata_client import ExternalMetadataClient, FileCache, ExternalUnavailable

client = ExternalMetadataClient(cache=FileCache(".data/external"))
try:
    record = client.lookup(doi="10.1109/CVPR.2016.90")
except ExternalUnavailable as exc:
    ...  # 如实报失败，不要写成"没有摘要"
if record is None:
    ...  # 有依据的"无摘要"
else:
    record.abstract                              # 给模型读的原文
    record.evidence_ref(publication_id="conf/cvpr/HeZRS16")  # 符合 packages/contracts/evidence.py
```

## 测试

```bash
# 离线（43 项）+ 真实 API（6 项，不可达/限流时自动 skip）
python -m unittest discover -s integrations/external-sources -t integrations/external-sources
```

2026-10-10 实测：`Ran 49 tests ... OK`（离线 43 + 真实 6，真实 6 项全部真跑通过）。
