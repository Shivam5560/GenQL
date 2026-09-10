"""a turn remembers how it was answered

Revision ID: 0014
Revises: 0013

Stage events were streamed and never stored, so the pipeline's reasoning
existed only for as long as the browser tab that watched it. Reloading a
thread left the user with a SQL statement and no way to check why it looks the
way it does — the opposite of what "defend in review" promises.

`stages_json` holds the same short lines the SSE stream ships (stage, status,
detail), not the state deltas behind them: a delta can carry the whole
schema-link set, and widening this column into a state dump would make the
history table the widest interface in the system.

Existing rows default to `[]`, which every reader already treats as "no
discussion recorded for this turn" — the same shape a turn asked through the
blocking endpoint writes, since that path has no stage events to record.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "genql_turn",
        sa.Column("stages_json", sa.JSON(), nullable=False, server_default="[]"),
        schema="genql",
    )


def downgrade() -> None:
    op.drop_column("genql_turn", "stages_json", schema="genql")
