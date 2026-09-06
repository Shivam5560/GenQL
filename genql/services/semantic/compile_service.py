"""Builds genql_search_document for a whole datasource, then optionally
writes descriptions back to the warehouse as COMMENT ON. write_back stays
off by default — this is the one path in this phase that writes to a
datasource other than GenQL's own."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.ports.comment_writer_factory import CommentWriterFactory
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.enrichment_reader import EnrichmentReader
from genql.domain.ports.search_document_writer import SearchDocumentWriter
from genql.domain.value_objects.schema_ref import SchemaRef


class CompileReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    documents: int
    comments_written: int


class CompileService:
    def __init__(
        self,
        search_document_writer: SearchDocumentWriter,
        enrichment_reader: EnrichmentReader,
        comment_writer_factory: CommentWriterFactory,
        datasource_repository: DatasourceRepository,
    ) -> None:
        self._writer = search_document_writer
        self._enrichment_reader = enrichment_reader
        self._comment_writer_factory = comment_writer_factory
        self._datasource_repository = datasource_repository

    def compile(self, datasource_name: str, write_back: bool = False) -> CompileReport:
        documents = self._writer.compile(datasource_name)
        comments_written = 0
        if write_back:
            datasource = self._datasource_repository.get(datasource_name)
            comment_writer = self._comment_writer_factory.for_datasource(datasource)
            object_enrichments = self._enrichment_reader.read_object_enrichments(datasource_name)
            for enrichment in object_enrichments:
                ref = SchemaRef(datasource_name=datasource_name, schema_name=enrichment.schema_name)
                comment_writer.write_object_comment(
                    ref, enrichment.object_name, enrichment.description
                )
                comments_written += 1
            for schema_name in {e.schema_name for e in object_enrichments}:
                ref = SchemaRef(datasource_name=datasource_name, schema_name=schema_name)
                for col in self._enrichment_reader.read_column_enrichments(ref):
                    comment_writer.write_column_comment(
                        ref, col.object_name, col.column_name, col.description
                    )
                    comments_written += 1
        return CompileReport(documents=documents, comments_written=comments_written)
