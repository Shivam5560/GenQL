from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.domain_member import DomainMember
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
