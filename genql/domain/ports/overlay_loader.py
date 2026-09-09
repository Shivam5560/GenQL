"""Finds the hand-written semantic overlay for a datasource, if there is one.

A port rather than a `Path` read inside the service: the overlay lives on disk
today (`semantic/<datasource>.yaml`), but the service's job is to decide
whether to apply one, not to know where files are. It also means a test can
supply an overlay without a temporary directory.
"""

from __future__ import annotations

from typing import Protocol

from genql.domain.entities.semantic_overlay import SemanticOverlay


class OverlayLoader(Protocol):
    def load(self, datasource_name: str) -> SemanticOverlay | None:
        """Return the overlay for this datasource, or None when none exists."""
        ...
