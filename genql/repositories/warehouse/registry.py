"""Warehouse readers, keyed by SQL dialect.

Adding Snowflake or BigQuery is one file plus one decorator: nothing in
services, discovery, or the CLI mentions a dialect by name.
"""

from __future__ import annotations

from genql.domain.ports.catalog_reader import CatalogReader
from genql.domain.ports.profile_reader import ProfileReader
from genql.registries.registry import Registry

CATALOG_READERS: Registry[CatalogReader] = Registry("catalog_readers")
PROFILE_READERS: Registry[ProfileReader] = Registry("profile_readers")
