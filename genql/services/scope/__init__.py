"""Registers every scope resolver with SCOPE_RESOLVERS."""

from __future__ import annotations

from genql.services.scope.default_scope_resolver import DefaultScopeResolver
from genql.services.scope.explicit_scope_resolver import ExplicitScopeResolver

__all__ = ["DefaultScopeResolver", "ExplicitScopeResolver"]
