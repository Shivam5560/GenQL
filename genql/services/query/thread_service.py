"""The read side of thread history. Writing happens inline in
start_turn/resume_turn (Task 12), not here, so a turn's persistence can
never race its own execution."""

from __future__ import annotations

from genql.domain.entities.thread_summary import ThreadSummary
from genql.domain.entities.turn_record import TurnRecord
from genql.domain.errors import ThreadOwnershipError, UnknownThreadError
from genql.domain.ports.thread_repository import ThreadRepository
from genql.domain.ports.turn_record_repository import TurnRecordRepository


class ThreadService:
    def __init__(self, threads: ThreadRepository, turns: TurnRecordRepository) -> None:
        self._threads = threads
        self._turns = turns

    def list_threads(self, user_id: str) -> tuple[ThreadSummary, ...]:
        return self._threads.list_for_user(user_id)

    def get_thread(
        self, user_id: str, thread_id: str
    ) -> tuple[ThreadSummary, tuple[TurnRecord, ...]]:
        summary = self._threads.by_id(thread_id)
        if summary is None:
            raise UnknownThreadError(thread_id)
        if summary.user_id != user_id:
            raise ThreadOwnershipError(f"thread {thread_id!r} does not belong to {user_id!r}")
        return summary, self._turns.list_for_thread(thread_id)
