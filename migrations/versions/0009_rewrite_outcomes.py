"""rewrite outcomes

Revision ID: 0009
Revises: 0008

One additive table: the plan-vs-actual record RewriteOutcomeRecordingService
writes after `EXPLAIN (ANALYZE, BUFFERS)` runs, and PostgresIndexRecommender
later aggregates by `datasource_id` and `shared_buffers_read` to justify an
index recommendation.

`datasource_id` is TEXT keyed on `genql_datasource.name`, not a surrogate
integer id, despite its name: this mirrors genql_rule and genql_schema
(genql_datasource's primary key is `name`, not `id`), and the column keeps
the `datasource_id` name because that is the name the repository's queries
and this migration's own test assert on.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "genql_rewrite_outcome",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("sql_hash", sa.Text, nullable=False),
        sa.Column("datasource_id", sa.Text, nullable=False),
        sa.Column("rules_applied", sa.ARRAY(sa.Text), nullable=False),
        sa.Column("estimated_cost", sa.Float, nullable=False),
        sa.Column("actual_total_time_ms", sa.Float, nullable=False),
        sa.Column("actual_rows", sa.BigInteger, nullable=False),
        sa.Column("shared_buffers_hit", sa.BigInteger, nullable=False),
        sa.Column("shared_buffers_read", sa.BigInteger, nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["datasource_id"],
            ["genql.genql_datasource.name"],
            name="fk_genql_rewrite_outcome_datasource",
            ondelete="CASCADE",
        ),
        schema="genql",
    )
    op.create_index(
        "genql_rewrite_outcome_datasource_idx",
        "genql_rewrite_outcome",
        ["datasource_id"],
        schema="genql",
    )


def downgrade() -> None:
    op.drop_index(
        "genql_rewrite_outcome_datasource_idx", table_name="genql_rewrite_outcome", schema="genql"
    )
    op.drop_table("genql_rewrite_outcome", schema="genql")
