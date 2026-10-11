"""HTTP-level tests for POST /api/explain.

Same discipline as ``test_translate.py``: the real app, real Pydantic models,
real error mapping — only the LLM socket is replaced (and the KG socket, so no
database is needed).

Centres of gravity:

* the answer must be the **agreed JSON shape** (category / brief / detail /
  whyItMatters / example) with Chinese on the human-readable surface —
  anything else is 502, never partially shown;
* an LLM outage is 503 and is never answered with invented-sounding prose;
* ``style='simple'`` ("更简单一点") is part of the cache key, so re-asking
  simpler actually reaches the model again.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_IMPORT_ERROR: str | None = None
try:
    from fastapi.testclient import TestClient

    from noesis_research_api import create_app
    from noesis_research_api.app import Settings
    from noesis_research_api.explain import ExplainBadResponse
    from noesis_research_api.translate import (
        FileCache,
        LLMNotConfigured,
        TranslateUnavailable,
    )
except Exception as exc:  # pragma: no cover - core-only CI job
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

if _IMPORT_ERROR is not None:
    raise unittest.SkipTest(f"fastapi/httpx not installed ({_IMPORT_ERROR}); see apps/api/requirements.txt")

PINNED_GRAPH = "ai-literature-ed16399925fac2a599ed"
TERM = "self-attention"
GOOD = {
    "category": "概念",
    "brief": "让序列中每个位置直接关注所有其他位置并加权聚合信息的机制。",
    "detail": "每个位置的表示由全体位置按注意力权重加权求和得到，权重由相似度归一化而来。\n它摆脱了循环结构，训练可以完全并行。",
    "whyItMatters": "它是 Transformer 的核心构件，长程依赖不再随距离衰减。",
    "example": "例如“it”在长句中可以同时对照“animal”与“street”来确定指代。",
}


def body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def completion(text: str) -> bytes:
    return body({"choices": [{"message": {"content": text}}]})


class FakeLLM:
    def __init__(self, responder) -> None:
        self.responder = responder
        self.calls: list[dict] = []

    def post(self, url: str, body: bytes, headers):  # noqa: ANN001
        self.calls.append({"url": url, "payload": json.loads(body), "headers": dict(headers)})
        return self.responder(self.calls[-1])


def ok(_call) -> tuple[int, bytes]:
    return 200, completion(json.dumps(GOOD, ensure_ascii=False))


def build_explainer(fake: FakeLLM, *, cache: FileCache | None = None, **overrides):
    settings = {"api_key": "k", "base_url": "https://llm.test/v1", "model": "m", "timeout": 5.0}
    settings.update(overrides)
    from noesis_research_api.explain import Explainer

    return Explainer(transport=fake, cache=cache, **settings)


def build_client(explainer):
    app = create_app(
        settings=Settings(base_url="http://stub", expected_graph_id=PINNED_GRAPH, timeout=5.0),
        explainer=explainer,
    )
    return TestClient(app)


def post(client: TestClient, payload: dict):
    return client.post("/api/explain", json=payload)


class ExplainTests(unittest.TestCase):
    def test_happy_path_returns_the_agreed_shape(self) -> None:
        fake = FakeLLM(ok)
        client = build_client(build_explainer(fake))
        response = post(client, {"text": TERM, "kind": "term"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["category"], "概念")
        self.assertIn("关注", payload["brief"])
        self.assertIn("\n", payload["detail"], "the prompt asks for \\n-separated paragraphs")
        self.assertEqual(payload["kind"], "term")
        self.assertEqual(payload["style"], "normal")
        self.assertFalse(payload["cached"])
        self.assertEqual(payload["model"], "m")
        sent = fake.calls[0]["payload"]
        self.assertIn("只输出一个 JSON 对象", sent["messages"][0]["content"])
        self.assertIn("不要编造出处", sent["messages"][1]["content"])

    def test_fenced_json_is_accepted(self) -> None:
        fenced = "```json\n" + json.dumps(GOOD, ensure_ascii=False) + "\n```"
        fake = FakeLLM(lambda _call: (200, completion(fenced)))
        client = build_client(build_explainer(fake))
        self.assertEqual(post(client, {"text": TERM}).status_code, 200)

    def test_second_identical_request_is_served_from_cache(self) -> None:
        fake = FakeLLM(ok)
        with tempfile.TemporaryDirectory() as tmp:
            client = build_client(build_explainer(fake, cache=FileCache(tmp, required_field="brief")))
            self.assertFalse(post(client, {"text": TERM}).json()["cached"])
            calls = len(fake.calls)
            second = post(client, {"text": TERM})
            self.assertTrue(second.json()["cached"], "identical text must be a cache hit")
            self.assertEqual(len(fake.calls), calls, "a cache hit must not call the LLM")

    def test_simple_style_is_a_different_cache_entry(self) -> None:
        """「更简单一点」必须真的再问一次模型，而不是把 normal 的答案改个标签。"""
        fake = FakeLLM(ok)
        with tempfile.TemporaryDirectory() as tmp:
            client = build_client(build_explainer(fake, cache=FileCache(tmp, required_field="brief")))
            self.assertEqual(post(client, {"text": TERM, "style": "normal"}).status_code, 200)
            calls = len(fake.calls)
            response = post(client, {"text": TERM, "style": "simple"})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["cached"])
            self.assertEqual(response.json()["style"], "simple")
            self.assertEqual(len(fake.calls), calls + 1)
            self.assertIn("最通俗", fake.calls[-1]["payload"]["messages"][1]["content"])

    def test_context_reaches_the_prompt_and_the_cache_key(self) -> None:
        fake = FakeLLM(ok)
        with tempfile.TemporaryDirectory() as tmp:
            client = build_client(build_explainer(fake, cache=FileCache(tmp, required_field="brief")))
            self.assertEqual(post(client, {"text": TERM, "context": "Attention Is All You Need"}).status_code, 200)
            self.assertIn("Attention Is All You Need", fake.calls[0]["payload"]["messages"][1]["content"])
            calls = len(fake.calls)
            response = post(client, {"text": TERM})
            self.assertFalse(response.json()["cached"], "different context ⇒ different cache entry")
            self.assertEqual(len(fake.calls), calls + 1)

    def test_unconfigured_llm_is_503(self) -> None:
        client = build_client(build_explainer(FakeLLM(ok), api_key=""))
        env = {k: os.environ.get(k) for k in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")}
        for key in env:
            os.environ.pop(key, None)
        try:
            response = post(client, {"text": TERM})
        finally:
            for key, value in env.items():
                if value is not None:
                    os.environ[key] = value
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "llm_not_configured")

    def test_llm_outage_is_503_translate_unavailable(self) -> None:
        for status in (500, 503, 429):
            with self.subTest(status=status):
                fake = FakeLLM(lambda _call, s=status: (s, b"{}"))
                client = build_client(build_explainer(fake))
                response = post(client, {"text": TERM})
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["error"]["code"], "translate_unavailable")

    def test_non_json_answer_is_502_explain_bad_response(self) -> None:
        fake = FakeLLM(lambda _call: (200, b"<html>gateway</html>"))
        client = build_client(build_explainer(fake))
        response = post(client, {"text": TERM})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "explain_bad_response")

    def test_prose_without_json_is_502(self) -> None:
        """A chatty model that ignores the JSON contract must not be shown."""
        fake = FakeLLM(lambda _call: (200, completion("自注意力是一种机制，它让每个词关注其他词。")))
        client = build_client(build_explainer(fake))
        self.assertEqual(post(client, {"text": TERM}).status_code, 502)

    def test_missing_fields_are_502(self) -> None:
        broken = {k: v for k, v in GOOD.items() if k != "example"}
        fake = FakeLLM(lambda _call: (200, completion(json.dumps(broken, ensure_ascii=False))))
        client = build_client(build_explainer(fake))
        response = post(client, {"text": TERM})
        self.assertEqual(response.status_code, 502)
        self.assertIn("example", response.json()["error"]["message"])

    def test_all_english_explanation_is_refused(self) -> None:
        english = {**GOOD, "brief": "A mechanism where every position attends to all others."}
        fake = FakeLLM(lambda _call: (200, completion(json.dumps(english))))
        client = build_client(build_explainer(fake))
        self.assertEqual(post(client, {"text": TERM}).status_code, 502)

    def test_validation_rejects_empty_text_bad_kind_bad_style(self) -> None:
        client = build_client(build_explainer(FakeLLM(ok)))
        self.assertEqual(post(client, {"text": ""}).status_code, 422)
        self.assertEqual(post(client, {"text": TERM, "kind": "poem"}).status_code, 422)
        self.assertEqual(post(client, {"text": TERM, "style": "poetic"}).status_code, 422)
        self.assertEqual(post(client, {"text": TERM, "context": "x" * 2001}).status_code, 422)

    def test_service_exceptions_surface_through_the_same_mapping(self) -> None:
        cases = (
            (LLMNotConfigured("no model"), 503, "llm_not_configured"),
            (TranslateUnavailable("down"), 503, "translate_unavailable"),
            (ExplainBadResponse("garbage"), 502, "explain_bad_response"),
        )
        for exc, status, code in cases:
            with self.subTest(code=code):

                class ExplodingExplainer:
                    def explain(self, *_args, **_kwargs):
                        raise exc

                client = build_client(ExplodingExplainer())  # type: ignore[arg-type]
                response = post(client, {"text": TERM})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()["error"]["code"], code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
