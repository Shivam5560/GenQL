"""One rule's complaint about one statement.

`repairable` is the rule's own claim about its own violation, which is what
lets StaticValidationService attempt a repair without knowing anything about
the rule that reported it. Default False: a new rule is unrepairable until it
says otherwise.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GuardrailViolation(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_name: str
    message: str
    repairable: bool = False
