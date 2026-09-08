"""One real probe-design call against a live model, skipped cleanly without a
key. Two candidates that disagree on grain (total rows vs. distinct stores)
prove the model actually designs a discriminating probe rather than one that
would return the same thing regardless of which candidate is right."""

from __future__ import annotations

import os

import pytest

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider
from genql.services.query.probe_designer import LlmProbeDesigner

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)

PLAN = QueryPlan(
    question="how many orders per store",
    plan_text=(
        "Count orders from shop.orders grouped by store id. Ambiguous whether "
        "'orders' means order rows or distinct order ids."
    ),
    referenced_objects=("local.shop.orders",),
)
ROW_COUNT_CANDIDATE = SqlCandidate(
    sql="SELECT store_id, COUNT(*) FROM shop.orders GROUP BY store_id",
    plan=PLAN,
)
DISTINCT_ID_CANDIDATE = SqlCandidate(
    sql="SELECT store_id, COUNT(DISTINCT order_id) FROM shop.orders GROUP BY store_id",
    plan=PLAN,
)
VALIDATED_SQLS = (
    "SELECT store_id, COUNT(*) FROM local.shop.orders GROUP BY store_id",
    "SELECT store_id, COUNT(DISTINCT order_id) FROM local.shop.orders GROUP BY store_id",
)


@pytest.fixture()
def designer() -> LlmProbeDesigner:
    provider = OpenRouterChatProvider(
        client=OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"]),
        model="anthropic/claude-sonnet-5",
    )
    return LlmProbeDesigner(provider)


def test_a_real_model_designs_a_probe_with_predictions_per_candidate(
    designer: LlmProbeDesigner,
) -> None:
    probes = designer.design(
        PLAN,
        (ROW_COUNT_CANDIDATE, DISTINCT_ID_CANDIDATE),
        VALIDATED_SQLS,
        (),
    )

    assert len(probes) >= 1
    probe = probes[0]
    assert probe.probe_sql.strip()
    assert len(probe.candidate_predictions) == 2
    predicted_indices = {idx for idx, _ in probe.candidate_predictions}
    assert predicted_indices == {0, 1}
