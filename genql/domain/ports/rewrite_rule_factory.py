"""Turns the REWRITE_RULES registry into an ordered rule list.

Exists so `OptimizationService` never imports `genql/repositories/`, which the
layering forbids and which is where the registry and its rules live. Mirrors
GuardrailFactory, which exists for exactly the same reason.

It takes no arguments: the sqlglot schema the rules used to need is built and
applied by OptimizationService's qualification step, before any rule runs.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.ports.rewrite_rule import RewriteRule


@runtime_checkable
class RewriteRuleFactory(Protocol):
    def rules(self) -> Sequence[RewriteRule]: ...
