"""Each node is an adapter: read the fields it needs off the state, call its
service, write the result back. StaticValidationNode's own tests live in
test_static_validation_node.py — its per-candidate survivor/escalation logic
is dense enough to want its own file under the 250-line limit; the other four
nodes are simple enough to share this one."""

from __future__ import annotations

import pytest

from genql.api.query_nodes import (
    CandidateGenerationNode,
    GuardedExecutionNode,
    PlanningNode,
    SchemaLinkingNode,
)
from genql.api.query_state import initial_state
from genql.domain.entities.datasource import Datasource
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import ExecutionError, GenerationError
from genql.domain.ports.query_executor import QueryExecutor
from genql.services.query.guarded_execution_service import GuardedExecutionService

LINK = SchemaLink(object_qualified_name="local.shop.orders", column_names=("id",))
PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT id FROM shop.orders LIMIT 1", plan=PLAN)
CANDIDATE_2 = SqlCandidate(sql="SELECT id FROM shop.orders LIMIT 2", plan=PLAN)
VIOLATION = GuardrailViolation(rule_name="fake", message="bad", repairable=True)
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
    def __init__(self, candidates: tuple[SqlCandidate, ...] = (CANDIDATE,)) -> None:
        self._candidates = candidates
        self.calls: list[dict[str, object]] = []

    def generate(  # noqa: PLR0913, PLR0917 - matches CandidateGenerator's signature
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...] = (),
        *,
        domain_id: int | None = None,
        contested: bool = False,
        escalated: bool = False,
    ) -> tuple[SqlCandidate, ...]:
        self.calls.append(
            {
                "violations": violations,
                "domain_id": domain_id,
                "contested": contested,
                "escalated": escalated,
            }
        )
        return self._candidates


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


def test_candidate_generation_forwards_state_into_the_generator() -> None:
    generator = FakeGenerator()
    state = initial_state("q", "local", "t-1", domain_id=7)
    state["links"] = (LINK,)
    state["plan"] = PLAN
    state["contested"] = True
    state["escalated"] = True

    CandidateGenerationNode(generator)(state)

    assert generator.calls == [
        {"violations": (), "domain_id": 7, "contested": True, "escalated": True}
    ]


def test_candidate_generation_writes_the_candidates_tuple() -> None:
    generator = FakeGenerator((CANDIDATE, CANDIDATE_2))
    state = initial_state("q", "local", "t-1")
    state["links"] = (LINK,)
    state["plan"] = PLAN

    update = CandidateGenerationNode(generator)(state)

    assert update["candidates"] == (CANDIDATE, CANDIDATE_2)


def test_candidate_generation_does_not_count_a_retry_on_the_first_attempt() -> None:
    generator = FakeGenerator()
    state = initial_state("q", "local", "t-1")
    state["links"] = (LINK,)
    state["plan"] = PLAN

    update = CandidateGenerationNode(generator)(state)

    assert update["retry_count"] == 0


def test_candidate_generation_counts_a_retry_and_forwards_the_violations() -> None:
    generator = FakeGenerator()
    state = initial_state("q", "local", "t-1")
    state["links"] = (LINK,)
    state["plan"] = PLAN
    state["violations"] = (VIOLATION,)

    update = CandidateGenerationNode(generator)(state)

    assert update["retry_count"] == 1
    assert generator.calls[0]["violations"] == (VIOLATION,)


def test_candidate_generation_without_a_plan_fails_loudly() -> None:
    with pytest.raises(GenerationError, match="without a plan"):
        CandidateGenerationNode(FakeGenerator())(initial_state("q", "local", "t-1"))


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
