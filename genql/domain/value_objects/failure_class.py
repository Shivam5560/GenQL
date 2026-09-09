"""The four failure classes the parent spec's §2 names.

A tuple plus a Literal rather than an enum, matching how AMBIGUITY_DIMENSIONS
is already declared: the values are written by hand in YAML fixtures, so they
need to be plain strings at the boundary, and the Literal is what makes a typo
in a fixture a validation error instead of a silently uncounted case.
"""

from __future__ import annotations

from typing import Literal

FailureClass = Literal[
    "ambiguous_intent",
    "absent_business_knowledge",
    "physical_modelling_variation",
    "context_sensitivity",
]

FAILURE_CLASSES: tuple[FailureClass, ...] = (
    "ambiguous_intent",
    "absent_business_knowledge",
    "physical_modelling_variation",
    "context_sensitivity",
)
