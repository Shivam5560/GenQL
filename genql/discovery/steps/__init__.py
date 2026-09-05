"""Registers every discovery step with DISCOVERY_STEPS.

This is the one place that imports step modules purely for their
`@DISCOVERY_STEPS.register(...)` decorator side effect. The composition root
imports this package (not the individual step classes) so the pipeline can be
built FROM the registry instead of a hand-maintained list of classes.
"""

from __future__ import annotations

from genql.discovery.steps.catalog_scan_step import CatalogScanStep
from genql.discovery.steps.data_profiling_step import DataProfilingStep

__all__ = ["CatalogScanStep", "DataProfilingStep"]
