"""The read side of JoinPathWriter — Phase 3 mined paths, Phase 5 reads them.

Filtered by object name rather than returning a whole datasource's paths:
schema linking only ever wants the paths touching the objects retrieval
actually returned.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.join_path import JoinPath


@runtime_checkable
class JoinPathReader(Protocol):
    def read_join_paths(
        self, datasource_name: str, object_names: Sequence[str]
    ) -> Sequence[JoinPath]: ...
