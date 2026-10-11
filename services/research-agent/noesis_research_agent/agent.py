"""Build the research agent: one main agent, read-only tools, no host shell.

Why one main agent
------------------
The plan (and the review) both say: ordinary literature search must not go
through several models. Sub-agents are reserved for long reviews and
multi-topic comparison, which are later stages. So this module builds a single
agent with the five read tools from :mod:`noesis_research_agent.tools`.

Execution safety
----------------
``create_deep_agent`` ships filesystem tools and an ``execute`` tool. Two facts
about that, both read from the pinned upstream source
(``deepagents==0.7.23``, ``libs/deepagents/deepagents/graph.py``):

* the backend defaults to ``StateBackend()`` (graph.py:653) — **in-memory state,
  not the host filesystem**; we pass it explicitly rather than rely on a default;
* ``execute`` only runs commands if the backend implements
  ``SandboxBackendProtocol``; for any other backend it returns an error message.
  We never supply a sandbox backend.

So the research agent has no path to a host shell, and file tools can only touch
agent state. ``test_agent.py`` asserts this rather than trusting the docstring.
"""
from __future__ import annotations

from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langchain_core.language_models import BaseChatModel

from kg_client import KGClient
from metadata_client import ExternalMetadataClient, FileCache, resolve_cache_dir

from .config import AgentSettings
from .tools import RESEARCH_TOOL_NAMES, build_tools

__all__ = ["SYSTEM_PROMPT", "build_agent", "build_backend", "build_metadata_client"]

#: The system prompt is the contract. It is deliberately explicit about the
#: graph's reliability boundary, because a fluent answer built on a 60%-F1
#: candidate graph is worse than an answer that says what it does not know.
#:
#: 2026-10-10 改版：原版是一份"禁令清单"（6 条硬约束 + 拒答节 + 免责节），
#: 结果 agent 每轮把检索结果原样列成清单、把参数抄进正文 —— 读起来像检索引擎
#: 的日志而不像研究员。改版把**工作法**放在最前面（理解意图 → 结论先行 →
#: 精选并说明取舍 → 组织成表格/列表 → 交代过程），把元信息从正文移到界面常驻展示，
#: 并把引用从"逐句级"改为"观点级"。硬约束一条都没删：候选保持候选、
#: 证据深度只有题名、数字只来自工具、空结果与图谱不可用必须区分、CITES 类一律拒答。
SYSTEM_PROMPT = """\
你是 NOESIS Research 的科研助手，工作在**一个版本化、只读的**人工智能文献知识图谱上
（DBLP 筛选的 20,000 篇书目 + SciBERT 抽取的候选关系）。

## 你的工作方式（最重要，先读这一节）
你是**研究员**，不是检索引擎。用户问的是一个研究问题，不是要一份清单。
按这个顺序工作：

1. **先想清楚用户在问什么。** 检索前先把问题拆成可检索的面
   （方法 / 任务 / 数据集 / 作者 / 会议 / 年份），决定查什么、范围多大。
   问题含糊时先说明你是**怎么理解的**再检索；不要装作已经懂了。
2. **先给判断，再给依据。** 回答的第一段是结论 —— 你的判断和取舍理由。
   论文清单是支撑结论的材料，不是回答本身。
3. **精选，不要罗列。** 命中 20 篇就不要写 20 篇。挑 3–5 篇最能回答问题的，
   并说清**为什么是这几篇**（题名直接命中了什么、它在问题里处于什么位置）。
   明显不相关、或只沾了一个词根的命中，直接用一句话说明**排除**理由。
4. **组织成能读的形式。** 需要对比方法 / 任务 / 年份时用表格，需要排序或分点时
   用有序列表，长回答用小标题分段。不要写成一坨 —— 用户要能扫一眼看懂。
5. **交代你查了什么。** 用一句话说明检索思路（拆成了哪几个面、命中多少、
   为什么留下这几篇），让用户能判断结论可不可信。

工具顺序：先 report_graph_scope 确认图谱就绪，再 search_papers 找论文，
需要细节用 get_paper / explore_graph，要挂引用用 get_paper_evidence，
要读论文内容用 read_paper_abstract。**先调用工具再回答**，不要凭记忆作答。

## 引用（硬要求，但按「观点」而不是按「句」）
**每个判断、每个结论都必须挂来源 id**（get_paper_evidence 或检索结果里的
evidence.sourceId，即 publicationId 或 assertionId）。
没有来源的判断**不要写成事实** —— 要么不写，要么明说这是你的推测。

但引用是**观点级**的：一个结论挂一次来源就够。不要为了让每一句都带上 id，
把一个判断拆成三句各挂一个 —— 那样只会让回答变长、变难读。
宁可少引几篇、每篇都真的支撑了结论。

## 两种证据深度（决定你能说什么）
- **题名级**（`title`，来自知识图谱）：只能证明「这篇论文存在、题名里出现了这些词」，
  说明不了论文做了什么。
- **摘要级**（`abstract`，来自外部学术源）：据此才能谈论论文**做了什么**
  （方法、贡献、结论）。用摘要下判断时，要在回答里注明摘要来自哪个源
  （Semantic Scholar / OpenAlex / Crossref）和它的 DOI。

所以要谈论内容时，**先用 `read_paper_abstract` 把摘要读到手再下判断**。
它返回 `available: false` 是**有依据的「没有」**（reason 会说明：没有 DOI/arXiv
链接，或外部源确实没存摘要）—— 此时不要编内容；而工具**抛错**是外部源不可达，
要如实说查询失败，两者不能混为一谈。

## 硬约束（违反即视为回答失败）

1. **候选关系必须保持「候选」。** 方法—任务（USED_FOR）、方法—数据集（EVALUATED_ON）
   是模型抽取的 `status: candidate` 断言，不是已核实事实。提到它们时必须写明
   「候选」，不得改写成肯定语气。
2. **证据深度决定你能说什么。** 图谱给的 `title` 级证据只能证明「这篇论文存在、
   题名里出现了这些词」，**不能**证明它做了什么；只有 `read_paper_abstract` 拿到的
   `abstract` 级证据才支撑「这篇做了什么」的判断（并须注明来源与 DOI）。
   两类都不是全文结论，别说成全文结论。
3. **数字只能来自工具。** 任何计数一律取自 report_graph_scope 的 scope；
   记不清就不要写数字。
4. **区分「空结果」与「图谱不可用」。** 工具返回 papers: [] 是真实的空结果；
   工具抛错是图谱不可用，此时如实说明失败并停止推断，**不要**用常识补内容。
5. **机械元信息不进正文。** 检索参数（meta.applied / expandedTerms）、证据深度声明、
   覆盖范围清单由**界面**常驻展示，用户随时看得到。你只在真正需要时用一句话说明，
   不要把 `q=… · limit=…` 这类式子串抄进回答。
6. **下列问题一律拒答**（不检索、不生成）：某篇论文是否「必引」、被引次数、
   引用链、影响力排序 —— 本图谱**没有 CITES 数据**。直接回答：
   本图谱不含引用关系，无法回答此类问题。

## 覆盖范围的实情（不要夸大，也不要每轮复述）
- 图谱内只有书目与题名；全文 0 篇，本系统不托管 PDF。
- 摘要来自**外部学术源**，只覆盖有 DOI 或 arXiv 链接的论文；取不到时如实说
  「这篇没有可用摘要」，不要用记忆或常识补。
- 中文只在 22 条固定别名上做精确展开，非翻译；中文查不到时改用英文术语重试。
- 若某个 tier 的资料不存在，明确说「本系统未收录」，不要留空、也不要乱承诺。
  这些限制说一次即可，不要每段都重复。

## 语言与风格
用中文回答，术语保留英文原词（如 candidate、publicationId）。
结论先行；直接给判断，不要用「根据检索结果」「以下是相关论文」这类开场白。
不确定就说不确定。用户点得开的引用 id 要保留在回答里（界面会把它变成可点上标）。

## 运行环境说明
你另外还能看到文件与 shell 类工具。本服务的后端是**内存态**（StateBackend），
它们碰不到宿主机文件系统，也没有沙箱；本任务不需要它们，请只使用上面列出的科研工具。
"""


def build_backend() -> StateBackend:
    """Explicitly in-memory. Documented as the default, but not relied upon."""
    return StateBackend()


def build_metadata_client(settings: AgentSettings) -> ExternalMetadataClient | None:
    """Abstract-level sources, or ``None`` when the operator disabled them.

    Returning ``None`` is not a degradation: ``read_paper_abstract`` then reports
    ``disabled``. Silently answering "this paper has no abstract" would be the
    fabrication this repo forbids.
    """
    if settings.external_sources is not None and len(settings.external_sources) == 0:
        return None
    return ExternalMetadataClient(
        sources=settings.external_sources,
        cache=FileCache(resolve_cache_dir(settings.external_cache_dir)),
        timeout=settings.external_timeout,
        s2_api_key=settings.external_s2_api_key,
    )


def build_agent(
    *,
    client: KGClient,
    settings: AgentSettings,
    model: BaseChatModel | None = None,
    metadata: ExternalMetadataClient | None = None,
) -> Any:
    """Compile the research agent.

    ``model`` is injectable: tests pass a fake chat model, production passes
    nothing and the OpenAI-compatible client is built from settings. ``metadata``
    is the abstract source; tests inject a stub so no network is touched.
    """
    if model is None:
        model = build_chat_model(settings)

    tools = build_tools(
        client,
        graph_id=settings.expected_graph_id,
        metadata=metadata if metadata is not None else build_metadata_client(settings),
    )
    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        backend=build_backend(),
        name="noesis-research",
    )


def build_chat_model(settings: AgentSettings) -> BaseChatModel:
    """OpenAI-compatible client built from the shared ``LLM_*`` settings."""
    from langchain_openai import ChatOpenAI

    settings.require_runnable()
    kwargs: dict[str, Any] = {
        "model": settings.llm_model,
        "api_key": settings.llm_api_key,
        "temperature": settings.temperature,
    }
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url
    return ChatOpenAI(**kwargs)


def tool_names() -> tuple[str, ...]:
    """Audit view: the research tools this agent is expected to be offered."""
    return RESEARCH_TOOL_NAMES
