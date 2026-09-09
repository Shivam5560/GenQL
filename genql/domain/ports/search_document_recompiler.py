"""Rebuilds genql_search_document under one ablation's overrides.

Only no_descriptions needs it. Every other ablation leaves the store untouched,
which is why this is a separate port rather than a step in the factory: a
caller reading AblationService can see exactly which ablations mutate shared
state and which do not.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.ablation import Ablation


@runtime_checkable
class SearchDocumentRecompiler(Protocol):
    def recompile(self, ablation: Ablation, datasource_name: str) -> int: ...
