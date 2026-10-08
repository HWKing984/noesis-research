"""Agent 服务的离线测试：事件翻译、引用核查、运行登记表、HTTP/SSE 面。

模型侧用**脚本化假 agent**（`agent_factory` 注入缝），所以在没有 LLM 的情况下也能把
"提问 → 事件流 → 引用核查 → 结束" 整条路径测完。

    services/research-agent/.venv/Scripts/python -m unittest discover \
        -s services/research-agent -t services/research-agent -v
"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_IMPORT_ERROR: str | None = None
try:
    # 先导入本包：它会装配 sys.path（kg_client 在 integrations/knowledge-graph）
    import noesis_research_agent  # noqa: F401

    from langchain_core.messages import AIMessage, ToolMessage

    from kg_client import KGClient

    from noesis_research_agent.config import AgentSettings
    from noesis_research_agent.runner import (
        RunRegistry,
        citation_report,
        extract_source_ids,
        summarize_tool_result,
        translate_chunks,
    )
except Exception as exc:  # pragma: no cover - core/API-only runs
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

if _IMPORT_ERROR is not None:
    raise unittest.SkipTest(f"runner suite unavailable ({_IMPORT_ERROR})")

PINNED = "ai-literature-ed16399925fac2a599ed"
PAPER_ID = "conf/IEEEwisa/LinGHW25"

try:
    from fastapi.testclient import TestClient

    from noesis_research_agent.server import create_app

    _HAS_FASTAPI = True
    _FASTAPI_ERROR = ""
except Exception as exc:  # pragma: no cover - agent venv without web deps
    _HAS_FASTAPI = False
    _FASTAPI_ERROR = f"{type(exc).__name__}: {exc}"

def tool_result_message(tool_name: str, payload: dict) -> ToolMessage:
    return ToolMessage(
        content=json.dumps(payload, ensure_ascii=False),
        tool_call_id="call-1",
        name=tool_name,
    )


def search_payload(pub_id: str = PAPER_ID) -> dict:
    return {
        "applied": {"q": "transformer", "limit": "5"},
        "expandedTerms": {},
        "papers": [
            {
                "publicationId": pub_id,
                "title": "ShrimpFormer-X",
                "year": 2025,
                "evidence": {
                    "sourceType": "kg_bibliography",
                    "sourceId": pub_id,
                    "publicationId": pub_id,
                    "evidenceLevel": "title",
                    "verificationStatus": "unverified",
                },
            }
        ],
    }


class ScriptedAgent:
    """按脚本吐 chunks，形状与 langgraph `stream_mode="updates"` 一致。"""

    def __init__(self, chunks, *, raises: Exception | None = None) -> None:
        self._chunks = chunks
        self._raises = raises
        self.calls = 0

    def stream(self, *_args, **_kwargs):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return iter(self._chunks)


class RoundAgent:
    """每次 stream() 返回下一轮脚本 —— 用于测服务端的"无工具结果自动重试"。"""

    def __init__(self, rounds) -> None:
        self._rounds = rounds
        self.calls = 0

    def stream(self, *_args, **_kwargs):
        index = min(self.calls, len(self._rounds) - 1)
        self.calls += 1
        return iter(self._rounds[index])


def chunk(node: str, messages) -> dict:
    return {node: {"messages": messages}}


CITING_CHUNKS = [
    chunk("model", [AIMessage(content="", tool_calls=[{"name": "search_papers", "args": {"query": "transformer"}, "id": "c1"}])]),
    chunk("tools", [tool_result_message("search_papers", search_payload())]),
    chunk("model", [AIMessage(content=f"结论先行：图谱里有相关论文。\n依据一：{PAPER_ID} 的题名出现了关键词（证据等级 title，未核验）。\n局限：题名级证据不能证明具体结论。")]),
]

UNCITED_CHUNKS = [
    chunk("model", [AIMessage(content="", tool_calls=[{"name": "search_papers", "args": {"query": "transformer"}, "id": "c1"}])]),
    chunk("tools", [tool_result_message("search_papers", search_payload())]),
    chunk("model", [AIMessage(content="图谱里有不少关于 transformer 的论文，其中若干篇来自 CVPR 2025，涵盖生成与检测任务。")]),
]


class ExtractIdTests(unittest.TestCase):
    def test_keeps_order_and_dedupes(self) -> None:
        payload = {"a": {"sourceId": "x"}, "b": [{"sourceId": "y"}, {"sourceId": "x"}], "c": {"assertionId": "z"}}
        self.assertEqual(extract_source_ids(payload), ["x", "y", "z"])

    def test_ignores_blank_and_non_mapping(self) -> None:
        self.assertEqual(extract_source_ids({"sourceId": "   "}), [])
        self.assertEqual(extract_source_ids("not a mapping"), [])
        self.assertEqual(extract_source_ids(None), [])


class SummarizeTests(unittest.TestCase):
    def test_counts_instead_of_shipping_the_payload(self) -> None:
        summary = summarize_tool_result("search_papers", search_payload())
        self.assertEqual(summary["papers"], 1)
        self.assertEqual(summary["applied"]["q"], "transformer")
        # 摘要是"规模"，不是把整包论文搬给前端
        self.assertIsInstance(summary["papers"], int)

    def test_search_results_carry_a_compact_paper_list_for_the_evidence_rail(self) -> None:
        summary = summarize_tool_result("search_papers", search_payload())
        items = summary["paperItems"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["publicationId"], PAPER_ID)
        self.assertEqual(items[0]["title"], "ShrimpFormer-X")
        self.assertEqual(items[0]["evidenceLevel"], "title")
        self.assertEqual(
            set(items[0].keys()),
            {"publicationId", "title", "year", "evidenceLevel", "verificationStatus"},
            "右栏论文卡只该有这几列",
        )
        self.assertNotIn("evidence", items[0])

    def test_paper_list_is_capped_for_the_frontend(self) -> None:
        payload = search_payload()
        payload["papers"] = [dict(payload["papers"][0], publicationId=f"conf/x/{i}") for i in range(30)]
        summary = summarize_tool_result("search_papers", payload)
        self.assertEqual(summary["papers"], 30)
        self.assertEqual(len(summary["paperItems"]), 20)

    def test_detail_result_carries_the_paper_title(self) -> None:
        summary = summarize_tool_result("get_paper", {"publicationId": PAPER_ID, "title": "T"})
        self.assertEqual(summary["publicationId"], PAPER_ID)
        self.assertEqual(summary["title"], "T")

    def test_graph_summary_keeps_node_and_edge_counts(self) -> None:
        summary = summarize_tool_result("explore_graph", {"nodes": [1, 2], "edges": [1], "paths": [], "mode": "paper", "graphId": PINNED})
        self.assertEqual(summary["nodes"], 2)
        self.assertEqual(summary["edges"], 1)
        self.assertEqual(summary["paths"], 0)
        self.assertEqual(summary["mode"], "paper")

    def test_unknown_shape_falls_back_to_keys(self) -> None:
        self.assertEqual(summarize_tool_result("x", {"weird": 1})["keys"], ["weird"])


class CitationRuleTests(unittest.TestCase):
    def test_matches_the_cli_rule(self) -> None:
        report = citation_report(
            f"结论先行：图谱中有两篇相关论文。\n依据一：{PAPER_ID} 的题名出现关键词。\n局限：题名级证据不能证明具体结论。",
            [PAPER_ID, "conf/cvpr/B25"],
        )
        self.assertEqual(report["available"], 2)
        self.assertEqual(report["cited"], 1)
        self.assertEqual(report["citedIds"], [PAPER_ID])
        self.assertEqual(report["consideredSentences"], 3)
        self.assertEqual(report["attributedSentences"], 1)
        self.assertTrue(report["passes"])

    def test_fluent_answer_without_ids_fails(self) -> None:
        report = citation_report("图谱里有不少论文，覆盖生成与检测任务，值得进一步阅读。", [PAPER_ID])
        self.assertEqual(report["cited"], 0)
        self.assertFalse(report["passes"])


class TranslateTests(unittest.TestCase):
    def _events(self, chunks):
        return list(
            translate_chunks(chunks, run_id="r1", question="q", graph_id=PINNED, model="m")
        )

    def test_message_stream_becomes_answer_delta_events(self) -> None:
        """双通道流：messages 通道的正文 token → answer_delta，界面才能逐字渲染。"""
        from langchain_core.messages import AIMessageChunk

        chunks = [
            ("messages", (AIMessageChunk(content="图谱里"), {"langgraph_node": "model"})),
            ("messages", (AIMessageChunk(content=f"有 {PAPER_ID}。"), {"langgraph_node": "model"})),
            ("updates", chunk("model", [AIMessage(content=f"图谱里有 {PAPER_ID}。")])),
        ]
        events = self._events(chunks)
        deltas = [e for e in events if e["type"] == "answer_delta"]
        self.assertEqual([e["delta"] for e in deltas], ["图谱里", f"有 {PAPER_ID}。"])
        answer = next(e for e in events if e["type"] == "answer")
        self.assertEqual(answer["text"], f"图谱里有 {PAPER_ID}。")

    def test_tool_decision_chunks_are_not_streamed_as_answer(self) -> None:
        """模型决定调工具的那几帧（带 tool_calls / tool_call_chunks）不能当回答播出去。"""
        from langchain_core.messages import AIMessageChunk

        deciding = AIMessageChunk(content="", tool_calls=[{"name": "search_papers", "args": {}, "id": "c1"}])
        with_call_chunk = AIMessageChunk(content="", tool_call_chunks=[{"name": "search_papers", "args": "{}", "id": "c1", "index": 0, "type": "tool_call_chunk"}])
        chunks = [
            ("messages", (with_call_chunk, {})),
            ("messages", (deciding, {})),
            ("messages", (AIMessageChunk(content="正文"), {})),
        ]
        deltas = [e for e in self._events(chunks) if e["type"] == "answer_delta"]
        self.assertEqual([e["delta"] for e in deltas], ["正文"])

    def test_tool_json_never_streams_as_answer_even_on_messages_only(self) -> None:
        """回归（thome 报的问题）：工具返回的原始 JSON 绝不能混进回答正文。

        真实运行里 updates 通道可能一条都不产出 —— ToolMessage 从 messages
        通道整条流过，旧过滤（只挡 tool_calls）会把它的 JSON 当正文播出。
        """
        from langchain_core.messages import AIMessageChunk, ToolMessage

        tool_payload = {
            "applied": {"q": "transformer", "limit": "25", "offset": "0"},
            "papers": [
                {
                    "publicationId": PAPER_ID,
                    "title": "ShrimpFormer-X",
                    "year": 2025,
                    "evidence": {"sourceId": PAPER_ID, "evidenceLevel": "title", "verificationStatus": "unverified"},
                }
            ],
        }
        call_id = "call-1"
        chunks = [
            ("messages", (AIMessageChunk(content="我先确认图谱就绪状态，再检索。"), {})),
            ("messages", (AIMessageChunk(content="", tool_calls=[{"name": "search_papers", "args": {"query": "x"}, "id": call_id}]), {})),
            ("messages", (ToolMessage(content=json.dumps(tool_payload, ensure_ascii=False), tool_call_id=call_id, name="search_papers"), {})),
            ("messages", (AIMessageChunk(content=f"结论先行：命中 {PAPER_ID}。"), {})),
        ]
        events = self._events(chunks)
        deltas = "".join(e["delta"] for e in events if e["type"] == "answer_delta")
        assert '{"applied"' not in deltas, f"工具 JSON 泄漏进正文：{deltas[:200]}"
        assert "publicationId" not in deltas

        kinds = [e["type"] for e in events]
        assert "tool_call" in kinds, kinds
        assert "tool_result" in kinds, kinds
        result = next(e for e in events if e["type"] == "tool_result")
        self.assertEqual(result["evidenceIds"], [PAPER_ID])

        answer = next(e for e in events if e["type"] == "answer")
        # 权威全文 = 最后一次工具结果之后的正文，旁白与工具 JSON 都不在
        self.assertEqual(answer["text"], f"结论先行：命中 {PAPER_ID}。")
        self.assertTrue(answer["citation"]["passes"])
        self.assertEqual(answer["citation"]["citedIds"], [PAPER_ID])

    def test_tool_result_not_duplicated_across_channels(self) -> None:
        """updates 与 messages 都见到同一条工具结果时，事件只发一次；且**迟到的重复
        副本不得重置正文边界**（跨通道乱序会把已流式输出的回答清掉——实际发生过）。"""
        from langchain_core.messages import AIMessageChunk, ToolMessage

        payload = json.dumps(search_payload(), ensure_ascii=False)
        call_id = "call-1"
        chunks = [
            ("updates", chunk("tools", [tool_result_message("search_papers", search_payload())])),
            ("messages", (ToolMessage(content=payload, tool_call_id=call_id, name="search_papers"), {})),
            ("messages", (AIMessageChunk(content=f"结论：命中 {PAPER_ID}。"), {})),
            # 迟到的重复副本：若它再次重置边界，上面已流出的正文会被清空
            ("updates", chunk("tools", [tool_result_message("search_papers", search_payload())])),
        ]
        events = self._events(chunks)
        results = [e for e in events if e["type"] == "tool_result"]
        self.assertEqual(len(results), 1, "同一 tool_call_id 只发一次")
        answer = next(e for e in events if e["type"] == "answer")
        self.assertEqual(answer["text"], f"结论：命中 {PAPER_ID}。")

    def test_tail_survives_late_duplicate_tool_result(self) -> None:
        """无 updates 权威全文时（updates 通道缺席），回答取自流式 tail，
        且迟到的重复工具结果不会把 tail 清空。"""
        from langchain_core.messages import AIMessageChunk, ToolMessage

        call_id = "call-1"
        chunks = [
            ("messages", (AIMessageChunk(content="先检索。"), {})),
            ("messages", (AIMessageChunk(content="", tool_calls=[{"name": "search_papers", "args": {"query": "x"}, "id": call_id}]), {})),
            ("messages", (ToolMessage(content=json.dumps(search_payload(), ensure_ascii=False), tool_call_id=call_id, name="search_papers"), {})),
            ("messages", (AIMessageChunk(content=f"结论：命中 {PAPER_ID}。"), {})),
            # 迟到的重复副本（跨通道乱序）
            ("messages", (ToolMessage(content=json.dumps(search_payload(), ensure_ascii=False), tool_call_id=call_id, name="search_papers"), {})),
        ]
        events = self._events(chunks)
        answer = next(e for e in events if e["type"] == "answer")
        self.assertEqual(answer["text"], f"结论：命中 {PAPER_ID}。")
        self.assertTrue(answer["citation"]["passes"])
        self.assertEqual(answer["citation"]["citedIds"], [PAPER_ID])

    def test_subgraph_tool_results_are_collected_and_subagent_text_not_streamed(self) -> None:
        """回归（间歇性漏证据）：deepagents 的 task 工具把工具执行放进子图，
        不开 subgraphs 就看不到 ToolMessage —— 证据收集会间歇性漏空。
        三元组 (namespace, mode, payload) 里：工具结果照收；子代理叙述不进回答。
        """
        from langchain_core.messages import AIMessageChunk, ToolMessage

        sub_ns = "task:abc123"
        payload = json.dumps(search_payload(), ensure_ascii=False)
        chunks = [
            ("messages", (AIMessageChunk(content="先查一下", role="assistant"), {"langgraph_checkpoint_ns": ""})),
            (sub_ns, "messages", (AIMessageChunk(content="子代理内部叙述", role="assistant"), {"langgraph_checkpoint_ns": sub_ns})),
            (sub_ns, "messages", (ToolMessage(content=payload, tool_call_id="call-9", name="search_papers"), {"langgraph_checkpoint_ns": sub_ns})),
            ("messages", (AIMessageChunk(content=f"结论：见 {PAPER_ID}。"), {"langgraph_checkpoint_ns": ""})),
        ]
        events = self._events(chunks)
        deltas = "".join(e["delta"] for e in events if e["type"] == "answer_delta")
        self.assertEqual(deltas, f"先查一下结论：见 {PAPER_ID}。", "子代理叙述不得混入回答")
        results = [e for e in events if e["type"] == "tool_result"]
        self.assertEqual(len(results), 1, "子图里的工具结果必须被收集")
        self.assertEqual(results[0]["evidenceIds"], [PAPER_ID])
        answer = next(e for e in events if e["type"] == "answer")
        self.assertTrue(answer["citation"]["passes"])

    def test_updates_only_behaviour_unchanged(self) -> None:
        """旧形态（纯 updates）回归：事件顺序与全文不受消息通道改造影响。"""
        chunks = [
            chunk("model", [AIMessage(content="", tool_calls=[{"name": "search_papers", "args": {"query": "transformer"}, "id": "c1"}])]),
            chunk("tools", [tool_result_message("search_papers", search_payload())]),
            chunk("model", [AIMessage(content=f"结论先行：图谱里有相关论文。\n依据一：{PAPER_ID}。")]),
        ]
        events = self._events(chunks)
        self.assertEqual(
            [e["type"] for e in events],
            ["run_started", "tool_call", "tool_result", "answer", "done"],
        )
        self.assertTrue(next(e for e in events if e["type"] == "answer")["citation"]["passes"])

    def test_full_happy_path_event_order(self) -> None:
        events = self._events(CITING_CHUNKS)
        kinds = [e["type"] for e in events]
        self.assertEqual(
            kinds,
            ["run_started", "tool_call", "tool_result", "answer", "done"],
        )
        self.assertEqual(events[1]["tool"], "search_papers")
        self.assertEqual(events[1]["args"]["query"], "transformer")
        self.assertEqual(events[2]["evidenceIds"], [PAPER_ID])
        self.assertEqual(events[2]["summary"]["papers"], 1)
        self.assertTrue(events[3]["citation"]["passes"])
        self.assertEqual(events[4]["status"], "ok")

    def test_answer_without_citation_is_still_ok_status_but_gate_fails(self) -> None:
        events = self._events(UNCITED_CHUNKS)
        answer = next(e for e in events if e["type"] == "answer")
        self.assertFalse(answer["citation"]["passes"])
        # 运行本身成功结束；是"引用闸门"判它不合格，两件事不能混为一谈
        self.assertEqual(events[-1]["status"], "ok")

    def test_tool_error_message_becomes_tool_error_event(self) -> None:
        chunks = [
            chunk("model", [AIMessage(content="", tool_calls=[{"name": "search_papers", "args": {}, "id": "c1"}])]),
            chunk(
                "tools",
                [
                    ToolMessage(
                        content="KGUnavailable: 图谱不可用",
                        tool_call_id="c1",
                        name="search_papers",
                        status="error",
                    )
                ],
            ),
        ]
        events = self._events(chunks)
        kinds = [e["type"] for e in events]
        self.assertIn("tool_error", kinds)
        self.assertNotIn("tool_result", kinds)

    def test_run_started_carries_graph_and_model(self) -> None:
        first = self._events([])[0]
        self.assertEqual(first["type"], "run_started")
        self.assertEqual(first["graphId"], PINNED)
        self.assertEqual(first["model"], "m")


class RegistryTests(unittest.TestCase):
    def test_lifecycle_and_tailing(self) -> None:
        registry = RunRegistry()
        run = registry.create("q", graph_id=PINNED, model="m")
        events, finished = registry.since(run.run_id, 0)
        self.assertEqual(events, [])
        self.assertFalse(finished)

        registry.append(run.run_id, {"type": "tool_call", "tool": "t"})
        registry.append(run.run_id, {"type": "answer", "text": "a", "citation": {"passes": False}})
        events, finished = registry.since(run.run_id, 0)
        self.assertEqual(len(events), 2)
        self.assertFalse(finished)

        registry.append(run.run_id, {"type": "done", "status": "ok"})
        _, finished = registry.since(run.run_id, 2)
        self.assertTrue(finished)
        self.assertEqual(run.status, "ok")
        self.assertEqual(run.answer, "a")
        self.assertEqual(run.to_dict()["toolCallCount"], 1)

    def test_failed_event_marks_status(self) -> None:
        registry = RunRegistry()
        run = registry.create("q", graph_id=None, model="m")
        registry.append(run.run_id, {"type": "failed", "message": "boom"})
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.error, "boom")

    def test_unknown_run_is_finished_and_empty(self) -> None:
        registry = RunRegistry()
        self.assertEqual(registry.since("nope", 0), ([], True))

    def test_old_runs_are_evicted(self) -> None:
        registry = RunRegistry(max_runs=2)
        ids = [registry.create(f"q{i}", graph_id=None, model="m").run_id for i in range(3)]
        self.assertIsNone(registry.get(ids[0]))
        self.assertIsNotNone(registry.get(ids[2]))


@unittest.skipUnless(_HAS_FASTAPI, f"fastapi not installed ({_FASTAPI_ERROR})")
class HttpSurfaceTests(unittest.TestCase):
    def _settings(self, *, with_llm: bool = True) -> AgentSettings:
        return AgentSettings(
            kg_base_url="http://stub",
            expected_graph_id=PINNED,
            kg_timeout=5.0,
            llm_api_key="k" if with_llm else "",
            llm_base_url=None,
            llm_model="m" if with_llm else "",
        )

    def _client(self, *, chunks=None, raises=None, with_llm=True):
        agent = ScriptedAgent(chunks if chunks is not None else CITING_CHUNKS, raises=raises)
        app = create_app(
            settings=self._settings(with_llm=with_llm),
            client=KGClient("http://stub", expected_graph_id=PINNED),
            agent_factory=lambda **_kwargs: agent,
        )
        return TestClient(app), agent

    def test_start_run_without_llm_is_503_not_a_fake_run(self) -> None:
        client, agent = self._client(with_llm=False)
        response = client.post("/runs", json={"question": "有什么关于 transformer 的论文？"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "llm_not_configured")
        self.assertEqual(agent.calls, 0, "未配置模型时不该真的开跑")

    def test_run_streams_events_and_records_the_citation_verdict(self) -> None:
        client, _ = self._client()
        started = client.post("/runs", json={"question": "有什么关于 transformer 的论文？"})
        self.assertEqual(started.status_code, 201, started.text)
        run_id = started.json()["runId"]

        stream = client.get(f"/runs/{run_id}/events")
        self.assertEqual(stream.status_code, 200)
        self.assertIn("text/event-stream", stream.headers["content-type"])
        body = stream.text
        for kind in ("run_started", "tool_call", "tool_result", "answer", "done"):
            self.assertIn(f"event: {kind}", body)

        record = client.get(f"/runs/{run_id}").json()
        self.assertEqual(record["status"], "ok")
        self.assertEqual(record["toolCallCount"], 1)
        self.assertTrue(record["citation"]["passes"])
        self.assertIn(PAPER_ID, record["answer"])

    def test_uncited_run_is_recorded_as_gate_failure(self) -> None:
        client, _ = self._client(chunks=UNCITED_CHUNKS)
        run_id = client.post("/runs", json={"question": "q"}).json()["runId"]
        client.get(f"/runs/{run_id}/events")
        record = client.get(f"/runs/{run_id}").json()
        self.assertEqual(record["status"], "ok")
        self.assertFalse(record["citation"]["passes"])
        self.assertEqual(record["citation"]["cited"], 0)

    def test_agent_exception_becomes_failed_event_not_silence(self) -> None:
        client, _ = self._client(raises=RuntimeError("模型挂了"))
        run_id = client.post("/runs", json={"question": "q"}).json()["runId"]
        body = client.get(f"/runs/{run_id}/events").text
        self.assertIn("event: failed", body)
        self.assertIn("RuntimeError", body)
        record = client.get(f"/runs/{run_id}").json()
        self.assertEqual(record["status"], "failed")
        self.assertIn("模型挂了", record["error"])

    def test_run_without_tool_results_is_retried_once_and_then_passes(self) -> None:
        """DeepSeek 偶发"并行工具调用不被执行、只交一句旁白"——
        服务端检测到"有调用、无结果"自动重跑一轮；两轮事件照实追加。"""
        sick_round = [
            chunk("model", [
                AIMessage(
                    content="我先确认图谱状态，并检索相关论文。",
                    tool_calls=[
                        {"name": "search_papers", "args": {"query": "transformer"}, "id": f"c{i}"}
                        for i in range(4)
                    ],
                )
            ]),
        ]
        rounds = [sick_round, CITING_CHUNKS]
        agent = RoundAgent(rounds)
        app = create_app(
            settings=self._settings(),
            client=KGClient("http://stub", expected_graph_id=PINNED),
            agent_factory=lambda **_kwargs: agent,
        )
        client = TestClient(app)
        run_id = client.post("/runs", json={"question": "有什么关于 transformer 的论文？"}).json()["runId"]
        body = client.get(f"/runs/{run_id}/events").text

        self.assertIn("event: run_retry", body)
        self.assertIn("没有取得工具结果", body)
        self.assertIn("event: tool_result", body, "重试轮的工具结果必须出现")
        self.assertEqual(body.count("event: done"), 1, "中间轮的 done 不落事件，界面不会提前断开")
        record = client.get(f"/runs/{run_id}").json()
        self.assertEqual(record["status"], "ok")
        self.assertTrue(record["citation"]["passes"])
        self.assertEqual(agent.calls, 2)

    def test_healthy_run_is_not_retried(self) -> None:
        client, agent = self._client()
        run_id = client.post("/runs", json={"question": "q"}).json()["runId"]
        client.get(f"/runs/{run_id}/events")
        self.assertEqual(agent.calls, 1, "健康的轮次不重试")

    def test_unknown_run_is_404_on_both_endpoints(self) -> None:
        client, _ = self._client()
        self.assertEqual(client.get("/runs/nope").status_code, 404)
        self.assertEqual(client.get("/runs/nope/events").status_code, 404)

    def test_blank_question_is_rejected(self) -> None:
        client, _ = self._client()
        self.assertEqual(client.post("/runs", json={"question": "   "}).status_code, 400)

    def test_health_reports_readiness_and_graph_scope(self) -> None:
        client, _ = self._client()
        payload = client.get("/health").json()
        self.assertTrue(payload["agentReady"])
        self.assertEqual(payload["model"], "m")
        self.assertEqual(payload["pinnedGraphId"], PINNED)
        # stub 客户端连不上，图谱状态应为 unavailable 而不是假装 ready
        self.assertEqual(payload["status"], "unavailable")
        self.assertIn("graphError", payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
