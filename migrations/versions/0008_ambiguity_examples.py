"""ambiguity examples

Revision ID: 0008
Revises: 0007

One additive table: the offline synthetic ambiguity log SyntheticAmbiguityLog-
Service writes per domain and CandidateGenerationService reads as few-shot
context on the contested path. Mirrors genql_search_document's pgvector/HNSW
setup exactly (Phase 4) — same extension, same index type, same distance
operator — so nothing new is asked of the ParadeDB image; `vector` is already
created by migration 0005 and is not re-created here.

domain_id is ON DELETE SET NULL, not CASCADE, unlike every other table this
phase's sibling tables use: an example's question/interpretations/resolution
triple stays a valid few-shot exemplar even once its domain is renamed or
re-clustered, so deleting the domain should not delete the example.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.create_table(
        "genql_ambiguity_example",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("domain_id", sa.BigInteger),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("interpretations", sa.ARRAY(sa.Text), nullable=False),
        sa.Column("resolution", sa.Text, nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=False),
        sa.ForeignKeyConstraint(
            ["domain_id"],
            ["genql.genql_domain.id"],
            name="fk_genql_ambiguity_example_domain",
            ondelete="SET NULL",
        ),
        schema="genql",
    )
    op.execute("""
        CREATE INDEX genql_ambiguity_example_hnsw
            ON genql.genql_ambiguity_example
            USING hnsw (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS genql.genql_ambiguity_example_hnsw")
    op.drop_table("genql_ambiguity_example", schema="genql")
