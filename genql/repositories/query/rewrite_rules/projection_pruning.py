"""Drop selected columns nothing downstream reads.

The `SELECT *` expansion half of the spec's projection_pruning is not here: it
happens in OptimizationService's schema-qualification step, before any rule
runs, because in sqlglot star expansion is what `qualify(schema=...)` does.
What remains — and what this rule is — is the unused-column removal.
"""

from __future__ import annotations

from sqlglot import exp
from sqlglot.optimizer.pushdown_projections import pushdown_projections

from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES
from genql.repositories.query.rewrite_rules.safe_apply import safe_apply


@REWRITE_RULES.register("projection_pruning")
class ProjectionPruningRule:
    name = "projection_pruning"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return safe_apply(lambda e: pushdown_projections(e, dialect="postgres"), expression)
