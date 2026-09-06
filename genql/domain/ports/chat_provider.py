"""One grounded LLM call, returning a validated Pydantic model rather than
prose to parse — a profiling or naming failure is a ValidationError the
caller catches, not a silent mis-parse."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class ChatProvider(Protocol):
    def complete(self, prompt: str, response_schema: type[T]) -> T: ...
