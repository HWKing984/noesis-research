"""POST /api/explain — LLM concept explanation as a **reading aid, never evidence**.

Sibling of ``/api/translate``. Error mapping (wired in ``app.py``):

===========================  ======  ==============================
condition                     status  ``error.code``
===========================  ======  ==============================
LLM_* not configured          503     ``llm_not_configured``
endpoint down / 429 / 5xx     503     ``translate_unavailable``
answer not the agreed shape   502     ``explain_bad_response``
===========================  ======  ==============================

The response carries no ``sources`` field on purpose: an explanation we cannot
verify is labelled "AI 解释" and never cited.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from .explain import Explainer, MAX_CONTEXT_CHARS
from .translate import MAX_INPUT_CHARS

router = APIRouter(prefix="/api", tags=["explain"])


class ExplainRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    kind: str = Field(default="term", pattern="^(term|title|abstract|text)$")
    style: str = Field(default="normal", pattern="^(normal|simple)$")
    context: str = Field(default="", max_length=MAX_CONTEXT_CHARS)


class ExplainResponse(BaseModel):
    text: str
    kind: str
    style: str
    category: str
    brief: str
    detail: str
    whyItMatters: str
    example: str
    cached: bool
    model: str | None = None


def _explainer(request: Request) -> Explainer:
    return request.app.state.explainer


@router.post(
    "/explain",
    response_model=ExplainResponse,
    summary="Explain a term / title / passage (AI reading aid, never evidence)",
)
def explain(payload: ExplainRequest, request: Request) -> ExplainResponse:
    """``style='simple'`` is the "更简单一点" re-ask — it is part of the cache
    key, so a simpler phrasing is a fresh (uncached) generation."""
    explanation = _explainer(request).explain(
        payload.text.strip(),
        kind=payload.kind,
        style=payload.style,
        context=payload.context.strip(),
    )
    return ExplainResponse(**explanation.to_dict())
