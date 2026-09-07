"""The only place that constructs dependencies.

The bulk of the wiring lives in `genql/composition/`, split by bounded
context (core/graph/gateway/semantic/query/turn) to stay under the project's
per-file line cap. `Container` here is the single inheritance point every
consumer imports; it only adds the piece that spans every discovery step: the
step-to-service map and the runner built from it.
"""

from __future__ import annotations

from typing import Any

from dependency_injector import providers

from genql.composition.turn_container import TurnContainer

# Imported for its registration side effect: every discovery step decorates
# itself into DISCOVERY_STEPS when genql.discovery.steps is imported. This is
# the one explicit place that import happens; the runner's step list below is
# built FROM the registry, not from a hardcoded list of step classes.
from genql.discovery import steps as _discovery_steps  # noqa: F401
from genql.discovery.registry import DISCOVERY_STEPS
from genql.discovery.runner import DiscoveryRunner


def _step_providers_in_registered_order(
    service_providers: dict[str, providers.Provider[Any]],
) -> list[providers.Provider[Any]]:
    """Build one Factory provider per registered step, in DISCOVERY_STEPS order.

    A plain function (rather than a class-body comprehension) because names
    assigned in a class body are not visible inside a nested comprehension's
    scope — this keeps the lookup working and keeps it obviously correct.
    """
    return [
        providers.Factory(DISCOVERY_STEPS.get(name), service=service_providers[name])
        for name in DISCOVERY_STEPS.keys()  # noqa: SIM118 - Registry, not a dict
    ]


class Container(TurnContainer):
    # Every step name registered in DISCOVERY_STEPS must have an entry here so
    # its constructor can be injected with the service it needs. A step
    # registered without an entry fails fast (KeyError) at import time rather
    # than being silently dropped from the pipeline.
    _step_service_providers: dict[str, providers.Provider[Any]] = {
        "catalog_scan": TurnContainer.catalog_scan_service,
        "data_profiling": TurnContainer.profiling_service,
        "graph_projection": TurnContainer.graph_projection_service,
        "object_profiling": TurnContainer.object_profiling_service,
    }

    discovery_runner = providers.Factory(
        DiscoveryRunner,
        steps=providers.List(*_step_providers_in_registered_order(_step_service_providers)),
        registrations=TurnContainer.schema_registration_repository,
    )
