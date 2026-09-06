"""Merges semantic/<datasource>.yaml over discovered/LLM enrichment. Overlay
always wins, via each field kind's registered Enricher — going through the
registry rather than an inline `if overlay is not None` keeps the merge rule
swappable per kind later without touching this service.

Metrics have no merge step: nothing else proposes a metric, so they are
always YAML-authored and simply upserted. Rules follow that precedent exactly
— nothing else proposes an ambiguity default either, so genql_rule is written
unconditionally through RuleWriter with no Enricher involved. Join hints
become JoinPath rows with provenance=YAML, written through the existing
JoinPathWriter — a YAML join hint is not a new concept, it is another path
with a different provenance."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.enrichment_field import EnrichmentField, EnrichmentKind
from genql.domain.entities.join_path import JoinPath
from genql.domain.entities.metric import Metric
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.entities.rule import Rule
from genql.domain.entities.semantic_overlay import SemanticOverlay
from genql.domain.ports.enricher import Enricher
from genql.domain.ports.enrichment_reader import EnrichmentReader
from genql.domain.ports.enrichment_writer import EnrichmentWriter
from genql.domain.ports.join_path_writer import JoinPathWriter
from genql.domain.ports.metric_writer import MetricWriter
from genql.domain.ports.rule_writer import RuleWriter
from genql.domain.value_objects.provenance import Provenance
from genql.domain.value_objects.schema_ref import SchemaRef


class OverlayReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    objects_updated: int
    columns_updated: int
    metrics_written: int
    rules_written: int
    join_hints_written: int


class SemanticOverlayService:
    def __init__(  # noqa: PLR0913, PLR0917 - one port per overlay kind (Task 4 adds RuleWriter)
        self,
        enrichment_reader: EnrichmentReader,
        enrichment_writer: EnrichmentWriter,
        metric_writer: MetricWriter,
        rule_writer: RuleWriter,
        join_path_writer: JoinPathWriter,
        enrichers: Sequence[Enricher],
    ) -> None:
        self._reader = enrichment_reader
        self._writer = enrichment_writer
        self._metric_writer = metric_writer
        self._rule_writer = rule_writer
        self._join_path_writer = join_path_writer
        self._enrichers = {e.key: e for e in enrichers}

    def apply(self, overlay: SemanticOverlay) -> OverlayReport:
        existing_objects = {
            (e.schema_name, e.object_name): e
            for e in self._reader.read_object_enrichments(overlay.datasource)
        }
        # Loaded once per schema on first use, not once per object — most
        # overlays touch several objects in the same schema, and re-reading
        # the same schema's columns for every one of them would be wasted
        # round trips for no different result.
        existing_columns_by_schema: dict[str, dict[tuple[str, str], ColumnEnrichment]] = {}

        objects_updated = 0
        columns_updated = 0
        for qualified_key, object_overlay in overlay.objects.items():
            schema_name, object_name = qualified_key.split(".", 1)
            qn = f"{overlay.datasource}.{schema_name}.{object_name}"
            current = existing_objects.get((schema_name, object_name))

            description = self._merge(
                "description",
                qn,
                current.description if current else None,
                current.provenance if current else None,
                object_overlay.description,
            )
            alias = self._merge(
                "alias",
                qn,
                current.business_alias if current else None,
                current.provenance if current else None,
                object_overlay.business_alias,
            )
            if description is not None:
                self._writer.write_object_enrichment(
                    ObjectEnrichment(
                        datasource_name=overlay.datasource,
                        schema_name=schema_name,
                        object_name=object_name,
                        description=description.value,
                        business_alias=alias.value if alias else None,
                        provenance=description.provenance,
                        confidence=current.confidence if current else 1.0,
                        embedding=current.embedding if current else None,
                    )
                )
                objects_updated += 1

            if schema_name not in existing_columns_by_schema:
                existing_columns_by_schema[schema_name] = {
                    (ce.object_name, ce.column_name): ce
                    for ce in self._reader.read_column_enrichments(
                        SchemaRef(datasource_name=overlay.datasource, schema_name=schema_name)
                    )
                }
            existing_columns = existing_columns_by_schema[schema_name]

            column_enrichments: list[ColumnEnrichment] = []
            for column_name, column_overlay in object_overlay.columns.items():
                col_qn = f"{qn}.{column_name}"
                existing_col = existing_columns.get((object_name, column_name))
                col_description = self._merge(
                    "description",
                    col_qn,
                    existing_col.description if existing_col else None,
                    existing_col.provenance if existing_col else None,
                    column_overlay.description,
                )
                col_unit = self._merge(
                    "unit",
                    col_qn,
                    existing_col.unit if existing_col else None,
                    existing_col.provenance if existing_col else None,
                    column_overlay.unit,
                )
                col_alias = self._merge(
                    "alias",
                    col_qn,
                    existing_col.business_alias if existing_col else None,
                    existing_col.provenance if existing_col else None,
                    column_overlay.business_alias,
                )
                if col_description is not None:
                    column_enrichments.append(
                        ColumnEnrichment(
                            datasource_name=overlay.datasource,
                            schema_name=schema_name,
                            object_name=object_name,
                            column_name=column_name,
                            description=col_description.value,
                            business_alias=col_alias.value if col_alias else None,
                            unit=col_unit.value if col_unit else None,
                            provenance=col_description.provenance,
                        )
                    )
            if column_enrichments:
                columns_updated += self._writer.write_column_enrichments(column_enrichments)

        metrics = [
            Metric(
                datasource_name=overlay.datasource,
                name=m.name,
                sql_expression=m.sql_expression,
                grain=m.grain,
                unit=m.unit,
                default_filters=m.default_filters,
            )
            for m in overlay.metrics
        ]
        metrics_written = self._metric_writer.write(metrics) if metrics else 0

        rules = tuple(
            Rule(
                name=r.name,
                dimension=r.dimension,
                value=r.value,
                description=r.description,
            )
            for r in overlay.rules
        )
        rules_written = self._rule_writer.write_rules(overlay.datasource, rules) if rules else 0

        join_hints = [
            JoinPath(
                datasource_name=overlay.datasource,
                schema_name=h.source_object.split(".", 1)[0],
                source_object=h.source_object.split(".", 1)[1],
                target_object=h.target_object.split(".", 1)[1],
                path=tuple(p.split(".", 1)[1] for p in h.path),
                weight=h.weight,
                provenance=Provenance.YAML,
            )
            for h in overlay.join_hints
        ]
        join_hints_written = self._join_path_writer.write(join_hints) if join_hints else 0

        return OverlayReport(
            objects_updated=objects_updated,
            columns_updated=columns_updated,
            metrics_written=metrics_written,
            rules_written=rules_written,
            join_hints_written=join_hints_written,
        )

    def _merge(
        self,
        kind: EnrichmentKind,
        qualified_name: str,
        discovered_value: str | None,
        discovered_provenance: Provenance | None,
        overlay_value: str | None,
    ) -> EnrichmentField | None:
        discovered = (
            EnrichmentField(
                kind=kind,
                qualified_name=qualified_name,
                value=discovered_value,
                provenance=discovered_provenance or Provenance.LLM,
            )
            if discovered_value is not None
            else None
        )
        overlay = (
            EnrichmentField(
                kind=kind,
                qualified_name=qualified_name,
                value=overlay_value,
                provenance=Provenance.YAML,
            )
            if overlay_value is not None
            else None
        )
        return self._enrichers[kind].merge(discovered, overlay)
