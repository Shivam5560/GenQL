"""Runs a registered datasource through the six stages that make it queryable.

The order is not a preference. Discovery must write a catalog before the
search index can compile from it, and discovery's `graph_projection` step must
have run before Leiden and FastRP have a graph to analyse. `STEP_SEQUENCE`
holds that order; this service is the only thing that executes it.

Every stage is reported through `report` the moment it starts and again the
moment it ends, so a client watching the stream sees "discovery, running"
rather than a four-minute gap. The service never touches the job store itself:
the worker owns persistence, this owns sequencing.

A stage that raises stops the run. There is no partial success worth having —
an index compiled from half a catalog answers questions wrongly rather than
not at all — so the job fails and `retry(start_from=...)` is how it resumes.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from genql.domain.entities.ingestion_job import (
    DISCOVERY,
    DOMAIN_DISCOVERY,
    GRAPH_ANALYSIS,
    SCHEMA_REGISTRATION,
    SEMANTIC_COMPILE,
    SEMANTIC_OVERLAY,
    IngestionStep,
    StepStatus,
)
from genql.domain.errors import DiscoveryError, EmptySchemaError
from genql.domain.ports.clock import Clock
from genql.domain.ports.discovery_scope_runner import DiscoveryScopeRunner
from genql.domain.ports.overlay_loader import OverlayLoader
from genql.domain.value_objects.query_scope import QueryScope
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.datasource.schema_registration_service import SchemaRegistrationService
from genql.services.graph.graph_analysis_service import GraphAnalysisService
from genql.services.semantic.compile_service import CompileService
from genql.services.semantic.domain_discovery_service import DomainDiscoveryService
from genql.services.semantic.semantic_overlay_service import SemanticOverlayService

Report = Callable[[IngestionStep], None]


class IngestionService:
    def __init__(  # noqa: PLR0913, PLR0917 - one collaborator per pipeline stage
        self,
        schemas: SchemaRegistrationService,
        discovery: DiscoveryScopeRunner,
        overlays: OverlayLoader,
        overlay_service: SemanticOverlayService,
        compiler: CompileService,
        graph: GraphAnalysisService,
        domains: DomainDiscoveryService,
        clock: Clock,
        sample_limit: int,
    ) -> None:
        self._schemas = schemas
        self._discovery = discovery
        self._overlays = overlays
        self._overlay_service = overlay_service
        self._compiler = compiler
        self._graph = graph
        self._domains = domains
        self._clock = clock
        self._sample_limit = sample_limit

    def run(
        self,
        datasource_name: str,
        schema_names: tuple[str, ...],
        steps: tuple[IngestionStep, ...],
        report: Report,
    ) -> None:
        """Execute exactly the steps given, in the order given.

        Callers pass a slice of STEP_SEQUENCE, which is how a retry resumes
        from the middle without re-profiling a warehouse that is already
        profiled.
        """
        runners: dict[str, Callable[[str, tuple[str, ...]], IngestionStep]] = {
            SCHEMA_REGISTRATION: self._register_schemas,
            DISCOVERY: self._discover,
            SEMANTIC_OVERLAY: self._apply_overlay,
            SEMANTIC_COMPILE: self._compile,
            GRAPH_ANALYSIS: self._analyze_graph,
            DOMAIN_DISCOVERY: self._discover_domains,
        }
        for step in steps:
            report(step.model_copy(update={"status": StepStatus.RUNNING}))
            started = self._clock.now()
            try:
                done = runners[step.name](datasource_name, schema_names)
            except Exception as exc:
                elapsed = self._elapsed_ms(started)
                report(
                    step.model_copy(
                        update={
                            "status": StepStatus.FAILED,
                            "detail": f"{type(exc).__name__}: {exc}",
                            "duration_ms": elapsed,
                        }
                    )
                )
                raise
            report(done.model_copy(update={"duration_ms": self._elapsed_ms(started)}))

    def _elapsed_ms(self, started: datetime) -> int:
        return int((self._clock.now() - started).total_seconds() * 1000)

    # ---- stages ---------------------------------------------------------

    def _register_schemas(self, datasource: str, schemas: tuple[str, ...]) -> IngestionStep:
        """Register every requested schema, refusing the job if none survive.

        One unreadable schema out of five is a typo worth reporting but not
        worth abandoning the run for; zero readable schemas means there is
        nothing to ingest, and continuing would produce an empty catalog that
        looks like a successful ingestion.
        """
        registered: list[str] = []
        rejected: list[str] = []
        for name in schemas:
            ref = SchemaRef(datasource_name=datasource, schema_name=name)
            try:
                self._schemas.register(ref, None)
                registered.append(name)
            except EmptySchemaError:
                rejected.append(name)
        if not registered:
            raise EmptySchemaError(f"{datasource}.[{', '.join(schemas)}]")
        detail = f"{len(registered)} schema(s) registered"
        if rejected:
            detail += f"; skipped {', '.join(rejected)} (empty or not visible)"
        return IngestionStep(
            name=SCHEMA_REGISTRATION,
            status=StepStatus.SUCCEEDED,
            detail=detail,
            records_written=len(registered),
        )

    def _discover(self, datasource: str, schemas: tuple[str, ...]) -> IngestionStep:
        registered = tuple(
            r.schema_name for r in self._schemas.list_for_datasource(datasource) if r.enabled
        )
        scope = QueryScope(datasource_name=datasource, schema_names=registered or schemas)
        outcomes = self._discovery.run_scope(scope, sample_limit=self._sample_limit)
        written = sum(r.records_written for o in outcomes for r in o.results)
        failed = [o for o in outcomes if not o.succeeded]
        if failed and len(failed) == len(outcomes):
            first = next(r for r in failed[0].results if not r.succeeded)
            raise DiscoveryError(f"discovery failed on every schema: {first.message}")
        detail = f"{len(outcomes) - len(failed)}/{len(outcomes)} schemas discovered"
        if failed:
            detail += f"; failed on {', '.join(o.ref.schema_name for o in failed)}"
        return IngestionStep(
            name=DISCOVERY,
            status=StepStatus.SUCCEEDED,
            detail=detail,
            records_written=written,
        )

    def _apply_overlay(self, datasource: str, _schemas: tuple[str, ...]) -> IngestionStep:
        overlay = self._overlays.load(datasource)
        if overlay is None:
            return IngestionStep(
                name=SEMANTIC_OVERLAY,
                status=StepStatus.SKIPPED,
                detail="no overlay file for this datasource",
            )
        report = self._overlay_service.apply(overlay)
        written = (
            report.objects_updated
            + report.columns_updated
            + report.metrics_written
            + report.rules_written
            + report.join_hints_written
        )
        return IngestionStep(
            name=SEMANTIC_OVERLAY,
            status=StepStatus.SUCCEEDED,
            detail=(
                f"{report.objects_updated} objects, {report.metrics_written} metrics, "
                f"{report.rules_written} rules"
            ),
            records_written=written,
        )

    def _compile(self, datasource: str, _schemas: tuple[str, ...]) -> IngestionStep:
        report = self._compiler.compile(datasource)
        return IngestionStep(
            name=SEMANTIC_COMPILE,
            status=StepStatus.SUCCEEDED,
            detail=f"{report.documents} search documents embedded",
            records_written=report.documents,
        )

    def _analyze_graph(self, datasource: str, _schemas: tuple[str, ...]) -> IngestionStep:
        report = self._graph.analyze(datasource)
        return IngestionStep(
            name=GRAPH_ANALYSIS,
            status=StepStatus.SUCCEEDED,
            detail=(
                f"{report.communities} communities, {report.embedded_nodes} nodes embedded, "
                f"{report.join_paths} join paths"
            ),
            records_written=report.embedded_nodes,
        )

    def _discover_domains(self, datasource: str, _schemas: tuple[str, ...]) -> IngestionStep:
        report = self._domains.discover(datasource)
        return IngestionStep(
            name=DOMAIN_DISCOVERY,
            status=StepStatus.SUCCEEDED,
            detail=f"{report.domains} domains over {report.members} members",
            records_written=report.domains,
        )
