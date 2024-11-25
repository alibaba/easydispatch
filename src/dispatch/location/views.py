from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy.orm import Session
from dispatch.auth.models import DispatchUser, UserRoles
from dispatch.auth.service import get_current_user
from dispatch.config import MAX_NBR_LOCATIONS_PER_CALL
from dispatch.database import get_db
from dispatch.org import service as org_service
from dispatch.team import service as team_service
from fastapi.responses import JSONResponse

from dispatch.database_util.service import common_parameters, search_filter_sort_paginate

from .models import (
    Location,
    LocationCreate,
    LocationPagination,
    LocationRead,
    LocationUpdate,
)
from dispatch.auth import service as auth_service
from .service import create, delete, get, get_all, search_by_location_group_code, update 

router = APIRouter()


@router.get("/", response_model=LocationPagination)
def get_locations(*, common: dict = Depends(common_parameters)):
    if common["items_per_page"] < 0 or common["items_per_page"] > MAX_NBR_LOCATIONS_PER_CALL:
        raise HTTPException(status_code=400, detail=f"items per page value is too large, values must be (1 - {MAX_NBR_LOCATIONS_PER_CALL}) ...")

    return search_filter_sort_paginate(model="Location", **common)


@router.get("/{code}", response_model=LocationRead)
def get_location(*, db_session: Session = Depends(get_db), code: str):
    """
    Update a location.
    """
    location = get(db_session=db_session, code=code)
    if not location:
        raise HTTPException(status_code=404, detail="The location with this id does not exist.")
    return location


@router.post("/", response_model=LocationRead)
def create_location(*, db_session: Session = Depends(get_db), location_in: LocationCreate,
                    current_user: DispatchUser = Depends(get_current_user),):
    """
    Create a new location.
    """
    org_service.verify_status(db_session=db_session, org_id=current_user.org_id)

    location_in.org_id = current_user.org_id
    location = get(db_session=db_session, code=location_in.code)
    if location:
        if not location_in.overwrite:
            raise HTTPException(
                status_code=400,
                detail=f"The location with this code ({location_in.code}) already exists.",
            )
        location = update(db_session=db_session, location=location, location_in=location_in)
        return location


    if current_user.role == UserRoles.CUSTOMER :
        location_in.dispatch_user = auth_service.get_by_email(db_session=db_session, email=current_user.email)
    if not location_in.team :
        location_in.team = team_service.get(db_session=db_session,team_id=current_user.default_team_id)
    location = create(db_session=db_session, location_in=location_in)
    return location


@router.put("/{code}", response_model=LocationRead)
def update_location(
    *, db_session: Session = Depends(get_db), code: str, location_in: LocationUpdate
):
    """
    Update a location.
    """
    location = get(db_session=db_session, code=code)
    if not location:
        raise HTTPException(status_code=404, detail="The location with this id does not exist.")

    location = update(db_session=db_session, location=location, location_in=location_in)
    return location


@router.delete("/{code}")
def delete_location(*, db_session: Session = Depends(get_db), code: str):
    """
    Delete a location.
    """
        
    location = get(db_session=db_session, code=code)
    if not location:
        raise HTTPException(status_code=404, detail="The location with this id does not exist.")
    delete(db_session=db_session, code=code)

    return JSONResponse({"status":200, "detail":f" location {code} delete success"})


    

@router.get("/search/code/{q}",response_model=List[str])
def search_location_group_code(*, db_session: Session = Depends(get_db), q = str):

    return search_by_location_group_code(db_session=db_session, code=q)
