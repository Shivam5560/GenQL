"""Topology-aware node embeddings over one datasource's whole graph."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class NodeEmbedder(Protocol):
    def embed(self, datasource_name: str) -> int: ...
