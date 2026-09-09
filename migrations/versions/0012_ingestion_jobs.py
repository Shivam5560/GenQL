"""ingestion jobs

Revision ID: 0012
Revises: 0011

The job table is also the queue. `claim_next` selects the oldest QUEUED row
`FOR UPDATE SKIP LOCKED` and flips it to RUNNING in the same transaction, so
two workers never take the same job and a crashed worker's row can be found
again by its `claimed_at`. That is why `status`/`created_at` and
`status`/`claimed_at` are both indexed: they are the queue's two hot paths,
not reporting conveniences.

Steps are stored as one JSON document rather than a child table. They are
always read and written as a whole list, never queried across jobs, and the
step vocabulary is a domain constant — a child table would buy joins nobody
performs at the cost of six writes per job instead of one.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "genql_ingestion_job",
        sa.Column("job_id", sa.Text(), primary_key=True),
        sa.Column(
            "datasource_name",
            sa.Text(),
            sa.ForeignKey("genql.genql_datasource.name", ondelete="CASCADE"),
            nullable=False,
        ),
        # No FK into auth.users, same rule as genql_thread.user_id: GoTrue
        # owns that table's lifecycle, not this migration set.
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("schemas_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("steps_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_step", sa.Text(), nullable=True),
        sa.Column("claimed_by", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="genql_ingestion_job_status_check",
        ),
        schema="genql",
    )
    op.create_index(
        "genql_ingestion_job_queue_idx",
        "genql_ingestion_job",
        ["status", "created_at"],
        schema="genql",
    )
    op.create_index(
        "genql_ingestion_job_claim_idx",
        "genql_ingestion_job",
        ["status", "claimed_at"],
        schema="genql",
    )
    op.create_index(
        "genql_ingestion_job_datasource_idx",
        "genql_ingestion_job",
        ["datasource_name", "created_at"],
        schema="genql",
    )
    # At most one live job per datasource, enforced by the database rather
    # than only by OnboardingService's check: the service's read-then-write is
    # not atomic, and two simultaneous submissions would otherwise both pass
    # it and then interleave their writes into one catalog.
    op.execute("""
        CREATE UNIQUE INDEX genql_ingestion_job_one_active_idx
        ON genql.genql_ingestion_job (datasource_name)
        WHERE status IN ('queued', 'running')
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS genql.genql_ingestion_job_one_active_idx")
    op.drop_index(
        "genql_ingestion_job_datasource_idx", table_name="genql_ingestion_job", schema="genql"
    )
    op.drop_index("genql_ingestion_job_claim_idx", table_name="genql_ingestion_job", schema="genql")
    op.drop_index("genql_ingestion_job_queue_idx", table_name="genql_ingestion_job", schema="genql")
    op.drop_table("genql_ingestion_job", schema="genql")
