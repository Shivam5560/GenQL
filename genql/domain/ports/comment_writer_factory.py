from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.datasource import Datasource
from genql.domain.ports.comment_writer import CommentWriter


@runtime_checkable
class CommentWriterFactory(Protocol):
    def for_datasource(self, datasource: Datasource) -> CommentWriter: ...
