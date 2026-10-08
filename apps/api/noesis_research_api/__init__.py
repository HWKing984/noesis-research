"""NOESIS Research API — FastAPI business layer over the read-only KG adapter.

Stage 1 exposes exactly three business endpoints plus a readiness probe:

=================================================  ==================================
``GET /api/papers/search``                         bibliography search (query echo + evidence)
``GET /api/papers/{publication_id}``               one paper: authors, venues, mentions, candidate assertions
``GET /api/graph/neighbors``                       bounded local neighbourhood
``GET /api/health``                                readiness; 503 when the graph is not usable
=================================================  ==================================

Library, PDF upload and report export deliberately live in later stages (see
``docs/02_phase1_plan.md``).

``create_app`` is exported **lazily**. This package is a sibling of its test
module, so ``unittest`` discovery imports it while walking ``apps/api``; an
eager ``from .app import create_app`` would drag FastAPI in at that moment and
turn "dependency not installed" into a hard import error instead of a skippable
test. The lazy re-export keeps the package importable with the standard library
alone. ``uvicorn noesis_research_api.app:app`` is unaffected.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import _paths  # noqa: F401  (sys.path wiring; must precede any package import)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .app import create_app as create_app

__all__ = ["create_app"]


def __getattr__(name: str):
    if name == "create_app":
        from .app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
