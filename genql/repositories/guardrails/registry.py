"""The guardrail registry, keyed by rule name.

Mirrors the EnricherRegistry pattern from Phase 4: one file plus one
decorator adds a rule. Rules are ordered by their declared `priority`, not by
registry key, so registration order and alphabetical key order are both
irrelevant to correctness.
"""

from __future__ import annotations

from genql.domain.ports.guardrail import Guardrail
from genql.registries.registry import Registry

GUARDRAILS: Registry[Guardrail] = Registry("guardrails")
