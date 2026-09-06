"""How an enrichment-layer row came to exist.

The parent spec assigns this vocabulary to every table in the enrichment
layer — `genql_join_path` here, `genql_object_enrichment` and friends in
Phase 4. A YAML overlay row always wins on merge; this is what a later
merge step checks to know it is looking at one.
"""

from __future__ import annotations

from enum import StrEnum


class Provenance(StrEnum):
    DISCOVERED = "discovered"
    LLM = "llm"
    YAML = "yaml"
