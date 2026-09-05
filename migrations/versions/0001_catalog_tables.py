"""catalog tables

Revision ID: 0001
Revises:
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS genql")

    op.create_table(
        "genql_object",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("object_type", sa.Text, nullable=False),
        sa.Column("row_estimate", sa.BigInteger),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("schema_name", "object_name", name="uq_genql_object_identity"),
        schema="genql",
    )

    op.create_table(
        "genql_column",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("column_name", sa.Text, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("data_type", sa.Text, nullable=False),
        sa.Column("is_nullable", sa.Boolean, nullable=False),
        sa.Column("is_primary_key", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.UniqueConstraint(
            "schema_name", "object_name", "column_name", name="uq_genql_column_identity"
        ),
        schema="genql",
    )

    op.create_table(
        "genql_constraint",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("constraint_name", sa.Text, nullable=False),
        sa.Column("constraint_type", sa.Text, nullable=False),
        sa.Column("definition", sa.Text, nullable=False),
        sa.Column("referenced_object_name", sa.Text),
        sa.UniqueConstraint(
            "schema_name", "object_name", "constraint_name", name="uq_genql_constraint_identity"
        ),
        schema="genql",
    )

    op.create_table(
        "genql_column_profile",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("object_name", sa.Text, nullable=False),
        sa.Column("column_name", sa.Text, nullable=False),
        sa.Column("distinct_count", sa.BigInteger),
        sa.Column("null_fraction", sa.Float),
        sa.Column("sample_values", sa.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("profiled_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "schema_name", "object_name", "column_name", name="uq_genql_profile_identity"
        ),
        schema="genql",
    )


def downgrade() -> None:
    op.drop_table("genql_column_profile", schema="genql")
    op.drop_table("genql_constraint", schema="genql")
    op.drop_table("genql_column", schema="genql")
    op.drop_table("genql_object", schema="genql")
    op.execute("DROP SCHEMA IF EXISTS genql")
