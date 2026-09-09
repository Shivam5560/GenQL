"""Runs the golden set once per ablation.

The parent spec's §15 calls this "the only mechanism that demonstrates whether
the semantic store earns its latency, which is the system's entire thesis", so
the service's job is to make the comparison fair rather than to make it come
out a particular way: each ablation gets its own pipeline built from its own
overrides, every ablation sees the same case list in the same order, and
nothing here knows which layers are supposed to matter.

The recompile is wrapped in try/finally rather than run at the end, because
`no_descriptions` mutates state every later turn reads — including real user
turns, if the process is also serving. Restoring on the way out of an
exception is the difference between a failed run and a silently degraded
installation.
"""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.ablation import Ablation
from genql.domain.entities.golden_case import GoldenCase
from genql.domain.entities.golden_run_report import GoldenRunReport
from genql.domain.errors import UnknownAblationError
from genql.domain.ports.search_document_recompiler import SearchDocumentRecompiler
from genql.domain.ports.turn_runner_factory import TurnRunnerFactory
from genql.registries.errors import UnknownRegistryKeyError
from genql.services.eval.golden_evaluation_service import GoldenEvaluationService
from genql.services.eval.registry import ABLATIONS

_BASELINE = "full"


class AblationService:
    def __init__(
        self,
        evaluation: GoldenEvaluationService,
        runners: TurnRunnerFactory,
        recompiler: SearchDocumentRecompiler,
    ) -> None:
        self._evaluation = evaluation
        self._runners = runners
        self._recompiler = recompiler

    def run(
        self, ablation_names: Sequence[str], cases: Sequence[GoldenCase]
    ) -> tuple[GoldenRunReport, ...]:
        names = list(ablation_names) or ABLATIONS.keys()
        ablations = [self._resolve(name) for name in names]
        return tuple(self._run_one(ablation, cases) for ablation in ablations)

    @staticmethod
    def _resolve(name: str) -> Ablation:
        try:
            return ABLATIONS.create(name)
        except UnknownRegistryKeyError as exc:
            raise UnknownAblationError(name, ABLATIONS.keys()) from exc

    def _run_one(self, ablation: Ablation, cases: Sequence[GoldenCase]) -> GoldenRunReport:
        if not ablation.requires_recompile:
            return self._evaluate(ablation, cases)

        datasource = cases[0].datasource_name if cases else "local"
        self._recompiler.recompile(ablation, datasource)
        try:
            return self._evaluate(ablation, cases)
        finally:
            self._recompiler.recompile(ABLATIONS.create(_BASELINE), datasource)

    def _evaluate(self, ablation: Ablation, cases: Sequence[GoldenCase]) -> GoldenRunReport:
        return self._evaluation.run(ablation.name, cases, self._runners.for_ablation(ablation))
