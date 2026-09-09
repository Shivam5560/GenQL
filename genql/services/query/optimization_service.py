"""The rewrite-and-cost-gate stage: the parent spec's §11, first two
sub-phases.

Qualification comes first and is not optional. sqlglot's optimizer passes
assume every column is bound to a relation; given an unqualified tree, the
predicate-pushdown pass will happily move a predicate into a subquery while
leaving it pointing at the *outer* alias, producing invalid SQL. Qualifying
against a schema built from the turn's SchemaLinks is what makes the passes
safe, and it is also what expands `SELECT *` into a real column list.

When qualification fails — a column no link declared, a statement sqlglot
cannot parse — this stage rewrites nothing and gates the original statement.
That is deliberate: static validation already passed the statement, so it is
correct; it simply does not get faster. Refusing to gate it would be worse
than not rewriting it.

A rule is recorded as applied when it changed the *rendered SQL*, not when it
returned a different object: sqlglot's passes mutate the tree in place and
return the same instance.

The single decomposition attempt is the only model call this stage makes, and
it is reached only when static rewriting left the statement over budget.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import sqlglot
import structlog
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError
from sqlglot.optimizer.qualify import qualify

from genql.domain.entities.optimization_result import OptimizationResult
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import CostEstimationError
from genql.domain.ports.cost_estimator import CostEstimator
from genql.domain.ports.query_decomposer import QueryDecomposer
from genql.domain.ports.rewrite_rule_factory import RewriteRuleFactory

_DIALECT = "postgres"

_log = structlog.get_logger(__name__)


def _schema_of(links: Sequence[SchemaLink]) -> dict[str, object]:
    """`{schema: {object: {column: type}}}`, the shape sqlglot's qualifier wants.

    Every column is typed UNKNOWN: qualification binds names to relations and
    expands stars, and none of that needs real types. Claiming types GenQL has
    not verified would be the only way this could be wrong.

    The return type widens to `dict[str, object]` because that is what sqlglot's
    `qualify` declares, and `dict` is invariant in its value type.
    """
    schema: dict[str, dict[str, dict[str, str]]] = {}
    for link in links:
        schema_name, _, object_name = link.schema_qualified_name.partition(".")
        if not object_name:
            continue
        schema.setdefault(schema_name, {})[object_name] = dict.fromkeys(
            link.column_names, "UNKNOWN"
        )
    return {name: objects for name, objects in schema.items()}


def _suggestion(cost: float, budget: float) -> str:
    ratio = cost / budget if budget > 0 else float("inf")
    return (
        f"this query's estimated cost is {ratio:.0f}x the configured budget, so it was not "
        "run — narrow the date range, add a more selective filter, or ask for a coarser grain"
    )


class OptimizationService:
    def __init__(
        self,
        rules: RewriteRuleFactory,
        estimator: CostEstimator,
        decomposer: QueryDecomposer,
        budget: float,
    ) -> None:
        self._rules = rules
        self._estimator = estimator
        self._decomposer = decomposer
        self._budget = budget

    def optimize(
        self,
        plan: QueryPlan,
        sql: str,
        links: Sequence[SchemaLink],
        datasource_name: str,
    ) -> OptimizationResult:
        rewritten, applied = self._rewrite(sql, links)
        cost = self._estimator.estimate(rewritten, datasource_name)
        if cost <= self._budget:
            return OptimizationResult(
                sql=rewritten,
                rules_applied=applied,
                estimated_cost=cost,
                within_budget=True,
            )
        return self._decompose(plan, rewritten, applied, cost, datasource_name)

    def _rewrite(self, sql: str, links: Sequence[SchemaLink]) -> tuple[str, tuple[str, ...]]:
        try:
            # `qualify` is typed as returning sqlglot's `Expr` base, one step
            # wider than the `Expression` the RewriteRule port takes; it hands
            # back the statement it was given, which `parse_one` typed exactly.
            expression = cast(
                exp.Expression,
                qualify(
                    sqlglot.parse_one(sql, dialect=_DIALECT),
                    dialect=_DIALECT,
                    schema=_schema_of(links),
                    identify=False,
                ),
            )
        except (ParseError, OptimizeError) as exc:
            # Deviation 2: the statement is still gated, just not rewritten.
            # Silently returning it would make an unqualifiable statement
            # indistinguishable from one no rule happened to match.
            _log.warning("optimization.qualify_failed", reason=str(exc))
            return sql, ()

        applied: list[str] = []
        for rule in self._rules.rules():
            before = expression.sql(dialect=_DIALECT)
            expression = rule.apply(expression)
            if expression.sql(dialect=_DIALECT) != before:
                applied.append(rule.name)
        return str(expression.sql(dialect=_DIALECT)), tuple(applied)

    def _decompose(
        self,
        plan: QueryPlan,
        sql: str,
        applied: tuple[str, ...],
        cost: float,
        datasource_name: str,
    ) -> OptimizationResult:
        candidate = self._decomposer.decompose(plan, sql, cost, self._budget)
        best_sql, best_cost = sql, cost
        if candidate != sql:
            try:
                candidate_cost = self._estimator.estimate(candidate, datasource_name)
            except CostEstimationError:
                candidate_cost = None
            if candidate_cost is not None and candidate_cost < cost:
                best_sql, best_cost = candidate, candidate_cost

        within = best_cost <= self._budget
        return OptimizationResult(
            sql=best_sql,
            rules_applied=applied,
            estimated_cost=best_cost,
            within_budget=within,
            narrowing_suggestion=None if within else _suggestion(best_cost, self._budget),
        )
