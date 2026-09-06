"""Mines the FK-graph route between object pairs that are not directly
FK-connected."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.join_path import JoinPath


@runtime_checkable
class JoinPathMiner(Protocol):
    def mine(self, datasource_name: str) -> Sequence[JoinPath]: ...
