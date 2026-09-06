"""Builds the full, priority-ordered rule set for one datasource.

Per-datasource rather than a process-wide singleton because one rule — the
object allowlist — is only meaningful against a particular datasource's
catalog. Mirrors CatalogReaderFactory and CommentWriterFactory exactly.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.ports.guardrail import Guardrail


@runtime_checkable
class GuardrailFactory(Protocol):
    def for_datasource(self, datasource_name: str) -> Sequence[Guardrail]: ...
