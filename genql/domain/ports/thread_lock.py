"""One thread, one in-flight turn.

A second `genql query` on the same thread_id waits rather than corrupting
checkpoint state. The lock is a context manager rather than an
acquire/release pair so that release is structurally guaranteed by the
`with` block instead of by every caller remembering a `finally`.

ThreadLockFactory exists because the lock's key — the thread_id — is runtime
data unknown when the container is constructed. That is the same shape
GuardrailFactory.for_datasource and QueryExecutorFactory.for_datasource
already use for per-key resources.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, runtime_checkable


@runtime_checkable
class ThreadLock(Protocol):
    def __enter__(self) -> None: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


@runtime_checkable
class ThreadLockFactory(Protocol):
    def for_thread(self, thread_id: str) -> ThreadLock: ...
