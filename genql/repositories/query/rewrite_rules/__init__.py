"""Importing this package is what populates REWRITE_RULES.

Each module registers its rule with a decorator at import time, so the
registry is empty until every module below has been imported once. This is the
same pattern `genql/repositories/guardrails/__init__.py` uses.
"""

from genql.repositories.query.rewrite_rules import (  # noqa: F401 - registration side effect
    cte_materialization,
    predicate_pushdown,
    projection_pruning,
    redundant_join_elimination,
)
from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES

__all__ = ["REWRITE_RULES"]
