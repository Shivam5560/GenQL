"""The evaluation harness's providers: the golden-set reader, report writer,
comparator, evaluation service, the turn-runner/recompiler adapters used by
ablations, and feedback.

Extends `OptimizerContainer` rather than adding to it in place, matching the
split-by-bounded-context convention the rest of `genql/composition/` follows.
"""

from __future__ import annotations

from dependency_injector import providers

import genql.services.eval.ablations  # noqa: F401 - populates ABLATIONS on import
from genql.api.graph_turn_runner import GraphTurnRunner
from genql.composition.optimizer_container import OptimizerContainer
from genql.infrastructure.eval.search_document_recompiler import SearchDocumentRecompilerImpl
from genql.infrastructure.eval.turn_runner_factory import TurnRunnerFactoryImpl
from genql.repositories.eval.json_report_repository import JsonReportWriter
from genql.repositories.eval.yaml_golden_set_repository import YamlGoldenSetReader
from genql.repositories.semantic.feedback_repository import PostgresFeedbackWriter
from genql.services.eval.ablation_service import AblationService
from genql.services.eval.golden_evaluation_service import GoldenEvaluationService
from genql.services.eval.result_comparator import ResultComparator
from genql.services.semantic.feedback_service import FeedbackService


class EvalContainer(OptimizerContainer):
    golden_set_reader = providers.Singleton(
        YamlGoldenSetReader, directory=OptimizerContainer.settings.provided.golden_set_dir
    )
    report_writer = providers.Singleton(JsonReportWriter)
    result_comparator = providers.Singleton(ResultComparator)
    golden_evaluation_service = providers.Singleton(
        GoldenEvaluationService,
        execution=OptimizerContainer.guarded_execution_service,
        comparator=result_comparator,
    )
    turn_runner = providers.Singleton(
        GraphTurnRunner,
        graph=OptimizerContainer.query_graph,
        locks=OptimizerContainer.thread_lock_factory,
    )
    turn_runner_factory = providers.Singleton(TurnRunnerFactoryImpl)
    search_document_recompiler = providers.Singleton(SearchDocumentRecompilerImpl)
    ablation_service = providers.Singleton(
        AblationService,
        evaluation=golden_evaluation_service,
        runners=turn_runner_factory,
        recompiler=search_document_recompiler,
    )
    feedback_writer = providers.Singleton(
        PostgresFeedbackWriter, engine=OptimizerContainer.semantic_engine
    )
    feedback_service = providers.Singleton(FeedbackService, writer=feedback_writer)
