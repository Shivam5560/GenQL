"""A pure, semantics-preserving sqlglot AST transform.

Returns an expression in every case — never None, never raising, including on
input it cannot handle, where it returns what it was given. `OptimizationService`
decides whether a rule fired by comparing the *rendered SQL* before and after,
not by object identity: sqlglot's own optimizer passes mutate the tree in place
and hand back the same object, so an identity check would report every rule as
a no-op.

Importing sqlglot here does not breach the domain-is-pure contract:
`.importlinter` forbids sqlalchemy, psycopg, neo4j, graphdatascience, and
httpx, and sqlglot is a pure parser with no I/O — the same reasoning
`StaticValidationService` records for importing it from `services/`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlglot import exp


@runtime_checkable
class RewriteRule(Protocol):
    name: str

    def apply(self, expression: exp.Expression) -> exp.Expression: ...
