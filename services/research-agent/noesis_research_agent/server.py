"""Agent 的 HTTP + SSE 服务 —— 让界面能"看着它干活"。

端点：

============================  ==========================================================
``GET  /health``              图谱是否就绪、LLM 是否配置齐全
``POST /runs``                提问，立即返回 ``runId``（后台线程开跑）
``GET  /runs/{id}/events``    **SSE** 事件流：工具调用 / 工具结果 / 回答 / 引用核查 / 结束
``GET  /runs/{id}``           单次运行的最终记录
``GET  /runs``                最近的运行列表
============================  ==========================================================

设计取舍：
* 提问立刻返回、执行放后台线程、SSE 按序读事件 —— 界面先看到"开始"，再看到逐步进展，
  而不是等一个黑箱结果。
* 运行记录**只存内存**（进程重启即丢）。持久化属后续阶段，这里如实标注，不假装有库。
* LLM 未配置时**拒绝开跑**（503 ``llm_not_configured``），不退回到某个"默认模型"。
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, Iterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import _paths  # noqa: F401  (sys.path wiring; must precede kg_client)

from kg_client import KGClient, KGError, KGGraphMismatch, KGUnavailable, resolve_base_url, resolve_expected_graph_id

from .agent import build_agent
from .config import AgentSettings, ConfigurationError
from .runner import RunRegistry, RunRecord, translate_chunks

logger = logging.getLogger(__name__)

SSE_POLL_SECONDS = 0.15
SSE_HEARTBEAT_SECONDS = 10.0


class StartRunRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class StartRunResponse(BaseModel):
    runId: str
    status: str
    question: str


def create_app(
    *,
    settings: AgentSettings | None = None,
    registry: RunRegistry | None = None,
    client: KGClient | None = None,
    agent_factory: Any | None = None,
) -> FastAPI:
    """构造应用。各依赖可注入，便于离线测试整条 HTTP 面。

    ``agent_factory`` 是测试缝：注入一个脚本化的假 agent，就能把
    "提问 → 事件流 → 引用核查 → 结束" 整条 SSE 路径在无 LLM 的情况下测完。
    """
    resolved = settings or AgentSettings.from_env()
    make_agent = agent_factory or build_agent
    app = FastAPI(
        title="NOESIS Research Agent",
        version="0.1.0",
        description=(
            "科研 Agent 服务：提问 → 自主检索知识图谱 → 返回带证据的回答。"
            "每条事实性断句都要挂来源 id；候选关系保持候选；没有引用即判定为失败。"
        ),
    )
    app.state.settings = resolved
    app.state.registry = registry or RunRegistry()
    app.state.kg = client or KGClient(
        resolved.kg_base_url,
        expected_graph_id=resolved.expected_graph_id,
        timeout=resolved.kg_timeout,
    )

    def _run_in_background(run: RunRecord) -> None:
        registry_ref = app.state.registry
        try:
            agent = make_agent(client=app.state.kg, settings=resolved)
            chunks = agent.stream(
                {"messages": [{"role": "user", "content": run.question}]},
                stream_mode="updates",
            )
            for event in translate_chunks(
                chunks,
                run_id=run.run_id,
                question=run.question,
                graph_id=resolved.expected_graph_id,
                model=resolved.llm_model,
            ):
                registry_ref.append(run.run_id, event)
        except Exception as exc:  # noqa: BLE001 - 必须落成可见事件，不能只打日志
            logger.exception("research run %s failed", run.run_id)
            registry_ref.append(
                run.run_id,
                {"type": "failed", "runId": run.run_id, "message": f"{type(exc).__name__}: {exc}"},
            )
            registry_ref.append(run.run_id, {"type": "done", "runId": run.run_id, "status": "failed"})

    @app.get("/health")
    def health() -> dict[str, Any]:
        missing = list(resolved.missing_for_run())
        payload: dict[str, Any] = {
            "agentReady": not missing,
            "missingSettings": missing,
            "model": resolved.llm_model or None,
            "llmBaseUrl": resolved.llm_base_url,
            "kgBaseUrl": resolved.kg_base_url,
            "pinnedGraphId": resolved.expected_graph_id,
        }
        try:
            report = app.state.kg.health()
            payload.update({"status": report.status, "graphId": report.graph_id, "scope": report.scope})
        except KGError as exc:
            payload.update({"status": "unavailable", "graphError": str(exc)})
        return payload

    @app.post("/runs", response_model=StartRunResponse, status_code=201)
    def start_run(request: StartRunRequest) -> Any:
        question = request.question.strip()
        if not question:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "invalid_request", "message": "question 不能为空"}},
            )
        if resolved.missing_for_run():
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "llm_not_configured",
                        "message": "Agent 未配置模型：" + ", ".join(resolved.missing_for_run()),
                    }
                },
            )
        run = app.state.registry.create(
            question, graph_id=resolved.expected_graph_id, model=resolved.llm_model
        )
        threading.Thread(target=_run_in_background, args=(run,), daemon=True).start()
        return StartRunResponse(runId=run.run_id, status=run.status, question=run.question)

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> Any:
        run = app.state.registry.get(run_id)
        if run is None:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "not_found", "message": f"没有这次运行：{run_id}"}},
            )
        return run.to_dict()

    @app.get("/runs")
    def list_runs(limit: int = 20) -> dict[str, Any]:
        return {"data": [run.to_dict() for run in app.state.registry.list_recent(limit)]}

    @app.get("/runs/{run_id}/events")
    async def stream_events(run_id: str, request: Request) -> Any:
        if app.state.registry.get(run_id) is None:
            return JSONResponse(
                status_code=404,
                content={"error": {"code": "not_found", "message": f"没有这次运行：{run_id}"}},
            )

        async def event_source() -> Any:
            index = 0
            idle = 0.0
            while True:
                if await request.is_disconnected():
                    return
                events, finished = app.state.registry.since(run_id, index)
                for event in events:
                    index += 1
                    idle = 0.0
                    yield f"event: {event.get('type')}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                if finished and index >= 1:
                    return
                await asyncio.sleep(SSE_POLL_SECONDS)
                idle += SSE_POLL_SECONDS
                if idle >= SSE_HEARTBEAT_SECONDS:
                    idle = 0.0
                    yield ": heartbeat\n\n"

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.exception_handler(KGUnavailable)
    async def _unavailable(request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "kg_unavailable", "message": str(exc)}},
        )

    @app.exception_handler(KGGraphMismatch)
    async def _mismatch(request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "kg_graph_version_mismatch", "message": str(exc)}},
        )

    @app.exception_handler(ConfigurationError)
    async def _unconfigured(request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "llm_not_configured", "message": str(exc)}},
        )

    return app


#: `uvicorn noesis_research_agent.server:app`
app = create_app()


def stream_events_for_testing(agent: Any, question: str, **kwargs: Any) -> Iterator[dict[str, Any]]:
    """测试用：直接翻译一次真实流，不起 HTTP。"""
    return translate_chunks(
        agent.stream({"messages": [{"role": "user", "content": question}]}, stream_mode="updates"),
        **kwargs,
    )


__all__ = ["app", "create_app", "resolve_base_url", "resolve_expected_graph_id"]
