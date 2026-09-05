"""Process configuration, read once from the environment.

`warehouse_dsn` is deliberately absent: it described a single warehouse, which
is exactly the assumption Phase 2.5 deletes. The value lives on as the
environment variable that the `local` datasource row names. `semantic_dsn`
stays, because GenQL's own store genuinely is singular.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GENQL_", env_file=".env", extra="ignore")

    semantic_dsn: str
    default_datasource: str | None = None
    scope_resolver: str = "default"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "genqlgenql"
    profile_sample_limit: int = 5
