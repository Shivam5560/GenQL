"""StaticValidationNode validates every candidate independently and collects
survivors rather than treating the batch as all-or-nothing. It also raises
its own typed error the moment no further attempt remains (Deviation 1 of
the Phase 6.5 plan), so the escalation budget is spent or refused in the same
evaluation that might flip it — never split across a node/router boundary."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.api.query_nodes import StaticValidationNode
from genql.api.query_state import initial_state
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import StaticValidationError
from genql.domain.ports.guardrail import Guardrail
from genql.services.query.static_validation_service import StaticValidationService

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT id FROM shop.orders LIMIT 1", plan=PLAN)
CANDIDATE_2 = SqlCandidate(sql="SELECT id FROM shop.orders LIMIT 2", plan=PLAN)
VIOLATION = GuardrailViolation(rule_name="fake", message="bad", repairable=True)


class PassingRule:
    name = "passing"
    priority = 10

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        return ()

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        return sql


class FailingRule:
    name = "failing"
    priority = 10

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        return (VIOLATION,)

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise StaticValidationError((VIOLATION,))


class UnrepairableRule:
    name = "unrepairable"
    priority = 10

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        return (GuardrailViolation(rule_name="unrepairable", message="fatal", repairable=False),)

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise StaticValidationError((violation,))


class FixedFactory:
    def __init__(self, rules: Sequence[Guardrail]) -> None:
        self._rules = rules

    def for_datasource(self, datasource_name: str) -> Sequence[Guardrail]:
        return self._rules


def test_static_validation_writes_survivors_and_their_qualified_sql() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([PassingRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE,)

    update = node(state)

    assert update["candidates"] == (CANDIDATE,)
    assert "shop.orders" in update["validated_sqls"][0]
    assert update["violations"] == ()


def test_static_validation_keeps_only_the_surviving_candidates() -> None:
    """One candidate references an unlisted column reported by FailingRule,
    the other passes — the survivor list is not all-or-nothing."""

    class MixedRule:
        name = "mixed"
        priority = 10

        def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
            if "LIMIT 2" in sql:
                return (VIOLATION,)
            return ()

        def repair(self, sql: str, violation: GuardrailViolation) -> str:
            raise StaticValidationError((violation,))

    node = StaticValidationNode(StaticValidationService(FixedFactory([MixedRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE, CANDIDATE_2)

    update = node(state)

    assert len(update["candidates"]) == 1
    assert update["candidates"][0] == CANDIDATE
    assert len(update["validated_sqls"]) == 1


def test_static_validation_grants_one_ordinary_retry_when_repairable() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([FailingRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE,)

    update = node(state)

    assert update["validated_sqls"] == ()
    assert update["violations"] == (VIOLATION,)
    assert "escalated" not in update


def test_static_validation_raises_immediately_on_an_unrepairable_violation() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([UnrepairableRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE,)

    with pytest.raises(StaticValidationError):
        node(state)


def test_static_validation_raises_on_a_second_ordinary_failure_when_not_contested() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([FailingRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE,)
    state["retry_count"] = 1

    with pytest.raises(StaticValidationError):
        node(state)


def test_static_validation_grants_one_escalated_retry_when_contested() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([FailingRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE,)
    state["retry_count"] = 1
    state["contested"] = True

    update = node(state)

    assert update["validated_sqls"] == ()
    assert update["escalated"] is True


def test_static_validation_raises_once_the_escalation_budget_is_already_spent() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([FailingRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidates"] = (CANDIDATE,)
    state["retry_count"] = 1
    state["contested"] = True
    state["escalated"] = True

    with pytest.raises(StaticValidationError):
        node(state)


def test_static_validation_without_any_candidates_fails_loudly() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([PassingRule()])))

    with pytest.raises(StaticValidationError, match="without any candidates"):
        node(initial_state("q", "local", "t-1"))
