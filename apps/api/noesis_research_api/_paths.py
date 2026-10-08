"""Put the repository's shared modules on ``sys.path``.

Temporary monorepo wiring: until ``integrations/`` and ``packages/`` are
installable distributions, the API imports them by path. Keeping it in one
module means switching to real packaging later is a single-file change.

Imported for its side effect; import it before anything that needs
``kg_client`` or ``packages.contracts``.
"""
from __future__ import annotations

import sys
from pathlib import Path

# .../noesis-research/apps/api/noesis_research_api/_paths.py
REPO_ROOT = Path(__file__).resolve().parents[3]

for _extra in (REPO_ROOT, REPO_ROOT / "integrations" / "knowledge-graph"):
    if _extra.is_dir() and str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

__all__ = ["REPO_ROOT"]
