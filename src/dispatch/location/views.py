from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import true
from dispatch.auth.models import DispatchUser, UserRoles
from dispatch.auth.service import get_current_user

from dispatch.database import get_db

from dispatch.database import get_db
from typing import List


from dispatch.database_util.service import common_parameters, search_filter_sort_paginate
from dispatch.search.service import search

from .models import (
    Location,
    LocationCreate,
    LocationPagination,
    LocationRead,
    LocationUpdate,
)
from .service import create, delete, get, get_all, get_by_location_code, update
from dispatch.auth import service as auth_service

router = APIRouter()


@router.get(
    "/", response_model=LocationPagination
)
def get_locations(*, common: dict = Depends(common_parameters)):
    """
    """
    return search_filter_sort_paginate(model="Location", **common)


@router.get("/{location_id}", response_model=LocationRead)
def get_location(*, db_session: Session = Depends(get_db), location_id: int):
    """
    Update a location.
    """
    location = get(db_session=db_session, location_id=location_id)
    if not location:
        raise HTTPException(status_code=404, detail="The location with this id does not exist.")
    return location


@router.post("/", response_model=LocationRead)
def create_location(*, db_session: Session = Depends(get_db), location_in: LocationCreate,
                    current_user: DispatchUser = Depends(get_current_user),):
    """
    Create a new location.
    """
    location_in.org_id = current_user.org_id
    location = get_by_location_code(db_session=db_session, location_code=location_in.location_code)
    if location:
        raise HTTPException(
            status_code=400,
            detail=f"The location with this location_code ({location_in.location_code}) already exists.",
        )
    if current_user.role == UserRoles.CUSTOMER :
        location_in.dispatch_user = auth_service.get_by_email(db_session=db_session, email=current_user.email)

    location = create(db_session=db_session, location_in=location_in)
    return location


@router.put("/{location_id}", response_model=LocationRead)
def update_location(
    *, db_session: Session = Depends(get_db), location_id: int, location_in: LocationUpdate
):
    """
    Update a location.
    """
    location = get(db_session=db_session, location_id=location_id)
    if not location:
        raise HTTPException(status_code=404, detail="The location with this id does not exist.")
    location = update(db_session=db_session, location=location, location_in=location_in)
    return location


@router.delete("/{location_id}")
def delete_location(*, db_session: Session = Depends(get_db), location_id: int):
    """
    Delete a location.
    """
    location = get(db_session=db_session, location_id=location_id)
    if not location:
        raise HTTPException(status_code=404, detail="The location with this id does not exist.")
    delete(db_session=db_session, location_id=location_id)
