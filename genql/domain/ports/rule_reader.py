from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.rule import Rule


@runtime_checkable
class RuleReader(Protocol):
    def read_rules(self, datasource_name: str) -> tuple[Rule, ...]: ...
