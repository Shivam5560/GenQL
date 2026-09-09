"""The factory is the only thing that reads the registry, so this is where the
"one file plus one decorator" claim is actually verified."""

from __future__ import annotations

from genql.domain.ports.rewrite_rule_factory import RewriteRuleFactory
from genql.infrastructure.query.rewrite_rule_factory import RewriteRuleFactoryImpl


def test_the_factory_satisfies_its_port() -> None:
    assert isinstance(RewriteRuleFactoryImpl(), RewriteRuleFactory)


def test_the_factory_returns_every_registered_rule_in_registry_order() -> None:
    names = [rule.name for rule in RewriteRuleFactoryImpl().rules()]

    assert names == [
        "cte_materialization",
        "predicate_pushdown",
        "projection_pruning",
        "redundant_join_elimination",
    ]


def test_the_factory_returns_fresh_instances_per_call() -> None:
    """Rules are stateless today, but the registry stores classes, and a rule
    that later holds per-call state must not be shared across turns."""
    first = RewriteRuleFactoryImpl().rules()
    second = RewriteRuleFactoryImpl().rules()

    assert first[0] is not second[0]
