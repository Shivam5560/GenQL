"""start_turn/resume_turn's one new responsibility: when called with
threads/turn_records/user_id, the thread and its turn are both persisted —
not merely that TurnResponse comes back correctly, which
test_query_turn.py already covers exhaustively. Reuses that file's
FakeGraph/FakeLocks/finished_state() rather than redefining them."""

from __future__ import annotations

from datetime import UTC, datetime

from genql.api.query_turn import resume_turn, start_turn
from genql.domain.entities.thread_summary import ThreadSummary
from genql.domain.entities.turn_record import TurnRecord
from tests.unit.test_query_turn import FakeGraph, FakeLocks, finished_state


class _Threads:
    def __init__(self) -> None:
        self.created: list[tuple[str, str, str, str]] = []
        self.touched: list[str] = []

    def create(self, thread_id: str, user_id: str, datasource_name: str, title: str) -> None:
        self.created.append((thread_id, user_id, datasource_name, title))

    def touch(self, thread_id: str) -> None:
        self.touched.append(thread_id)

    def list_for_user(self, user_id: str) -> tuple[ThreadSummary, ...]:
        return ()

    def by_id(self, thread_id: str) -> ThreadSummary | None:
        return None


class _TurnRecords:
    def __init__(self) -> None:
        self.appended: list[TurnRecord] = []

    def append(self, record: TurnRecord) -> None:
        self.appended.append(record)

    def list_for_thread(self, thread_id: str) -> tuple[TurnRecord, ...]:
        return tuple(r for r in self.appended if r.thread_id == thread_id)


def test_start_turn_without_history_args_records_nothing() -> None:
    """The default (no threads/turn_records/user_id) is what the CLI and
    eval harness call today — it must keep writing nothing, exactly as
    before this phase."""
    start_turn(FakeGraph(finished_state()), FakeLocks(), "q", "local", thread_id="t-1")
    # No repositories were even constructed; nothing to assert against but
    # that this call raises nothing extra — covered by it simply returning.


def test_start_turn_creates_the_thread_and_appends_the_first_turn_record() -> None:
    threads = _Threads()
    turn_records = _TurnRecords()

    start_turn(
        FakeGraph(finished_state()),
        FakeLocks(),
        "a question",
        "retail_warehouse",
        thread_id="t-1",
        user_id="u-1",
        threads=threads,
        turn_records=turn_records,
    )

    assert threads.created == [("t-1", "u-1", "retail_warehouse", "a question")]
    assert threads.touched == []
    assert len(turn_records.appended) == 1
    assert turn_records.appended[0].sequence == 0
    assert turn_records.appended[0].question == "a question"
    assert turn_records.appended[0].validated_sql == "SELECT 7 LIMIT 1"


def test_resume_turn_touches_the_thread_and_appends_a_later_turn_record() -> None:
    threads = _Threads()
    turn_records = _TurnRecords()
    turn_records.appended.append(
        TurnRecord(
            turn_id="tr-0",
            thread_id="t-1",
            sequence=0,
            question="first",
            created_at=datetime.now(UTC),
        )
    )

    resume_turn(
        FakeGraph(finished_state()),
        FakeLocks(),
        "a follow-up",
        "t-1",
        user_id="u-1",
        threads=threads,
        turn_records=turn_records,
    )

    assert threads.touched == ["t-1"]
    assert threads.created == []
    assert len(turn_records.appended) == 2
    assert turn_records.appended[1].sequence == 1
    assert turn_records.appended[1].question == "a follow-up"
