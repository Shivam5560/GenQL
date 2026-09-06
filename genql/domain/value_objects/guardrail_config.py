"""Everything any guardrail needs, in one immutable bundle.

Every rule takes exactly this one constructor argument, which is what lets
GUARDRAILS.create(key, config=config) build all of them uniformly. A rule that
needs nothing from it (statement_kind) still accepts it, so adding a rule that
needs a new field is a change to this value object plus one new file — never a
change to how the factory constructs rules.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GuardrailConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    row_cap: int
    statement_timeout_ms: int
    allowed_objects: frozenset[str]
