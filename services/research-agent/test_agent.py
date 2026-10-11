"""Offline tests for the research agent's tools, wiring, and safety posture.

No LLM and no Neo4j: the KG side is a fake transport and the model is a fake
chat model. What is being checked is the part that must not drift — the tool
surface, the parameter echo, the evidence refs, and the "no host shell" claim.

Run (needs the service venv):
    services/research-agent/.venv/Scripts/python -m unittest discover \
        -s services/research-agent -t services/research-agent -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_IMPORT_ERROR: str | None = None
try:
    # 先导入本包：它会装配 sys.path（kg_client / noesis_research_api 都在别处）
    import noesis_research_agent  # noqa: F401

    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from pydantic import Field

    from deepagents.backends import StateBackend
    from deepagents.backends.protocol import SandboxBackendProtocol

    from kg_client import KGClient, KGUnavailable

    from noesis_research_agent.agent import SYSTEM_PROMPT, build_agent, build_backend
    from noesis_research_agent.config import AgentSettings, ConfigurationError
    from noesis_research_agent.tools import RESEARCH_TOOL_NAMES, build_tools

    from metadata_client import ExternalNoIdentifier, ExternalRecord, ExternalUnavailable
except Exception as exc:  # pragma: no cover - exercised by the core-only run
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

if _IMPORT_ERROR is not None:
    raise unittest.SkipTest(
        f"deepagents/langchain not installed ({_IMPORT_ERROR}); "
        "install with: pip install -r services/research-agent/requirements.txt"
    )

PINNED = "ai-literature-ed16399925fac2a599ed"
PUB_ID = "conf/IEEEwisa/LinGHW25"


def body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class FakeTransport:
    def __init__(self, routes: dict[str, list[tuple[int, bytes]]]) -> None:
        self._routes = {path: list(v) for path, v in routes.items()}
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, path: str, params):  # noqa: ANN001
        self.calls.append((path, dict(params)))
        queue = self._routes.get(path)
        if not queue:
            raise AssertionError(f"no stubbed response for {path} {dict(params)}")
        return queue.pop(0) if len(queue) > 1 else queue[0]


def health_payload() -> bytes:
    return body(
        {
            "data": {
                "status": "ready",
                "graphId": PINNED,
                "source": "live_neo4j",
                "scope": {
                    "bibliographyTitles": 20000,
                    "modelTitles": 19999,
                    "rejectedNERTitles": 1,
                    "candidateAssertions": 21497,
                },
                "terminology": {"version": "zh_alias_v1"},
            }
        }
    )


def publication(graph_id: str = PINNED, pub_id: str = PUB_ID) -> dict:
    return {
        "id": f"{graph_id}:Publication:4725bc95",
        "publicationId": pub_id,
        "graphId": graph_id,
        "title": "ShrimpFormer-X: A Transformer-Based Framework",
        "year": 2025,
        "type": "inproceedings",
        "doi": "10.1000/example",
        "dblpUrl": "https://dblp.org/rec/conf/IEEEwisa/LinGHW25",
        "urls": ["https://doi.org/10.1000/example"],
        "modelApplied": True,
        "modelApplicationStatus": "applied",
    }


def search_payload(items=None) -> bytes:
    return body(
        {
            "data": items if items is not None else [publication()],
            "meta": {
                "offset": 0,
                "limit": 5,
                "hasNext": True,
                "source": "live_neo4j",
                "aliasVersion": "zh_alias_v1",
                "expandedTerms": {"method": ["diffusion model", "diffusion models"]},
            },
        }
    )


def detail_payload() -> bytes:
    return body(
        {
            "data": {
                "publication": publication(),
                "authors": [{"name": "Lin", "position": 1, "identityStatus": "dblp_homepage_resolved"}],
                "venues": [{"name": "IEEE WISA", "type": "conference"}],
                "mentions": [{"text": "shrimp larvae", "label": "TASK", "start": 60, "end": 73}],
                "assertions": [
                    {
                        "assertion": {
                            "id": f"{PINNED}:Assertion:27d1a77da78f",
                            "pairId": "pair-1",
                            "predicate": "USED_FOR",
                            "status": "candidate",
                            "confidence": 0.9999832,
                            "confidenceCalibrated": False,
                            "source": "model_prediction",
                            "evidence": "ShrimpFormer-X: A Transformer-Based Framework",
                            "graphId": PINNED,
                        },
                        "head": {"text": "ShrimpFormer-X", "label": "METHOD"},
                        "tail": {"text": "shrimp larvae", "label": "TASK"},
                    }
                ],
                "citationDraft": "Lin. ShrimpFormer-X IEEE WISA, 2025. DOI: 10.1000/example",
                "notice": "候选参考文献；引用前阅读原文并核验书目信息。",
            }
        }
    )


def graph_payload() -> bytes:
    root = f"{PINNED}:Publication:4725bc95"
    return body(
        {
            "data": {
                "nodes": [
                    {"kind": "Publication", "props": {"id": root, "publicationId": PUB_ID, "graphId": PINNED}},
                    {"kind": "Person", "props": {"id": f"{PINNED}:Person:abc", "graphId": PINNED, "name": "Lin"}},
                ],
                "edges": [{"id": "e1", "kind": "AUTHORED", "source": f"{PINNED}:Person:abc", "target": root}],
                "paths": [{"nodes": [root, f"{PINNED}:Person:abc"], "edges": ["e1"]}],
                "rootId": root,
            },
            "meta": {"graphId": PINNED, "mode": "paper", "hasMorePaths": False, "notice": "局部有界路径"},
        }
    )


def build_client(routes) -> tuple[KGClient, FakeTransport]:
    transport = FakeTransport(routes)
    return KGClient("http://stub", transport=transport, expected_graph_id=PINNED), transport


def tool_by_name(tools, name: str):
    for item in tools:
        if getattr(item, "name", "") == name:
            return item
    raise AssertionError(f"tool {name!r} not found in {[getattr(t, 'name', '?') for t in tools]}")


class RecordingChatModel(BaseChatModel):
    """Records which tools the harness offers the model, then answers nothing."""

    bound_tools: list[str] = Field(default_factory=list)
    seen_messages: int = 0

    @property
    def _llm_type(self) -> str:
        return "recording"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN003
        self.bound_tools = [
            getattr(item, "name", None) or getattr(item, "__name__", str(item)) for item in tools
        ]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001, ANN003
        self.seen_messages = len(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="(stub)"))])


class ToolSurfaceTests(unittest.TestCase):
    def test_declared_names_match_built_tools(self) -> None:
        client, _ = build_client({})
        tools = build_tools(client, graph_id=PINNED)
        self.assertEqual(tuple(item.name for item in tools), RESEARCH_TOOL_NAMES)

    def test_search_tool_echoes_parameters_and_expansion(self) -> None:
        client, transport = build_client({"/api/publications": [(200, search_payload())]})
        tools = build_tools(client, graph_id=PINNED)
        result = tool_by_name(tools, "search_papers").invoke({"query": "transformer", "method": "扩散模型"})

        self.assertEqual(result["applied"]["q"], "transformer")
        self.assertEqual(result["applied"]["method"], "扩散模型")
        self.assertEqual(result["applied"]["limit"], "5")
        self.assertEqual(result["expandedTerms"]["method"], ["diffusion model", "diffusion models"])
        _, params = transport.calls[0]
        self.assertEqual(params["method"], "扩散模型")

    def test_search_tool_caps_limit_below_the_tool_ceiling(self) -> None:
        client, transport = build_client({"/api/publications": [(200, search_payload())]})
        tools = build_tools(client, graph_id=PINNED)
        result = tool_by_name(tools, "search_papers").invoke({"query": "x", "limit": 999})
        self.assertEqual(result["applied"]["limit"], "25")
        _, params = transport.calls[0]
        self.assertEqual(params["limit"], "25")

    def test_every_paper_carries_a_citable_evidence_ref(self) -> None:
        client, _ = build_client({"/api/publications": [(200, search_payload())]})
        result = tool_by_name(build_tools(client, graph_id=PINNED), "search_papers").invoke({"query": "x"})
        paper = result["papers"][0]
        self.assertEqual(paper["evidence"]["sourceId"], paper["publicationId"])
        self.assertEqual(paper["evidence"]["evidenceLevel"], "title")
        self.assertEqual(paper["evidence"]["verificationStatus"], "unverified")

    def test_tool_results_are_compact_for_the_model(self) -> None:
        """工具返回值要进模型上下文，必须精简 —— 这是成本与延迟的直接约束。"""
        client, _ = build_client({"/api/publications": [(200, search_payload())]})
        result = tool_by_name(build_tools(client, graph_id=PINNED), "search_papers").invoke({"query": "x"})
        paper = result["papers"][0]
        self.assertEqual(
            set(paper.keys()),
            {"publicationId", "title", "year", "doi", "evidence"},
            "模型视图只该有判断需要的那几列",
        )
        self.assertEqual(
            set(paper["evidence"].keys()),
            {"sourceId", "evidenceLevel", "verificationStatus"},
        )
        self.assertNotIn("urls", paper)
        self.assertNotIn("modelApplicationStatus", paper)

    def test_evidence_tool_keeps_assertions_as_candidates(self) -> None:
        client, _ = build_client({"/api/publication": [(200, detail_payload())]})
        result = tool_by_name(build_tools(client, graph_id=PINNED), "get_paper_evidence").invoke(
            {"publication_id": PUB_ID}
        )
        self.assertEqual(result["publicationId"], PUB_ID)
        self.assertEqual(result["bibliographyEvidence"]["sourceId"], PUB_ID)
        assertion = result["assertions"][0]
        self.assertEqual(assertion["status"], "candidate")
        self.assertEqual(assertion["predicate"], "USED_FOR")
        self.assertFalse(assertion["confidenceCalibrated"])
        self.assertEqual(assertion["evidence"]["sourceId"], result["assertions"][0]["assertionId"])
        self.assertEqual(assertion["evidence"]["evidenceLevel"], "title")
        self.assertEqual(assertion["evidence"]["verificationStatus"], "unverified")

    def test_graph_tool_is_bounded(self) -> None:
        client, transport = build_client({"/api/graph": [(200, graph_payload())]})
        result = tool_by_name(build_tools(client, graph_id=PINNED), "explore_graph").invoke(
            {"publication_id": PUB_ID, "mode": "paper", "limit": 999}
        )
        self.assertEqual(result["graphId"], PINNED)
        self.assertEqual(result["rootId"], f"{PINNED}:Publication:4725bc95")
        _, params = transport.calls[0]
        self.assertEqual(params["limit"], "15")

    def test_scope_tool_reports_real_counts_and_pinned_version(self) -> None:
        client, _ = build_client({"/api/health": [(200, health_payload())]})
        result = tool_by_name(build_tools(client, graph_id=PINNED), "report_graph_scope").invoke({})
        self.assertEqual(result["graphId"], PINNED)
        self.assertEqual(result["pinnedGraphId"], PINNED)
        self.assertEqual(result["scope"]["candidateAssertions"], 21497)

    def test_unavailable_graph_raises_instead_of_returning_nothing(self) -> None:
        error = body({"error": {"code": "neo4j_unavailable", "message": "未使用离线替代数据。"}})
        client, _ = build_client({"/api/publications": [(503, error)]})
        with self.assertRaises(KGUnavailable):
            tool_by_name(build_tools(client, graph_id=PINNED), "search_papers").invoke({"query": "x"})

    def test_real_empty_result_is_not_an_error(self) -> None:
        client, _ = build_client({"/api/publications": [(200, search_payload(items=[]))]})
        result = tool_by_name(build_tools(client, graph_id=PINNED), "search_papers").invoke({"query": "nothing"})
        self.assertEqual(result["papers"], [])


class SafetyPostureTests(unittest.TestCase):
    def test_backend_is_in_memory_and_not_a_sandbox(self) -> None:
        backend = build_backend()
        self.assertIsInstance(backend, StateBackend)
        # No sandbox backend => the built-in `execute` tool cannot run commands.
        self.assertFalse(isinstance(backend, SandboxBackendProtocol))

    def test_agent_compiles_and_is_offered_the_research_tools(self) -> None:
        client, _ = build_client({"/api/health": [(200, health_payload())]})
        model = RecordingChatModel()
        settings = AgentSettings(
            kg_base_url="http://stub",
            expected_graph_id=PINNED,
            kg_timeout=5.0,
            llm_api_key="test-key",
            llm_base_url=None,
            llm_model="test-model",
        )
        agent = build_agent(client=client, settings=settings, model=model)
        agent.invoke({"messages": [{"role": "user", "content": "有什么关于 transformer 的论文？"}]})

        offered = set(model.bound_tools)
        for name in RESEARCH_TOOL_NAMES:
            with self.subTest(tool=name):
                self.assertIn(name, offered, f"{name} was not offered to the model; offered={sorted(offered)}")
        # The model was actually called (the graph ran), not just constructed.
        self.assertGreater(model.seen_messages, 0)


class StubMetadata:
    """Duck-typed stand-in for ``ExternalMetadataClient``: no network, no cache."""

    def __init__(self, *, record: object = None, error: Exception | None = None) -> None:
        self.record = record
        self.error = error
        self.calls: list[dict] = []

    def lookup_publication(self, *, doi=None, urls=()):  # noqa: ANN001, ANN202
        self.calls.append({"doi": doi, "urls": list(urls)})
        if self.error is not None:
            raise self.error
        return self.record


class AbstractToolTests(unittest.TestCase):
    """``read_paper_abstract`` — the tool that finally lets the agent read content.

    Before it existed the agent could only ever restate titles, which is why
    every answer looked like a metadata dump.
    """

    def _invoke(self, metadata, publication_id: str = PUB_ID):
        client, _ = build_client({"/api/publication": [(200, detail_payload())]})
        tools = build_tools(client, graph_id=PINNED, metadata=metadata)
        return tool_by_name(tools, "read_paper_abstract").invoke({"publication_id": publication_id})

    def test_abstract_comes_back_as_abstract_level_evidence(self) -> None:
        record = ExternalRecord(
            source="semanticscholar",
            doi="10.1000/example",
            title="ShrimpFormer-X: A Transformer-Based Framework",
            abstract="A" * 400,
            year=2025,
            venue="IEEE WISA",
        )
        result = self._invoke(StubMetadata(record=record))
        self.assertTrue(result["available"])
        self.assertEqual(result["evidenceLevel"], "abstract")
        self.assertEqual(result["source"], "semanticscholar")
        self.assertEqual(result["sourceLabel"], "Semantic Scholar")
        self.assertEqual(result["publicationId"], PUB_ID)
        self.assertEqual(result["evidence"]["sourceType"], "external_record")
        self.assertEqual(result["evidence"]["sourceId"], "doi:10.1000/example")
        self.assertEqual(result["evidence"]["evidenceLevel"], "abstract")
        self.assertTrue(result["evidenceText"].strip())

    def test_the_graph_records_doi_is_used_as_the_lookup_key(self) -> None:
        stub = StubMetadata(record=None)
        self._invoke(stub)
        self.assertEqual(stub.calls[0]["doi"], "10.1000/example")
        self.assertEqual(stub.calls[0]["urls"], ["https://doi.org/10.1000/example"])

    def test_no_identifier_is_reported_as_no_identifier(self) -> None:
        result = self._invoke(StubMetadata(error=ExternalNoIdentifier("no DOI or arXiv id")))
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "no_identifier")

    def test_a_record_without_an_abstract_is_reported_as_such(self) -> None:
        result = self._invoke(StubMetadata(record=None))
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "no_abstract")

    def test_disabled_sources_report_disabled_not_empty(self) -> None:
        result = self._invoke(None)
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "disabled")

    def test_a_source_outage_raises_instead_of_looking_like_an_empty_result(self) -> None:
        with self.assertRaises(ExternalUnavailable):
            self._invoke(StubMetadata(error=ExternalUnavailable("semanticscholar answered HTTP 429")))

    def test_abstract_for_the_model_is_capped(self) -> None:
        record = ExternalRecord(
            source="openalex", doi="10.1000/example", title="t", abstract="word " * 2000,
        )
        result = self._invoke(StubMetadata(record=record))
        self.assertLess(len(result["evidenceText"]), 2200)
        self.assertIn("已截断", result["evidenceText"])


class PromptContractTests(unittest.TestCase):
    """The prompt is a contract; weakening it should fail a test, not go unnoticed.

    2026-10-10：提示词从"禁令清单"改版为"研究工作法"。硬约束一条没删（下面第一条
    测试守着它们），新增的三条守着改版的**意图** —— 否则下一轮很容易又滑回
    "把工具结果原样列成清单 + 把参数抄进正文"的检索引擎形态。
    """

    def test_prompt_keeps_the_hard_constraints(self) -> None:
        required = (
            "来源",  # must attach a source id
            "候选",  # candidate stays candidate
            "title",  # evidence depth is title-only
            "CITES",  # refuse citation-count style questions
            "meta.applied",  # the parameter echo exists (now shown by the UI)
            "图谱不可用",  # distinguish an outage from an empty result
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, SYSTEM_PROMPT)

    def test_prompt_asks_for_a_verdict_and_a_selection(self) -> None:
        """改版的核心：先给判断、精选少而准、说明排除理由。"""
        for phrase in ("结论", "精选", "排除"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, SYSTEM_PROMPT)

    def test_prompt_treats_citations_as_claim_level_not_sentence_level(self) -> None:
        """引用按「观点」而不是按「句」—— 防止滑回"逐句硬挂 id"的啰嗦形态。"""
        self.assertIn("观点", SYSTEM_PROMPT)
        self.assertNotIn(
            "挂不上来源的句子就不要写",
            SYSTEM_PROMPT,
            "句子级引用要求会把回答变成长清单；已改为观点级",
        )

    def test_prompt_keeps_mechanical_meta_out_of_the_prose(self) -> None:
        """参数回显 / 证据深度 / 覆盖范围交给界面常驻展示，不再逐轮抄进正文。"""
        self.assertIn("meta.applied", SYSTEM_PROMPT)
        self.assertIn("界面", SYSTEM_PROMPT)

    def test_prompt_knows_both_evidence_depths(self) -> None:
        """2026-10-10: abstracts are now available, so the prompt must say so.

        Without this the model keeps treating title-only evidence as the ceiling
        and never calls ``read_paper_abstract`` — which is exactly the state that
        made it read like a metadata lookup rather than a researcher.
        """
        for phrase in ("abstract", "read_paper_abstract", "摘要"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, SYSTEM_PROMPT)
        # The older, stronger claim ("evidence depth is title-only") must be gone.
        self.assertNotIn("证据深度只有题名", SYSTEM_PROMPT)

    def test_prompt_denies_host_filesystem_access(self) -> None:
        self.assertIn("StateBackend", SYSTEM_PROMPT)


class CliTests(unittest.TestCase):
    """Smoke-test the CLI entry point.

    This exists because a real run found an import-order bug that every other
    test missed: ``run.py`` imported ``kg_client`` *before* the ``_paths`` wiring
    ran, so the CLI died with ModuleNotFoundError while the library was fine.
    """

    def test_run_module_imports_and_needs_llm_settings(self) -> None:
        import importlib

        module = importlib.import_module("run")
        with mock.patch.dict(os.environ, {}, clear=False):
            for name in ("LLM_API_KEY", "LLM_MODEL"):
                os.environ.pop(name, None)
            code = module.main(["随便问一句"])
        self.assertEqual(code, 2, "missing LLM settings must exit 2, not start a run")

    def test_research_tools_are_reachable_through_the_cli_import_graph(self) -> None:
        import importlib

        module = importlib.import_module("run")
        self.assertTrue(hasattr(module, "build_agent"))
        self.assertTrue(hasattr(module, "KGClient"))

    def test_citation_report_counts_ids_in_the_answer_not_in_tool_results(self) -> None:
        import run as run_module

        available = ["conf/aaai/A25", "conf/cvpr/B25"]
        answer = (
            "结论先行：图谱中有两篇相关论文。\n"
            "依据一：conf/aaai/A25 的题名出现了关键词（证据等级 title，核验状态 unverified）。\n"
            "依据二：conf/cvpr/B25 同样如此。\n"
            "局限：题名级证据不能证明论文的具体结论。"
        )
        report = run_module.citation_report(answer, available)
        self.assertEqual(report["available"], 2)
        self.assertEqual(report["cited"], 2)
        # 4 considered sentences, 2 of them carry an id.
        self.assertEqual(report["consideredSentences"], 4)
        self.assertEqual(report["attributedSentences"], 2)
        self.assertEqual(report["citationRate"], 0.5)

    def test_citation_report_flags_an_answer_that_cites_nothing(self) -> None:
        import run as run_module

        available = ["conf/aaai/A25"]
        answer = "图谱里有不少关于 transformer 的论文，其中若干篇来自 CVPR 2025，涵盖了生成与检测任务。"
        report = run_module.citation_report(answer, available)
        self.assertEqual(report["cited"], 0)
        self.assertEqual(report["citedIds"], [])
        self.assertEqual(report["citationRate"], 0.0, "an answer citing nothing must score 0")

    def test_citation_report_ignores_short_fragments(self) -> None:
        import run as run_module

        report = run_module.citation_report("###\nA\n", ["conf/aaai/A25"])
        self.assertEqual(report["consideredSentences"], 0)
        self.assertEqual(report["citationRate"], 0.0)

    def test_citation_report_on_an_empty_answer(self) -> None:
        import run as run_module

        report = run_module.citation_report("", ["conf/aaai/A25"])
        self.assertEqual(report["cited"], 0)
        self.assertEqual(report["consideredSentences"], 0)


class ConfigurationTests(unittest.TestCase):
    def test_missing_llm_settings_are_reported_not_defaulted(self) -> None:
        settings = AgentSettings(
            kg_base_url="http://stub",
            expected_graph_id=None,
            kg_timeout=5.0,
            llm_api_key="",
            llm_base_url=None,
            llm_model="",
        )
        self.assertEqual(set(settings.missing_for_run()), {"LLM_API_KEY", "LLM_MODEL"})
        with self.assertRaises(ConfigurationError):
            settings.require_runnable()

    def test_ready_settings_pass(self) -> None:
        settings = AgentSettings(
            kg_base_url="http://stub",
            expected_graph_id=PINNED,
            kg_timeout=5.0,
            llm_api_key="k",
            llm_base_url="https://example.invalid/v1",
            llm_model="m",
        )
        self.assertEqual(settings.missing_for_run(), ())
        settings.require_runnable()


if __name__ == "__main__":
    unittest.main(verbosity=2)
