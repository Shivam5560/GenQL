"""run_scope executes the step sequence once per schema in the scope."""

from __future__ import annotations

from typing import ClassVar

import pytest

from genql.discovery.runner import DiscoveryRunner
from genql.domain.errors import MissingDatasourceSecretError, UnknownDiscoveryStepError
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


class RaisingStep:
    """A step whose failure arrives as an exception rather than a StepResult.

    This is the real shape of a missing DSN or a dropped warehouse connection:
    the error is raised while the step is resolving its datasource, before any
    StepResult exists.
    """

    name: ClassVar[str] = "raising"

    def run(self, ctx: DiscoveryContext) -> StepResult:
        raise MissingDatasourceSecretError(ctx.datasource_name, "GENQL_ABSENT_DSN")


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


def test_a_raised_domain_error_becomes_a_failed_result_for_that_schema_only() -> None:
    """One unreachable warehouse must not abort the scope with a traceback."""
    registrations = FakeRegistrations()
    step = RecordingStep()

    results = DiscoveryRunner([RaisingStep(), step], registrations).run_scope(SCOPE, sample_limit=5)

    assert [r.succeeded for r in results] == [False, False]
    assert registrations.discovered == []
    assert "GENQL_ABSENT_DSN" in results[0].results[0].message
    # Both schemas were attempted, and the run halted at the failing step.
    assert len(results) == 2
    assert step.seen == []


def test_an_unknown_start_from_is_raised_once_not_reported_per_schema() -> None:
    """It is the caller's mistake, so it must reach the CLI's error handler
    rather than being flattened into n failed schemas."""
    runner = DiscoveryRunner([RecordingStep()], FakeRegistrations())

    with pytest.raises(UnknownDiscoveryStepError):
        runner.run_scope(SCOPE, sample_limit=5, start_from="typo")


def test_a_run_with_no_steps_is_not_a_success() -> None:
    """`all(())` is True, so an empty pipeline would otherwise stamp
    last_discovered_at for a schema nothing was read from."""
    registrations = FakeRegistrations()

    results = DiscoveryRunner([], registrations).run_scope(SCOPE, sample_limit=5)

    assert [r.succeeded for r in results] == [False, False]
    assert registrations.discovered == []
