"""Services are tested with fakes. No database, no network, no container."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.entities.datasource import Datasource
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.discovery.catalog_scan_service import CatalogScanService

OBJECT = DatabaseObject(
    datasource_name="local",
    schema_name="shop",
    object_name="customer",
    object_type=ObjectType.TABLE,
    row_estimate=7,
)
COLUMN = Column(
    datasource_name="local",
    schema_name="shop",
    object_name="customer",
    column_name="c_state",
    ordinal=2,
    data_type="text",
    is_nullable=True,
)
CONSTRAINT = Constraint(
    datasource_name="local",
    schema_name="shop",
    object_name="customer",
    constraint_name="customer_pkey",
    constraint_type=ConstraintType.PRIMARY_KEY,
    definition="PRIMARY KEY (c_customer_sk)",
)


class FakeReader:
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        return [OBJECT]

    def read_columns(self, ref: SchemaRef) -> Sequence[Column]:
        return [COLUMN]

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]:
        return [CONSTRAINT]


class FakeWriter:
    def __init__(self) -> None:
        self.objects: list[DatabaseObject] = []
        self.columns: list[Column] = []
        self.constraints: list[Constraint] = []

    def write_objects(self, objects: Sequence[DatabaseObject]) -> int:
        self.objects.extend(objects)
        return len(objects)

    def write_columns(self, columns: Sequence[Column]) -> int:
        self.columns.extend(columns)
        return len(columns)

    def write_constraints(self, constraints: Sequence[Constraint]) -> int:
        self.constraints.extend(constraints)
        return len(constraints)


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


def test_scan_persists_everything_it_reads() -> None:
    writer = FakeWriter()
    ref = SchemaRef(datasource_name="local", schema_name="shop")
    report = CatalogScanService(FakeDatasources(), FakeReaderFactory(FakeReader()), writer).scan(
        ref
    )

    assert report.objects == 1
    assert report.columns == 1
    assert report.constraints == 1
    assert writer.objects == [OBJECT]
    assert writer.columns == [COLUMN]
    assert writer.constraints == [CONSTRAINT]


def test_total_counts_all_records() -> None:
    ref = SchemaRef(datasource_name="local", schema_name="shop")
    report = CatalogScanService(
        FakeDatasources(), FakeReaderFactory(FakeReader()), FakeWriter()
    ).scan(ref)
    assert report.total == 3


def test_the_reader_is_bound_to_the_refs_datasource() -> None:
    seen: list[str] = []

    class RecordingFactory(FakeReaderFactory):
        def for_datasource(self, datasource: Datasource) -> object:
            seen.append(datasource.name)
            return self._reader

    CatalogScanService(FakeDatasources(), RecordingFactory(FakeReader()), FakeWriter()).scan(
        SchemaRef(datasource_name="wh2", schema_name="shop")
    )

    assert seen == ["wh2"]
