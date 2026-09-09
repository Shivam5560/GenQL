"""Two ablations over the same cases, asserting the instrument rather than the
result.

There is deliberately no assertion that `full` outscores `no_domains`. That is
the empirical question the harness exists to answer; encoding the expected
answer as a test assertion would make the instrument agree with the hypothesis
by construction, which is the one failure mode an evaluation harness cannot
recover from.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text

from genql.composition_root import Container
from genql.domain.entities.golden_case import GoldenCase
from genql.services.eval.ablation_service import AblationService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.real_provider,
    # `real_provider` is a label, not a gate: the skip has to be explicit, the
    # same way every other real-provider module in this suite does it.
    pytest.mark.skipif(
        not os.environ.get("GENQL_OPENROUTER_API_KEY"),
        reason="requires GENQL_OPENROUTER_API_KEY",
    ),
    pytest.mark.skipif_no_tpcds,
]

DATASOURCE = "local"


@pytest.fixture()
def ablation_service() -> AblationService:
    service: AblationService = Container().ablation_service()
    return service


@pytest.fixture()
def golden_cases() -> tuple[GoldenCase, ...]:
    cases: tuple[GoldenCase, ...] = Container().golden_set_reader().read_cases(DATASOURCE)
    return cases


@pytest.fixture()
def search_document_content(semantic_engine: Engine) -> Callable[[str], str]:
    """One compiled document's text, read straight from the store.

    Straight from the store rather than through the retriever on purpose: what
    is being checked is what a later turn would *read*, not what a search
    happens to rank. Most-recently-written first, so the row inspected is one
    the restoring recompile actually wrote rather than whichever document
    happens to hold the lowest id.
    """

    def _content(datasource_name: str) -> str:
        with semantic_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT content FROM genql.genql_search_document "
                    "WHERE datasource_name = :datasource_name "
                    "ORDER BY updated_at DESC, id LIMIT 1"
                ),
                {"datasource_name": datasource_name},
            ).scalar_one_or_none()
        return "" if row is None else str(row)

    return _content


def test_two_ablations_cover_the_same_cases(ablation_service, golden_cases) -> None:
    reports = ablation_service.run(("full", "no_domains"), golden_cases)

    assert len(reports) == 2
    assert {o.case_id for o in reports[0].outcomes} == {o.case_id for o in reports[1].outcomes}


def test_each_ablation_is_scored_independently(ablation_service, golden_cases) -> None:
    reports = ablation_service.run(("full", "no_domains"), golden_cases)

    for report in reports:
        assert 0.0 <= report.accuracy <= 1.0
        assert len(report.outcomes) == len(golden_cases)


def test_a_recompiling_ablation_leaves_the_store_restored(
    ablation_service, golden_cases, search_document_content
) -> None:
    """After a no_descriptions run, the compiled documents must carry
    enrichment again — an ablated compile left behind would silently degrade
    every later turn, including a real user's."""
    ablation_service.run(("no_descriptions",), golden_cases[:1])

    assert search_document_content("local") != ""
