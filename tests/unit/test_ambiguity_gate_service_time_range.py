"""AmbiguityGateService's schema-aware time_range filter, split out of
test_ambiguity_gate_service.py to stay under the house file-length limit: a
question with no date/time column anywhere in scope never has `time_range`
asked about, regardless of confidence scoring, and SCD2 bookkeeping columns
(*_rec_start_date, *_rec_end_date, *_closed_date_sk) don't count as one."""

from __future__ import annotations

from genql.domain.entities.schema_link import SchemaLink
from tests.unit.test_ambiguity_gate_service import FakeChat, service


def test_time_range_is_never_asked_about_when_no_linked_column_is_date_shaped() -> None:
    """`store` has no date column at all — asking "what time period?" about a
    row count over it is exactly the over-triggering this filter exists to
    remove, and it must not depend on the model noticing on its own."""
    chat = FakeChat(vague=("entity", "time_range", "grain"))
    links = (SchemaLink(object_qualified_name="local.tpcds.store", column_names=("s_store_id",)),)

    assessment = service(chat).assess("how many stores are there", "local", links=links)

    assert assessment.missing_dimension == "entity"
    assert "Dimensions still to judge:\n- time_range" not in chat.prompts[0]


def test_time_range_ignores_scd_bookkeeping_columns() -> None:
    """`tpcds.store` carries only SCD2 row-validity columns and a closure-date
    lifecycle column — real dates, but not a business time dimension a generic
    "how many stores" question could mean."""
    chat = FakeChat(vague=("entity", "time_range", "grain"))
    links = (
        SchemaLink(
            object_qualified_name="local.tpcds.store",
            column_names=("s_store_id", "s_rec_start_date", "s_rec_end_date", "s_closed_date_sk"),
        ),
    )

    assessment = service(chat).assess("how many stores are there", "local", links=links)

    assert assessment.missing_dimension == "entity"


def test_time_range_is_still_asked_about_when_a_linked_column_is_date_shaped() -> None:
    chat = FakeChat(vague=("time_range",), question="Which quarter?")
    links = (
        SchemaLink(
            object_qualified_name="local.tpcds.store_sales",
            column_names=("ss_sold_date_sk", "ss_quantity"),
        ),
    )

    assessment = service(chat).assess("total items sold", "local", links=links)

    assert assessment.missing_dimension == "time_range"


def test_no_links_at_all_does_not_suppress_time_range() -> None:
    """An empty/unknown `links` tuple means "we don't know the schema yet",
    not "the schema has no date column" — the filter only fires once
    schema_linking actually ran."""
    chat = FakeChat(vague=("time_range",), question="Which quarter?")

    assessment = service(chat).assess("total items sold", "local", links=())

    assert assessment.missing_dimension == "time_range"
