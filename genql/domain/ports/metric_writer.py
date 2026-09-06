from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.metric import Metric


@runtime_checkable
class MetricWriter(Protocol):
    def write(self, metrics: Sequence[Metric]) -> int: ...
