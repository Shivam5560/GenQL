"""Builds the rewrite pipeline from REWRITE_RULES.

Importing `genql.repositories.query.rewrite_rules` is what populates the
registry. Nothing here names a rule class, so adding a rule is one new file
plus one decorator plus one import line in that package's `__init__` — never
an edit here. Mirrors GuardrailFactoryImpl exactly.
"""

from __future__ import annotations

from collections.abc import Sequence

import genql.repositories.query.rewrite_rules  # noqa: F401 - registration side effect
from genql.domain.ports.rewrite_rule import RewriteRule
from genql.repositories.query.rewrite_rules.registry import REWRITE_RULES


class RewriteRuleFactoryImpl:
    def rules(self) -> Sequence[RewriteRule]:
        return [
            REWRITE_RULES.create(key)
            for key in REWRITE_RULES.keys()  # noqa: SIM118 - Registry, not a dict
        ]
