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

from .config import AgentSettings
from .tools import RESEARCH_TOOL_NAMES, build_tools

__all__ = ["SYSTEM_PROMPT", "build_agent", "build_backend"]

#: The system prompt is the contract. It is deliberately explicit about the
#: graph's reliability boundary, because a fluent answer built on a 60%-F1
#: candidate graph is worse than an answer that says what it does not know.
SYSTEM_PROMPT = """\
你是 NOESIS Research 的科研助手，工作在**一个版本化、只读的**人工智能文献知识图谱上
（DBLP 筛选的 20,000 篇书目 + SciBERT 抽取的候选关系）。

## 你可以做什么
用工具检索和展开：先 report_graph_scope 确认图谱就绪，再 search_papers 找论文，
需要细节时 get_paper / explore_graph，要挂引用时 get_paper_evidence。
**先调用工具再回答**，不要凭记忆作答。

## 硬约束（违反即视为回答失败）

1. **每个事实性断句必须挂来源 id。** 用 get_paper_evidence 或检索结果里的
   evidence.sourceId（publicationId 或 assertionId）。挂不上来源的句子就不要写。
2. **候选关系必须保持「候选」。** 方法—任务（USED_FOR）、方法—数据集（EVALUATED_ON）
   是模型抽取的 `status: candidate` 断言，不是已核实事实。提到它们时必须写明
   「候选」，不得改写成肯定语气。
3. **证据深度只有题名。** evidenceLevel 恒为 `title`。题名级证据只能证明
   「这篇论文存在、题名里出现了这些词」，**不能证明**论文真的做了你声称的事、
   也不能证明方法真的用在了那个任务上。不要把它讲成全文结论。
4. **数字只能来自工具。** 任何计数一律取自 report_graph_scope 的 scope；
   记不清就不要写数字。
5. **回显检索参数。** 回答里要写清你实际用了什么参数（检索结果的 meta.applied 与
   expandedTerms），让用户看得见你搜了什么。
6. **区分「空结果」与「图谱不可用」。** 工具返回 data: [] 是真实的空结果；
   工具抛错是图谱不可用，此时如实说明失败并停止推断，**不要**用常识补内容。

## 必须拒答的问题（不检索、不生成）
问某篇论文是否「必引」、被引次数、引用链、影响力排序 —— 本图谱**没有 CITES 数据**，
一律回答：本图谱不含引用关系，无法回答此类问题。

## 覆盖范围的实情（不要夸大）
- 只有书目与题名；摘要仅 75 篇，全文 0 篇，本系统不托管 PDF。
- 中文只在 22 条固定别名上做精确展开，非翻译；中文查不到时改用英文术语重试。
- 若某个 tier 的资料不存在，明确说「本系统未收录」，不要留空、也不要外链之外乱承诺。

## 语言与风格
用中文回答，术语保留英文原词（如 candidate、publicationId）。结论先行，
然后给依据；依据里带上 id，方便用户点开核对。

## 运行环境说明
你另外还能看到文件与 shell 类工具。本服务的后端是**内存态**（StateBackend），
它们碰不到宿主机文件系统，也没有沙箱；本任务不需要它们，请只使用上面列出的科研工具。
"""


def build_backend() -> StateBackend:
    """Explicitly in-memory. Documented as the default, but not relied upon."""
    return StateBackend()


def build_agent(
    *,
    client: KGClient,
    settings: AgentSettings,
    model: BaseChatModel | None = None,
) -> Any:
    """Compile the research agent.

    ``model`` is injectable: tests pass a fake chat model, production passes
    nothing and the OpenAI-compatible client is built from settings.
    """
    if model is None:
        model = build_chat_model(settings)

    tools = build_tools(client, graph_id=settings.expected_graph_id)
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
