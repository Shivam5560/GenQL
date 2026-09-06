"""semantic store and retrieval

Revision ID: 0005
Revises: 0004

Six new tables, purely additive. `vector` and `pg_search` are created here
rather than assumed present — tests/integration/conftest.py has created them
ad hoc for every test run so far, but a real deployment applies this
migration once and should not depend on test fixtures to have extensions
ready. `genql_search_document`'s BM25 and HNSW indexes cannot be expressed
through SQLAlchemy's table DDL and are added with raw `op.execute`.

Two embeddings exist for a reason: `genql_object_enrichment.embedding` is
computed straight from the LLM profile, before a domain name exists (fused
clustering needs it to produce that name). `genql_search_document.embedding`
is computed later, over the fuller compiled text that includes the domain
name. `genql_column_enrichment` carries no embedding — column text is folded
into the parent object's search document instead of embedded a second time.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_EMBEDDING_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")

    op.create_table(
        "genql_object_enrichment",
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("business_alias", sa.Text),
        sa.Column("provenance", sa.Text, nullable=False, server_default="llm"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("embedding", Vector(_EMBEDDING_DIM)),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "datasource_name", "schema_name", "object_name", name="pk_genql_object_enrichment"
        ),
        sa.ForeignKeyConstraint(
            ["datasource_name", "schema_name"],
            ["genql.genql_schema.datasource_name", "genql.genql_schema.schema_name"],
            name="fk_genql_object_enrichment_schema",
            ondelete="CASCADE",
        ),
        schema="genql",
    )

    op.create_table(
        "genql_column_enrichment",
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("column_name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("business_alias", sa.Text),
        sa.Column("unit", sa.Text),
        sa.Column("provenance", sa.Text, nullable=False, server_default="llm"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "datasource_name",
            "schema_name",
            "object_name",
            "column_name",
            name="pk_genql_column_enrichment",
        ),
        sa.ForeignKeyConstraint(
            ["datasource_name", "schema_name"],
            ["genql.genql_schema.datasource_name", "genql.genql_schema.schema_name"],
            name="fk_genql_column_enrichment_schema",
            ondelete="CASCADE",
        ),
        schema="genql",
    )

    op.create_table(
        "genql_domain",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("provenance", sa.Text, nullable=False, server_default="llm"),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("datasource_name", "name", name="uq_genql_domain_identity"),
        sa.ForeignKeyConstraint(
            ["datasource_name"],
            ["genql.genql_datasource.name"],
            name="fk_genql_domain_datasource",
            ondelete="CASCADE",
        ),
        schema="genql",
    )

    op.create_table(
        "genql_domain_member",
        sa.Column("domain_id", sa.BigInteger, nullable=False),
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("membership_score", sa.Float, nullable=False, server_default="1.0"),
        sa.PrimaryKeyConstraint(
            "domain_id",
            "datasource_name",
            "schema_name",
            "object_name",
            name="pk_genql_domain_member",
        ),
        sa.ForeignKeyConstraint(
            ["domain_id"],
            ["genql.genql_domain.id"],
            name="fk_genql_domain_member_domain",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["datasource_name", "schema_name"],
            ["genql.genql_schema.datasource_name", "genql.genql_schema.schema_name"],
            name="fk_genql_domain_member_schema",
            ondelete="CASCADE",
        ),
        schema="genql",
    )

    op.create_table(
        "genql_metric",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("sql_expression", sa.Text, nullable=False),
        sa.Column("grain", sa.Text, nullable=False),
        sa.Column("unit", sa.Text),
        sa.Column("default_filters", JSONB, nullable=False, server_default="{}"),
        sa.Column("provenance", sa.Text, nullable=False, server_default="yaml"),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("datasource_name", "name", name="uq_genql_metric_identity"),
        sa.ForeignKeyConstraint(
            ["datasource_name"],
            ["genql.genql_datasource.name"],
            name="fk_genql_metric_datasource",
            ondelete="CASCADE",
        ),
        schema="genql",
    )

    op.create_table(
        "genql_search_document",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("domain_name", sa.Text),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(_EMBEDDING_DIM), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "datasource_name",
            "schema_name",
            "object_name",
            name="uq_genql_search_document_identity",
        ),
        sa.ForeignKeyConstraint(
            ["datasource_name", "schema_name"],
            ["genql.genql_schema.datasource_name", "genql.genql_schema.schema_name"],
            name="fk_genql_search_document_schema",
            ondelete="CASCADE",
        ),
        schema="genql",
    )

    op.execute("""
        CREATE INDEX genql_search_document_bm25
            ON genql.genql_search_document
            USING bm25 (id, content)
            WITH (key_field = 'id')
    """)
    op.execute("""
        CREATE INDEX genql_search_document_hnsw
            ON genql.genql_search_document
            USING hnsw (embedding vector_cosine_ops)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS genql.genql_search_document_hnsw")
    op.execute("DROP INDEX IF EXISTS genql.genql_search_document_bm25")
    op.drop_table("genql_search_document", schema="genql")
    op.drop_table("genql_metric", schema="genql")
    op.drop_table("genql_domain_member", schema="genql")
    op.drop_table("genql_domain", schema="genql")
    op.drop_table("genql_column_enrichment", schema="genql")
    op.drop_table("genql_object_enrichment", schema="genql")
    # Extensions are not dropped: another table in this database may still need them.
