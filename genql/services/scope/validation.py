"""Turns a datasource name and schema names into a validated QueryScope.

Shared by both resolvers, which differ only in what they are willing to infer
before they get here.
"""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.errors import UnknownSchemaRegistrationError
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.schema_registration_repository import SchemaRegistrationRepository
from genql.domain.value_objects.query_scope import QueryScope
from genql.domain.value_objects.schema_ref import SchemaRef


def build_scope(
    datasources: DatasourceRepository,
    registrations: SchemaRegistrationRepository,
    datasource_name: str,
    schema_names: Sequence[str],
) -> QueryScope:
    datasources.get(datasource_name)  # raises UnknownDatasourceError
    enabled = registrations.list_for_datasource(datasource_name, enabled_only=True)
    available = [r.schema_name for r in enabled]

    if not schema_names:
        if not available:
            raise UnknownSchemaRegistrationError(f"{datasource_name}.*", [])
        return QueryScope(datasource_name=datasource_name, schema_names=tuple(available))

    for name in schema_names:
        if name not in available:
            raise UnknownSchemaRegistrationError(
                SchemaRef(datasource_name=datasource_name, schema_name=name).qualified_name,
                [f"{datasource_name}.{a}" for a in available],
            )
    return QueryScope(datasource_name=datasource_name, schema_names=tuple(schema_names))
