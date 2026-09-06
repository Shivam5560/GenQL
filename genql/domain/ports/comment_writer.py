"""Writes to the WAREHOUSE, not the semantic store — the one port in this
phase that touches a datasource other than GenQL's own. Off by default at
every call site."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.value_objects.schema_ref import SchemaRef


@runtime_checkable
class CommentWriter(Protocol):
    def write_object_comment(self, ref: SchemaRef, object_name: str, comment: str) -> None: ...

    def write_column_comment(
        self, ref: SchemaRef, object_name: str, column_name: str, comment: str
    ) -> None: ...
