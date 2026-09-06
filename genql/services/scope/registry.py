"""Scope resolvers, keyed by name.

Phase 5 registers an LLM-backed resolver here. `Settings.scope_resolver`
selects one; no call site names a resolver class.
"""

from __future__ import annotations

from genql.domain.ports.scope_resolver import ScopeResolver
from genql.registries.registry import Registry

SCOPE_RESOLVERS: Registry[ScopeResolver] = Registry("scope_resolvers")
