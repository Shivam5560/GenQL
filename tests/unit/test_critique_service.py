"""The deterministic column check runs with no ChatProvider involved — DummyChat
below records whether it was ever called, and the pure-deterministic tests
assert it was not. The one merge test proves deterministic and model-found
defects both survive onto the same CritiqueReport."""

from __future__ import annotations

from pydantic import BaseModel

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.services.query.critique_service import CritiqueService

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE_A = SqlCandidate(sql="SELECT o.id FROM shop.orders o LIMIT 1", plan=PLAN)
CANDIDATE_B = SqlCandidate(sql="SELECT o.bogus_col FROM shop.orders o LIMIT 1", plan=PLAN)
LINKS = (SchemaLink(object_qualified_name="local.shop.orders", column_names=("id", "total")),)


class RecordingChatProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        self.calls += 1
        return response_schema.model_validate(self.payload)


def _batch(reports: list[dict[str, object]]) -> dict[str, object]:
    return {"reports": reports}


def test_a_clean_candidate_has_no_deterministic_defects() -> None:
    chat = RecordingChatProvider(_batch([{"candidate_index": 0, "defects": [], "score": 0.9}]))

    reports = CritiqueService(chat).critique(
        PLAN, (CANDIDATE_A,), ("SELECT o.id FROM local.shop.orders o LIMIT 1",), LINKS
    )

    assert reports[0].defects == ()
    assert reports[0].score == 0.9


def test_an_unknown_column_becomes_a_fatal_deterministic_defect() -> None:
    chat = RecordingChatProvider(_batch([{"candidate_index": 0, "defects": [], "score": 0.1}]))

    reports = CritiqueService(chat).critique(
        PLAN, (CANDIDATE_B,), ("SELECT o.bogus_col FROM local.shop.orders o LIMIT 1",), LINKS
    )

    assert any(d.severity == "fatal" for d in reports[0].defects)


def test_the_deterministic_check_makes_no_model_call() -> None:
    """It is pure sqlglot parsing against SchemaLink.column_names — asserted by
    checking the chat provider directly, independent of critique()'s own model
    call for join/plan-alignment judgment."""
    chat = RecordingChatProvider(_batch([]))

    CritiqueService(chat)._deterministic_defects(  # noqa: SLF001 - unit-testing the pure check directly
        "SELECT o.bogus_col FROM local.shop.orders o LIMIT 1", LINKS
    )

    assert chat.calls == 0


def test_model_found_defects_and_deterministic_defects_both_survive() -> None:
    chat = RecordingChatProvider(
        _batch(
            [
                {
                    "candidate_index": 0,
                    "defects": [
                        {"dimension": "grain", "severity": "repairable", "message": "wrong grain"}
                    ],
                    "score": 0.4,
                }
            ]
        )
    )

    reports = CritiqueService(chat).critique(
        PLAN, (CANDIDATE_B,), ("SELECT o.bogus_col FROM local.shop.orders o LIMIT 1",), LINKS
    )

    severities = {d.severity for d in reports[0].defects}
    assert severities == {"fatal", "repairable"}


def test_exactly_one_model_call_regardless_of_candidate_count() -> None:
    chat = RecordingChatProvider(
        _batch(
            [
                {"candidate_index": 0, "defects": [], "score": 0.5},
                {"candidate_index": 1, "defects": [], "score": 0.6},
            ]
        )
    )

    CritiqueService(chat).critique(
        PLAN,
        (CANDIDATE_A, CANDIDATE_A),
        ("SELECT o.id FROM local.shop.orders o LIMIT 1",) * 2,
        LINKS,
    )

    assert chat.calls == 1


def test_a_candidate_the_model_omitted_scores_zero_with_no_extra_defects() -> None:
    chat = RecordingChatProvider(_batch([{"candidate_index": 0, "defects": [], "score": 0.5}]))

    reports = CritiqueService(chat).critique(
        PLAN,
        (CANDIDATE_A, CANDIDATE_A),
        ("SELECT o.id FROM local.shop.orders o LIMIT 1",) * 2,
        LINKS,
    )

    assert reports[1].score == 0.0
    assert reports[1].defects == ()


def test_reports_preserve_candidate_order() -> None:
    chat = RecordingChatProvider(
        _batch(
            [
                {"candidate_index": 1, "defects": [], "score": 0.9},
                {"candidate_index": 0, "defects": [], "score": 0.1},
            ]
        )
    )

    reports = CritiqueService(chat).critique(
        PLAN,
        (CANDIDATE_A, CANDIDATE_A),
        ("SELECT o.id FROM local.shop.orders o LIMIT 1",) * 2,
        LINKS,
    )

    assert [r.candidate_index for r in reports] == [0, 1]
    assert reports[0].score == 0.1
    assert reports[1].score == 0.9
