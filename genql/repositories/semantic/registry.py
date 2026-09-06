"""ENRICHERS (this task) and RETRIEVERS (Task 10), colocated the way
repositories/graph/registry.py colocates its three graph-algorithm
registries."""

from __future__ import annotations

from genql.domain.ports.enricher import Enricher
from genql.domain.ports.retriever import Retriever
from genql.registries.registry import Registry

ENRICHERS: Registry[Enricher] = Registry("enrichers")
RETRIEVERS: Registry[Retriever] = Registry("retrievers")
