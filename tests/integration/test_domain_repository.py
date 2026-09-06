from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.domain_member import DomainMember
from genql.domain.value_objects.provenance import Provenance
from genql.repositories.semantic.domain_repository import PostgresDomainRepository


def test_write_domains_returns_rows_with_ids_populated(migrated_engine: Engine) -> None:
    repo = PostgresDomainRepository(migrated_engine)
    domain = BusinessDomain(datasource_name="local", name="sales", description="Sales activity.")

    written = repo.write_domains([domain])

    assert written[0].domain_id is not None


def test_write_members_after_write_domains(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "domain_member_test")
    repo = PostgresDomainRepository(migrated_engine)
    domain = repo.write_domains(
        [BusinessDomain(datasource_name="local", name="sales_2", description="Sales activity.")]
    )[0]
    assert domain.domain_id is not None
    member = DomainMember(
        domain_id=domain.domain_id,
        datasource_name="local",
        schema_name="domain_member_test",
        object_name="orders",
    )

    count = repo.write_members([member])

    assert count == 1


def test_domain_id_by_name_returns_the_written_id(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("lookup_ds", "public")
    repo = PostgresDomainRepository(migrated_engine)
    written = repo.write_domains(
        [
            BusinessDomain(
                datasource_name="lookup_ds",
                name="Sales",
                description="Orders and revenue.",
                provenance=Provenance.LLM,
            )
        ]
    )

    found = repo.domain_id_by_name("lookup_ds", "Sales")

    assert found == written[0].domain_id


def test_domain_id_by_name_returns_none_for_an_unknown_name(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("lookup_ds", "public")

    assert (
        PostgresDomainRepository(migrated_engine).domain_id_by_name("lookup_ds", "No Such Domain")
        is None
    )


def test_domain_id_by_name_does_not_cross_datasources(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("lookup_ds", "public")
    register_schema("lookup_ds_2", "public")
    repo = PostgresDomainRepository(migrated_engine)
    repo.write_domains(
        [
            BusinessDomain(
                datasource_name="lookup_ds",
                name="Sales",
                description="Orders and revenue.",
                provenance=Provenance.LLM,
            )
        ]
    )

    assert repo.domain_id_by_name("lookup_ds_2", "Sales") is None
