"""One compiled, retrievable document per object: BM25 text plus its
embedding. This embedding is computed over the fuller compiled text
(including the domain name) — a separate computation from
ObjectEnrichment.embedding, which exists earlier, before a domain name is
known."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SearchDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str
    object_name: str
    domain_name: str | None
    content: str
    embedding: tuple[float, ...]
