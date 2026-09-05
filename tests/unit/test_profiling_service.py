from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.column import Column
from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.entities.datasource import Datasource
from genql.domain.errors import ProfilingError
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.discovery.profiling_service import ProfilingService

COLUMNS = [
    Column(
        datasource_name="local",
        schema_name="shop",
        object_name="customer",
        column_name=name,
        ordinal=i + 1,
        data_type="text",
        is_nullable=True,
    )
    for i, name in enumerate(["c_state", "c_broken"])
]


class FakeCatalog:
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        return []

    def read_columns(self, ref: SchemaRef) -> Sequence[Column]:
        return COLUMNS

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]:
        return []


class FakeProfileReader:
    def profile_column(self, column: Column, sample_limit: int) -> ColumnProfile:
        if column.column_name == "c_broken":
            raise ProfilingError(column.qualified_name, "type not comparable")
        return ColumnProfile(
            datasource_name=column.datasource_name,
            schema_name=column.schema_name,
            object_name=column.object_name,
            column_name=column.column_name,
            distinct_count=13,
            null_fraction=0.0,
            sample_values=("CA", "OR"),
        )


class FakeProfileWriter:
    def __init__(self) -> None:
        self.written: list[ColumnProfile] = []

    def write_profiles(self, profiles: Sequence[ColumnProfile]) -> int:
        self.written.extend(profiles)
        return len(profiles)


class FakeDatasources:
    def add(self, datasource: Datasource) -> None: ...

    def get(self, name: str) -> Datasource:
        return Datasource(name=name, dialect="postgres", dsn_env_var="X")

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        return [self.get("local")]

    def remove(self, name: str) -> None: ...


class FakeReaderFactory:
    def __init__(self, reader: object) -> None:
        self._reader = reader

    def for_datasource(self, datasource: Datasource) -> object:
        return self._reader


def test_a_failing_column_does_not_abort_the_run() -> None:
    writer = FakeProfileWriter()
    service = ProfilingService(
        FakeDatasources(),
        FakeReaderFactory(FakeCatalog()),
        FakeReaderFactory(FakeProfileReader()),
        writer,
    )

    ref = SchemaRef(datasource_name="local", schema_name="shop")
    written = service.profile(ref, sample_limit=5)

    assert written == 1
    assert [p.column_name for p in writer.written] == ["c_state"]


def test_skipped_columns_are_reported() -> None:
    service = ProfilingService(
        FakeDatasources(),
        FakeReaderFactory(FakeCatalog()),
        FakeReaderFactory(FakeProfileReader()),
        FakeProfileWriter(),
    )
    ref = SchemaRef(datasource_name="local", schema_name="shop")
    service.profile(ref, sample_limit=5)
    assert service.skipped == ["local.shop.customer.c_broken"]


def test_the_reader_is_bound_to_the_refs_datasource() -> None:
    seen: list[str] = []

    class RecordingFactory(FakeReaderFactory):
        def for_datasource(self, datasource: Datasource) -> object:
            seen.append(datasource.name)
            return self._reader

    ProfilingService(
        FakeDatasources(),
        RecordingFactory(FakeCatalog()),
        RecordingFactory(FakeProfileReader()),
        FakeProfileWriter(),
    ).profile(SchemaRef(datasource_name="wh2", schema_name="shop"), sample_limit=5)

    assert seen == ["wh2", "wh2"]
