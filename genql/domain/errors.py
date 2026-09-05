"""Typed failures. Every stage returns one of these so callers can route."""

from __future__ import annotations


class GenqlError(Exception):
    """Base class for every GenQL failure."""


class DiscoveryError(GenqlError):
    """A discovery step could not complete."""


class CatalogAccessError(DiscoveryError):
    """The target warehouse catalog could not be read."""


class ProfilingError(DiscoveryError):
    """A column could not be profiled."""

    def __init__(self, qualified_name: str, reason: str) -> None:
        super().__init__(f"failed to profile {qualified_name}: {reason}")
        self.qualified_name = qualified_name
