"""Grounds each domain's generation prompt on its name, description, and the
datasource's full metric list (Deviation 5) — no per-domain object membership
read is added this phase. Zero domains is a valid, zero-record outcome, not a
failure (Deviation 6): a first `genql discover` run reaches this step before
`genql graph domains` has ever run."""

from __future__ import annotations

from pydantic import BaseModel

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.metric import Metric
from genql.services.discovery.synthetic_ambiguity_log_service import SyntheticAmbiguityLogService

SALES = BusinessDomain(
    datasource_name="local", domain_id=1, name="Sales", description="Orders and revenue."
)
METRIC = Metric(
    datasource_name="local", name="net_revenue", sql_expression="sum(total)", grain="order"
)


class FakeChatProvider:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        self.prompts.append(prompt)
        return response_schema.model_validate(self.payload)


class FakeEmbeddingProvider:
    def embed(self, texts):  # type: ignore[no-untyped-def]
        return [(0.1,) for _ in texts]


class FakeDomains:
    def __init__(self, domains: tuple[BusinessDomain, ...]) -> None:
        self._domains = domains

    def domain_id_by_name(self, datasource_name: str, name: str) -> int | None:
        return None

    def list_domains(self, datasource_name: str) -> tuple[BusinessDomain, ...]:
        return self._domains


class FakeMetrics:
    def __init__(self, metrics: tuple[Metric, ...]) -> None:
        self._metrics = metrics

    def read_metrics(self, datasource_name: str):  # type: ignore[no-untyped-def]
        return self._metrics


class RecordingWriter:
    def __init__(self) -> None:
        self.written: list[AmbiguityExample] = []

    def write(self, examples: tuple[AmbiguityExample, ...]) -> None:
        self.written.extend(examples)


def _payload() -> dict[str, object]:
    return {
        "examples": [
            {
                "question": "show me revenue",
                "interpretations": ["gross revenue", "net revenue"],
                "resolution": "Net revenue, per the finance glossary.",
            }
        ]
    }


def test_generates_and_writes_one_example_per_domain() -> None:
    chat = FakeChatProvider(_payload())
    writer = RecordingWriter()
    service = SyntheticAmbiguityLogService(
        chat, FakeEmbeddingProvider(), FakeDomains((SALES,)), FakeMetrics((METRIC,)), writer
    )

    written = service.generate("local")

    assert written == 1
    assert writer.written[0].domain_id == 1


def test_grounds_the_prompt_on_domain_and_metric_names() -> None:
    chat = FakeChatProvider(_payload())
    service = SyntheticAmbiguityLogService(
        chat,
        FakeEmbeddingProvider(),
        FakeDomains((SALES,)),
        FakeMetrics((METRIC,)),
        RecordingWriter(),
    )

    service.generate("local")

    assert "Sales" in chat.prompts[0]
    assert "net_revenue" in chat.prompts[0]


def test_zero_domains_writes_zero_examples_and_makes_no_model_call() -> None:
    chat = FakeChatProvider(_payload())
    service = SyntheticAmbiguityLogService(
        chat, FakeEmbeddingProvider(), FakeDomains(()), FakeMetrics(()), RecordingWriter()
    )

    written = service.generate("local")

    assert written == 0
    assert chat.prompts == []


def test_one_call_per_domain() -> None:
    other = BusinessDomain(
        datasource_name="local", domain_id=2, name="Support", description="Tickets."
    )
    chat = FakeChatProvider(_payload())
    service = SyntheticAmbiguityLogService(
        chat,
        FakeEmbeddingProvider(),
        FakeDomains((SALES, other)),
        FakeMetrics((METRIC,)),
        RecordingWriter(),
    )

    service.generate("local")

    assert len(chat.prompts) == 2
