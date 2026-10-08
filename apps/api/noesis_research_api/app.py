"""FastAPI application factory, settings, and upstream-error translation.

The single most important behaviour in this file: **an upstream failure never
becomes a success**. The knowledge graph's own rule (``scripts/course_graph.py``
raises ``DatabaseUnavailable`` → HTTP 503, "未使用离线替代数据") is carried
through unchanged:

===========================  ======  ==============================
upstream condition            status  ``error.code``
===========================  ======  ==============================
graph / Neo4j not usable      503     ``kg_unavailable``
pinned graph version differs  503     ``kg_graph_version_mismatch``
bad request parameters        400     ``invalid_request``
unknown publication           404     ``not_found``
upstream answered malformed   502     ``kg_bad_response``
anything else                 500     ``internal_error``
===========================  ======  ==============================

There is no code path that turns any of these into an empty result list.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import _paths  # noqa: F401  (sys.path wiring; must precede kg_client)

from kg_client import (
    KGClient,
    KGError,
    KGGraphMismatch,
    KGInvalidRequest,
    KGNotFound,
    KGUnavailable,
    resolve_base_url,
    resolve_expected_graph_id,
)

from .models import ErrorModel, ErrorResponse
from .routes import router

logger = logging.getLogger(__name__)

ENV_TIMEOUT = "KG_TIMEOUT"
DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class Settings:
    """Runtime configuration. All three values are environment-driven."""

    base_url: str
    expected_graph_id: str | None
    timeout: float

    @classmethod
    def from_env(cls) -> "Settings":
        raw_timeout = os.environ.get(ENV_TIMEOUT, "")
        try:
            timeout = float(raw_timeout) if raw_timeout.strip() else DEFAULT_TIMEOUT_SECONDS
        except (TypeError, ValueError):
            logger.warning("%s=%r is not a number; using %s", ENV_TIMEOUT, raw_timeout, DEFAULT_TIMEOUT_SECONDS)
            timeout = DEFAULT_TIMEOUT_SECONDS
        if timeout <= 0:
            timeout = DEFAULT_TIMEOUT_SECONDS
        return cls(
            base_url=resolve_base_url(),
            expected_graph_id=resolve_expected_graph_id(),
            timeout=timeout,
        )


# Ordered: subclasses first, KGError last (every other error here is a KGError).
_ERROR_STATUS: tuple[tuple[type[Exception], int, str], ...] = (
    (KGUnavailable, 503, "kg_unavailable"),
    (KGGraphMismatch, 503, "kg_graph_version_mismatch"),
    (KGInvalidRequest, 400, "invalid_request"),
    (KGNotFound, 404, "not_found"),
    (KGError, 502, "kg_bad_response"),
)


def _error_handler(status_code: int, code: str):
    async def handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content=ErrorResponse(error=ErrorModel(code=code, message=str(exc))).model_dump(),
        )

    return handler


def create_app(*, settings: Settings | None = None, kg_client: KGClient | None = None) -> FastAPI:
    """Build the application.

    ``kg_client`` is injectable so tests can drive the whole HTTP surface
    without a database: a fake transport plus a real client exercises exactly
    the code path production uses.
    """
    resolved = settings or Settings.from_env()
    app = FastAPI(
        title="NOESIS Research API",
        version="0.1.0",
        description=(
            "Read-only research API over the AI-Literature-KG. Every paper and every candidate "
            "assertion carries an evidence reference; candidate relations are never presented as facts."
        ),
    )
    app.state.settings = resolved
    app.state.kg = kg_client or KGClient(
        resolved.base_url,
        expected_graph_id=resolved.expected_graph_id,
        timeout=resolved.timeout,
    )

    for exc_type, status_code, code in _ERROR_STATUS:
        app.add_exception_handler(exc_type, _error_handler(status_code, code))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:  # pragma: no cover - defensive
        logger.exception("unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error=ErrorModel(code="internal_error", message="Request failed")
            ).model_dump(),
        )

    app.include_router(router)
    return app


#: Module-level app for ``uvicorn noesis_research_api.app:app``.
app = create_app()
