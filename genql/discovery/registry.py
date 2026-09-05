"""The registry of discovery steps.

A new step is one file plus one decorator.
"""

from __future__ import annotations

from genql.domain.ports.discovery_step import DiscoveryStep
from genql.registries.registry import Registry

DISCOVERY_STEPS: Registry[DiscoveryStep] = Registry("discovery_steps")
