"""Name-keyed registry.

Adding an implementation is one file plus one decorator. No existing call site
changes, which is the open/closed principle made operational.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Generic, TypeVar

from genql.registries.errors import DuplicateRegistrationError, UnknownRegistryKeyError

T = TypeVar("T")


# UP046 (PEP 695 `class Registry[T]:`) is deliberately not applied: that syntax
# interacts with the pydantic.mypy plugin and dependency-injector in ways not
# worth discovering here. See final-review.md item 1.
class Registry(Generic[T]):  # noqa: UP046
    def __init__(self, name: str) -> None:
        self._name = name
        self._items: dict[str, type[T]] = {}

    @property
    def name(self) -> str:
        return self._name

    def register(self, key: str) -> Callable[[type[T]], type[T]]:
        def decorator(implementation: type[T]) -> type[T]:
            if key in self._items:
                raise DuplicateRegistrationError(self._name, key)
            self._items[key] = implementation
            return implementation

        return decorator

    def get(self, key: str) -> type[T]:
        try:
            return self._items[key]
        except KeyError:
            raise UnknownRegistryKeyError(self._name, key, self.keys()) from None

    def create(self, key: str, *args: Any, **kwargs: Any) -> T:
        return self.get(key)(*args, **kwargs)

    def keys(self) -> list[str]:
        return sorted(self._items)
