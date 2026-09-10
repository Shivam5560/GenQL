"""0014 gives a turn somewhere to keep its pipeline trail.

Two properties are worth a real database rather than a unit test. The column is
NOT NULL with a server default, and what matters is that an insert written by
code which has never heard of `stages_json` — every turn already in the table —
still succeeds and reads back as an empty trail. The other is that a real trail
survives the JSON column round-trip with its order and its missing details
intact, since order is the whole point of a trail.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, inspect, text

from genql.domain.entities.stage_event import StageEvent
from genql.domain.entities.turn_record import TurnRecord
from genql.repositories.query.sqlalchemy_turn_record_repository import (
    SqlAlchemyTurnRecordRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def thread(migrated_engine: Engine) -> Iterator[str]:
    thread_id = "t-mig14"
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_thread (thread_id, user_id, datasource_name, title) "
                "VALUES (:t, 'u-mig14', 'local', 'a question')"
            ),
            {"t": thread_id},
        )
    yield thread_id
    with migrated_engine.begin() as conn:
        conn.execute(text("DELETE FROM genql.genql_turn WHERE thread_id = :t"), {"t": thread_id})
        conn.execute(text("DELETE FROM genql.genql_thread WHERE thread_id = :t"), {"t": thread_id})


def test_upgrade_adds_the_stages_column(migrated_engine: Engine) -> None:
    columns = {
        c["name"] for c in inspect(migrated_engine).get_columns("genql_turn", schema="genql")
    }

    assert "stages_json" in columns


def test_a_row_written_without_a_trail_reads_back_as_an_empty_one(
    migrated_engine: Engine, thread: str
) -> None:
    """The pre-migration insert, verbatim: no stages_json, and no failure."""
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_turn (turn_id, thread_id, sequence, question) "
                "VALUES ('tr-mig14-old', :t, 0, 'an older question')"
            ),
            {"t": thread},
        )
        stored = conn.execute(
            text("SELECT stages_json FROM genql.genql_turn WHERE turn_id = 'tr-mig14-old'")
        ).scalar_one()

    assert (json.loads(stored) if isinstance(stored, str) else stored) == []


def test_a_turns_stage_trail_survives_the_repository_round_trip(
    migrated_engine: Engine, thread: str
) -> None:
    repository = SqlAlchemyTurnRecordRepository(migrated_engine)
    repository.append(
        TurnRecord(
            turn_id="tr-mig14-new",
            thread_id=thread,
            sequence=0,
            question="how many rows?",
            validated_sql="SELECT 1",
            stages=(
                StageEvent(stage="schema_linking", status="completed", detail="10 objects linked"),
                StageEvent(stage="ambiguity_gate", status="paused", detail="which quarter?"),
                StageEvent(stage="guarded_execution", status="completed"),
            ),
            created_at=datetime.now(UTC),
        )
    )

    (record,) = repository.list_for_thread(thread)

    assert [(s.stage, s.status, s.detail) for s in record.stages] == [
        ("schema_linking", "completed", "10 objects linked"),
        ("ambiguity_gate", "paused", "which quarter?"),
        ("guarded_execution", "completed", None),
    ]


def test_a_turn_recorded_without_stages_round_trips_as_an_empty_trail(
    migrated_engine: Engine, thread: str
) -> None:
    """What the blocking endpoint writes: it has no stage events to record,
    and that is not a failure to distinguish from one."""
    repository = SqlAlchemyTurnRecordRepository(migrated_engine)
    repository.append(
        TurnRecord(
            turn_id="tr-mig14-blocking",
            thread_id=thread,
            sequence=0,
            question="asked without streaming",
            created_at=datetime.now(UTC),
        )
    )

    (record,) = repository.list_for_thread(thread)

    assert record.stages == ()
