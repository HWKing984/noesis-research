"""把 Agent 的一次执行翻译成**可流式传输的事件流**，并保存运行记录。

这是"agent 是主体"那条要求的技术底座：界面要能一边跑一边看见 agent 在做什么
（调了哪个工具、拿到多少条真实证据、最后回答引用了几条），而不是等一个黑箱结果。

## 事件契约

```json
{"type":"run_started","runId":"…","question":"…","graphId":"…","model":"…"}
{"type":"tool_call","runId":"…","tool":"search_papers","args":{…}}
{"type":"tool_result","runId":"…","tool":"search_papers","summary":{…},"evidenceIds":[…]}
{"type":"tool_error","runId":"…","tool":"…","message":"…"}
{"type":"answer","runId":"…","text":"…","citation":{…}}
{"type":"failed","runId":"…","message":"…"}
{"type":"done","runId":"…","status":"ok|failed"}
```

事件翻译刻意**按消息类型**判断（有没有 `tool_calls`、是不是 `tool` 消息），而不是按节点名
—— deepagents 的图里节点名属实现细节，换版本就可能变；消息类型是稳定契约。

`citation` 用的是与 CLI（`run.py`）和前端（`apps/web/src/lib/evidence.js`）**同一条规则**：
统计回答里实际出现的 sourceId，而不是工具结果里有多少 id。
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator, Mapping, Sequence

RUN_STATUSES = ("running", "ok", "failed")

_RUN_STARTED = "run_started"
_TOOL_CALL = "tool_call"
_TOOL_RESULT = "tool_result"
_TOOL_ERROR = "tool_error"
_ANSWER = "answer"
_FAILED = "failed"
_DONE = "done"

#: 短到不构成断言的句子不计入引用可溯率（与 CLI / 前端同一规则）。
MIN_CLAIM_CHARS = 8


def extract_source_ids(value: Any) -> list[str]:
    """从任意嵌套结构里收集 sourceId / assertionId，保持出现顺序且去重。"""
    found: list[str] = []
    seen: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, item in node.items():
                if key in ("sourceId", "assertionId") and isinstance(item, str) and item.strip():
                    if item not in seen:
                        seen.add(item)
                        found.append(item)
                else:
                    visit(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                visit(item)

    visit(value)
    return found


def _as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, Mapping) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(part for part in parts if part)
    return "" if content is None else str(content)


def _as_payload(content: Any) -> Any:
    import json

    if isinstance(content, (dict, list)):
        return content
    text = _as_text(content)
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


def _paper_for_rail(item: Mapping[str, Any]) -> dict[str, Any]:
    """证据流右栏要的论文卡：精简三列 + 证据深度。"""
    evidence = item.get("evidence") if isinstance(item.get("evidence"), Mapping) else {}
    return {
        "publicationId": item.get("publicationId"),
        "title": item.get("title"),
        "year": item.get("year"),
        "evidenceLevel": evidence.get("evidenceLevel"),
        "verificationStatus": evidence.get("verificationStatus"),
    }


def summarize_tool_result(tool_name: str, payload: Any) -> dict[str, Any]:
    """给界面看的**短摘要**：不搬运整包数据，只给规模与关键参数。

    长 payload 会撑爆上下文与前端；界面要的是"这一步拿到了什么"，不是全量数据。
    例外是论文卡列表：证据流右栏需要渲染它们，因此带一份**精简**清单（截断到 20 条），
    字段与给模型的视图同源，不会把原始载荷漏给前端。
    """
    if not isinstance(payload, Mapping):
        return {"text": _as_text(payload)[:200]}

    summary: dict[str, Any] = {}
    if "applied" in payload:
        summary["applied"] = payload.get("applied")
    if "expandedTerms" in payload:
        summary["expandedTerms"] = payload.get("expandedTerms")
    for key, count_key in (("papers", "papers"), ("assertions", "assertions"), ("nodes", "nodes")):
        value = payload.get(key)
        if isinstance(value, list):
            summary[count_key] = len(value)
    if isinstance(payload.get("edges"), list):
        summary["edges"] = len(payload["edges"])
    if isinstance(payload.get("paths"), list):
        summary["paths"] = len(payload["paths"])
    if "publicationId" in payload:
        summary["publicationId"] = payload["publicationId"]
    if "title" in payload:
        summary["title"] = payload["title"]
    if isinstance(payload.get("scope"), Mapping):
        summary["scope"] = payload["scope"]
    if "status" in payload and "graphId" in payload:
        summary["status"] = payload["status"]
        summary["graphId"] = payload["graphId"]
    if "mode" in payload:
        summary["mode"] = payload["mode"]
    papers = payload.get("papers")
    if isinstance(papers, list):
        summary["paperItems"] = [
            _paper_for_rail(item) for item in papers[:20] if isinstance(item, Mapping)
        ]
    if not summary:
        summary["keys"] = sorted(str(key) for key in payload)[:8]
    return summary


def claim_sentences(answer: str) -> list[str]:
    import re

    return [
        sentence.strip()
        for sentence in re.split(r"[。！？!?\n]+", str(answer or ""))
        if len(sentence.strip()) >= MIN_CLAIM_CHARS
    ]


def citation_report(answer: str, available_ids: Sequence[str]) -> dict[str, Any]:
    """与 CLI、前端同一条规则：统计**回答里**实际引用的 id。"""
    text = str(answer or "")
    ids = [item for item in available_ids if isinstance(item, str) and item.strip()]
    cited = [item for item in ids if item in text]
    sentences = claim_sentences(text)
    attributed = [s for s in sentences if any(item in s for item in ids)]
    return {
        "available": len(ids),
        "cited": len(cited),
        "citedIds": cited,
        "consideredSentences": len(sentences),
        "attributedSentences": len(attributed),
        "citationRate": (len(attributed) / len(sentences)) if sentences else 0.0,
        "passes": len(cited) > 0,
    }


def _messages_of(update: Any) -> list[Any]:
    if isinstance(update, Mapping):
        messages = update.get("messages")
        if isinstance(messages, (list, tuple)):
            return list(messages)
    return []


def _answer_delta(chunk: Any, metadata: Any = None) -> str:
    """从 langgraph 的 messages 通道里取**回答正文增量**。

    严格只认 ``AIMessageChunk`` 的纯文本帧，且**只收根图** —— 子代理
    （deepagents 的 task 工具会开子图）的内部叙述不属于给用户的回答。
    两类东西也绝不能从这里漏出去：
    * ``ToolMessage``（type=="tool"）—— 它的 content 是工具返回的原始 JSON，
      一旦当成回答播出，界面就会把整包工具载荷当正文渲染（实际发生过）；
    * 模型决定调工具的那几帧（带 tool_calls / tool_call_chunks）。
    """
    if getattr(chunk, "type", None) != "AIMessageChunk":
        return ""
    # 子图判定不在这里做：实测根图 chunk 也带非空 langgraph_checkpoint_ns
    # （"model:<uuid>"），拿它当子图标记会把正文增量全部滤掉 —— 由调用方按
    # 流三元组的 namespace（根图为空）判定。
    content = getattr(chunk, "content", None)
    if not isinstance(content, str) or not content:
        return ""
    if getattr(chunk, "tool_call_chunks", None):
        return ""
    if getattr(chunk, "tool_calls", None):
        return ""
    return content


def _iter_stream_items(chunks: Iterable[Any]) -> Iterator[tuple[str | None, Any, str | None]]:
    """把各种流形态统一成 ``(mode, payload, namespace)``。

    * 旧形态（updates 字典）→ ``(None, 原样, None)``；
    * 单模式元组 ``(mode, payload)`` → namespace None；
    * 带 ``subgraphs=True`` 的三元组 ``(namespace, mode, payload)`` → 原样。
    """
    for item in chunks:
        if isinstance(item, tuple):
            if len(item) == 3 and isinstance(item[1], str):
                namespace, mode, payload = item
                yield mode, payload, (namespace or None)
            elif len(item) == 2 and isinstance(item[0], str):
                yield item[0], item[1], None
            else:
                yield None, item, None
        else:
            yield None, item, None


def translate_chunks(
    chunks: Iterable[Any],
    *,
    run_id: str,
    question: str,
    graph_id: str | None,
    model: str,
) -> Iterator[dict[str, Any]]:
    """把 Agent 的流式输出翻译成本项目的事件流。

    按**消息类型**判断，不按节点名 —— 节点名是实现细节。

    支持两种流形态，且**消息通道必须能自给自足**（实测 updates 通道在部分
    运行里一条都不产出，不能依赖它兜底）：
    * 旧形态：直接迭代 updates 字典（离线脚本化测试用）；
    * 双通道：``stream_mode=["updates","messages"]`` 产出的 ``(mode, payload)``
      元组 —— ``messages`` 通道给出正文 token 增量（answer_delta）、
      工具调用（AIMessageChunk.tool_calls）与工具结果（ToolMessage，type=="tool"）。

    跨通道去重：工具调用按 call id、工具结果按 tool_call_id，先到先得；
    但**工具边界**（重置"最后一次工具结果之后的正文"）两个通道都要认。
    """
    yield {
        "type": _RUN_STARTED,
        "runId": run_id,
        "question": question,
        "graphId": graph_id,
        "model": model,
    }

    available_ids: list[str] = []
    evidence_levels: set[str] = set()
    updates_answer = ""            # updates 通道里最后一条（无工具调用的）AI 文本 = 权威全文
    streamed_tail = ""             # messages 通道：最后一次工具结果之后的正文增量
    emitted_call_ids: set[str] = set()
    seen_tool_result_ids: set[str] = set()

    def collect_tool_payload(tool_name: str, payload: Any) -> list[dict[str, Any]]:
        # 工具结果无论来自主图还是子图都要收集：证据不问命名空间
        ids = extract_source_ids(payload)
        for item in ids:
            if item not in available_ids:
                available_ids.append(item)
        if isinstance(payload, Mapping):
            papers = payload.get("papers")
            if isinstance(papers, list):
                for paper in papers:
                    evidence = paper.get("evidence") if isinstance(paper, Mapping) else None
                    level = evidence.get("evidenceLevel") if isinstance(evidence, Mapping) else None
                    if isinstance(level, str) and level:
                        evidence_levels.add(level)
        return [
            {
                "type": _TOOL_RESULT,
                "runId": run_id,
                "tool": tool_name,
                "summary": summarize_tool_result(tool_name, payload),
                "evidenceIds": ids,
            }
        ]

    def handle_tool_message(message: Any) -> list[dict[str, Any]]:
        tool_name = str(getattr(message, "name", "") or "")
        status = getattr(message, "status", None)
        if status == "error":
            return [
                {
                    "type": _TOOL_ERROR,
                    "runId": run_id,
                    "tool": tool_name,
                    "message": _as_text(getattr(message, "content", ""))[:400],
                }
            ]
        payload = _as_payload(getattr(message, "content", ""))
        return collect_tool_payload(tool_name, payload)

    def emit_tool_call(call: Any) -> dict[str, Any] | None:
        if not isinstance(call, Mapping):
            return None
        call_id = str(call.get("id") or "")
        if call_id and call_id in emitted_call_ids:
            return None
        if call_id:
            emitted_call_ids.add(call_id)
        return {
            "type": _TOOL_CALL,
            "runId": run_id,
            "tool": str(call.get("name") or ""),
            "args": call.get("args") or {},
        }

    for mode, payload, _namespace in _iter_stream_items(chunks):
        if mode == "messages":
            chunk = payload[0] if isinstance(payload, tuple) else payload
            metadata = payload[1] if isinstance(payload, tuple) and len(payload) > 1 else {}
            msg_type = getattr(chunk, "type", None)
            if msg_type == "tool":
                # 边界重置必须在**去重之后**：迟到的重复工具结果副本（跨通道乱序）
                # 若也重置一次，会把已流式输出的回答正文清掉（实际发生过）
                call_id = str(getattr(chunk, "tool_call_id", "") or "")
                if call_id:
                    if call_id in seen_tool_result_ids:
                        continue
                    seen_tool_result_ids.add(call_id)
                streamed_tail = ""  # 工具边界：之后的正文才是给用户的回答
                for event in handle_tool_message(chunk):
                    yield event
                continue
            for call in getattr(chunk, "tool_calls", None) or []:
                event = emit_tool_call(call)
                if event:
                    yield event
            # 正文增量只收根图：子代理（namespace 非空）的内部叙述不进回答
            if _namespace is None:
                delta = _answer_delta(chunk, metadata)
                if delta:
                    streamed_tail += delta
                    yield {"type": "answer_delta", "runId": run_id, "delta": delta}
            continue
        if mode == "updates":
            updates = [payload]
        else:
            updates = payload.values() if isinstance(payload, Mapping) else [payload]
        for update in updates:
            for message in _messages_of(update):
                message_type = getattr(message, "type", None) or getattr(message, "role", None)

                if message_type == "tool":
                    # 与 messages 通道同权：重置在去重之后（理由同上）
                    call_id = str(getattr(message, "tool_call_id", "") or "")
                    if call_id:
                        if call_id in seen_tool_result_ids:
                            continue
                        seen_tool_result_ids.add(call_id)
                    streamed_tail = ""  # 工具边界（与 messages 通道同权）
                    for event in handle_tool_message(message):
                        yield event
                    continue

                for call in getattr(message, "tool_calls", None) or []:
                    event = emit_tool_call(call)
                    if event:
                        yield event

                if message_type == "ai":
                    text = _as_text(getattr(message, "content", "")).strip()
                    if text and not getattr(message, "tool_calls", None):
                        updates_answer = text

    # 权威全文的取舍：messages 通道是可靠的那条（updates 在部分运行里一条不产出），
    # 且 tail 恰好是"最后一次工具结果之后"的正文 —— 用户看着它逐字流出来。
    # updates_answer 只作兜底（纯 updates 形态的离线测试/部署）。
    final_answer = streamed_tail or updates_answer
    report = citation_report(final_answer, available_ids)
    report["evidenceLevels"] = sorted(evidence_levels)
    report["titleOnly"] = bool(evidence_levels) and evidence_levels == {"title"}
    yield {"type": _ANSWER, "runId": run_id, "text": final_answer, "citation": report}
    yield {"type": _DONE, "runId": run_id, "status": "ok"}


# --------------------------------------------------------------------------- #
# 运行登记表
# --------------------------------------------------------------------------- #


@dataclass
class RunRecord:
    """一次运行的全部可见状态。**纯内存**：进程重启即丢，持久化在后续阶段。"""

    run_id: str
    question: str
    status: str = "running"
    graph_id: str | None = None
    model: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    events: list[dict[str, Any]] = field(default_factory=list)
    answer: str = ""
    citation: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "runId": self.run_id,
            "question": self.question,
            "status": self.status,
            "graphId": self.graph_id,
            "model": self.model,
            "createdAt": self.created_at,
            "answer": self.answer,
            "citation": self.citation,
            "error": self.error,
            "eventCount": len(self.events),
            "toolCallCount": sum(1 for e in self.events if e.get("type") == _TOOL_CALL),
        }


class RunRegistry:
    """线程安全的运行登记表。Agent 在后台线程里跑，SSE 端按序读取事件。"""

    def __init__(self, *, max_runs: int = 200) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, RunRecord] = {}
        self._max_runs = max_runs

    def create(self, question: str, *, graph_id: str | None, model: str) -> RunRecord:
        run = RunRecord(run_id=uuid.uuid4().hex, question=question, graph_id=graph_id, model=model)
        with self._lock:
            self._runs[run.run_id] = run
            if len(self._runs) > self._max_runs:
                for stale in sorted(self._runs.values(), key=lambda r: r.created_at)[: len(self._runs) - self._max_runs]:
                    self._runs.pop(stale.run_id, None)
        return run

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def list_recent(self, limit: int = 20) -> list[RunRecord]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)[:limit]

    def append(self, run_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return
            run.events.append(event)
            kind = event.get("type")
            if kind == _ANSWER:
                run.answer = str(event.get("text") or "")
                run.citation = event.get("citation")
            elif kind == _DONE:
                run.status = str(event.get("status") or "ok")
            elif kind == _FAILED:
                run.status = "failed"
                run.error = str(event.get("message") or "")

    def since(self, run_id: str, index: int) -> tuple[list[dict[str, Any]], bool]:
        """返回 (从 index 起的新事件, 是否已结束)。"""
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return [], True
            return list(run.events[index:]), run.status != "running"
