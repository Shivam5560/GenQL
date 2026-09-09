"""`_parse_embedding` must handle pgvector's text wire format, since no
adapter is registered on this engine to deserialize `vector` columns for us
— a raw `psycopg`/SQLAlchemy read returns them as `"[0.1,0.2,...]"` strings,
not Python sequences."""

from __future__ import annotations

from genql.repositories.semantic.enrichment_repository import _parse_embedding


def test_parses_pgvectors_text_wire_format() -> None:
    assert _parse_embedding("[-0.03,0.007,0.06]") == (-0.03, 0.007, 0.06)


def test_none_becomes_an_empty_tuple() -> None:
    assert _parse_embedding(None) == ()


def test_an_already_sequence_value_passes_through_as_a_tuple() -> None:
    assert _parse_embedding([1.0, 2.0]) == (1.0, 2.0)
