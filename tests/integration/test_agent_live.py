"""Live agent-loop check against the real knowledge graph.

Everything is real except the LLM: a **scripted** chat model replaces the model
so the test can be deterministic and needs no API key. What is being verified is
the part that has no excuse for being wrong:

    agent harness → research tools → real Neo4j → real publicationIds
                  → evidence refs → answer text that cites them

The scripted model does exactly what the system prompt asks a real model to do:
call ``search_papers``, then answer while quoting a ``sourceId`` it saw in the
tool result. If the plumbing drops an id, this test fails.

Skipped when deepagents is not installed or the KG service is unreachable.

    KG_BASE_URL=http://127.0.0.1:8765 \
    KG_LOCK_FILE=D:/a-open_source/neo4j/resources/course_graph_runtime.json \
    services/research-agent/.venv/Scripts/python -m unittest \
        discover -s tests/integration -t tests/integration -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (
    _REPO_ROOT,
    _REPO_ROOT / "services" / "research-agent",
    _REPO_ROOT / "integrations" / "knowledge-graph",
):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

BASE_URL = os.environ.get("KG_BASE_URL", "http://127.0.0.1:8765")
LOCK_FILE = os.environ.get("KG_LOCK_FILE", "")

try:
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from pydantic import Field

    from kg_client import KGClient, KGError, KGUnavailable

    from noesis_research_agent.agent import build_agent
    from noesis_research_agent.config import AgentSettings
except Exception as exc:  # pragma: no cover - core/API-only runs have no deepagents
    raise unittest.SkipTest(f"live agent suite unavailable ({type(exc).__name__}: {exc})")


def _pinned_graph_id() -> str | None:
    explicit = os.environ.get("KG_EXPECTED_GRAPH_ID")
    if explicit:
        return explicit.strip()
    if LOCK_FILE and Path(LOCK_FILE).is_file():
        value = json.loads(Path(LOCK_FILE).read_text(encoding="utf-8")).get("graphId")
        return str(value).strip() if value else None
    return None


def _probe() -> tuple[bool, str]:
    try:
        report = KGClient(BASE_URL, timeout=5).health()
    except KGUnavailable as exc:
        return False, f"KG service unreachable at {BASE_URL}: {exc}"
    except KGError as exc:
        return False, f"KG service answered but is unusable: {exc}"
    return True, f"live graph {report.graph_id} ({report.status})"


PINNED = _pinned_graph_id()
_AVAILABLE, _PROBE_NOTE = _probe()

QUESTION = "有哪些关于 transformer 的论文？"


def _tool_result_text(message) -> str:  # noqa: ANN001
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)


def _first_source_id(payload_text: str) -> str | None:
    try:
        payload = json.loads(payload_text)
    except (TypeError, ValueError):
        return None
    papers = payload.get("papers") or []
    if not papers:
        return None
    evidence = papers[0].get("evidence") or {}
    return evidence.get("sourceId") or papers[0].get("publicationId")


class ScriptedResearchModel(BaseChatModel):
    """Calls ``search_papers`` once, then answers citing what it got back."""

    offered_tools: list[str] = Field(default_factory=list)
    tool_calls_seen: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-research"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN003
        self.offered_tools = [
            getattr(item, "name", None) or getattr(item, "__name__", str(item)) for item in tools
        ]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001, ANN003
        tool_messages = [m for m in messages if getattr(m, "type", "") == "tool"]
        if not tool_messages:
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "search_papers",
                                    "args": {"query": "transformer", "limit": 3},
                                    "id": "call-1",
                                }
                            ],
                        )
                    )
                ]
            )

        self.tool_calls_seen = len(tool_messages)
        source_id = _first_source_id(_tool_result_text(tool_messages[-1]))
        if source_id:
            answer = (
                "结论先行：图谱中有与 transformer 相关的论文。\n"
                f"依据：检索命中条目，来源 id `{source_id}`（证据等级 title，核验状态 unverified）。\n"
                "注意：题名级证据只能证明该论文存在、题名出现相关词，不能证明其具体结论。"
            )
        else:
            answer = "检索没有返回可引用的来源，因此无法给出带证据的结论。"
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=answer))])


@unittest.skipUnless(_AVAILABLE, f"KG service not available — {_PROBE_NOTE}")
class LiveAgentLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings = AgentSettings(
            kg_base_url=BASE_URL,
            expected_graph_id=PINNED,
            kg_timeout=20.0,
            llm_api_key="not-used-scripted-model",
            llm_base_url=None,
            llm_model="scripted",
        )
        cls.client = KGClient(BASE_URL, expected_graph_id=PINNED, timeout=20.0)

    def _run(self) -> tuple[ScriptedResearchModel, list, str]:
        model = ScriptedResearchModel()
        agent = build_agent(client=self.client, settings=self.settings, model=model)
        result = agent.invoke({"messages": [{"role": "user", "content": QUESTION}]})
        messages = list(result.get("messages", []))
        answer = ""
        for message in messages:
            if getattr(message, "type", "") == "ai":
                text = message.content if isinstance(message.content, str) else ""
                if text.strip():
                    answer = text
        return model, messages, answer

    def test_agent_loop_reaches_real_neo4j_and_cites_a_real_id(self) -> None:
        model, messages, answer = self._run()

        self.assertEqual(model.tool_calls_seen, 1, "the harness should have run exactly one tool call")
        for name in ("search_papers", "get_paper", "explore_graph", "get_paper_evidence", "report_graph_scope"):
            self.assertIn(name, model.offered_tools)

        tool_texts = [_tool_result_text(m) for m in messages if getattr(m, "type", "") == "tool"]
        self.assertTrue(tool_texts, "no tool result reached the model")
        payload = json.loads(tool_texts[-1])
        papers = payload.get("papers") or []
        self.assertTrue(papers, "real graph returned no papers for 'transformer'")

        paper = papers[0]
        self.assertTrue(paper["publicationId"])
        self.assertIn("/", paper["publicationId"], "DBLP keys contain slashes")
        self.assertEqual(paper["evidence"]["sourceId"], paper["publicationId"])
        self.assertEqual(paper["evidence"]["evidenceLevel"], "title")
        self.assertEqual(paper["evidence"]["verificationStatus"], "unverified")
        # 图谱版本一致性不再断言在模型视图里（它是精简的，不含 graphId）——
        # 这条保证由 test_scope_tool_reports_the_pinned_version 与 test_kg_live 负责。

        # The answer must quote that real id — this is the "clickable evidence" claim.
        self.assertIn(paper["publicationId"], answer)
        self.assertIn("title", answer)

    def test_echoed_parameters_survive_the_loop(self) -> None:
        _, messages, _ = self._run()
        payload = json.loads(_tool_result_text([m for m in messages if getattr(m, "type", "") == "tool"][-1]))
        self.assertEqual(payload["applied"]["q"], "transformer")
        self.assertEqual(payload["applied"]["limit"], "3")

    def test_scope_tool_reports_the_pinned_version(self) -> None:
        from noesis_research_agent.tools import build_tools

        tools = {tool.name: tool for tool in build_tools(self.client, graph_id=PINNED)}
        scope = tools["report_graph_scope"].invoke({})
        self.assertEqual(scope["status"], "ready")
        self.assertEqual(scope["scope"]["candidateAssertions"], 21497)
        if PINNED:
            self.assertEqual(scope["graphId"], PINNED)

    def test_unavailable_graph_surfaces_as_an_error_not_an_empty_answer(self) -> None:
        """Point the client at a dead port: tools must raise, not return []."""
        from noesis_research_agent.tools import build_tools

        dead = KGClient("http://127.0.0.1:1", timeout=2.0)
        tools = {tool.name: tool for tool in build_tools(dead, graph_id=None)}
        with self.assertRaises(KGUnavailable):
            tools["search_papers"].invoke({"query": "transformer"})


if __name__ == "__main__":
    print(f"probe: {_PROBE_NOTE}")
    print(f"pinned graph id: {PINNED}")
    unittest.main(verbosity=2)
