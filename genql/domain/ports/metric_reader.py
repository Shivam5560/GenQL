"""The read side of MetricWriter — Phase 4's YAML overlay authored them,
schema linking surfaces them so a plan can name a metric rather than
re-deriving its expression."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.metric import Metric


@runtime_checkable
class MetricReader(Protocol):
    def read_metrics(self, datasource_name: str) -> Sequence[Metric]: ...
