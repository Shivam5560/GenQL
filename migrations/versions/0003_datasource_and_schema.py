"""datasource and schema levels

Revision ID: 0003
Revises: 0002

Inserts the two identity levels above `object`. The upgrade is non-destructive:
`datasource_name` is added with a server default of 'local', so PostgreSQL
backfills every existing row as part of the DDL, and the default is dropped
only afterwards. Rows discovered in Phase 2 become addressable as
`local.<schema>` rather than being thrown away.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_CATALOG_TABLES = ("genql_object", "genql_column", "genql_constraint", "genql_column_profile")
_IDENTITY_CONSTRAINTS = {
    "genql_object": ("uq_genql_object_identity", ["schema_name", "object_name"]),
    "genql_column": ("uq_genql_column_identity", ["schema_name", "object_name", "column_name"]),
    "genql_constraint": (
        "uq_genql_constraint_identity",
        ["schema_name", "object_name", "constraint_name"],
    ),
    "genql_column_profile": (
        "uq_genql_profile_identity",
        ["schema_name", "object_name", "column_name"],
    ),
}


def upgrade() -> None:
    op.create_table(
        "genql_datasource",
        sa.Column("name", sa.Text, primary_key=True),
        sa.Column("dialect", sa.Text, nullable=False),
        sa.Column("dsn_env_var", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema="genql",
    )

    op.create_table(
        "genql_schema",
        sa.Column("datasource_name", sa.Text, nullable=False),
        sa.Column("schema_name", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("datasource_name", "schema_name", name="pk_genql_schema"),
        sa.ForeignKeyConstraint(
            ["datasource_name"],
            ["genql.genql_datasource.name"],
            name="fk_genql_schema_datasource",
            ondelete="CASCADE",
        ),
        schema="genql",
    )

    # The datasource Phase 2 was pointed at. Named for the environment variable
    # that already carries its DSN, so nothing about the local setup changes.
    op.execute(
        """
        INSERT INTO genql.genql_datasource (name, dialect, dsn_env_var, description)
        VALUES ('local', 'postgres', 'GENQL_WAREHOUSE_DSN',
                'Datasource migrated from the single-warehouse configuration')
        """
    )

    for table in _CATALOG_TABLES:
        op.add_column(
            table,
            sa.Column("datasource_name", sa.Text, nullable=False, server_default="local"),
            schema="genql",
        )

    op.execute(
        """
        INSERT INTO genql.genql_schema (datasource_name, schema_name)
        SELECT DISTINCT 'local', schema_name FROM genql.genql_object
        ON CONFLICT ON CONSTRAINT pk_genql_schema DO NOTHING
        """
    )

    for table in _CATALOG_TABLES:
        op.alter_column(table, "datasource_name", server_default=None, schema="genql")
        constraint_name, columns = _IDENTITY_CONSTRAINTS[table]
        op.drop_constraint(constraint_name, table, type_="unique", schema="genql")
        op.create_unique_constraint(
            constraint_name, table, ["datasource_name", *columns], schema="genql"
        )
        op.create_foreign_key(
            f"fk_{table}_schema",
            table,
            "genql_schema",
            ["datasource_name", "schema_name"],
            ["datasource_name", "schema_name"],
            source_schema="genql",
            referent_schema="genql",
            ondelete="CASCADE",
        )


def downgrade() -> None:
    # Safe only on a single-datasource store. Restoring the pre-datasource
    # unique constraints drops `datasource_name` from the identity, so a store
    # holding the same (schema_name, object_name) in two datasources — exactly
    # what the upgrade makes possible — fails here on a duplicate key. Reduce
    # to one datasource before downgrading.
    for table in _CATALOG_TABLES:
        op.drop_constraint(f"fk_{table}_schema", table, type_="foreignkey", schema="genql")
        constraint_name, columns = _IDENTITY_CONSTRAINTS[table]
        op.drop_constraint(constraint_name, table, type_="unique", schema="genql")
        op.create_unique_constraint(constraint_name, table, columns, schema="genql")
        op.drop_column(table, "datasource_name", schema="genql")

    op.drop_table("genql_schema", schema="genql")
    op.drop_table("genql_datasource", schema="genql")
