"""rules and checkpoints

Revision ID: 0007
Revises: 0006

One additive table, genql_rule: the YAML-authored defaults the ambiguity gate
applies before deciding a question is under-specified.

Keyed on datasource_name TEXT, not a surrogate datasource_id, so it matches
genql_metric — the table the spec explicitly says to mirror — and so both
RuleReader and RuleWriter can take the name they are already given by the
overlay service. `dimension` is a plain TEXT column with no CHECK constraint
against the six known dimensions: a typo'd dimension is silently never applied
rather than rejected here, the same tradeoff genql_metric.sql_expression
already accepts.

Nothing here creates LangGraph's checkpoint tables. `checkpoints`,
`checkpoint_blobs`, `checkpoint_writes`, and `checkpoint_migrations` belong to
langgraph and are created by PostgresSaver.setup(), which runs once when the
composition root first builds the saver. Hand-writing them as Alembic DDL
would freeze langgraph's schema at this release and break on its next one.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "genql_rule",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("dimension", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("datasource_name", "name", name="uq_genql_rule_identity"),
        sa.ForeignKeyConstraint(
            ["datasource_name"],
            ["genql.genql_datasource.name"],
            name="fk_genql_rule_datasource",
            ondelete="CASCADE",
        ),
        schema="genql",
    )


def downgrade() -> None:
    op.drop_table("genql_rule", schema="genql")
    # LangGraph's checkpoint tables are not dropped: this migration never
    # created them, and a downgrade that deleted another library's state
    # would silently destroy every paused turn.
