"""run_scope executes the step sequence once per schema in the scope."""

from __future__ import annotations

from typing import ClassVar

from genql.discovery.runner import DiscoveryRunner
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult
from genql.domain.value_objects.query_scope import QueryScope
from genql.domain.value_objects.schema_ref import SchemaRef

SCOPE = QueryScope(datasource_name="local", schema_names=("tpcds", "shop"))


class RecordingStep:
    name: ClassVar[str] = "recording"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def run(self, ctx: DiscoveryContext) -> StepResult:
        self.seen.append(ctx.ref.qualified_name)
        return StepResult(step_name=self.name, succeeded=True, records_written=1, message="ok")


class FailingStep:
    name: ClassVar[str] = "failing"

    def run(self, ctx: DiscoveryContext) -> StepResult:
        return StepResult(step_name=self.name, succeeded=False, records_written=0, message="no")


class FakeRegistrations:
    def __init__(self) -> None:
        self.discovered: list[SchemaRef] = []

    def add(self, registration: object) -> None: ...

    def get(self, ref: SchemaRef) -> object:
        raise NotImplementedError

    def list_for_datasource(self, datasource_name: str, enabled_only: bool = False) -> list[object]:
        return []

    def remove(self, ref: SchemaRef) -> None: ...

    def mark_discovered(self, ref: SchemaRef) -> None:
        self.discovered.append(ref)


def test_each_schema_in_the_scope_gets_its_own_run() -> None:
    step = RecordingStep()

    results = DiscoveryRunner([step], FakeRegistrations()).run_scope(SCOPE, sample_limit=5)

    assert step.seen == ["local.tpcds", "local.shop"]
    assert [r.ref.schema_name for r in results] == ["tpcds", "shop"]
    assert all(r.succeeded for r in results)


def test_a_successful_run_stamps_last_discovered_at() -> None:
    registrations = FakeRegistrations()

    DiscoveryRunner([RecordingStep()], registrations).run_scope(SCOPE, sample_limit=5)

    assert [r.qualified_name for r in registrations.discovered] == ["local.tpcds", "local.shop"]


def test_a_failed_schema_is_not_stamped_and_does_not_stop_the_others() -> None:
    registrations = FakeRegistrations()

    results = DiscoveryRunner([FailingStep()], registrations).run_scope(SCOPE, sample_limit=5)

    assert registrations.discovered == []
    assert [r.succeeded for r in results] == [False, False]
