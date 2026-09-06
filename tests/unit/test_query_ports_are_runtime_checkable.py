"""A plain class satisfying each port proves every Phase 5 service can be
tested without a database, an LLM, or a network call. Guardrail and
GuardrailFactory carry non-method members, so these are isinstance checks —
issubclass is not defined for data protocols."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.join_path import JoinPath
from genql.domain.entities.metric import Metric
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.ports.candidate_generator import CandidateGenerator
from genql.domain.ports.guardrail import Guardrail
from genql.domain.ports.guardrail_factory import GuardrailFactory
from genql.domain.ports.join_path_reader import JoinPathReader
from genql.domain.ports.metric_reader import MetricReader
from genql.domain.ports.object_name_reader import ObjectNameReader
from genql.domain.ports.planner import Planner
from genql.domain.ports.query_executor import QueryExecutor
from genql.domain.ports.query_executor_factory import QueryExecutorFactory
from genql.domain.ports.schema_linker import SchemaLinker

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=())


class FakeSchemaLinker:
    def link(
        self, question: str, datasource_name: str, domain_id: int | None = None
    ) -> tuple[SchemaLink, ...]:
        return ()


class FakePlanner:
    def plan(self, question: str, links: tuple[SchemaLink, ...]) -> QueryPlan:
        return PLAN


class FakeCandidateGenerator:
    def generate(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...] = (),
    ) -> SqlCandidate:
        return SqlCandidate(sql="SELECT 1", plan=plan)


class FakeGuardrail:
    name = "fake"
    priority = 10

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        return ()

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        return sql


class FakeGuardrailFactory:
    def for_datasource(self, datasource_name: str) -> Sequence[Guardrail]:
        return [FakeGuardrail()]


class FakeQueryExecutor:
    def execute(self, sql: str, row_cap: int) -> ExecutionResult:
        return ExecutionResult(columns=(), rows=(), row_count=0, truncated=False)


class FakeQueryExecutorFactory:
    def for_datasource(self, datasource: Datasource) -> QueryExecutor:
        return FakeQueryExecutor()


class FakeJoinPathReader:
    def read_join_paths(
        self, datasource_name: str, object_names: Sequence[str]
    ) -> Sequence[JoinPath]:
        return []


class FakeMetricReader:
    def read_metrics(self, datasource_name: str) -> Sequence[Metric]:
        return []


class FakeObjectNameReader:
    def read_object_names(self, datasource_name: str) -> frozenset[str]:
        return frozenset()


def test_a_plain_class_satisfies_each_phase_5_port() -> None:
    assert isinstance(FakeSchemaLinker(), SchemaLinker)
    assert isinstance(FakePlanner(), Planner)
    assert isinstance(FakeCandidateGenerator(), CandidateGenerator)
    assert isinstance(FakeGuardrail(), Guardrail)
    assert isinstance(FakeGuardrailFactory(), GuardrailFactory)
    assert isinstance(FakeQueryExecutor(), QueryExecutor)
    assert isinstance(FakeQueryExecutorFactory(), QueryExecutorFactory)
    assert isinstance(FakeJoinPathReader(), JoinPathReader)
    assert isinstance(FakeMetricReader(), MetricReader)
    assert isinstance(FakeObjectNameReader(), ObjectNameReader)
