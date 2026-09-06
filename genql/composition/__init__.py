"""Split pieces of the composition root, grouped by bounded context.

`genql/composition_root.py` remains the single importable entry point
(`Container`): it inherits from `SemanticContainer` here, adding only the
discovery-runner assembly that spans every step. Splitting by context keeps
each file under the project's line-count cap without changing how any
consumer constructs the container.
"""

from __future__ import annotations
