"""Fills in whatever the caller omitted, and refuses to guess when it cannot.

Order of preference for the datasource: what was asked for, then the
configured default, then the sole enabled datasource. More than one candidate
and no way to choose is an error naming the candidates, not a coin flip.
"""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import AmbiguousScopeError
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.schema_registration_repository import SchemaRegistrationRepository
from genql.domain.value_objects.query_scope import QueryScope
from genql.services.scope.registry import SCOPE_RESOLVERS
from genql.services.scope.validation import build_scope


@SCOPE_RESOLVERS.register("default")
class DefaultScopeResolver:
    def __init__(
        self,
        datasources: DatasourceRepository,
        registrations: SchemaRegistrationRepository,
        default_datasource: str | None = None,
    ) -> None:
        self._datasources = datasources
        self._registrations = registrations
        self._default_datasource = default_datasource

    def resolve(self, datasource_name: str | None, schema_names: Sequence[str]) -> QueryScope:
        return build_scope(
            self._datasources,
            self._registrations,
            self._pick_datasource(datasource_name),
            schema_names,
        )

    def _pick_datasource(self, datasource_name: str | None) -> str:
        if datasource_name is not None:
            return datasource_name
        if self._default_datasource is not None:
            return self._default_datasource
        candidates = [d.name for d in self._datasources.list_all(enabled_only=True)]
        if len(candidates) != 1:
            raise AmbiguousScopeError(candidates)
        return candidates[0]
