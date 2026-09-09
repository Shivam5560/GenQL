"""The ablation registry, keyed by ablation name.

It lives under `services/` rather than `repositories/` because an Ablation is
a pure value with no I/O — the same reason `genql/services/scope/registry.py`
lives there. Registry stores classes, so each ablation is an Ablation subclass
whose defaults *are* its values, and `ABLATIONS.create(key)` returns the value.

Adding an ablation is one new file plus one decorator. AblationService never
names one, which is what keeps "measure another layer" from being a code
change to the harness.
"""

from __future__ import annotations

from genql.domain.entities.ablation import Ablation
from genql.registries.registry import Registry

ABLATIONS: Registry[Ablation] = Registry("ablations")
