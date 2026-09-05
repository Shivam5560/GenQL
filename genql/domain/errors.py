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


class UnknownDiscoveryStepError(DiscoveryError):
    """`--start-from` named a step that is not part of the pipeline."""

    def __init__(self, step_name: str, available: list[str]) -> None:
        options = ", ".join(available) or "<empty>"
        super().__init__(f"{step_name!r} is not a known discovery step. Available: {options}")
        self.step_name = step_name
