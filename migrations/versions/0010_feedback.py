"""feedback

Revision ID: 0010
Revises: 0009

One additive table: a rating on one turn, optionally with the SQL the user
would have wanted instead. `thread_id` carries no foreign key on purpose:
langgraph's checkpoint tables are created and owned by `PostgresSaver`, not
by these migrations, and a constraint against a table another library may
reshape is a liability. Feedback on an expired thread is still worth
keeping.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "genql_feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("thread_id", sa.Text(), nullable=False),
        sa.Column("rating", sa.Text(), nullable=False),
        sa.Column("corrected_sql", sa.Text(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rating IN ('good', 'bad')", name="genql_feedback_rating_check"),
        schema="genql",
    )
    op.create_index("genql_feedback_thread_idx", "genql_feedback", ["thread_id"], schema="genql")


def downgrade() -> None:
    op.drop_index("genql_feedback_thread_idx", table_name="genql_feedback", schema="genql")
    op.drop_table("genql_feedback", schema="genql")
