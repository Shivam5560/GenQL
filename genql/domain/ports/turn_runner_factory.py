"""Builds a TurnRunner over a container constructed with one ablation's
overrides.

AblationService holds this rather than a Container, because a service may not
import the composition root — and because "give me a pipeline with domains
switched off" is the actual thing the service needs, not a DI container.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.ablation import Ablation
from genql.domain.ports.turn_runner import TurnRunner


@runtime_checkable
class TurnRunnerFactory(Protocol):
    def for_ablation(self, ablation: Ablation) -> TurnRunner: ...
