from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.join_path import JoinPath


class NullJoinPathReader:
    """JoinPathReader that has mined nothing."""

    def read_join_paths(
        self, datasource_name: str, object_names: Sequence[str]
    ) -> Sequence[JoinPath]:
        return ()
