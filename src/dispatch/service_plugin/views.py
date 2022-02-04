from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from dispatch.enums import Visibility
from dispatch.auth.models import DispatchUser, UserRoles
from dispatch.auth.service import get_current_user
from dispatch.database import get_db
from dispatch.database_util.service import common_parameters, search_filter_sort_paginate

from .models import (
    ServicePluginCreate,
    ServicePluginPagination,
    ServicePluginRead,
    ServicePluginUpdate,
)
from .service import create, delete, get, update


router = APIRouter()


@router.get(
    "/", response_model=ServicePluginPagination, summary="Retrieve a list of all service_plugins."
)
def get_service_plugins(*, common: dict = Depends(common_parameters)):
    """
    """
    return search_filter_sort_paginate(model="ServicePlugin", **common)


@router.get(
    "/{service_plugin_id}",
    response_model=ServicePluginRead,
    summary="Retrieve a single service_plugin.",
)
def get_service_plugin(
    *,
    db_session: Session = Depends(get_db),
    service_plugin_id: str,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve details about a specific service_plugin.
    """
    service_plugin = get(db_session=db_session, service_plugin_id=service_plugin_id)
    if not service_plugin:
        raise HTTPException(status_code=404, detail="The requested service_plugin does not exist.")

    # we want to provide additional protections around restricted service_plugins
    if service_plugin.visibility == Visibility.restricted:
        if not service_plugin.reporter == current_user:
            if not current_user.role != UserRoles.OWNER:
                raise HTTPException(
                    status_code=401, detail="You do no have permission to view this service_plugin."
                )

    return service_plugin


@router.post("/", response_model=ServicePluginRead, summary="Create a new service_plugin.")
def create_service_plugin(
    *,
    db_session: Session = Depends(get_db),
    service_plugin_in: ServicePluginCreate,
    current_user: DispatchUser = Depends(get_current_user),
    background_tasks: BackgroundTasks,
):
    """
    Create a new service_plugin.
    """
    service_plugin_in.org_id = current_user.org_id
    service_plugin_in.service.org_id = current_user.org_id
    service_plugin = create(
        db_session=db_session,
        service_plugin_in=service_plugin_in,
    )

    # background_tasks.add_task(service_plugin_create_flow, service_plugin_id=service_plugin.id)

    return service_plugin


@router.put(
    "/{service_plugin_id}",
    response_model=ServicePluginRead,
    summary="Update an existing service_plugin.",
)
def update_service_plugin(
    *,
    db_session: Session = Depends(get_db),
    service_plugin_id: int,
    service_plugin_in: ServicePluginUpdate,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Update an worker service_plugin.
    """
    service_plugin = get(db_session=db_session, service_plugin_id=service_plugin_id)
    if not service_plugin:
        raise HTTPException(status_code=404, detail="The requested service_plugin does not exist.")
    if (service_plugin_in.service is None) or (service_plugin_in.plugin is None):
        raise HTTPException(
            status_code=400, detail="The request does not contain valid service and plugin.")

    previous_service_plugin = ServicePluginRead.from_orm(service_plugin)

    # NOTE: Order matters we have to get the previous state for change detection
    service_plugin_in.org_id = current_user.org_id
    service_plugin = update(
        db_session=db_session, service_plugin=service_plugin, service_plugin_in=service_plugin_in
    )

    return service_plugin


@router.delete(
    "/{service_plugin_id}", response_model=ServicePluginRead, summary="Delete an service_plugin."
)
def delete_service_plugin(*, db_session: Session = Depends(get_db), service_plugin_id: str):
    """
    Delete an worker service_plugin.
    """
    service_plugin = get(db_session=db_session, service_plugin_id=service_plugin_id)
    if not service_plugin:
        raise HTTPException(status_code=404, detail="The requested service_plugin does not exist.")
    delete(db_session=db_session, service_plugin_id=service_plugin.id)
