"""HTTP-level tests for POST /api/translate.

Same discipline as ``test_api.py``: the real app, real Pydantic models, real
error mapping — only the LLM socket is replaced (and the KG socket, so no
database is needed).

The single behavioural centre of gravity: **an LLM failure is never answered
with the original text pretending to be a translation.**
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
    from noesis_research_api.translate import (
        FileCache,
        LLMNotConfigured,
        TranslateBadResponse,
        TranslateUnavailable,
        Translator,
    )
except Exception as exc:  # pragma: no cover - core-only CI job
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

if _IMPORT_ERROR is not None:
    raise unittest.SkipTest(f"fastapi/httpx not installed ({_IMPORT_ERROR}); see apps/api/requirements.txt")

PINNED_GRAPH = "ai-literature-ed16399925fac2a599ed"
TITLE = "Deep Residual Learning for Image Recognition"
ZH = "用于图像识别的深度残差学习"


def body(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def completion(text: str) -> bytes:
    return body({"choices": [{"message": {"content": text}}]})


class FakeLLM:
    """Transport stub. ``responder`` maps the parsed request to (status, bytes)."""

    def __init__(self, responder) -> None:
        self.responder = responder
        self.calls: list[dict] = []

    def post(self, url: str, body: bytes, headers):  # noqa: ANN001
        self.calls.append({"url": url, "payload": json.loads(body), "headers": dict(headers)})
        return self.responder(self.calls[-1])


def ok(_call) -> tuple[int, bytes]:
    return 200, completion(ZH)


def build_translator(fake: FakeLLM, *, cache: FileCache | None = None, **overrides) -> Translator:
    settings = {"api_key": "k", "base_url": "https://llm.test/v1", "model": "m", "timeout": 5.0}
    settings.update(overrides)
    return Translator(transport=fake, cache=cache, **settings)


def build_client(translator: Translator):
    app = create_app(
        settings=Settings(base_url="http://stub", expected_graph_id=PINNED_GRAPH, timeout=5.0),
        translator=translator,
    )
    return TestClient(app)


def post(client: TestClient, payload: dict):
    return client.post("/api/translate", json=payload)


class TranslateTests(unittest.TestCase):
    def test_happy_path_returns_a_chinese_translation(self) -> None:
        fake = FakeLLM(ok)
        client = build_client(build_translator(fake))
        response = post(client, {"text": TITLE, "kind": "title"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["zh"], ZH)
        self.assertEqual(payload["kind"], "title")
        self.assertEqual(payload["targetLang"], "zh-Hans")
        self.assertFalse(payload["cached"])
        # provenance the UI must show: which names stayed English, which model answered.
        # This title contains no protected name at all → the list is honestly empty.
        self.assertEqual(payload["keptTerms"], [])
        self.assertEqual(payload["model"], "m")
        # the prompt the model saw carries the keep list
        sent = fake.calls[0]["payload"]
        self.assertIn("保留英文原文", sent["messages"][1]["content"])
        self.assertEqual(fake.calls[0]["headers"]["Authorization"], "Bearer k")

    def test_a_second_identical_request_is_served_from_cache(self) -> None:
        fake = FakeLLM(ok)
        with tempfile.TemporaryDirectory() as tmp:
            translator = build_translator(fake, cache=FileCache(tmp))
            client = build_client(translator)
            first = post(client, {"text": TITLE})
            self.assertEqual(first.status_code, 200)
            self.assertFalse(first.json()["cached"])
            calls_after_first = len(fake.calls)
            second = post(client, {"text": TITLE})
            self.assertEqual(second.status_code, 200)
            self.assertTrue(second.json()["cached"], "identical text must be a cache hit")
            self.assertEqual(second.json()["zh"], ZH)
            self.assertEqual(len(fake.calls), calls_after_first, "a cache hit must not call the LLM")

    def test_glossary_version_change_invalidates_cached_entries(self) -> None:
        import noesis_research_api.translate as translate_module

        fake = FakeLLM(ok)
        with tempfile.TemporaryDirectory() as tmp:
            translator = build_translator(fake, cache=FileCache(tmp))
            client = build_client(translator)
            self.assertEqual(post(client, {"text": TITLE}).status_code, 200)
            calls = len(fake.calls)
            translate_module.GLOSSARY_VERSION += 1
            try:
                response = post(client, {"text": TITLE})
            finally:
                translate_module.GLOSSARY_VERSION -= 1
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["cached"], "a glossary edit must invalidate the cache")
            self.assertEqual(len(fake.calls), calls + 1)

    def test_unconfigured_llm_is_503_llm_not_configured(self) -> None:
        fake = FakeLLM(ok)
        client = build_client(build_translator(fake, api_key=""))
        env = {k: os.environ.get(k) for k in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")}
        for key in env:
            os.environ.pop(key, None)
        try:
            response = post(client, {"text": TITLE})
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
                client = build_client(build_translator(fake))
                response = post(client, {"text": TITLE})
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["error"]["code"], "translate_unavailable")

    def test_rejected_credentials_are_unavailable_not_bad_response(self) -> None:
        fake = FakeLLM(lambda _call: (401, b'{"error": "bad key"}'))
        client = build_client(build_translator(fake))
        response = post(client, {"text": TITLE})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "translate_unavailable")

    def test_non_json_answer_is_502(self) -> None:
        fake = FakeLLM(lambda _call: (200, b"<html>gateway</html>"))
        client = build_client(build_translator(fake))
        response = post(client, {"text": TITLE})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "translate_bad_response")

    def test_a_completion_without_chinese_is_refused(self) -> None:
        """The failure mode that would silently hand back the English original."""
        fake = FakeLLM(lambda _call: (200, completion(TITLE)))
        client = build_client(build_translator(fake))
        response = post(client, {"text": TITLE})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "translate_bad_response")

    def test_a_completion_identical_to_the_input_is_refused(self) -> None:
        """Whitespace-normalised equality with the input is not a translation."""
        chinese_input = "这是一个中文输入测试，用于检查复读。"
        fake = FakeLLM(lambda _call: (200, completion(chinese_input)))
        client = build_client(build_translator(fake))
        response = post(client, {"text": chinese_input})
        self.assertEqual(response.status_code, 502)

    def test_malformed_payload_shape_is_502(self) -> None:
        fake = FakeLLM(lambda _call: (200, body({"choices": []})))
        client = build_client(build_translator(fake))
        response = post(client, {"text": TITLE})
        self.assertEqual(response.status_code, 502)

    def test_validation_rejects_empty_text_and_bad_kind(self) -> None:
        fake = FakeLLM(ok)
        client = build_client(build_translator(fake))
        self.assertEqual(post(client, {"text": ""}).status_code, 422)
        self.assertEqual(post(client, {"text": TITLE, "kind": "poem"}).status_code, 422)

    def test_service_exceptions_surface_through_the_same_mapping(self) -> None:
        """The route itself raises; app.py's handler maps type → status → code."""
        cases = (
            (LLMNotConfigured("no model"), 503, "llm_not_configured"),
            (TranslateUnavailable("down"), 503, "translate_unavailable"),
            (TranslateBadResponse("garbage"), 502, "translate_bad_response"),
        )
        for exc, status, code in cases:
            with self.subTest(code=code):

                class ExplodingTranslator:
                    def translate(self, *_args, **_kwargs):
                        raise exc

                client = build_client(ExplodingTranslator())  # type: ignore[arg-type]
                response = post(client, {"text": TITLE})
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json()["error"]["code"], code)

    def test_kept_terms_echo_names_that_actually_occurred(self) -> None:
        """The popover shows *which* names survived on purpose — in glossary order."""
        fake = FakeLLM(ok)
        client = build_client(build_translator(fake))
        response = post(client, {"text": "ResNet beats prior CNN baselines on ImageNet classification."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["keptTerms"], ["ResNet", "ImageNet"])

    def test_health_endpoint_still_works_alongside(self) -> None:
        """The new router must not disturb the existing surface."""
        fake = FakeLLM(ok)
        client = build_client(build_translator(fake))
        health = client.get("/api/health")
        # KG is a stubbed client with no routes here → 502 kg_bad_response is fine;
        # what matters is that the endpoint exists and answers, not 404.
        self.assertIn(health.status_code, (200, 502, 503))


if __name__ == "__main__":
    unittest.main(verbosity=2)
