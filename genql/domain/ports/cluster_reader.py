"""Reads a clustering algorithm's node-property assignment back out of
Neo4j — the read side FusedClusteringAlgorithm's `detect` doesn't itself
provide, since ClusteringAlgorithm.detect returns only a count."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable


@runtime_checkable
class ClusterReader(Protocol):
    def read_clusters(
        self, datasource_name: str, property_name: str
    ) -> Mapping[int, Sequence[str]]: ...
