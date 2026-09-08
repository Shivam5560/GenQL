"""One ChatProvider.complete call, mapped into AmbiguityProbe entities. No cap
is applied here — AmbiguityProbingService applies probing_max_probes on the
designer's output, keeping "how many probes to ask for" and "how many to
actually run" as two separate, independently testable concerns."""

from __future__ import annotations

from pydantic import BaseModel

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.services.query.probe_designer import LlmProbeDesigner

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))
CANDIDATE = SqlCandidate(sql="SELECT 1 LIMIT 1", plan=PLAN)


class FakeChatProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls = 0

    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        self.calls += 1
        return response_schema.model_validate(self.payload)


def test_designs_a_probe_per_dimension_with_a_prediction_per_candidate() -> None:
    chat = FakeChatProvider(
        {
            "probes": [
                {
                    "dimension": "grain",
                    "probe_sql": "SELECT count(*) FROM shop.orders LIMIT 1",
                    "candidate_predictions": [
                        {"candidate_index": 0, "prediction": "12"},
                        {"candidate_index": 1, "prediction": "144"},
                    ],
                }
            ]
        }
    )

    probes = LlmProbeDesigner(chat).design(PLAN, (CANDIDATE, CANDIDATE), ("SELECT 1",) * 2, ())

    assert probes[0].dimension == "grain"
    assert probes[0].candidate_predictions == ((0, "12"), (1, "144"))


def test_exactly_one_provider_call_is_made() -> None:
    chat = FakeChatProvider({"probes": []})

    LlmProbeDesigner(chat).design(PLAN, (CANDIDATE,), ("SELECT 1",), ())

    assert chat.calls == 1


def test_no_probes_is_a_valid_response() -> None:
    chat = FakeChatProvider({"probes": []})

    probes = LlmProbeDesigner(chat).design(PLAN, (CANDIDATE,), ("SELECT 1",), ())

    assert probes == ()
