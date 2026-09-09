"""Rebuilds genql_search_document under one ablation's overrides.

Used only by no_descriptions. Returns the document count so AblationService's
caller can print what it did — a recompile that silently produced zero
documents would make every case in that run fail for the wrong reason.
"""

from __future__ import annotations

from genql.domain.entities.ablation import Ablation


class SearchDocumentRecompilerImpl:
    def recompile(self, ablation: Ablation, datasource_name: str) -> int:
        # Deferred for the same reason as TurnRunnerFactoryImpl: importing
        # Container at module level would close the composition_root ->
        # container -> this module cycle.
        from genql.composition_root import Container  # noqa: PLC0415

        container = Container.with_overrides(**dict(ablation.setting_overrides))
        return container.compile_service().compile(datasource_name).documents
