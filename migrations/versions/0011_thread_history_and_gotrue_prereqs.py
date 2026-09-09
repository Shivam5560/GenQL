"""thread history and GoTrue prerequisites

Revision ID: 0011
Revises: 0010

Two unrelated things share one revision because the second depends on the
first being live before the `gotrue` docker-compose service (Task 2) can
boot successfully — GoTrue's migrations were confirmed live against this
exact ParadeDB instance in the spec's §2a spike, needing exactly these three
prerequisites (auth schema, two extensions, a placeholder postgres role)
before they apply cleanly. genql_thread/genql_turn/genql_user_profile are
GenQL's own read-model tables, additive and independent of GoTrue's auth.*
tables, which this migration never touches.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS auth")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'postgres') THEN
                CREATE ROLE postgres NOLOGIN;
            END IF;
        END
        $$
    """)

    op.create_table(
        "genql_thread",
        sa.Column("thread_id", sa.Text(), primary_key=True),
        # No foreign key into auth.users: GoTrue owns that table's lifecycle,
        # not this migration set, matching genql_feedback.thread_id's existing
        # no-cross-table-FK precedent.
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("datasource_name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="genql",
    )
    op.create_index(
        "genql_thread_user_active_idx",
        "genql_thread",
        ["user_id", "last_active_at"],
        schema="genql",
    )

    op.create_table(
        "genql_turn",
        sa.Column("turn_id", sa.Text(), primary_key=True),
        sa.Column(
            "thread_id", sa.Text(), sa.ForeignKey("genql.genql_thread.thread_id"), nullable=False
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("recap", sa.Text(), nullable=True),
        sa.Column("validated_sql", sa.Text(), nullable=True),
        sa.Column("clarifying_question", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("applied_defaults_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("thread_id", "sequence", name="genql_turn_thread_sequence_uq"),
        schema="genql",
    )
    op.create_index("genql_turn_thread_idx", "genql_turn", ["thread_id"], schema="genql")

    op.create_table(
        "genql_user_profile",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("theme_preference", sa.Text(), nullable=False, server_default="system"),
        sa.CheckConstraint(
            "theme_preference IN ('light', 'dark', 'system')",
            name="genql_user_profile_theme_check",
        ),
        schema="genql",
    )


def downgrade() -> None:
    op.drop_table("genql_user_profile", schema="genql")
    op.drop_index("genql_turn_thread_idx", table_name="genql_turn", schema="genql")
    op.drop_table("genql_turn", schema="genql")
    op.drop_index("genql_thread_user_active_idx", table_name="genql_thread", schema="genql")
    op.drop_table("genql_thread", schema="genql")
    # auth schema, its extensions, and the postgres role are intentionally
    # left in place on downgrade: GoTrue owns tables inside auth.* by then,
    # and dropping the schema here would destroy live GoTrue data this
    # migration set does not own.
