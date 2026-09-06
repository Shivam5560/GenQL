"""Domains and their membership. write_domains upserts by (datasource_name,
name) and returns rows with `id` populated via RETURNING, since the caller's
BusinessDomain instances arrive with domain_id=None before the first write."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.domain_member import DomainMember

_UPSERT_DOMAIN = text("""
    INSERT INTO genql.genql_domain (datasource_name, name, description, provenance)
    VALUES (:datasource_name, :name, :description, :provenance)
    ON CONFLICT ON CONSTRAINT uq_genql_domain_identity DO UPDATE
        SET description = EXCLUDED.description,
            provenance = EXCLUDED.provenance,
            discovered_at = now()
    RETURNING id
""")

_UPSERT_MEMBER = text("""
    INSERT INTO genql.genql_domain_member
        (domain_id, datasource_name, schema_name, object_name, membership_score)
    VALUES (:domain_id, :datasource_name, :schema_name, :object_name, :membership_score)
    ON CONFLICT ON CONSTRAINT pk_genql_domain_member DO UPDATE
        SET membership_score = EXCLUDED.membership_score
""")


class PostgresDomainRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write_domains(self, domains: Sequence[BusinessDomain]) -> Sequence[BusinessDomain]:
        written: list[BusinessDomain] = []
        with self._engine.begin() as conn:
            for domain in domains:
                domain_id = conn.execute(
                    _UPSERT_DOMAIN,
                    {
                        "datasource_name": domain.datasource_name,
                        "name": domain.name,
                        "description": domain.description,
                        "provenance": domain.provenance.value,
                    },
                ).scalar_one()
                written.append(BusinessDomain(**{**domain.model_dump(), "domain_id": domain_id}))
        return written

    def write_members(self, members: Sequence[DomainMember]) -> int:
        if not members:
            return 0
        rows = [m.model_dump(mode="json") for m in members]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_MEMBER, rows)
        return len(rows)
