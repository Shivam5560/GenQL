"""Remove a joined relation nothing references and whose join cannot change
cardinality.

sqlglot proves "cannot change cardinality" from the query's own structure — a
GROUP BY or DISTINCT that makes the joined relation unique on the key — not
from GenQL's foreign-key metadata. On a plain FK join it therefore declines,
which is the safe answer and is asserted as a test rather than left to be
discovered. See the plan's "Deliberately Not Done".
"""

from __future__ import annotations

from sqlglot import exp
from sqlglot.optimizer.eliminate_joins import eliminate_joins

from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES
from genql.repositories.query.rewrite_rules.safe_apply import safe_apply


@REWRITE_RULES.register("redundant_join_elimination")
class RedundantJoinEliminationRule:
    name = "redundant_join_elimination"

    def apply(self, expression: exp.Expression) -> exp.Expression:
        return safe_apply(eliminate_joins, expression)
