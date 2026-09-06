"""Produces the natural-language plan, grounded on schema links."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink


@runtime_checkable
class Planner(Protocol):
    def plan(self, question: str, links: tuple[SchemaLink, ...]) -> QueryPlan: ...
