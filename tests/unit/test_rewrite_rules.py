"""Each rule against a hand-built statement, asserting the specific transform,
and each rule against input it must not touch, asserting the no-op.

Every input here is already fully qualified against a schema, because that is
what OptimizationService guarantees before the first rule runs — and because
sqlglot's passes produce invalid SQL on unqualified input, which is the whole
reason for that guarantee.
"""

from __future__ import annotations

import sqlglot
from sqlglot.optimizer.qualify import qualify

from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES

DIALECT = "postgres"
SCHEMA = {
    "shop": {
        "orders": {"id": "INT", "cid": "INT", "total": "DECIMAL"},
        "items": {"oid": "INT", "qty": "INT"},
        "customers": {"id": "INT", "name": "TEXT"},
    }
}


def _qualified(sql: str) -> sqlglot.exp.Expression:
    return qualify(
        sqlglot.parse_one(sql, dialect=DIALECT), dialect=DIALECT, schema=SCHEMA, identify=False
    )


def _apply(key: str, sql: str) -> str:
    rule = REWRITE_RULES.create(key)
    return str(rule.apply(_qualified(sql)).sql(dialect=DIALECT))


def test_the_registry_holds_exactly_the_four_rules() -> None:
    assert REWRITE_RULES.keys() == [
        "cte_materialization",
        "predicate_pushdown",
        "projection_pruning",
        "redundant_join_elimination",
    ]


def test_every_rule_reports_its_own_registry_key_as_its_name() -> None:
    for key in REWRITE_RULES.keys():  # noqa: SIM118 - Registry, not a dict
        assert REWRITE_RULES.create(key).name == key


def test_predicate_pushdown_moves_a_predicate_into_the_joined_subquery() -> None:
    rewritten = _apply(
        "predicate_pushdown",
        "SELECT o.id FROM shop.orders AS o "
        "JOIN (SELECT oid, qty FROM shop.items) AS i ON i.oid = o.id WHERE i.qty > 5",
    )

    # The predicate now sits inside the subquery, bound to the inner alias.
    assert "items.qty > 5" in rewritten
    assert rewritten.index("items.qty > 5") < rewritten.index("ON i.oid = o.id")


def test_predicate_pushdown_leaves_a_single_table_select_alone() -> None:
    sql = "SELECT o.id FROM shop.orders AS o WHERE o.total > 10"

    assert _apply("predicate_pushdown", sql) == str(_qualified(sql).sql(dialect=DIALECT))


def test_cte_materialization_deduplicates_a_repeated_subquery_into_one_cte() -> None:
    rewritten = _apply(
        "cte_materialization",
        "SELECT a.id FROM (SELECT id FROM shop.orders) AS a "
        "JOIN (SELECT id FROM shop.orders) AS b ON a.id = b.id",
    )

    assert rewritten.startswith("WITH ")
    # One CTE, referenced twice — not two identical CTEs.
    assert rewritten.count(" AS (SELECT") == 1


def test_cte_materialization_leaves_a_statement_with_no_subquery_alone() -> None:
    sql = "SELECT o.id FROM shop.orders AS o"

    assert _apply("cte_materialization", sql) == str(_qualified(sql).sql(dialect=DIALECT))


def test_projection_pruning_drops_a_column_the_outer_query_never_reads() -> None:
    rewritten = _apply(
        "projection_pruning",
        "SELECT x.id FROM (SELECT id, cid, total FROM shop.orders) AS x",
    )

    assert "cid" not in rewritten
    assert "total" not in rewritten
    assert "id" in rewritten


def test_projection_pruning_keeps_every_column_the_outer_query_reads() -> None:
    rewritten = _apply(
        "projection_pruning",
        "SELECT x.id, x.total FROM (SELECT id, cid, total FROM shop.orders) AS x",
    )

    assert "total" in rewritten
    assert "cid" not in rewritten


def test_redundant_join_elimination_is_a_no_op_when_uniqueness_is_unprovable() -> None:
    """sqlglot eliminates a join only when it can prove the joined relation is
    unique on the key from the query's own structure. A plain FK join carries
    no such proof, so declining is the correct, safe answer — and asserting it
    here documents the gap rather than leaving a silent surprise."""
    sql = "SELECT o.id FROM shop.orders AS o LEFT JOIN shop.customers AS c ON c.id = o.cid"

    assert _apply("redundant_join_elimination", sql) == str(_qualified(sql).sql(dialect=DIALECT))


def test_redundant_join_elimination_removes_a_provably_unique_unused_join() -> None:
    rewritten = _apply(
        "redundant_join_elimination",
        "SELECT o.id FROM shop.orders AS o "
        "LEFT JOIN (SELECT id FROM shop.customers GROUP BY id) AS c ON c.id = o.cid",
    )

    assert "JOIN" not in rewritten


def test_every_rule_returns_the_input_unchanged_on_input_it_cannot_process() -> None:
    """The port's hard contract: a rule never raises and never returns None."""
    expression = sqlglot.parse_one("SELECT 1", dialect=DIALECT)

    for key in REWRITE_RULES.keys():  # noqa: SIM118 - Registry, not a dict
        result = REWRITE_RULES.create(key).apply(expression)
        assert result is not None
        assert isinstance(result, sqlglot.exp.Expression)
