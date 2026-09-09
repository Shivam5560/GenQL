"""One route, no logic: list the registered datasources, minus their secrets."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from genql.api.deps import get_container, get_current_user
from genql.api.dtos.datasource_dtos import DatasourceDto
from genql.domain.value_objects.authenticated_user import AuthenticatedUser

router = APIRouter(tags=["datasources"])


@router.get("/datasources", response_model=list[DatasourceDto])
def list_datasources(
    container: Annotated[Any, Depends(get_container)],
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> list[DatasourceDto]:
    datasources = container.datasource_repository().list_all()
    return [DatasourceDto.from_domain(datasource) for datasource in datasources]
