from datetime import datetime, timedelta
from typing import List

from arrow.util import total_seconds
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from dispatch import config
from dispatch.auth.models import DispatchUser
from dispatch.auth.service import get_current_user
from dispatch.database import get_db
from dispatch.database_util.service import common_parameters, search_filter_sort_paginate
from dispatch.plugins.kandbox_planner.util.kandbox_date_util import get_current_day_string
from dispatch.service.planner_service import get_active_planner
from sqlalchemy.exc import IntegrityError


from .service import (  # , get_recommendation_slots_single_job
    create,
    delete,
    get,
    get_by_code,
    update,
)
from .models import (
    ServiceCreate,
    ServicePagination,
    ServiceRead,
    ServiceUpdate,
)

from dispatch.config import NBR_OF_OBSERVED_WORKERS, MINUTES_PER_DAY, MAX_NBR_OF_JOBS_PER_DAY_WORKER

router = APIRouter()


@router.get(
    "/", response_model=ServicePagination
)
def get_service_plugins(*, common: dict = Depends(common_parameters)):
    """
    """
    return search_filter_sort_paginate(model="Service", **common)


@router.post("/", response_model=ServiceRead)
def create_service(
    *,
    db_session: Session = Depends(get_db),
    current_user: DispatchUser = Depends(get_current_user),
    service_in: ServiceCreate = Body(
        ...,
        example={
            "name": "myService",
            "type": "pagerduty",
            "is_active": True,
            "external_id": "234234",
        },
    ),
):
    """
    Create a new service.
    """
    service = get_by_code(db_session=db_session, code=service_in.code)
    service_in.org_id = current_user.org_id
    if service:
        raise HTTPException(
            status_code=400,
            detail=f"The service with this code ({service_in.code}) already exists.",
        )
    service_in.org_id = current_user.org_id
    service = create(db_session=db_session, service_in=service_in)
    return service


@router.put("/{service_id}", response_model=ServiceRead)
def update_service(
    *, db_session: Session = Depends(get_db),
    current_user: DispatchUser = Depends(get_current_user), service_id: int, service_in: ServiceUpdate
):
    """
    Update an existing service.
    """
    service = get(db_session=db_session, service_id=service_id)
    if not service:
        raise HTTPException(status_code=404, detail="The service with this id does not exist.")

    service_in.org_id = current_user.org_id
    service = update(db_session=db_session, service=service, service_in=service_in)
    return service


@router.get("/{service_id}", response_model=ServiceRead)
def get_service(*, db_session: Session = Depends(get_db), service_id: int):
    """
    Get a single service.
    """
    service = get(db_session=db_session, service_id=service_id)
    if not service:
        raise HTTPException(status_code=404, detail="The service with this id does not exist.")
    return service


@router.delete("/{service_id}")
def delete_service(*, db_session: Session = Depends(get_db), service_id: int):
    """
    Delete a single service.
    """
    service = get(db_session=db_session, service_id=service_id)
    if not service:
        raise HTTPException(status_code=404, detail="The service with this id does not exist.")
    try:
        delete(db_session=db_session, service_id=service_id)
    except IntegrityError:
        raise HTTPException(
            status_code=400, detail="The service is used by a team and can not be deleted.")
