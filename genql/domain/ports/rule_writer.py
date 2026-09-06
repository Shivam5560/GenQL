from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.rule import Rule


@runtime_checkable
class RuleWriter(Protocol):
    """Returns the count written, matching MetricWriter.write — the overlay
    report prints it, so a None return would make the report lie."""

    def write_rules(self, datasource_name: str, rules: tuple[Rule, ...]) -> int: ...
