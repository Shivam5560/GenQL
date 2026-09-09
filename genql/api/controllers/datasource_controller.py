"""Register a warehouse, watch it become queryable, and manage it afterwards.

Registration is synchronous and ingestion is not, which is the whole shape of
this file. `POST /datasources` validates the dialect, proves the DSN variable
is set, writes the row, queues a job, and returns 202 in milliseconds — the
five to fifty minutes of catalog scanning, profiling, embedding and graph
analysis happen in a worker draining that queue.

The client is given two ways to follow it: a stream per job, for the page that
submitted it, and one app-wide stream of transitions, so "your warehouse is
ready" arrives wherever the person has navigated to by then.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from genql.api.deps import get_container, get_current_user
from genql.api.dtos.datasource_dtos import (
    DatasourceAcceptedDto,
    DatasourceDto,
    IngestionJobDto,
    RegisterDatasourceRequest,
    RetryIngestionRequest,
)
from genql.api.sse.ingestion_events import datasource_event_stream, ingestion_event_stream
from genql.domain.value_objects.authenticated_user import AuthenticatedUser

router = APIRouter(tags=["datasources"])

Container = Annotated[Any, Depends(get_container)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


@router.get("/datasources", response_model=list[DatasourceDto])
def list_datasources(container: Container, user: CurrentUser) -> list[DatasourceDto]:
    datasources = container.datasource_repository().list_all()
    return [DatasourceDto.from_domain(datasource) for datasource in datasources]


@router.post(
    "/datasources",
    response_model=DatasourceAcceptedDto,
    status_code=status.HTTP_202_ACCEPTED,
)
def register_datasource(
    request: RegisterDatasourceRequest, container: Container, user: CurrentUser
) -> DatasourceAcceptedDto:
    """202, not 201: the datasource exists but cannot answer anything yet."""
    datasource, job = container.onboarding_service().register_and_submit(
        request.name,
        request.dialect,
        request.dsn_env_var,
        request.description,
        request.schemas,
        user.user_id,
    )
    return DatasourceAcceptedDto(
        datasource=DatasourceDto.from_domain(datasource),
        job=IngestionJobDto.from_domain(job),
        stream_url=f"/v1/datasources/{datasource.name}/onboarding/stream",
    )


@router.get("/datasources/{name}/onboarding", response_model=IngestionJobDto)
def onboarding_status(name: str, container: Container, user: CurrentUser) -> IngestionJobDto:
    return IngestionJobDto.from_domain(container.onboarding_service().status(name))


@router.post(
    "/datasources/{name}/onboarding/retry",
    response_model=IngestionJobDto,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_onboarding(
    name: str, request: RetryIngestionRequest, container: Container, user: CurrentUser
) -> IngestionJobDto:
    """Queue another run, optionally resuming from one step forward.

    This is also how a datasource registered by the CLI gets its first job.
    """
    job = container.onboarding_service().retry(name, request.start_from, user.user_id)
    return IngestionJobDto.from_domain(job)


@router.get("/datasources/{name}/onboarding/stream")
def stream_onboarding(name: str, container: Container, user: CurrentUser) -> EventSourceResponse:
    """One job's progress. Resolved by datasource so a reconnecting client
    does not need to have kept the job id."""
    job = container.onboarding_service().status(name)
    generator = ingestion_event_stream(container.ingestion_job_repository(), job.job_id)
    return EventSourceResponse(iterate_in_threadpool(generator))


@router.get("/datasources/events")
def stream_datasource_events(container: Container, user: CurrentUser) -> EventSourceResponse:
    """Every datasource's transitions, for the lifetime of a browser tab."""
    generator = datasource_event_stream(container.ingestion_job_repository())
    return EventSourceResponse(iterate_in_threadpool(generator))


@router.delete("/datasources/{name}", status_code=status.HTTP_204_NO_CONTENT)
def remove_datasource(name: str, container: Container, user: CurrentUser) -> Response:
    """Cascades: the catalog, profiles, search documents and ingestion jobs
    discovered from this warehouse go with it."""
    container.datasource_service().remove(name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
