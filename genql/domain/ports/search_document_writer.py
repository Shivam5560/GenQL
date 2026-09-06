from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SearchDocumentWriter(Protocol):
    def compile(self, datasource_name: str) -> int: ...
