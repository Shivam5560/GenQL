"""Builds a TurnRunner over a container carrying one ablation's overrides.

In `infrastructure/` rather than `services/` because it constructs a Container,
and the composition root is not something a service may reach. AblationService
holds the port; this is the only code that knows an ablation becomes a
container.
"""

from __future__ import annotations

from genql.api.graph_turn_runner import GraphTurnRunner
from genql.domain.entities.ablation import Ablation
from genql.domain.ports.turn_runner import TurnRunner


class TurnRunnerFactoryImpl:
    def for_ablation(self, ablation: Ablation) -> TurnRunner:
        # Deferred on purpose: composition_root imports every container,
        # which imports this module, and a module-level import here would
        # close the cycle. This is the one place in the codebase that needs
        # a deferred import.
        from genql.composition_root import Container  # noqa: PLC0415

        container = Container.with_overrides(**dict(ablation.setting_overrides))
        return GraphTurnRunner(container.query_graph(), container.thread_lock_factory())
