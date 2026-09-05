"""Requires the caller to say exactly what it means.

Registered for contexts where an implicit default would be dangerous — an API
process serving several tenants, for instance, where "the only enabled
datasource" is an accident of configuration rather than an intention.
"""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import AmbiguousScopeError
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.schema_registration_repository import SchemaRegistrationRepository
from genql.domain.value_objects.query_scope import QueryScope
from genql.services.scope.registry import SCOPE_RESOLVERS
from genql.services.scope.validation import build_scope


@SCOPE_RESOLVERS.register("explicit")
class ExplicitScopeResolver:
    def __init__(
        self,
        datasources: DatasourceRepository,
        registrations: SchemaRegistrationRepository,
        default_datasource: str | None = None,
    ) -> None:
        self._datasources = datasources
        self._registrations = registrations

    def resolve(self, datasource_name: str | None, schema_names: Sequence[str]) -> QueryScope:
        if datasource_name is None:
            raise AmbiguousScopeError([])
        if not schema_names:
            raise AmbiguousScopeError([datasource_name])
        return build_scope(self._datasources, self._registrations, datasource_name, schema_names)
