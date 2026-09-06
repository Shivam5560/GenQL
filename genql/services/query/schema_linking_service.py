"""Binds retrieval hits to concrete SQL identifiers.

The parent spec's §9 stage 5. Deliberately free of any LLM call: retrieval
decides which objects, and the semantic store supplies everything else, so
this stage keeps working with every model provider unreachable.

A metric is bound to an object when the metric's SQL expression names that
object. It is a substring match on a normalized name rather than a parse:
`Metric.sql_expression` is a fragment authored in YAML (`sum(orders.total)`),
not a whole statement, so there is nothing for sqlglot to parse reliably.

Columns are read once per distinct schema rather than once per object: a
question that retrieves eight objects from one schema is one read, not eight.
"""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import RetrievalError, SchemaLinkingError
from genql.domain.ports.join_path_reader import JoinPathReader
from genql.domain.ports.metric_reader import MetricReader
from genql.domain.ports.retriever import SearchResult
from genql.domain.ports.semantic_catalog_reader import SemanticCatalogReader
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.semantic.retrieval_service import RetrievalService


class SchemaLinkingService:
    def __init__(
        self,
        retrieval: RetrievalService,
        reader: SemanticCatalogReader,
        join_paths: JoinPathReader,
        metrics: MetricReader,
        top_k: int,
    ) -> None:
        self._retrieval = retrieval
        self._reader = reader
        self._join_paths = join_paths
        self._metrics = metrics
        self._top_k = top_k

    def link(
        self, question: str, datasource_name: str, domain_id: int | None = None
    ) -> tuple[SchemaLink, ...]:
        try:
            results = self._retrieval.search(datasource_name, question, self._top_k, domain_id)
        except RetrievalError as exc:
            raise SchemaLinkingError(f"retrieval failed for {question!r}: {exc}") from exc
        if not results:
            raise SchemaLinkingError(
                f"no catalogued object matched {question!r} in datasource {datasource_name!r}"
            )

        object_names = [r.object_name for r in results]
        paths = self._join_paths.read_join_paths(datasource_name, object_names)
        metrics = self._metrics.read_metrics(datasource_name)
        columns_by_object = self._columns_by_object(datasource_name, results)

        return tuple(
            SchemaLink(
                object_qualified_name=f"{datasource_name}.{r.schema_name}.{r.object_name}",
                column_names=tuple(columns_by_object.get(r.object_name, ())),
                join_paths=tuple(
                    f"{p.source_object}->{p.target_object}"
                    for p in paths
                    if r.object_name in (p.source_object, p.target_object)
                ),
                metric_names=tuple(
                    m.name for m in metrics if r.object_name.lower() in m.sql_expression.lower()
                ),
                domain_id=None,
            )
            for r in results
        )

    def _columns_by_object(
        self, datasource_name: str, results: Sequence[SearchResult]
    ) -> dict[str, list[str]]:
        schema_names = sorted({r.schema_name for r in results})
        columns_by_object: dict[str, list[str]] = {}
        for schema_name in schema_names:
            ref = SchemaRef(datasource_name=datasource_name, schema_name=schema_name)
            for column in self._reader.read_columns(ref):
                columns_by_object.setdefault(column.object_name, []).append(column.column_name)
        return columns_by_object
