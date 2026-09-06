"""Drops whatever connection a process is holding for one datasource.

Removing a datasource deletes its row, but the process doing the removing may
still hold a pooled Engine keyed by that name — and a later `add` of the same
name would then reuse a connection to the old target. A service may not import
infrastructure, so it depends on this port; the composition root passes
DatasourceEngineProvider, which satisfies it structurally.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EngineInvalidator(Protocol):
    def invalidate(self, name: str) -> None: ...
