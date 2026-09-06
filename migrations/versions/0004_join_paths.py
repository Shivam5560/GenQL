"""join paths

Revision ID: 0004
Revises: 0003

Purely additive: one new table, no existing table changes, no backfill.
`path` is the full object sequence from source to target inclusive, in join
order. Removing a schema cascades to its mined paths, the same rule Phase 2.5
established for every catalog table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "genql_join_path",
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("source_object", sa.Text, nullable=False),
        sa.Column("target_object", sa.Text, nullable=False),
        sa.Column("path", sa.ARRAY(sa.Text), nullable=False),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column("provenance", sa.Text, nullable=False, server_default="discovered"),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint(
            "datasource_name",
            "schema_name",
            "source_object",
            "target_object",
            name="pk_genql_join_path",
        ),
        sa.ForeignKeyConstraint(
            ["datasource_name", "schema_name"],
            ["genql.genql_schema.datasource_name", "genql.genql_schema.schema_name"],
            name="fk_genql_join_path_schema",
            ondelete="CASCADE",
        ),
        schema="genql",
    )


def downgrade() -> None:
    op.drop_table("genql_join_path", schema="genql")
