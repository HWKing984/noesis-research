"""Click-to-explain: LLM explanation of a term / title / passage, NOESIS-style.

Sibling of :mod:`translate` and built on the same skeleton (shared transport,
cache, error discipline). The one boundary that shapes this module:

**An explanation is reading aid, not evidence.** It never produces an
``EvidenceRef``, never enters the citation gate, and is always labelled
"AI 解释" in the UI. What this module must guarantee is the same twin rule
the whole repo lives by:

* an unconfigured / unreachable / nonsense LLM is a **failure**
  (:class:`LLMNotConfigured` / :class:`TranslateUnavailable` /
  :class:`ExplainBadResponse` → 503 / 503 / 502). It is never answered with
  fabricated-sounding prose pretending the model said nothing wrong;
* the model is asked for a fixed JSON shape (category / brief / detail /
  whyItMatters / example — mirroring NOESIS's Term card). A response that
  cannot be parsed into that shape, or whose human-readable parts contain no
  Chinese, is rejected rather than partially shown.

The explanation must stay honest about uncertainty: the prompt forbids
inventing sources, and the response carries no ``sources`` field precisely
because we do not attach citations we cannot verify.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .translate import (
    FileCache,
    LLMNotConfigured,
    LLMTransport,
    MAX_INPUT_CHARS,
    TranslateUnavailable,
    _is_chinese,
)

__all__ = [
    "EXPLAIN_VERSION",
    "MAX_CONTEXT_CHARS",
    "ExplainBadResponse",
    "Explanation",
    "Explainer",
]

#: Bump when the prompt contract changes — cache keys include it, so every
#: stored explanation invalidates at once.
EXPLAIN_VERSION = 1

#: Optional "结合当前内容" context (e.g. the paper title the term appeared in).
MAX_CONTEXT_CHARS = 2000

_REQUIRED_FIELDS = ("category", "brief", "detail", "whyItMatters", "example")

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class ExplainBadResponse(Exception):
    """The endpoint answered, but not with a usable explanation."""


# ---------------------------------------------------------------------------
# prompt
# ---------------------------------------------------------------------------
_KIND_LABEL = {"term": "术语 / 概念", "title": "论文标题", "abstract": "摘要片段", "text": "文本片段"}


def _prompt(text: str, *, kind: str, style: str, context: str) -> str:
    context_line = f"\n出现语境（供理解，不要复述）：{context}" if context else ""
    simple_line = (
        "4. 读者刚入门：用最通俗的话解释，先打比方再给术语，避免行话。"
        if style == "simple"
        else "4. 面向有一定基础的研究者，直接给出准确表述。"
    )
    return (
        f"请解释学术语境中的下面这个{_KIND_LABEL.get(kind, '内容')}，供研究者快速理解。\n"
        f"\n对象：{text}{context_line}\n"
        f"\n规则：\n"
        f"1. 只输出一个 JSON 对象，字段固定为：\n"
        f"   category（类别，取「概念/方法/模型/数据集/任务/其他」之一）、\n"
        f"   brief（一句话定义，不超过 60 字）、\n"
        f"   detail（详细解释，2~4 句，需要分段用 \\n 分隔）、\n"
        f"   whyItMatters（为什么重要，1~2 句）、\n"
        f"   example（一个具体例子或典型用法，1~2 句）。\n"
        f"2. 全部用简体中文；专有名词（模型名、数据集名等）保留英文原文。\n"
        f"3. 解释必须忠实于学术含义；不确定就写「尚无定论」，不要编造出处或引用。\n"
        f"{simple_line}\n\n"
        f"只输出 JSON 本身，不要 markdown 代码块，不要任何别的文字。"
    )


# ---------------------------------------------------------------------------
# service
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Explanation:
    text: str
    kind: str
    style: str
    category: str
    brief: str
    detail: str
    why_it_matters: str
    example: str
    cached: bool
    model: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "kind": self.kind,
            "style": self.style,
            "category": self.category,
            "brief": self.brief,
            "detail": self.detail,
            "whyItMatters": self.why_it_matters,
            "example": self.example,
            "cached": self.cached,
            "model": self.model or None,
        }


def _extract_json(content: str) -> dict[str, Any]:
    raw = content.strip()
    fenced = _FENCE.match(raw)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        parsed = json.loads(raw)
    except ValueError:
        block = _JSON_BLOCK.search(raw)
        if block is None:
            raise ValueError("no JSON object in the completion") from None
        try:
            parsed = json.loads(block.group(0))
        except ValueError as exc:
            raise ValueError(f"completion is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("completion JSON is not an object")
    return parsed


class Explainer:
    """Explain one term / title / passage; cached after the first success.

    Shares the transport seam and cache with :class:`~.translate.Translator`;
    only the prompt, the response shape and the validation differ.
    """

    def __init__(
        self,
        *,
        transport: LLMTransport | None = None,
        cache: FileCache | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._explicit = (api_key, base_url, model)
        self._transport = transport
        self._cache = cache
        self._timeout = timeout

    def settings(self) -> tuple[str, str, str]:
        from .translate import resolve_llm_settings  # local: avoid import cycle noise

        key, url, model = self._explicit
        if not (key and url and model):
            env_key, env_url, env_model = resolve_llm_settings()
            key = key or env_key
            url = url or env_url
            model = model or env_model
        return (key, url, model)

    def ready(self) -> bool:
        key, url, model = self.settings()
        return bool(key and url and model)

    def require_ready(self) -> None:
        if not self.ready():
            key, url, model = self.settings()
            missing = [
                name
                for name, value in (("LLM_API_KEY", key), ("LLM_BASE_URL", url), ("LLM_MODEL", model))
                if not value
            ]
            raise LLMNotConfigured("解释服务未配置模型：" + ", ".join(missing))

    def explain(
        self,
        text: str,
        *,
        kind: str = "term",
        style: str = "normal",
        context: str = "",
    ) -> Explanation:
        self.require_ready()
        clean = " ".join(str(text or "").split())
        if not clean:
            raise ExplainBadResponse("empty input")
        if len(clean) > MAX_INPUT_CHARS:
            raise ExplainBadResponse(f"input exceeds {MAX_INPUT_CHARS} chars")
        clean_context = " ".join(str(context or "").split())[:MAX_CONTEXT_CHARS]

        key = self._cache_key(clean, kind=kind, style=style, context=clean_context)
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached:
                return Explanation(
                    text=clean,
                    kind=kind,
                    style=style,
                    category=str(cached["category"]),
                    brief=str(cached["brief"]),
                    detail=str(cached["detail"]),
                    why_it_matters=str(cached["whyItMatters"]),
                    example=str(cached["example"]),
                    cached=True,
                    model=str(cached.get("model") or ""),
                )

        payload_fields, model = self._call_llm(clean, kind=kind, style=style, context=clean_context)
        if self._cache is not None:
            self._cache.put(key, {**payload_fields, "model": model})
        return Explanation(
            text=clean,
            kind=kind,
            style=style,
            cached=False,
            model=model,
            category=payload_fields["category"],
            brief=payload_fields["brief"],
            detail=payload_fields["detail"],
            why_it_matters=payload_fields["whyItMatters"],
            example=payload_fields["example"],
        )

    @staticmethod
    def _cache_key(text: str, *, kind: str, style: str, context: str) -> str:
        import hashlib

        seed = f"explain v{EXPLAIN_VERSION}|{kind}|{style}|{context}|{text}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]

    # -- LLM call ------------------------------------------------------------
    def _endpoint(self, base_url: str) -> str:
        return f"{base_url}/chat/completions"

    def _call_llm(self, text: str, *, kind: str, style: str, context: str) -> tuple[dict[str, str], str]:
        key, base_url, model = self.settings()
        transport = self._transport
        if transport is None:
            from .translate import HttpLLMTransport

            transport = HttpLLMTransport(timeout=self._timeout)

        body = json.dumps(
            {
                "model": model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": "你是严谨的学术讲解助手。只输出一个 JSON 对象，不输出任何别的文字。"},
                    {"role": "user", "content": _prompt(text, kind=kind, style=style, context=context)},
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")

        from .translate import MAX_RESPONSE_BYTES

        status, raw = transport.post(
            self._endpoint(base_url),
            body,
            {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        )

        if status == 401 or status == 403:
            raise TranslateUnavailable(f"LLM endpoint rejected the credentials (HTTP {status})")
        if status == 429 or status >= 500:
            raise TranslateUnavailable(f"LLM endpoint answered HTTP {status}")
        if status != 200:
            raise ExplainBadResponse(f"LLM endpoint answered HTTP {status}")
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ExplainBadResponse("LLM response exceeds the size cap")

        try:
            payload = json.loads(raw.decode("utf-8", "replace"))
        except ValueError as exc:
            raise ExplainBadResponse(f"LLM did not return JSON: {exc}") from exc
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ExplainBadResponse("LLM payload has no choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise ExplainBadResponse("LLM returned an empty completion")

        try:
            fields = _extract_json(content)
        except ValueError as exc:
            raise ExplainBadResponse(f"explanation is not the agreed JSON shape: {exc}") from exc

        missing = [name for name in _REQUIRED_FIELDS if not str(fields.get(name) or "").strip()]
        if missing:
            raise ExplainBadResponse(f"explanation JSON is missing fields: {', '.join(missing)}")

        out: dict[str, str] = {}
        for name in _REQUIRED_FIELDS:
            value = " ".join(str(fields[name]).strip().split()) if name != "detail" else str(fields[name]).strip()
            if len(value) > 6000:
                raise ExplainBadResponse(f"explanation field {name} is implausibly long")
            out[name] = value

        # The human-readable surface must actually be Chinese — an all-English
        # blob is not the reading aid this endpoint promises.
        if not (_is_chinese(out["brief"]) and _is_chinese(out["detail"])):
            raise ExplainBadResponse("explanation contains no Chinese; refusing to pass it off as an explanation")
        return out, str(model)
