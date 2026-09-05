from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.column import Column
from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.errors import ProfilingError
from genql.services.discovery.profiling_service import ProfilingService

COLUMNS = [
    Column(
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
    def read_objects(self, schema: str) -> Sequence[DatabaseObject]:
        return []

    def read_columns(self, schema: str) -> Sequence[Column]:
        return COLUMNS

    def read_constraints(self, schema: str) -> Sequence[Constraint]:
        return []


class FakeProfileReader:
    def profile_column(self, column: Column, sample_limit: int) -> ColumnProfile:
        if column.column_name == "c_broken":
            raise ProfilingError(column.qualified_name, "type not comparable")
        return ColumnProfile(
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


def test_a_failing_column_does_not_abort_the_run() -> None:
    writer = FakeProfileWriter()
    service = ProfilingService(FakeCatalog(), FakeProfileReader(), writer)

    written = service.profile("shop", sample_limit=5)

    assert written == 1
    assert [p.column_name for p in writer.written] == ["c_state"]


def test_skipped_columns_are_reported() -> None:
    service = ProfilingService(FakeCatalog(), FakeProfileReader(), FakeProfileWriter())
    service.profile("shop", sample_limit=5)
    assert service.skipped == ["shop.customer.c_broken"]
