"""The registered guardrail rules.

Importing this package is what populates GUARDRAILS: each module below
decorates its class into the registry. Adding a rule is one new file plus one
import line here — no factory, service, or call site changes.
"""

from genql.repositories.guardrails.forbidden_function_guardrail import ForbiddenFunctionGuardrail
from genql.repositories.guardrails.limit_injection_guardrail import LimitInjectionGuardrail
from genql.repositories.guardrails.object_allowlist_guardrail import ObjectAllowlistGuardrail
from genql.repositories.guardrails.statement_kind_guardrail import StatementKindGuardrail
from genql.repositories.guardrails.statement_timeout_guardrail import StatementTimeoutGuardrail

__all__ = [
    "ForbiddenFunctionGuardrail",
    "LimitInjectionGuardrail",
    "ObjectAllowlistGuardrail",
    "StatementKindGuardrail",
    "StatementTimeoutGuardrail",
]
