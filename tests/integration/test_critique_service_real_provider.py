"""One real critique pass against a live model, skipped cleanly without a key.

Two candidates, for the same reason as the gate and intent real-provider
tests: a critic that scores everything the same would pass a one-sided test.
Comparing a candidate that matches the plan against one with an unrelated
column proves the model call actually discriminates, on top of the
deterministic column check this service also runs.
"""

from __future__ import annotations

import os

import pytest

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.ports.chat_provider import ChatProvider
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient
from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider
from genql.services.query.critique_service import CritiqueService

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)

PLAN = QueryPlan(
    question="total revenue per store",
    plan_text="Sum total_paid from store_sales grouped by store id.",
    referenced_objects=("local.shop.store_sales",),
)
LINKS = (
    SchemaLink(
        object_qualified_name="local.shop.store_sales",
        column_names=("store_id", "total_paid"),
    ),
)


@pytest.fixture()
def critic() -> CritiqueService:
    provider = OpenRouterChatProvider(
        client=OpenRouterClient(api_key=os.environ["GENQL_OPENROUTER_API_KEY"]),
        model="anthropic/claude-sonnet-5",
    )
    return CritiqueService(provider)


def test_a_matching_candidate_scores_higher_than_an_unrelated_one(
    critic: CritiqueService,
) -> None:
    good = SqlCandidate(
        sql="SELECT store_id, SUM(total_paid) FROM shop.store_sales GROUP BY store_id",
        plan=PLAN,
    )
    bad = SqlCandidate(
        sql="SELECT store_id, COUNT(*) FROM shop.store_sales GROUP BY store_id",
        plan=PLAN,
    )
    validated_sqls = (
        "SELECT store_id, SUM(total_paid) FROM local.shop.store_sales GROUP BY store_id",
        "SELECT store_id, COUNT(*) FROM local.shop.store_sales GROUP BY store_id",
    )

    reports = critic.critique(PLAN, (good, bad), validated_sqls, LINKS)

    assert reports[0].score > reports[1].score


def test_an_unknown_column_is_a_fatal_deterministic_defect(critic: CritiqueService) -> None:
    candidate = SqlCandidate(sql="SELECT bogus_col FROM shop.store_sales LIMIT 1", plan=PLAN)
    validated_sqls = ("SELECT bogus_col FROM local.shop.store_sales LIMIT 1",)

    reports = critic.critique(PLAN, (candidate,), validated_sqls, LINKS)

    assert reports[0].is_fatal


_STORE_PLAN = QueryPlan(
    question="how many stores do we have",
    plan_text="count distinct stores",
    referenced_objects=("local.public.store",),
)
_STORE_LINKS = (SchemaLink(object_qualified_name="local.public.store", column_names=("store_id",)),)
_CLEAN = SqlCandidate(sql="SELECT count(*) FROM public.store LIMIT 1", plan=_STORE_PLAN)
_BROKEN = SqlCandidate(sql="SELECT bogus_col FROM public.store LIMIT 1", plan=_STORE_PLAN)


def test_a_real_critique_call_scores_both_candidates(
    openrouter_chat_provider: ChatProvider,
) -> None:
    """One real call against two hand-written candidates — one clean, one
    referencing a column no SchemaLink lists — using the shared session-scoped
    provider fixture directly rather than the module's own `critic` fixture."""
    reports = CritiqueService(openrouter_chat_provider).critique(
        _STORE_PLAN,
        (_CLEAN, _BROKEN),
        (
            "SELECT count(*) FROM local.public.store LIMIT 1",
            "SELECT bogus_col FROM local.public.store LIMIT 1",
        ),
        _STORE_LINKS,
    )

    assert len(reports) == 2
    assert reports[1].is_fatal  # the deterministic unknown-column check alone guarantees this
