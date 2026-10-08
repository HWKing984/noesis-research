"""Agent configuration, entirely environment-driven.

The LLM variable names are the **same** ones NOESIS uses (``LLM_API_KEY`` /
``LLM_BASE_URL`` / ``LLM_MODEL``), so an operator can point this service at the
already-configured OpenAI-compatible endpoint without inventing a second
convention. Nothing is hard-coded, and no default endpoint is assumed: if the
key is missing the service refuses to start a run instead of silently falling
back to a model nobody configured.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from . import _paths  # noqa: F401  (sys.path wiring; must precede kg_client)

from kg_client import resolve_base_url, resolve_expected_graph_id

ENV_LLM_API_KEY = "LLM_API_KEY"
ENV_LLM_BASE_URL = "LLM_BASE_URL"
ENV_LLM_MODEL = "LLM_MODEL"
ENV_KG_TIMEOUT = "KG_TIMEOUT"

DEFAULT_KG_TIMEOUT_SECONDS = 20.0
DEFAULT_LLM_TEMPERATURE = 0.0


class ConfigurationError(RuntimeError):
    """Raised when a required setting is absent. Never silently defaulted."""


@dataclass(frozen=True)
class AgentSettings:
    kg_base_url: str
    expected_graph_id: str | None
    kg_timeout: float
    llm_api_key: str
    llm_base_url: str | None
    llm_model: str
    temperature: float = DEFAULT_LLM_TEMPERATURE

    @classmethod
    def from_env(cls) -> "AgentSettings":
        raw_timeout = os.environ.get(ENV_KG_TIMEOUT, "")
        try:
            timeout = float(raw_timeout) if raw_timeout.strip() else DEFAULT_KG_TIMEOUT_SECONDS
        except (TypeError, ValueError):
            timeout = DEFAULT_KG_TIMEOUT_SECONDS
        if timeout <= 0:
            timeout = DEFAULT_KG_TIMEOUT_SECONDS

        return cls(
            kg_base_url=resolve_base_url(),
            expected_graph_id=resolve_expected_graph_id(),
            kg_timeout=timeout,
            llm_api_key=os.environ.get(ENV_LLM_API_KEY, "").strip(),
            llm_base_url=(os.environ.get(ENV_LLM_BASE_URL, "").strip() or None),
            llm_model=os.environ.get(ENV_LLM_MODEL, "").strip(),
        )

    def missing_for_run(self) -> tuple[str, ...]:
        """Which settings a live run still needs. Empty tuple means ready."""
        missing: list[str] = []
        if not self.llm_api_key:
            missing.append(ENV_LLM_API_KEY)
        if not self.llm_model:
            missing.append(ENV_LLM_MODEL)
        return tuple(missing)

    def require_runnable(self) -> None:
        missing = self.missing_for_run()
        if missing:
            raise ConfigurationError(
                "cannot start a research run: missing " + ", ".join(missing)
            )
