"""Persists mined join paths into the semantic store."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.join_path import JoinPath


@runtime_checkable
class JoinPathWriter(Protocol):
    def write(self, paths: Sequence[JoinPath]) -> int: ...
