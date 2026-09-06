"""One registered safety rule.

`check` returns the violations it found; `repair` is only ever called for a
violation this same rule reported as repairable, so an unrepairable rule's
`repair` may raise rather than pretend.

`priority` orders the rules deterministically at the factory. It exists
because alphabetical registry order would run the object allowlist before the
statement-kind check, and a DELETE deserves to be rejected for being a DELETE.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.guardrail_violation import GuardrailViolation


@runtime_checkable
class Guardrail(Protocol):
    name: str
    priority: int

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]: ...

    def repair(self, sql: str, violation: GuardrailViolation) -> str: ...
