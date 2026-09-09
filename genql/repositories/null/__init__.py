"""Port implementations that return nothing, used only by the ablation harness.

They live under `repositories/` rather than beside the services because they
stand in for repositories: the composition root swaps one in exactly where the
real repository would have gone, so the service under ablation runs its normal
code against an empty upstream. That is what makes the measurement honest — a
service that branched on being ablated would not be the service being
measured.
"""

from __future__ import annotations
