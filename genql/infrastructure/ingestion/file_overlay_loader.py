"""Reads `semantic/<datasource>.yaml`, the same file the CLI applies.

A malformed overlay raises rather than being skipped. Silently ignoring a
file someone wrote by hand would hand them a datasource that ingested
"successfully" while every metric and join hint they defined was dropped.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from genql.domain.entities.semantic_overlay import SemanticOverlay
from genql.domain.errors import OverlayError


class FileOverlayLoader:
    def __init__(self, root: Path) -> None:
        self._root = root

    def load(self, datasource_name: str) -> SemanticOverlay | None:
        path = self._root / f"{datasource_name}.yaml"
        if not path.exists():
            return None
        try:
            return SemanticOverlay.model_validate(yaml.safe_load(path.read_text()))
        except (ValidationError, yaml.YAMLError) as exc:
            raise OverlayError(f"{path} failed validation: {exc}") from exc
