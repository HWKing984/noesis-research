"""Run one research question against the live knowledge graph.

    python run.py "用扩散模型做图像生成的工作有哪些？"
    python run.py --transcript out.json "图神经网络在异常检测中的应用"

Prints three things, in this order:

1. the tool calls the agent actually made (so the search parameters are visible);
2. the answer;
3. every evidence id the answer can point at.

The third block is the point: an answer that cites nothing is a failed run, not
a fluent success. This CLI deliberately does not hide the tool trace.

Credentials come from the environment (``LLM_API_KEY`` / ``LLM_BASE_URL`` /
``LLM_MODEL``). Nothing is read from, or written to, any other repository.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from kg_client import KGClient

from noesis_research_agent import _paths  # noqa: F401
from noesis_research_agent.agent import build_agent
from noesis_research_agent.config import AgentSettings, ConfigurationError


def _message_role(message: Any) -> str:
    role = getattr(message, "type", None) or getattr(message, "role", None)
    return str(role or type(message).__name__)


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(part for part in parts if part)
    return str(content)


def _collect_evidence_ids(messages: list[Any]) -> list[str]:
    """Pull every sourceId out of tool results — the citable ids."""
    found: list[str] = []
    seen: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("sourceId", "assertionId") and isinstance(value, str) and value.strip():
                    if value not in seen:
                        seen.add(value)
                        found.append(value)
                else:
                    visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    for message in messages:
        if _message_role(message) != "tool":
            continue
        content = getattr(message, "content", "")
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str)
        try:
            visit(json.loads(text))
        except (TypeError, ValueError):
            visit(text)
    return found


def _blocks(messages: list[Any]) -> tuple[list[dict[str, Any]], str]:
    calls: list[dict[str, Any]] = []
    answer = ""
    for message in messages:
        role = _message_role(message)
        if role == "ai":
            for call in getattr(message, "tool_calls", None) or []:
                calls.append({"tool": call.get("name"), "args": call.get("args")})
            text = _message_text(message).strip()
            if text:
                answer = text
        elif role == "human" and not answer:
            continue
    return calls, answer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", help="研究问题（自然语言）")
    parser.add_argument("--transcript", type=Path, help="把完整消息链写到该 JSON 文件")
    args = parser.parse_args(argv)

    try:
        settings = AgentSettings.from_env()
        settings.require_runnable()
    except ConfigurationError as exc:
        print(f"[配置不足] {exc}", file=sys.stderr)
        print("需要的环境变量：LLM_API_KEY、LLM_MODEL（可选 LLM_BASE_URL、KG_BASE_URL、KG_EXPECTED_GRAPH_ID）", file=sys.stderr)
        return 2

    client = KGClient(
        settings.kg_base_url,
        expected_graph_id=settings.expected_graph_id,
        timeout=settings.kg_timeout,
    )

    print(f"[kg] {settings.kg_base_url}  pinned={settings.expected_graph_id or '(未锁定)'}")
    try:
        health = client.assert_graph_version()
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim, never swallowed
        print(f"[图谱不可用] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    print(f"[kg] status={health.status} graphId={health.graph_id} scope={json.dumps(health.scope, ensure_ascii=False)}")
    print(f"[llm] model={settings.llm_model} base_url={settings.llm_base_url or '(provider 默认)'}")
    print()

    agent = build_agent(client=client, settings=settings)
    result = agent.invoke({"messages": [{"role": "user", "content": args.question}]})
    messages = list(result.get("messages", [])) if isinstance(result, dict) else []

    calls, answer = _blocks(messages)
    evidence = _collect_evidence_ids(messages)

    print(f"--- 工具调用（{len(calls)} 次）---")
    for index, call in enumerate(calls, start=1):
        print(f"{index}. {call['tool']}  {json.dumps(call['args'], ensure_ascii=False)}")
    print()
    print("--- 回答 ---")
    print(answer or "(模型没有给出文本回答)")
    print()
    print(f"--- 可引用证据 id（{len(evidence)} 条）---")
    for item in evidence:
        print(f"  {item}")

    if args.transcript:
        payload = {
            "question": args.question,
            "graphId": health.graph_id,
            "model": settings.llm_model,
            "toolCalls": calls,
            "answer": answer,
            "evidenceIds": evidence,
            "messages": [
                {"role": _message_role(message), "text": _message_text(message)}
                for message in messages
            ],
        }
        args.transcript.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print()
        print(f"[transcript] {args.transcript}")

    return 0 if evidence else 1


if __name__ == "__main__":
    raise SystemExit(main())
