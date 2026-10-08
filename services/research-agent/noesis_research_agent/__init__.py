"""NOESIS Research agent service.

A single Deep Agent wired to read-only research tools over the versioned
knowledge graph. Nothing here writes to the graph, and the agent has no host
shell (see :mod:`noesis_research_agent.agent`).

Imports are lazy on purpose: this package is a sibling of its test modules, so
``unittest`` discovery imports it while walking ``services/research-agent``. An
eager ``from .agent import build_agent`` would drag the whole LangChain stack in
at that moment and turn "deepagents not installed" into a hard import error
instead of a skippable test.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import _paths  # noqa: F401  (sys.path wiring; must precede any package import)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .agent import SYSTEM_PROMPT, build_agent, build_backend
    from .config import AgentSettings, ConfigurationError
    from .tools import RESEARCH_TOOL_NAMES, build_tools

__all__ = [
    "RESEARCH_TOOL_NAMES",
    "SYSTEM_PROMPT",
    "AgentSettings",
    "ConfigurationError",
    "build_agent",
    "build_backend",
    "build_tools",
]

_LAZY = {
    "SYSTEM_PROMPT": ("agent", "SYSTEM_PROMPT"),
    "build_agent": ("agent", "build_agent"),
    "build_backend": ("agent", "build_backend"),
    "AgentSettings": ("config", "AgentSettings"),
    "ConfigurationError": ("config", "ConfigurationError"),
    "build_tools": ("tools", "build_tools"),
    "RESEARCH_TOOL_NAMES": ("tools", "RESEARCH_TOOL_NAMES"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    from importlib import import_module

    value = getattr(import_module(f"{__name__}.{module_name}"), attribute)
    globals()[name] = value
    return value
