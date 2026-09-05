from __future__ import annotations

from typing import Protocol

import pytest

from genql.registries.errors import DuplicateRegistrationError, UnknownRegistryKeyError
from genql.registries.registry import Registry


class Greeter(Protocol):
    def greet(self) -> str: ...


def test_registered_implementation_is_retrievable() -> None:
    registry: Registry[Greeter] = Registry("greeters")

    @registry.register("english")
    class English:
        def greet(self) -> str:
            return "hello"

    assert registry.get("english") is English
    assert registry.create("english").greet() == "hello"


def test_keys_are_sorted() -> None:
    registry: Registry[Greeter] = Registry("greeters")

    @registry.register("zulu")
    class Zulu:
        def greet(self) -> str:
            return "sawubona"

    @registry.register("arabic")
    class Arabic:
        def greet(self) -> str:
            return "marhaba"

    assert registry.keys() == ["arabic", "zulu"]


def test_duplicate_key_is_rejected() -> None:
    registry: Registry[Greeter] = Registry("greeters")

    @registry.register("english")
    class First:
        def greet(self) -> str:
            return "hello"

    with pytest.raises(DuplicateRegistrationError) as excinfo:

        @registry.register("english")
        class Second:
            def greet(self) -> str:
                return "hi"

    assert "greeters" in str(excinfo.value)


def test_unknown_key_lists_available_options() -> None:
    registry: Registry[Greeter] = Registry("greeters")

    @registry.register("english")
    class English:
        def greet(self) -> str:
            return "hello"

    with pytest.raises(UnknownRegistryKeyError) as excinfo:
        registry.get("klingon")

    assert "english" in str(excinfo.value)
