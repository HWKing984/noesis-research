"""POST /api/translate — machine translation as a **reading aid, never evidence**.

Error mapping (wired in ``app.py``):

===========================  ======  ==============================
condition                     status  ``error.code``
===========================  ======  ==============================
LLM_* not configured          503     ``llm_not_configured``
endpoint down / 429 / 5xx     503     ``translate_unavailable``
answer not a translation      502     ``translate_bad_response``
===========================  ======  ==============================

There is deliberately **no** path that returns the original text as if it were
the translation.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from .translate import MAX_INPUT_CHARS, Translator

router = APIRouter(prefix="/api", tags=["translate"])


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_INPUT_CHARS)
    kind: str = Field(default="text", pattern="^(title|abstract|text)$")


class TranslateResponse(BaseModel):
    zh: str
    kind: str
    targetLang: str
    cached: bool
    keptTerms: list[str]
    model: str | None = None


def _translator(request: Request) -> Translator:
    return request.app.state.translator


@router.post(
    "/translate",
    response_model=TranslateResponse,
    summary="Translate a title / abstract / passage to Chinese (reading aid only)",
)
def translate(payload: TranslateRequest, request: Request) -> TranslateResponse:
    """The response carries ``keptTerms`` (protected names left in English) and
    ``model`` so the UI can label the provenance of every rendering."""
    translation = _translator(request).translate(payload.text.strip(), kind=payload.kind)
    return TranslateResponse(**translation.to_dict())
