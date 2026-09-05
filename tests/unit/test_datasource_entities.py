from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.value_objects.schema_ref import SchemaRef


def test_datasource_defaults_to_enabled() -> None:
    ds = Datasource(name="local", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")
    assert ds.enabled is True
    assert ds.description is None


def test_datasource_is_frozen() -> None:
    ds = Datasource(name="local", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")
    with pytest.raises(ValidationError):
        ds.name = "other"  # type: ignore[misc]


def test_schema_registration_exposes_its_ref() -> None:
    reg = SchemaRegistration(datasource_name="local", schema_name="tpcds")

    assert reg.ref == SchemaRef(datasource_name="local", schema_name="tpcds")
    assert reg.enabled is True
    assert reg.last_discovered_at is None
