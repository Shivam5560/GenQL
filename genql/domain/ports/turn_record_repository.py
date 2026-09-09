from __future__ import annotations

from typing import Protocol

from genql.domain.entities.turn_record import TurnRecord


class TurnRecordRepository(Protocol):
    def append(self, record: TurnRecord) -> None: ...
    def list_for_thread(self, thread_id: str) -> tuple[TurnRecord, ...]: ...
