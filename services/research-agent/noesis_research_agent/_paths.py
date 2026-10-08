"""Put the repository's shared modules on ``sys.path``.

Same monorepo wiring trick as ``apps/api/noesis_research_api/_paths.py``: until
``integrations/`` and ``packages/`` are installable distributions, both services
import them by path. Keeping it in one module per service means the switch to
real packaging is a single-file change per service.

``apps/api`` is on the path so the agent reuses the **same** response mapping the
HTTP API uses. That is deliberate: the agent's tool output is then byte-identical
to what the UI receives, which is what makes the "the agent only orchestrates, it
does not change the retrieval result" guarantee checkable instead of aspirational.
"""
from __future__ import annotations

import sys
from pathlib import Path

# .../noesis-research/services/research-agent/noesis_research_agent/_paths.py
REPO_ROOT = Path(__file__).resolve().parents[3]

for _extra in (
    REPO_ROOT,
    REPO_ROOT / "integrations" / "knowledge-graph",
    REPO_ROOT / "apps" / "api",
):
    if _extra.is_dir() and str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

__all__ = ["REPO_ROOT"]
