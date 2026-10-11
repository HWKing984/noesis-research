"""Click-to-translate: Chinese rendering of titles / abstracts over the shared LLM.

The one rule that shapes everything here
----------------------------------------
**A translation is reading aid, not evidence.** It never produces an
``EvidenceRef``, never enters the citation gate, never changes a candidate's
status — the front end states this in the popover itself. What this module must
guarantee on its side is the twin rule the whole repo lives by:

* an LLM that is not configured, unreachable, or answering nonsense is a
  **failure** (:class:`LLMNotConfigured` / :class:`TranslateUnavailable` /
  :class:`TranslateBadResponse` → HTTP 503 / 503 / 502). It is *never* answered
  with the original text pretending to be a translation — that would silently
  present "we could not translate" as "here is the Chinese", which is exactly
  the fabrication pattern this project forbids;
* a response that is not Chinese, or one identical to the input, is rejected as
  a bad response rather than returned.

Terminology discipline
----------------------
Machine translation ruins technical text by localising proper names. The keep
list (:data:`GLOSSARY_KEEP`) is sent to the model verbatim, and the terms that
actually occurred in the input are echoed back to the UI
(``keptTerms``) so the popover can show *which* names stayed in English.
Bump :data:`GLOSSARY_VERSION` when editing the list — cache entries are keyed
by it, so edits invalidate every stored translation at once.

Standard library only: apps/api deliberately avoids an OpenAI SDK (see
``requirements.txt``); the transport follows the same hardening as
``integrations/external-sources`` — ``ProxyHandler({})`` (an *empty* proxy map:
``None`` would read the ambient ``HTTP_PROXY``, and the sandbox proxy answers
502), mapped timeout errors, and a response size cap.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

__all__ = [
    "ENV_LLM_API_KEY",
    "ENV_LLM_BASE_URL",
    "ENV_LLM_MODEL",
    "ENV_TIMEOUT",
    "ENV_CACHE_DIR",
    "GLOSSARY_KEEP",
    "GLOSSARY_VERSION",
    "DEFAULT_TIMEOUT",
    "DEFAULT_CACHE_DIR",
    "MAX_INPUT_CHARS",
    "LLMNotConfigured",
    "TranslateUnavailable",
    "TranslateBadResponse",
    "Translation",
    "LLMTransport",
    "HttpLLMTransport",
    "FileCache",
    "Translator",
    "kept_terms",
    "resolve_llm_settings",
]

ENV_LLM_API_KEY = "LLM_API_KEY"
ENV_LLM_BASE_URL = "LLM_BASE_URL"
ENV_LLM_MODEL = "LLM_MODEL"
ENV_TIMEOUT = "TRANSLATE_TIMEOUT"
ENV_CACHE_DIR = "TRANSLATE_CACHE_DIR"

DEFAULT_TIMEOUT = 30.0
DEFAULT_CACHE_DIR = ".data/translations"
MAX_RESPONSE_BYTES = 1 * 1024 * 1024

#: Input ceiling: a long abstract is fine, a pasted paper is not what this is for.
MAX_INPUT_CHARS = 6000

#: Bump when the keep list changes — cache keys include this.
GLOSSARY_VERSION = 1

#: Proper names that must survive translation untouched. The popover echoes the
#: ones that actually occurred, so the reader knows what stayed English on purpose.
GLOSSARY_KEEP = (
    "ResNet",
    "Transformer",
    "BERT",
    "GPT",
    "ViT",
    "ImageNet",
    "COCO",
    "ImageNet-21k",
    "softmax",
    "DBLP",
    "arXiv",
    "DOI",
    "OpenAlex",
    "Crossref",
    "Semantic Scholar",
)

_TARGET_LANG = "zh-Hans"

_ZH_CHAR = re.compile(r"[\u4e00-\u9fff]")


# ---------------------------------------------------------------------------
# errors → mapped to HTTP in app.py
# ---------------------------------------------------------------------------
class LLMNotConfigured(Exception):
    """No ``LLM_API_KEY`` / ``LLM_MODEL`` in the environment.

    Surfaced as 503 ``llm_not_configured``. Never defaulted to "some model" —
    that would be a silent substitution, and the answer would carry a provenance
    nobody configured.
    """


class TranslateUnavailable(Exception):
    """The LLM endpoint could not be reached, timed out, or answered 5xx/429."""


class TranslateBadResponse(Exception):
    """The endpoint answered, but not with a usable Chinese translation."""


def resolve_llm_settings() -> tuple[str, str, str]:
    """``(api_key, base_url, model)`` from the shared ``LLM_*`` variables."""
    return (
        os.environ.get(ENV_LLM_API_KEY, "").strip(),
        (os.environ.get(ENV_LLM_BASE_URL, "").strip() or "").rstrip("/"),
        os.environ.get(ENV_LLM_MODEL, "").strip(),
    )


def resolve_timeout(explicit: float | None = None) -> float:
    if explicit is not None:
        return float(explicit)
    raw = os.environ.get(ENV_TIMEOUT, "").strip()
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


def resolve_cache_dir(explicit: str | os.PathLike[str] | None = None) -> Path:
    return Path(explicit or os.environ.get(ENV_CACHE_DIR) or DEFAULT_CACHE_DIR)


def kept_terms(text: str) -> list[str]:
    """Which protected names actually occur in the input (case-insensitive)."""
    found: list[str] = []
    for term in GLOSSARY_KEEP:
        if re.search(rf"(?<![\w]){re.escape(term)}(?![\w])", text, re.IGNORECASE):
            found.append(term)
    return found


def cache_key(text: str, *, target_lang: str = _TARGET_LANG) -> str:
    """Cache identity includes the glossary version: editing it invalidates all."""
    seed = f"v{GLOSSARY_VERSION}|{target_lang}|{text}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]


def _is_chinese(text: str) -> bool:
    return bool(_ZH_CHAR.search(text))


# ---------------------------------------------------------------------------
# transport seam
# ---------------------------------------------------------------------------
class LLMTransport(Protocol):
    """Minimal POST seam. Returns ``(status_code, raw_body_bytes)``."""

    def post(self, url: str, body: bytes, headers: Mapping[str, str]) -> "tuple[int, bytes]":  # pragma: no cover
        ...


class HttpLLMTransport:
    """``urllib`` transport with the ambient proxy explicitly disabled.

    Same reasoning as everywhere else in this repo: the sandbox/host may export
    ``HTTP_PROXY`` that answers 502 for arbitrary hosts; an LLM call must not be
    routed through it by accident. Operators who genuinely need a proxy can set
    one explicitly on the transport, not through the environment.
    """

    def __init__(self, *, timeout: float | None = None, opener: urllib.request.OpenerDirector | None = None) -> None:
        self.timeout = resolve_timeout(timeout)
        self._opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}),  # empty dict, NOT None
        )

    def post(self, url: str, body: bytes, headers: Mapping[str, str]) -> tuple[int, bytes]:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return int(response.status), response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:  # subclass of URLError — first
            return int(exc.code), exc.read(MAX_RESPONSE_BYTES + 1) if hasattr(exc, "read") else b""
        except urllib.error.URLError as exc:
            raise TranslateUnavailable(f"cannot reach LLM endpoint: {exc.reason}") from exc
        except TimeoutError as exc:  # read-phase timeouts are bare TimeoutError
            raise TranslateUnavailable("timed out reading from the LLM endpoint") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise TranslateUnavailable(f"transport error calling the LLM endpoint: {exc}") from exc


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------
class FileCache:
    """One JSON file per key. Translation is deterministic given the glossary
    version, so entries have no TTL; a corrupt file is just a miss."""

    def __init__(self, root: str | os.PathLike[str], *, required_field: str = "zh") -> None:
        self.root = Path(root)
        #: The one field that proves the payload is complete for its purpose
        #: ("zh" for translations; callers storing other shapes pick their own).
        self.required_field = required_field

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(self._path(key).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return payload if isinstance(payload, dict) and payload.get(self.required_field) else None

    def put(self, key: str, payload: Mapping[str, Any]) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            tmp = self._path(key).with_suffix(".json.tmp")
            tmp.write_text(json.dumps(dict(payload), ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self._path(key))
        except OSError:
            pass  # a cache that cannot be written is a slow cache, not a broken one


# ---------------------------------------------------------------------------
# service
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Translation:
    zh: str
    kind: str
    target_lang: str
    cached: bool
    kept: tuple[str, ...]
    model: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "zh": self.zh,
            "kind": self.kind,
            "targetLang": self.target_lang,
            "cached": self.cached,
            "keptTerms": list(self.kept),
            "model": self.model or None,
        }


def _prompt(text: str, kind: str, kept: tuple[str, ...]) -> str:
    keep_line = "、".join(kept) if kept else "（本条没有出现受保护术语）"
    shape = (
        "这是一篇学术论文的标题，给出通顺、符合学术习惯的中文译名。"
        if kind == "title"
        else "这是一段学术文本（论文摘要或正文片段），翻译成自然、准确的简体中文。"
    )
    return (
        f"{shape}\n"
        f"规则：\n"
        f"1. 以下专有名/架构名/数据集名保留英文原文，不要音译：{keep_line}。\n"
        f"2. 只输出译文本身：不加「以下是翻译」之类的话，不用 markdown，不加引号。\n"
        f"3. 数字、公式、引用标记原样保留。\n"
        f"4. 译文必须是中文；不确定的术语宁可保留英文。\n\n"
        f"原文：\n{text}"
    )


class Translator:
    """Translate one piece of text; cached after the first success."""

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
        self._resolved: tuple[str, str, str] | None = None

    # -- config --------------------------------------------------------------
    def settings(self) -> tuple[str, str, str]:
        if self._resolved is None:
            key, url, model = self._explicit
            if not (key and url and model):
                env_key, env_url, env_model = resolve_llm_settings()
                key = key or env_key
                url = url or env_url
                model = model or env_model
            self._resolved = (key, url, model)
        return self._resolved

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
            raise LLMNotConfigured("翻译服务未配置模型：" + ", ".join(missing))

    # -- translate -----------------------------------------------------------
    def translate(self, text: str, *, kind: str = "text") -> Translation:
        """Translate ``text``; cached results carry ``cached=True``.

        ``kind`` shapes the prompt (title vs. passage) but is not trusted from
        the wire beyond the route's pattern check.
        """
        self.require_ready()
        clean = " ".join(str(text or "").split())
        if not clean:
            raise TranslateBadResponse("empty input")
        if len(clean) > MAX_INPUT_CHARS:
            raise TranslateBadResponse(f"input exceeds {MAX_INPUT_CHARS} chars")

        key = cache_key(clean)
        if self._cache is not None:
            cached = self._cache.get(key)
            if cached:
                return Translation(
                    zh=str(cached["zh"]),
                    kind=kind,
                    target_lang=_TARGET_LANG,
                    cached=True,
                    kept=tuple(cached.get("kept", ())),
                    model=str(cached.get("model") or ""),
                )

        zh, model = self._call_llm(clean, kind)
        payload = {"zh": zh, "kept": list(kept_terms(clean)), "model": model}
        if self._cache is not None:
            self._cache.put(key, payload)
        return Translation(
            zh=zh,
            kind=kind,
            target_lang=_TARGET_LANG,
            cached=False,
            kept=tuple(payload["kept"]),
            model=model,
        )

    # -- LLM call ------------------------------------------------------------
    def _endpoint(self, base_url: str) -> str:
        return f"{base_url}/chat/completions"

    def _call_llm(self, text: str, kind: str) -> tuple[str, str]:
        key, base_url, model = self.settings()
        transport = self._transport
        if transport is None:
            transport = HttpLLMTransport(timeout=self._timeout)

        body = json.dumps(
            {
                "model": model,
                "temperature": 0.0,
                "messages": [
                    {"role": "system", "content": "你是严谨的学术翻译。只输出译文，不输出任何别的文字。"},
                    {"role": "user", "content": _prompt(text, kind, kept_terms(text))},
                ],
            },
            ensure_ascii=False,
        ).encode("utf-8")

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
            raise TranslateBadResponse(f"LLM endpoint answered HTTP {status}")
        if len(raw) > MAX_RESPONSE_BYTES:
            raise TranslateBadResponse("LLM response exceeds the size cap")

        try:
            payload = json.loads(raw.decode("utf-8", "replace"))
        except ValueError as exc:
            raise TranslateBadResponse(f"LLM did not return JSON: {exc}") from exc

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TranslateBadResponse("LLM payload has no choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise TranslateBadResponse("LLM returned an empty completion")

        zh = " ".join(content.strip().strip('"').split())
        if not _is_chinese(zh):
            raise TranslateBadResponse("LLM completion contains no Chinese; refusing to pass it off as a translation")
        if zh == " ".join(text.split()):
            raise TranslateBadResponse("LLM returned the input unchanged; refusing to pass it off as a translation")
        if len(zh) > max(2000, len(text) * 3):
            raise TranslateBadResponse("LLM completion is implausibly long for the input")
        return zh, str(model)
