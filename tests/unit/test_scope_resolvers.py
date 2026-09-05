from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.errors import (
    AmbiguousScopeError,
    UnknownDatasourceError,
    UnknownSchemaRegistrationError,
)
from genql.domain.value_objects.query_scope import QueryScope
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.scope.default_scope_resolver import DefaultScopeResolver
from genql.services.scope.explicit_scope_resolver import ExplicitScopeResolver

LOCAL = Datasource(name="local", dialect="postgres", dsn_env_var="A")
WH2 = Datasource(name="wh2", dialect="postgres", dsn_env_var="B")


class FakeDatasources:
    def __init__(self, rows: list[Datasource]) -> None:
        self.rows = {d.name: d for d in rows}

    def add(self, datasource: Datasource) -> None: ...

    def get(self, name: str) -> Datasource:
        try:
            return self.rows[name]
        except KeyError:
            raise UnknownDatasourceError(name, sorted(self.rows)) from None

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        return [d for d in self.rows.values() if d.enabled or not enabled_only]

    def remove(self, name: str) -> None: ...


class FakeRegistrations:
    def __init__(self, rows: list[SchemaRegistration]) -> None:
        self.rows = rows

    def add(self, registration: SchemaRegistration) -> None: ...

    def get(self, ref: SchemaRef) -> SchemaRegistration:
        for row in self.rows:
            if row.ref == ref:
                return row
        raise UnknownSchemaRegistrationError(
            ref.qualified_name, [r.ref.qualified_name for r in self.rows]
        )

    def list_for_datasource(
        self, datasource_name: str, enabled_only: bool = False
    ) -> Sequence[SchemaRegistration]:
        return [
            r
            for r in self.rows
            if r.datasource_name == datasource_name and (r.enabled or not enabled_only)
        ]

    def remove(self, ref: SchemaRef) -> None: ...

    def mark_discovered(self, ref: SchemaRef) -> None: ...


TPCDS = SchemaRegistration(datasource_name="local", schema_name="tpcds")
SHOP = SchemaRegistration(datasource_name="local", schema_name="shop")
STALE = SchemaRegistration(datasource_name="local", schema_name="stale", enabled=False)


def _default(
    datasources: list[Datasource],
    registrations: list[SchemaRegistration],
    default_datasource: str | None = None,
) -> DefaultScopeResolver:
    return DefaultScopeResolver(
        datasources=FakeDatasources(datasources),
        registrations=FakeRegistrations(registrations),
        default_datasource=default_datasource,
    )


def test_sole_enabled_datasource_is_used_when_none_is_given() -> None:
    resolver = _default([LOCAL], [TPCDS, SHOP])

    assert resolver.resolve(None, []) == QueryScope(
        datasource_name="local", schema_names=("tpcds", "shop")
    )


def test_disabled_schemas_are_excluded_from_the_implicit_scope() -> None:
    resolver = _default([LOCAL], [TPCDS, STALE])

    assert resolver.resolve(None, []).schema_names == ("tpcds",)


def test_two_enabled_datasources_and_no_choice_is_ambiguous() -> None:
    resolver = _default([LOCAL, WH2], [TPCDS])

    with pytest.raises(AmbiguousScopeError, match="local"):
        resolver.resolve(None, [])


def test_the_configured_default_settles_ambiguity() -> None:
    resolver = _default([LOCAL, WH2], [TPCDS], default_datasource="local")

    assert resolver.resolve(None, []).datasource_name == "local"


def test_an_explicitly_named_schema_must_be_registered() -> None:
    resolver = _default([LOCAL], [TPCDS])

    with pytest.raises(UnknownSchemaRegistrationError, match="local.absent"):
        resolver.resolve("local", ["absent"])


def test_a_datasource_with_no_registered_schemas_is_rejected() -> None:
    resolver = _default([LOCAL], [])

    with pytest.raises(UnknownSchemaRegistrationError):
        resolver.resolve("local", [])


def test_explicit_resolver_refuses_to_infer_the_datasource() -> None:
    resolver = ExplicitScopeResolver(
        datasources=FakeDatasources([LOCAL]),
        registrations=FakeRegistrations([TPCDS]),
        default_datasource=None,
    )

    with pytest.raises(AmbiguousScopeError):
        resolver.resolve(None, ["tpcds"])


def test_explicit_resolver_refuses_to_infer_the_schemas() -> None:
    resolver = ExplicitScopeResolver(
        datasources=FakeDatasources([LOCAL]),
        registrations=FakeRegistrations([TPCDS]),
        default_datasource=None,
    )

    with pytest.raises(AmbiguousScopeError):
        resolver.resolve("local", [])


def test_explicit_resolver_accepts_a_fully_specified_scope() -> None:
    resolver = ExplicitScopeResolver(
        datasources=FakeDatasources([LOCAL]),
        registrations=FakeRegistrations([TPCDS]),
        default_datasource=None,
    )

    assert resolver.resolve("local", ["tpcds"]) == QueryScope(
        datasource_name="local", schema_names=("tpcds",)
    )
