"""Each node is an adapter: read the fields it needs off the state, call its
service, write the result back. The two that carry logic are the ones tested
hardest — static validation turns its typed failure into state so the router
can decide, and candidate generation counts a retry only when it was given
something to fix."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.api.query_nodes import (
    CandidateGenerationNode,
    GuardedExecutionNode,
    PlanningNode,
    SchemaLinkingNode,
    StaticValidationNode,
)
from genql.api.query_state import initial_state
from genql.domain.entities.datasource import Datasource
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import ExecutionError, GenerationError, StaticValidationError
from genql.domain.ports.guardrail import Guardrail
from genql.domain.ports.query_executor import QueryExecutor
from genql.services.query.guarded_execution_service import GuardedExecutionService
from genql.services.query.static_validation_service import StaticValidationService

LINK = SchemaLink(object_qualified_name="local.shop.orders", column_names=("id",))
PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT id FROM shop.orders LIMIT 1", plan=PLAN)
VIOLATION = GuardrailViolation(rule_name="fake", message="bad", repairable=False)
RESULT = ExecutionResult(columns=("id",), rows=((1,),), row_count=1, truncated=False)
DS = Datasource(name="local", dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")


class FakeLinker:
    def link(
        self, question: str, datasource_name: str, domain_id: int | None = None
    ) -> tuple[SchemaLink, ...]:
        return (LINK,)


class FakePlanner:
    def plan(self, question: str, links: tuple[SchemaLink, ...]) -> QueryPlan:
        return PLAN


class FakeGenerator:
    def __init__(self) -> None:
        self.seen: list[tuple[GuardrailViolation, ...]] = []

    def generate(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...] = (),
    ) -> SqlCandidate:
        self.seen.append(violations)
        return CANDIDATE


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
        raise StaticValidationError((violation,))


class FixedFactory:
    def __init__(self, rules: Sequence[Guardrail]) -> None:
        self._rules = rules

    def for_datasource(self, datasource_name: str) -> Sequence[Guardrail]:
        return self._rules


class FixedExecutorFactory:
    def for_datasource(self, datasource: Datasource) -> QueryExecutor:
        class _Executor:
            def execute(self, sql: str, row_cap: int) -> ExecutionResult:
                return RESULT

        return _Executor()


class FakeDatasourceRepository:
    def add(self, datasource: Datasource) -> None:
        raise NotImplementedError

    def get(self, name: str) -> Datasource:
        return DS

    def list_all(self, enabled_only: bool = False) -> list[Datasource]:
        return [DS]

    def remove(self, name: str) -> None:
        raise NotImplementedError


def test_schema_linking_writes_links_onto_the_state() -> None:
    state = initial_state("q", "local", "t-1")

    assert SchemaLinkingNode(FakeLinker())(state) == {"links": (LINK,)}


def test_planning_writes_the_plan_onto_the_state() -> None:
    state = initial_state("q", "local", "t-1")
    state["links"] = (LINK,)

    assert PlanningNode(FakePlanner())(state) == {"plan": PLAN}


def test_candidate_generation_does_not_count_a_retry_on_the_first_attempt() -> None:
    generator = FakeGenerator()
    state = initial_state("q", "local", "t-1")
    state["links"] = (LINK,)
    state["plan"] = PLAN

    update = CandidateGenerationNode(generator)(state)

    assert update["retry_count"] == 0
    assert generator.seen == [()]


def test_candidate_generation_counts_a_retry_and_forwards_the_violations() -> None:
    generator = FakeGenerator()
    state = initial_state("q", "local", "t-1")
    state["links"] = (LINK,)
    state["plan"] = PLAN
    state["violations"] = (VIOLATION,)

    update = CandidateGenerationNode(generator)(state)

    assert update["retry_count"] == 1
    assert generator.seen == [(VIOLATION,)]


def test_candidate_generation_without_a_plan_fails_loudly() -> None:
    with pytest.raises(GenerationError, match="without a plan"):
        CandidateGenerationNode(FakeGenerator())(initial_state("q", "local", "t-1"))


def test_static_validation_writes_the_validated_sql_and_clears_violations() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([PassingRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidate"] = CANDIDATE

    update = node(state)

    assert update["violations"] == ()
    assert "shop.orders" in str(update["validated_sql"])


def test_static_validation_turns_its_failure_into_state_rather_than_raising() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([FailingRule()])))
    state = initial_state("q", "local", "t-1")
    state["candidate"] = CANDIDATE

    update = node(state)

    assert update["validated_sql"] is None
    assert update["violations"] == (VIOLATION,)


def test_guarded_execution_writes_the_result_onto_the_state() -> None:
    service = GuardedExecutionService(
        datasources=FakeDatasourceRepository(),
        executors=FixedExecutorFactory(),
        row_cap=100,
    )
    state = initial_state("q", "local", "t-1")
    state["validated_sql"] = "SELECT id FROM shop.orders LIMIT 1"

    assert GuardedExecutionNode(service)(state) == {"result": RESULT}


def test_guarded_execution_without_validated_sql_fails_loudly() -> None:
    service = GuardedExecutionService(
        datasources=FakeDatasourceRepository(),
        executors=FixedExecutorFactory(),
        row_cap=100,
    )

    with pytest.raises(ExecutionError, match="without validated SQL"):
        GuardedExecutionNode(service)(initial_state("q", "local", "t-1"))


def test_a_node_reached_without_its_input_fails_loudly() -> None:
    node = StaticValidationNode(StaticValidationService(FixedFactory([PassingRule()])))

    with pytest.raises(StaticValidationError, match="without a candidate"):
        node(initial_state("q", "local", "t-1"))
