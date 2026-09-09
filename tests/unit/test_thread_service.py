"""ThreadService's one piece of logic: a thread that exists but belongs to
someone else is indistinguishable, from the caller's side, from a thread
that never existed — both raise, never a silent None."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from genql.domain.entities.thread_summary import ThreadSummary
from genql.domain.entities.turn_record import TurnRecord
from genql.domain.errors import ThreadOwnershipError, UnknownThreadError
from genql.services.query.thread_service import ThreadService

_NOW = datetime(2026, 9, 9, tzinfo=UTC)


class _Threads:
    def __init__(self, summaries: dict[str, ThreadSummary]) -> None:
        self._summaries = summaries

    def create(self, thread_id: str, user_id: str, datasource_name: str, title: str) -> None:
        raise NotImplementedError("ThreadService never writes")

    def touch(self, thread_id: str) -> None:
        raise NotImplementedError("ThreadService never writes")

    def list_for_user(self, user_id: str) -> tuple[ThreadSummary, ...]:
        return tuple(s for s in self._summaries.values() if s.user_id == user_id)

    def by_id(self, thread_id: str) -> ThreadSummary | None:
        return self._summaries.get(thread_id)


class _Turns:
    def __init__(self, records: dict[str, tuple[TurnRecord, ...]]) -> None:
        self._records = records

    def append(self, record: TurnRecord) -> None:
        raise NotImplementedError("ThreadService never writes")

    def list_for_thread(self, thread_id: str) -> tuple[TurnRecord, ...]:
        return self._records.get(thread_id, ())


def _summary(thread_id: str, user_id: str) -> ThreadSummary:
    return ThreadSummary(
        thread_id=thread_id,
        user_id=user_id,
        datasource_name="retail_warehouse",
        title="a question",
        created_at=_NOW,
        last_active_at=_NOW,
    )


def test_list_threads_returns_only_the_callers_threads() -> None:
    threads = _Threads({"t-1": _summary("t-1", "u-1"), "t-2": _summary("t-2", "u-2")})
    service = ThreadService(threads, _Turns({}))

    result = service.list_threads("u-1")

    assert [t.thread_id for t in result] == ["t-1"]


def test_get_thread_returns_summary_and_turns_for_the_owner() -> None:
    turn = TurnRecord(turn_id="tr-1", thread_id="t-1", sequence=0, question="q", created_at=_NOW)
    threads = _Threads({"t-1": _summary("t-1", "u-1")})
    service = ThreadService(threads, _Turns({"t-1": (turn,)}))

    summary, turns = service.get_thread("u-1", "t-1")

    assert summary.thread_id == "t-1"
    assert turns == (turn,)


def test_get_thread_raises_for_an_unknown_thread() -> None:
    service = ThreadService(_Threads({}), _Turns({}))

    with pytest.raises(UnknownThreadError):
        service.get_thread("u-1", "t-missing")


def test_get_thread_raises_ownership_error_for_someone_elses_thread() -> None:
    threads = _Threads({"t-1": _summary("t-1", "u-2")})
    service = ThreadService(threads, _Turns({}))

    with pytest.raises(ThreadOwnershipError):
        service.get_thread("u-1", "t-1")
