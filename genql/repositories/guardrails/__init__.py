"""The registered guardrail rules.

Importing this package is what populates GUARDRAILS: each module below
decorates its class into the registry. Adding a rule is one new file plus one
import line here — no factory, service, or call site changes.
"""

from genql.repositories.guardrails.bind_parameter_guardrail import BindParameterGuardrail
from genql.repositories.guardrails.forbidden_function_guardrail import ForbiddenFunctionGuardrail
from genql.repositories.guardrails.limit_injection_guardrail import LimitInjectionGuardrail
from genql.repositories.guardrails.object_allowlist_guardrail import ObjectAllowlistGuardrail
from genql.repositories.guardrails.statement_kind_guardrail import StatementKindGuardrail
from genql.repositories.guardrails.statement_timeout_guardrail import StatementTimeoutGuardrail
from genql.repositories.guardrails.surrogate_key_date_guardrail import SurrogateKeyDateGuardrail

__all__ = [
    "BindParameterGuardrail",
    "ForbiddenFunctionGuardrail",
    "LimitInjectionGuardrail",
    "ObjectAllowlistGuardrail",
    "StatementKindGuardrail",
    "StatementTimeoutGuardrail",
    "SurrogateKeyDateGuardrail",
]
