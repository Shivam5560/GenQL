"""YAML-authored ambiguity defaults, upserted by (datasource_name, name) and
read back by datasource.

Two classes in one file, deliberately: they are the two halves of one table's
access and they share its two statements. This mirrors how the metric side is
organised, except that metrics happen to need only a writer plus a reader on
the same class — here the reader is consumed by a service (AmbiguityGateService)
and the writer by a different one (SemanticOverlayService), so they are split
into two types the container can inject independently.

ORDER BY name is not cosmetic: when two rules claim the same dimension, the
gate takes the first, so an unordered read would make the winner depend on
physical row order.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.rule import Rule

_UPSERT_RULE = text("""
    INSERT INTO genql.genql_rule (datasource_name, name, dimension, value, description)
    VALUES (:datasource_name, :name, :dimension, :value, :description)
    ON CONFLICT ON CONSTRAINT uq_genql_rule_identity DO UPDATE
        SET dimension = EXCLUDED.dimension,
            value = EXCLUDED.value,
            description = EXCLUDED.description,
            discovered_at = now()
""")

_SELECT_RULES = text("""
    SELECT name, dimension, value, description
    FROM genql.genql_rule
    WHERE datasource_name = :datasource_name
    ORDER BY name
""")


class PostgresRuleReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read_rules(self, datasource_name: str) -> tuple[Rule, ...]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_RULES, {"datasource_name": datasource_name}).all()
        return tuple(Rule.model_validate(r._mapping) for r in rows)  # noqa: SLF001


class PostgresRuleWriter:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write_rules(self, datasource_name: str, rules: Sequence[Rule]) -> int:
        if not rules:
            return 0
        params = [
            {"datasource_name": datasource_name, **rule.model_dump(mode="json")} for rule in rules
        ]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_RULE, params)
        return len(params)
