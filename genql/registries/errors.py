"""Errors raised by registries."""

from __future__ import annotations


class RegistryError(Exception):
    """Base class for registry failures."""


class DuplicateRegistrationError(RegistryError):
    def __init__(self, registry_name: str, key: str) -> None:
        super().__init__(f"{key!r} is already registered in registry {registry_name!r}")


class UnknownRegistryKeyError(RegistryError):
    def __init__(self, registry_name: str, key: str, available: list[str]) -> None:
        options = ", ".join(available) or "<empty>"
        super().__init__(
            f"{key!r} is not registered in registry {registry_name!r}. Available: {options}"
        )
