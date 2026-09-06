"""write_back=False never touches the CommentWriterFactory — proving that is
the whole point of the flag defaulting off."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.datasource import Datasource
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.semantic.compile_service import CompileService

OBJECT_ENRICHMENT = ObjectEnrichment(
    datasource_name="local",
    schema_name="shop",
    object_name="orders",
    description="x",
)


class FakeSearchDocumentWriter:
    def compile(self, datasource_name: str) -> int:
        return 3


class FakeEnrichmentReader:
    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]:
        return [OBJECT_ENRICHMENT]

    def read_column_enrichments(self, ref: SchemaRef) -> Sequence[ColumnEnrichment]:
        return []


class FakeCommentWriter:
    def __init__(self) -> None:
        self.object_comments: list[str] = []

    def write_object_comment(self, ref: SchemaRef, object_name: str, comment: str) -> None:
        self.object_comments.append(object_name)

    def write_column_comment(
        self, ref: SchemaRef, object_name: str, column_name: str, comment: str
    ) -> None:
        return None


class FakeCommentWriterFactory:
    def __init__(self) -> None:
        self.writer = FakeCommentWriter()
        self.calls = 0

    def for_datasource(self, datasource: Datasource) -> FakeCommentWriter:
        self.calls += 1
        return self.writer


class FakeDatasourceRepository:
    def get(self, name: str) -> Datasource:
        return Datasource(name=name, dialect="postgres", dsn_env_var="X")


def test_compile_without_write_back_never_touches_the_comment_factory() -> None:
    factory = FakeCommentWriterFactory()
    service = CompileService(
        FakeSearchDocumentWriter(), FakeEnrichmentReader(), factory, FakeDatasourceRepository()
    )

    report = service.compile("local", write_back=False)

    assert report.documents == 3
    assert report.comments_written == 0
    assert factory.calls == 0


def test_compile_with_write_back_writes_one_comment_per_object() -> None:
    factory = FakeCommentWriterFactory()
    service = CompileService(
        FakeSearchDocumentWriter(), FakeEnrichmentReader(), factory, FakeDatasourceRepository()
    )

    report = service.compile("local", write_back=True)

    assert report.comments_written == 1
    assert factory.writer.object_comments == ["orders"]
