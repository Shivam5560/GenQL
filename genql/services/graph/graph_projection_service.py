"""Reads a schema's structure back from the semantic store and projects it.

Depends only on ports, exactly like CatalogScanService — it cannot reach
Postgres or Neo4j even by accident, which is what makes the unit test above
possible.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.ports.graph_writer import GraphWriter
from genql.domain.ports.semantic_catalog_reader import SemanticCatalogReader
from genql.domain.value_objects.schema_ref import SchemaRef


class GraphProjectionReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    objects: int
    edges: int

    @property
    def total(self) -> int:
        return self.objects + self.edges


class GraphProjectionService:
    def __init__(self, reader: SemanticCatalogReader, writer: GraphWriter) -> None:
        self._reader = reader
        self._writer = writer

    def project(self, ref: SchemaRef) -> GraphProjectionReport:
        objects = self._writer.write_objects(self._reader.read_objects(ref))
        edges = self._writer.write_edges(self._reader.read_constraints(ref))
        return GraphProjectionReport(objects=objects, edges=edges)
