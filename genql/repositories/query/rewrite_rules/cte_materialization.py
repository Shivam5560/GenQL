"""Lift derived tables into CTEs, deduplicating identical ones.

This is precisely the spec's "wraps a repeated subquery referenced more than
once in the same statement in a WITH CTE, so the planner does not re-evaluate
it": sqlglot's eliminate_subqueries rewrites every derived table as a CTE and
collapses duplicates into one.
"""

from __future__ import annotations

from sqlglot import exp
from sqlglot.optimizer.eliminate_subqueries import eliminate_subqueries

from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES
from genql.repositories.query.rewrite_rules.safe_apply import safe_apply


@REWRITE_RULES.register("cte_materialization")
class CteMaterializationRule:
    name = "cte_materialization"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return safe_apply(eliminate_subqueries, expression)
