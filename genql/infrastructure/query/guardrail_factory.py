"""Builds the priority-ordered rule set for one datasource.

Importing `genql.repositories.guardrails` is what populates GUARDRAILS: the
package imports each rule module for its registration decorator. Nothing here
names a rule class, so adding a rule is one file plus one decorator plus one
import line in that package — never an edit here.

The object allowlist is read once per call rather than cached: `genql discover`
adds objects between invocations, and a validation that trusts a stale
allowlist would reject freshly-catalogued tables.
"""

from __future__ import annotations

from collections.abc import Sequence

import genql.repositories.guardrails  # noqa: F401 - registration side effect
from genql.domain.ports.guardrail import Guardrail
from genql.domain.ports.object_name_reader import ObjectNameReader
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS


class GuardrailFactoryImpl:
    def __init__(self, objects: ObjectNameReader, row_cap: int, statement_timeout_ms: int) -> None:
        self._objects = objects
        self._row_cap = row_cap
        self._statement_timeout_ms = statement_timeout_ms

    def for_datasource(self, datasource_name: str) -> Sequence[Guardrail]:
        config = GuardrailConfig(
            row_cap=self._row_cap,
            statement_timeout_ms=self._statement_timeout_ms,
            allowed_objects=self._objects.read_object_names(datasource_name),
        )
        rules = [
            GUARDRAILS.create(key, config=config)
            for key in GUARDRAILS.keys()  # noqa: SIM118 - Registry, not a dict
        ]
        return sorted(rules, key=lambda rule: (rule.priority, rule.name))
