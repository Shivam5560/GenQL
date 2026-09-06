"""Merge-time rule for one of description/alias/unit: given the current
discovered/LLM value and an optional YAML override, decide which value wins.
The default rule (an overlay always wins) is identical across all three
registered kinds; each still gets its own class so a future kind needing
different validation costs one new file, not a branch in an existing one."""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from genql.domain.entities.enrichment_field import EnrichmentField


@runtime_checkable
class Enricher(Protocol):
    key: ClassVar[str]

    def merge(
        self, discovered: EnrichmentField | None, overlay: EnrichmentField | None
    ) -> EnrichmentField | None: ...
