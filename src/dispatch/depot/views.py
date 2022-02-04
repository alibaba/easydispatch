from dispatch.database import get_db
from dispatch.org import service as orgService
import random
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from dispatch.auth.models import DispatchUser
from dispatch.auth.service import get_current_user

from dispatch.database_util.service import common_parameters, search_filter_sort_paginate
from .models import (
    Depot,
    DepotCreate,
    DepotPagination,
    DepotRead,
    DepotUpdate,
)
from .service import create, delete, get, get_by_code, get_by_code_org_id, update

router = APIRouter()


@router.get(
    "/", response_model=DepotPagination
)
def get_depots(*, common: dict = Depends(common_parameters)):
    """
    """
    return search_filter_sort_paginate(model="Depot", **common)


@router.get("/select/", response_model=DepotPagination)
def select_depots(
    db_session: Session = Depends(get_db),
    page: int = 1,
    depots_per_page: int = Query(5, alias="depotsPerPage"),
    query_str: str = Query(None, alias="q"),
    sort_by: List[str] = Query(None, alias="sortBy[]"),
    descending: List[bool] = Query(None, alias="descending[]"),
    fields: List[str] = Query([], alias="field[]"),
    ops: List[str] = Query([], alias="op[]"),
    values: List[str] = Query([], alias="value[]"),
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve depot contacts.
    """

    return {
        "depots": db_session.query(Depot).filter(Depot.org_id == current_user.org_id, Depot.code.like(f'%{query_str}%')).limit(10).all(),
        "depotsPerPage": 0,
        "page": 1,
        "total": 0,
    }


@router.post("/", response_model=DepotRead)
def create_depot(*, db_session: Session = Depends(get_db), depot_in: DepotCreate,
                 current_user: DispatchUser = Depends(get_current_user)):
    """
    Create a new depot contact.
    """
    # limit max
    org_data = orgService.get(db_session=db_session, org_code=current_user.org_code)
    if not org_data:
        raise HTTPException(status_code=400, detail="org not exists")

    depot_in.org_id = current_user.org_id
    depot = get_by_code_org_id(db_session=db_session,
                               code=depot_in.code, org_id=current_user.org_id)
    if depot:
        raise HTTPException(status_code=400, detail="The depot with this code already exists.")
    depot = create(db_session=db_session, depot_in=depot_in)
    return depot


@router.get("/{depot_id}", response_model=DepotRead)
def get_depot(*, db_session: Session = Depends(get_db), depot_id: int):
    """
    Get a depot contact.
    """
    depot = get(db_session=db_session, depot_id=depot_id)
    if not depot:
        raise HTTPException(status_code=404, detail="The depot with this id does not exist.")
    return depot


@router.put("/{depot_id}", response_model=DepotRead)
def update_depot(
    *,
    db_session: Session = Depends(get_db),
    depot_id: int,
    depot_in: DepotUpdate, current_user: DispatchUser = Depends(get_current_user)
):
    """
    Update a depot contact.
    """
    depot_in.org_id = current_user.org_id
    depot = get(db_session=db_session, depot_id=depot_id)
    if not depot:
        raise HTTPException(status_code=404, detail="The depot with this id does not exist.")
    if not depot_in.location:
        raise HTTPException(status_code=404, detail="Please select a valid location code.")

    depot = update(
        db_session=db_session,
        depot=depot,
        depot_in=depot_in,
    )
    return depot


@router.put("/depot_code/{depot_code}", response_model=DepotRead)
def update_depot_by_code(
    *,
    db_session: Session = Depends(get_db),
    depot_code: str,
    depot_in: DepotUpdate, current_user: DispatchUser = Depends(get_current_user)
):
    """
    Update a depot contact.
    """
    depot_in.org_id = current_user.org_id
    depot = get_by_code(db_session=db_session, code=depot_code)
    if not depot:
        raise HTTPException(status_code=404, detail="The depot with this id does not exist.")

    depot = update(
        db_session=db_session,
        depot=depot,
        depot_in=depot_in,
    )

    return depot


@router.delete("/{depot_id}")
def delete_depot(*, db_session: Session = Depends(get_db), depot_id: int):
    """
    Delete a depot contact.
    """
    depot = get(db_session=db_session, depot_id=depot_id)
    if not depot:
        raise HTTPException(status_code=404, detail="The depot with this id does not exist.")

    delete(db_session=db_session, depot_id=depot_id)
