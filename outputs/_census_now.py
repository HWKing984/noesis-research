# -*- coding: utf-8 -*-
"""普查：当前代码下 messages 通道是否还流 ToolMessage（工具是否真的被执行）。"""
import json
import os
import sys
from pathlib import Path

REPO = Path(r"D:\a-open_source\noesis-research")
sys.path.insert(0, str(REPO / "integrations" / "knowledge-graph"))
sys.path.insert(0, str(REPO / "services" / "research-agent"))

env_path = Path(r"D:\a-Soft\backend\.env")
for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
    line = line.strip()
    if "=" in line:
        name, _, value = line.partition("=")
        if name.strip() in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
            os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))
os.environ.setdefault("KG_BASE_URL", "http://127.0.0.1:8765")
os.environ.setdefault("KG_EXPECTED_GRAPH_ID", "ai-literature-ed16399925fac2a599ed")

from noesis_research_agent.agent import build_agent  # noqa: E402
from noesis_research_agent.config import AgentSettings  # noqa: E402
from kg_client import KGClient  # noqa: E402

settings = AgentSettings.from_env()
client = KGClient(settings.kg_base_url, expected_graph_id=settings.expected_graph_id, timeout=settings.kg_timeout)
agent = build_agent(client=client, settings=settings)

rows = []
for item in agent.stream(
    {"messages": [{"role": "user", "content": "有哪些关于 transformer 的论文？"}]},
    stream_mode=["updates", "messages"],
    subgraphs=True,
):
    if isinstance(item, tuple) and len(item) == 3:
        ns, mode, payload = item
    elif isinstance(item, tuple) and len(item) == 2:
        ns, mode, payload = None, item[0], item[1]
    else:
        ns, mode, payload = None, None, item
    ns_str = "root" if not ns else str(ns)[:30]
    if mode == "messages":
        chunk = payload[0] if isinstance(payload, tuple) else payload
        meta = payload[1] if isinstance(payload, tuple) and len(payload) > 1 else {}
        ctype = getattr(chunk, "type", None)
        content = getattr(chunk, "content", "")
        clen = len(content) if isinstance(content, str) else "-"
        tcc = getattr(chunk, "tool_call_chunks", None)
        tc = getattr(chunk, "tool_calls", None)
        rows.append({
            "ns": ns_str, "type": ctype, "len": clen,
            "head": str(content)[:36] if isinstance(content, str) else "-",
            "tcc": len(tcc) if tcc else 0,
            "tc": len(tc) if tc else 0,
            "ckpt": str(meta.get("langgraph_checkpoint_ns", ""))[:20] if isinstance(meta, dict) else "?",
        })
    else:
        nodes = list(payload.keys()) if isinstance(payload, dict) else []
        rows.append({"ns": ns_str, "type": f"updates:{','.join(str(n)[:24] for n in nodes)}", "len": "-", "head": "-", "tcc": "-", "tc": "-", "ckpt": "-"})

summary = {}
for r in rows:
    key = (r["ns"], r["type"])
    summary[key] = summary.get(key, 0) + 1

out = {"total": len(rows), "summary": {str(k): v for k, v in summary.items()}, "rows": rows}
Path(r"C:\Users\Y7000P\AppData\Local\Temp\_census_now.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
)
print("WROTE", len(rows))
