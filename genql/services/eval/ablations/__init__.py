"""Importing this package is what populates ABLATIONS.

Each module registers its ablation with a decorator at import time, so the
registry is empty until every module below has been imported once. This is
the same pattern `genql/repositories/query/rewrite_rules/__init__.py` uses.
"""

from genql.services.eval.ablations import (  # noqa: F401 - registration side effect
    full,
    no_ambiguity_examples,
    no_descriptions,
    no_domains,
    no_join_paths,
    no_probing,
)
from genql.services.eval.registry import ABLATIONS

__all__ = ["ABLATIONS"]
