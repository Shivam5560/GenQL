"""Selection is a pure function, not a model call, per the parent spec's §20:
"Selection is deterministic by default. When probing resolves every contested
dimension, selection is a lookup rather than a judgement." Takes no
ChatProvider at all.

Assumes len(candidates) >= 2: the single-survivor case is handled by
CandidateSelectionNode's own guard before this service is ever called, per
§7 of the spec.
"""

from __future__ import annotations

from genql.domain.entities.candidate_selection import CandidateSelection
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.probe_result import ProbeResult
from genql.domain.entities.sql_candidate import SqlCandidate


class CandidateSelectionService:
    def select(
        self,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        critiques: tuple[CritiqueReport, ...],
        probe_results: tuple[ProbeResult, ...],
    ) -> CandidateSelection:
        resolved = self._probe_resolved_index(probe_results)
        if resolved is not None:
            return CandidateSelection(
                selected=candidates[resolved],
                selected_sql=validated_sqls[resolved],
                method="probe_resolved",
                rationale=(
                    f"probing resolved every contested dimension in favor of candidate {resolved}"
                ),
            )
        winner = self._critique_ranked_index(critiques)
        if winner is None:
            return CandidateSelection(
                selected=candidates[0],
                selected_sql=validated_sqls[0],
                method="critique_ranked",
                rationale=(
                    "no critique report was available to rank the candidates; "
                    "fell back to the first surviving candidate"
                ),
            )
        return CandidateSelection(
            selected=candidates[winner],
            selected_sql=validated_sqls[winner],
            method="critique_ranked",
            rationale=(
                f"candidate {winner} had the highest critique score among non-fatal survivors"
            ),
        )

    @staticmethod
    def _probe_resolved_index(probe_results: tuple[ProbeResult, ...]) -> int | None:
        """Every probe must resolve, and every one must agree on the same
        candidate — a single disagreeing or inconclusive probe is as
        inconclusive as none at all, per the spec's own selection rule."""
        if not probe_results:
            return None
        resolved_indices = {r.resolved_candidate_index for r in probe_results}
        if None in resolved_indices or len(resolved_indices) != 1:
            return None
        return next(iter(resolved_indices))

    @staticmethod
    def _critique_ranked_index(critiques: tuple[CritiqueReport, ...]) -> int | None:
        """None when there is nothing to rank.

        The spec's Risk section contemplates "critique_ranked selection over
        an empty critique set" as a reachable state, and `Critic` is a port
        any implementation may satisfy — so an empty tuple must return a
        signal the caller can act on rather than raise ValueError out of
        max() from inside a service that is meant to be a pure function.
        """
        non_fatal = [c for c in critiques if not c.is_fatal]
        pool = non_fatal or list(critiques)
        if not pool:
            return None
        best = max(pool, key=lambda c: (c.score, -c.candidate_index))
        return best.candidate_index
