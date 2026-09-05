"""The runner's step list must be built FROM the registry, not hand-listed.

Before this fix, genql/composition_root.py hardcoded
`providers.List(Factory(CatalogScanStep, ...), Factory(DataProfilingStep, ...))`,
so a newly `@DISCOVERY_STEPS.register(...)`-ed step could be silently left out
of the pipeline. This asserts the constructed runner's step order always
equals DISCOVERY_STEPS's registered order, so that omission is caught here
instead of discovered in production. See final-review.md I4.
"""

from __future__ import annotations

import pytest

from genql.composition_root import Container
from genql.discovery.registry import DISCOVERY_STEPS


@pytest.fixture()
def container(monkeypatch: pytest.MonkeyPatch) -> Container:
    # Engines are constructed lazily by SQLAlchemy (no connection attempt at
    # create_engine() time), so a syntactically valid but unreachable DSN is
    # enough to build the container without touching a real database.
    monkeypatch.setenv("GENQL_WAREHOUSE_DSN", "postgresql+psycopg://x:x@localhost/x")
    monkeypatch.setenv("GENQL_SEMANTIC_DSN", "postgresql+psycopg://x:x@localhost/x")
    Container().reset_singletons()
    return Container()


def test_runner_step_names_equal_the_registered_order(container: Container) -> None:
    runner = container.discovery_runner()

    step_names = [step.name for step in runner._steps]  # noqa: SLF001

    assert step_names == DISCOVERY_STEPS.keys()


def test_every_registered_step_has_a_service_provider(container: Container) -> None:
    """A step registered without a service-provider entry fails fast (KeyError)."""
    runner = container.discovery_runner()

    assert len(runner._steps) == len(DISCOVERY_STEPS.keys())  # noqa: SLF001


def test_the_container_builds_a_catalog_reader_factory(container: Container) -> None:
    factory = container.catalog_reader_factory()

    assert hasattr(factory, "for_datasource")
