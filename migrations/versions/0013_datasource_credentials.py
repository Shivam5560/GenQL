"""datasource connection credentials

Revision ID: 0013
Revises: 0012

Registering a warehouse used to mean naming an environment variable the server
already had set, which is fine for one datasource configured by whoever
deployed the server and impossible for anyone connecting their own from a
browser. These columns are what the connect form fills in.

`dsn_env_var` becomes nullable rather than being dropped. The `local` row that
0003 inserted, and anything the CLI registered, still resolve through it; the
engine provider picks whichever of the two a row carries. Dropping it would
have meant a data migration that cannot be written — the environment variable's
VALUE is not in this database, so there is nothing to convert into a host and a
port.

`password_ciphertext` holds a Fernet token, not a password. The key lives in
the server's environment (GENQL_SECRET_KEY), so a dump of this table is not a
dump of the credentials, which is the property the old env-var design had for
free and this one has to buy.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "genql_datasource",
        "dsn_env_var",
        existing_type=sa.Text(),
        nullable=True,
        schema="genql",
    )
    for column in (
        sa.Column("host", sa.Text(), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("database", sa.Text(), nullable=True),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("password_ciphertext", sa.Text(), nullable=True),
        sa.Column("options", sa.Text(), nullable=True),
    ):
        op.add_column("genql_datasource", column, schema="genql")

    # Every row must say where its warehouse is exactly one way. Without this a
    # registration that half-wrote — a host with no env var and no port — would
    # read back as a datasource that resolves to nothing at connect time,
    # minutes into an ingestion run.
    op.create_check_constraint(
        "genql_datasource_endpoint_check",
        "genql_datasource",
        "(dsn_env_var IS NOT NULL) <> (host IS NOT NULL AND port IS NOT NULL)",
        schema="genql",
    )


def downgrade() -> None:
    op.drop_constraint(
        "genql_datasource_endpoint_check",
        "genql_datasource",
        schema="genql",
        type_="check",
    )
    for name in ("options", "password_ciphertext", "username", "database", "port", "host"):
        op.drop_column("genql_datasource", name, schema="genql")
    # Rows registered by host cannot be expressed as an environment variable
    # name, so downgrading past this point deletes them rather than inventing
    # one. The alternative is a NOT NULL that cannot be satisfied.
    op.execute("DELETE FROM genql.genql_datasource WHERE dsn_env_var IS NULL")
    op.alter_column(
        "genql_datasource",
        "dsn_env_var",
        existing_type=sa.Text(),
        nullable=False,
        schema="genql",
    )
