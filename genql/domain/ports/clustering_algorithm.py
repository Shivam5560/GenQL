"""Community detection over one datasource's whole graph.

Takes a datasource name rather than a QueryScope: Leiden runs once over the
datasource's whole projected graph, not per schema — schemas are a
projection-time concept, not an analysis-time one.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ClusteringAlgorithm(Protocol):
    def detect(self, datasource_name: str) -> int: ...
