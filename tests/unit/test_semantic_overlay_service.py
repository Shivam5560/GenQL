"""Overlay always wins on merge. An object entry with no prior profiling and
only a business_alias override (no description) writes nothing — an
ObjectEnrichment cannot exist without a description."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.metric import Metric
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.entities.rule import Rule
from genql.domain.entities.semantic_overlay import (
    ColumnOverlay,
    MetricOverlay,
    ObjectOverlay,
    RuleOverlay,
    SemanticOverlay,
)
from genql.domain.value_objects.provenance import Provenance
from genql.repositories.semantic.enricher_repository import (
    AliasEnricher,
    DescriptionEnricher,
    UnitEnricher,
)
from genql.services.semantic.semantic_overlay_service import SemanticOverlayService

EXISTING = ObjectEnrichment(
    datasource_name="local",
    schema_name="shop",
    object_name="orders",
    description="from LLM",
)
EXISTING_COLUMN = ColumnEnrichment(
    datasource_name="local",
    schema_name="shop",
    object_name="orders",
    column_name="total",
    description="from LLM",
    provenance=Provenance.LLM,
)


class FakeEnrichmentReader:
    def __init__(
        self,
        objects: Sequence[ObjectEnrichment] = (),
        columns: Sequence[ColumnEnrichment] = (),
    ) -> None:
        self._objects = objects
        self._columns = columns

    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]:
        return self._objects

    def read_column_enrichments(self, ref: object) -> Sequence[ColumnEnrichment]:
        return self._columns


class FakeEnrichmentWriter:
    def __init__(self) -> None:
        self.objects: list[ObjectEnrichment] = []
        self.columns: list[ColumnEnrichment] = []

    def write_object_enrichment(self, enrichment: ObjectEnrichment) -> None:
        self.objects.append(enrichment)

    def write_column_enrichments(self, enrichments: Sequence[ColumnEnrichment]) -> int:
        self.columns.extend(enrichments)
        return len(enrichments)


class FakeMetricWriter:
    def __init__(self) -> None:
        self.written: list[Metric] = []

    def write(self, metrics: Sequence[Metric]) -> int:
        self.written.extend(metrics)
        return len(metrics)


class FakeJoinPathWriter:
    def __init__(self) -> None:
        self.written: list[object] = []

    def write(self, paths: Sequence[object]) -> int:
        self.written.extend(paths)
        return len(paths)


class FakeRuleWriter:
    def __init__(self) -> None:
        self.written: list[Rule] = []
        self.datasources: list[str] = []

    def write_rules(self, datasource_name: str, rules: Sequence[Rule]) -> int:
        self.datasources.append(datasource_name)
        self.written.extend(rules)
        return len(rules)


def _service(
    objects: Sequence[ObjectEnrichment] = (),
    columns: Sequence[ColumnEnrichment] = (),
) -> tuple[
    SemanticOverlayService,
    FakeEnrichmentWriter,
    FakeMetricWriter,
    FakeRuleWriter,
    FakeJoinPathWriter,
]:
    writer = FakeEnrichmentWriter()
    metrics = FakeMetricWriter()
    rules = FakeRuleWriter()
    join_paths = FakeJoinPathWriter()
    service = SemanticOverlayService(
        FakeEnrichmentReader(objects, columns),
        writer,
        metrics,
        rules,
        join_paths,
        [DescriptionEnricher(), AliasEnricher(), UnitEnricher()],
    )
    return service, writer, metrics, rules, join_paths


def test_overlay_description_overrides_the_llm_value() -> None:
    service, writer, _, _, _ = _service([EXISTING])
    overlay = SemanticOverlay(
        datasource="local",
        objects={"shop.orders": ObjectOverlay(description="from YAML")},
    )

    report = service.apply(overlay)

    assert report.objects_updated == 1
    assert writer.objects[0].description == "from YAML"


def test_alias_only_overlay_on_an_unprofiled_object_writes_nothing() -> None:
    service, writer, _, _, _ = _service([])
    overlay = SemanticOverlay(
        datasource="local",
        objects={"shop.orders": ObjectOverlay(business_alias="orders desk")},
    )

    report = service.apply(overlay)

    assert report.objects_updated == 0
    assert writer.objects == []


def test_column_overlay_overrides_unit() -> None:
    service, writer, _, _, _ = _service([EXISTING])
    overlay = SemanticOverlay(
        datasource="local",
        objects={
            "shop.orders": ObjectOverlay(
                columns={"total": ColumnOverlay(description="Order total.", unit="USD")}
            )
        },
    )

    service.apply(overlay)

    assert writer.columns[0].unit == "USD"
    assert writer.columns[0].description == "Order total."


def test_unit_only_overlay_preserves_existing_column_description() -> None:
    """A unit-only override must not silently drop an already-profiled
    column's LLM description — that would happen if existing column
    enrichments were never read before merging."""
    service, writer, _, _, _ = _service([EXISTING], [EXISTING_COLUMN])
    overlay = SemanticOverlay(
        datasource="local",
        objects={"shop.orders": ObjectOverlay(columns={"total": ColumnOverlay(unit="USD")})},
    )

    service.apply(overlay)

    assert writer.columns[0].description == "from LLM"
    assert writer.columns[0].unit == "USD"


def test_metrics_are_written_as_is() -> None:
    service, _, metrics, _, _ = _service([])
    overlay = SemanticOverlay(
        datasource="local",
        metrics=(MetricOverlay(name="net_sales", sql_expression="a - b", grain="line_item"),),
    )

    report = service.apply(overlay)

    assert report.metrics_written == 1
    assert metrics.written[0].name == "net_sales"


def test_rules_are_written_unconditionally_with_no_merge_step() -> None:
    """Same shape as test_metrics_are_written_as_is: nothing else in the system
    proposes a rule, so there is no discovered value to merge against and the
    Enricher registry is not consulted."""
    service, _, _, rules, _ = _service([])

    report = service.apply(
        SemanticOverlay(
            datasource="local",
            rules=(
                RuleOverlay(
                    name="default_period",
                    dimension="time_range",
                    value="fiscal_year_to_date",
                    description="An unqualified period means the fiscal year to date.",
                ),
            ),
        )
    )

    assert report.rules_written == 1
    assert rules.datasources == ["local"]
    assert rules.written[0] == Rule(
        name="default_period",
        dimension="time_range",
        value="fiscal_year_to_date",
        description="An unqualified period means the fiscal year to date.",
    )


def test_an_overlay_with_no_rules_writes_none_and_reports_zero() -> None:
    service, _, _, rules, _ = _service([])

    report = service.apply(SemanticOverlay(datasource="local"))

    assert report.rules_written == 0
    assert rules.written == []
