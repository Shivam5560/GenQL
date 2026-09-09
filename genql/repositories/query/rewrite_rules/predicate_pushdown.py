"""Push WHERE predicates down past joins and into subqueries.

sqlglot's own pass rather than hand-written AST surgery, for the reason the
plan's Deviation 1 gives: a rule that is not actually semantics-preserving
corrupts results silently, and the library's pass is the most tested version
of this transform available.
"""

from __future__ import annotations

from sqlglot import exp
from sqlglot.optimizer.pushdown_predicates import pushdown_predicates

from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES
from genql.repositories.query.rewrite_rules.safe_apply import safe_apply


@REWRITE_RULES.register("predicate_pushdown")
class PredicatePushdownRule:
    name = "predicate_pushdown"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return safe_apply(lambda e: pushdown_predicates(e, dialect="postgres"), expression)
