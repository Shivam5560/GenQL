"""The registered guardrail rules.

Importing this package is what populates GUARDRAILS: each module below
decorates its class into the registry. Adding a rule is one new file plus one
import line here — no factory, service, or call site changes.
"""

from genql.repositories.guardrails.forbidden_function_guardrail import ForbiddenFunctionGuardrail
from genql.repositories.guardrails.statement_kind_guardrail import StatementKindGuardrail

__all__ = [
    "ForbiddenFunctionGuardrail",
    "StatementKindGuardrail",
]
