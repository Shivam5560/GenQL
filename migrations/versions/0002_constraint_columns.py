"""constraint column names

Revision ID: 0002
Revises: 0001

Adds the constrained and (for foreign keys) referenced column names to
genql_constraint, sourced from pg_constraint conkey/confkey. Without these,
building the FK join graph would require regex-parsing pg_get_constraintdef.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "genql_constraint",
        sa.Column(
            "column_names",
            sa.ARRAY(sa.Text),
            nullable=False,
            server_default="{}",
        ),
        schema="genql",
    )
    op.add_column(
        "genql_constraint",
        sa.Column(
            "referenced_column_names",
            sa.ARRAY(sa.Text),
            nullable=False,
            server_default="{}",
        ),
        schema="genql",
    )


def downgrade() -> None:
    op.drop_column("genql_constraint", "referenced_column_names", schema="genql")
    op.drop_column("genql_constraint", "column_names", schema="genql")
