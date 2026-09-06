"""Grounds one schema's objects and columns in an LLM-generated description,
one call per object — the grounding context (columns, types, foreign keys,
sample values) is shared across that object's whole column list, so this
stays one call, not one call per object plus one per column."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.column import Column
from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.errors import ChatProviderError, EmbeddingProviderError, EnrichmentError
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.embedding_provider import EmbeddingProvider
from genql.domain.ports.enrichment_writer import EnrichmentWriter
from genql.domain.ports.semantic_catalog_reader import SemanticCatalogReader
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.schema_ref import SchemaRef


class _ColumnProfileResponse(BaseModel):
    column_name: str
    description: str
    business_alias: str | None = None
    unit: str | None = None


class _ObjectProfileResponse(BaseModel):
    description: str
    business_alias: str | None = None
    columns: list[_ColumnProfileResponse]


class ObjectProfilingReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    objects_profiled: int
    columns_profiled: int


class ObjectProfilingService:
    def __init__(
        self,
        reader: SemanticCatalogReader,
        chat: ChatProvider,
        embedder: EmbeddingProvider,
        writer: EnrichmentWriter,
    ) -> None:
        self._reader = reader
        self._chat = chat
        self._embedder = embedder
        self._writer = writer

    def profile(self, ref: SchemaRef, sample_limit: int) -> ObjectProfilingReport:
        objects = self._reader.read_objects(ref)
        constraints = self._reader.read_constraints(ref)
        columns = self._reader.read_columns(ref)
        profiles = {p.column_name: p for p in self._reader.read_column_profiles(ref)}

        objects_profiled = 0
        columns_profiled = 0
        for obj in objects:
            object_columns = [c for c in columns if c.object_name == obj.object_name]
            object_constraints = [c for c in constraints if c.object_name == obj.object_name]
            prompt = self._build_prompt(
                obj, object_columns, object_constraints, profiles, sample_limit
            )
            try:
                response = self._chat.complete(prompt, _ObjectProfileResponse)
                embedding = self._embedder.embed([response.description])[0]
            except (ChatProviderError, EmbeddingProviderError) as exc:
                raise EnrichmentError(f"failed to profile {obj.qualified_name}: {exc}") from exc

            self._writer.write_object_enrichment(
                ObjectEnrichment(
                    datasource_name=obj.datasource_name,
                    schema_name=obj.schema_name,
                    object_name=obj.object_name,
                    description=response.description,
                    business_alias=response.business_alias,
                    embedding=embedding,
                )
            )
            column_enrichments = [
                ColumnEnrichment(
                    datasource_name=obj.datasource_name,
                    schema_name=obj.schema_name,
                    object_name=obj.object_name,
                    column_name=col.column_name,
                    description=col.description,
                    business_alias=col.business_alias,
                    unit=col.unit,
                )
                for col in response.columns
            ]
            self._writer.write_column_enrichments(column_enrichments)
            objects_profiled += 1
            columns_profiled += len(column_enrichments)

        return ObjectProfilingReport(
            objects_profiled=objects_profiled, columns_profiled=columns_profiled
        )

    def _build_prompt(
        self,
        obj: DatabaseObject,
        object_columns: Sequence[Column],
        object_constraints: Sequence[Constraint],
        profiles: Mapping[str, ColumnProfile],
        sample_limit: int,
    ) -> str:
        column_lines = []
        for col in object_columns:
            profile = profiles.get(col.column_name)
            samples = list(profile.sample_values[:sample_limit]) if profile else []
            column_lines.append(f"- {col.column_name} ({col.data_type}); samples: {samples}")
        fk_lines = [
            f"- {', '.join(c.column_names)} -> {c.referenced_object_name}"
            for c in object_constraints
            if c.constraint_type == ConstraintType.FOREIGN_KEY
        ]
        return (
            f"Object: {obj.object_name} ({obj.object_type.value})\n"
            "Columns:\n" + "\n".join(column_lines) + "\n"
            "Foreign keys:\n" + "\n".join(fk_lines) + "\n"
            "Write a one-sentence plain-English description of this object, a short business "
            "alias, and for each column a one-sentence description with an optional unit. "
            "Ground every claim in the column names, types, and sample values given above — do "
            "not invent business meaning the data does not support."
        )
