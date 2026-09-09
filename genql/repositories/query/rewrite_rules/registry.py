"""The rewrite-rule registry, keyed by rule name.

Mirrors GUARDRAILS and CANDIDATE_STRATEGIES: one file plus one decorator adds
a rule, and OptimizationService never names one.

`Registry.keys()` returns its keys *sorted*, so the pipeline runs
alphabetically — cte_materialization, predicate_pushdown, projection_pruning,
redundant_join_elimination — not in decorator order. That is acceptable only
because the pipeline is order-independent by construction: no rule re-creates
a pattern another one removes, which is also why it is a single pass rather
than a loop to a fixpoint. A rule that ever needs to run after another one
must instead be written to iterate internally.
"""

from __future__ import annotations

from genql.domain.ports.rewrite_rule import RewriteRule
from genql.registries.registry import Registry

REWRITE_RULES: Registry[RewriteRule] = Registry("rewrite_rules")
