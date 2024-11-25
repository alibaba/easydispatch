from fastapi import APIRouter, Depends, HTTPException, Query

from sqlalchemy.orm import Session
from dispatch.auth.models import DispatchUser, UserRoles
from dispatch.auth.service import get_current_user

from dispatch.database import get_db
from dispatch.org import service as org_service
from dispatch.team import service as team_service

from dispatch.database_util.service import common_parameters, search_filter_sort_paginate

from .models import (
    LocationGroup,
    LocationGroupCreate,
    LocationGroupPagination,
    LocationGroupRead,
    LocationGroupUpdate,
    LocationGroupBatchUpdate,
    LocationGroupBatchUpdateResult
)
from dispatch.auth import service as auth_service
from .service import create, delete, get, update ,delete_by_requested_primary_worker_code
import logging
from fastapi.responses import JSONResponse

log = logging.getLogger("location_group_views")

router = APIRouter()


@router.get("/", response_model=LocationGroupPagination)
def get_location_groups(*, common: dict = Depends(common_parameters)):

    return search_filter_sort_paginate(model="LocationGroup", **common)


@router.get("/{location_group_code}", response_model=LocationGroupRead)
def get_location_group(*, db_session: Session = Depends(get_db), location_group_code: str):
    """
    Update a location_group.
    """
    location_group = get(db_session=db_session, code=location_group_code)
    if not location_group:
        raise HTTPException(status_code=404, detail="The location_group with this id does not exist.")
    return location_group

def verify_replacement(location_group_in, location_group = None):
    if location_group_in.replacement_worker is not None:
        if (location_group_in.replacement_start_day is None) or (
            location_group_in.replacement_end_day is  None):
            raise HTTPException(
                status_code=400,
                detail=f"The replacement period must be valid if replacement worker is specified.",
            )
    else:
        location_group_in.replacement_start_day = None
        location_group_in.replacement_end_day = None

    if (location_group_in.replacement_start_day is not None) and (
        location_group_in.replacement_end_day is not None) and (
        location_group_in.replacement_worker is not None):
        if location_group_in.replacement_start_day >= location_group_in.replacement_end_day:
            raise HTTPException(
                status_code=400,
                detail=f"The replacement start date must be ealier than the end date.",
            )
        return True
    # if (location_group_in.replacement_start_day is None) and (
    #     location_group_in.replacement_end_day is None) and (
    #     location_group_in.replacement_worker is None):
    return True



@router.post("/batch_update", response_model=LocationGroupBatchUpdateResult)
def batch_update_location_group(
    *,  db_session: Session = Depends(get_db), batch_update_in: LocationGroupBatchUpdate,
        current_user: DispatchUser = Depends(get_current_user),):
    """
    Create a new location_group.
    """
    org_service.verify_status(db_session=db_session, org_id=current_user.org_id)
    verify_replacement(batch_update_in)
    print(batch_update_in)
    res = LocationGroupBatchUpdateResult()
    
    for lg_i, lg_code in enumerate(batch_update_in.location_group_codes):
        lg = get(
            db_session = db_session, 
            code = lg_code
        )
        if not lg:
            log.info( f"location_group={lg.code}, is not created...")
            res.created_count +=1
            continue

            lgc = LocationGroupCreate(
                code = lg.code,
                name = lg.name,
                flex_form_data = {},
                team = team ,
                requested_primary_worker = p_worker
            )
            create(
                db_session = db_session, 
                location_group_in = lgc)

        else:
            location_group_in = LocationGroupCreate(
                **lg.__dict__
            )
            location_group_in.requested_primary_worker = batch_update_in.requested_primary_worker
            location_group_in.replacement_start_day = batch_update_in.replacement_start_day
            location_group_in.replacement_end_day = batch_update_in.replacement_end_day
            location_group_in.replacement_worker = batch_update_in.replacement_worker
            update(
                db_session = db_session, 
                location_group = lg,
                location_group_in = location_group_in,
                )
            res.updated_count +=1
            log.info( f"location_group={lg.code}, primary worker = {batch_update_in.requested_primary_worker.code} is created...")

    return res





@router.post("/", response_model=LocationGroupRead)
def create_location_group(*, 
    db_session: Session = Depends(get_db), 
    location_group_in: LocationGroupCreate,
    current_user: DispatchUser = Depends(get_current_user),):
    """
    Create a new location_group.
    """
    org_service.verify_status(db_session=db_session, org_id=current_user.org_id)

    location_group_in.org_id = current_user.org_id
    location_group = get(db_session=db_session, code=location_group_in.code)
    if location_group:
        raise HTTPException(
            status_code=400,
            detail=f"The location_group with this code ({location_group_in.code}) already exists.",
        )
    verify_replacement(location_group_in)
    if not location_group_in.team :
        location_group_in.team = team_service.get(db_session=db_session,team_id=current_user.default_team_id)


    location_group = create(db_session=db_session, location_group_in=location_group_in)
    return location_group


@router.put("/{location_group_code}", response_model=LocationGroupRead)
def update_location(
    *, db_session: Session = Depends(get_db), 
    location_group_code: str, location_group_in: LocationGroupUpdate
):
    """
    Update a location_group.
    """
    location_group = get(db_session=db_session, code=location_group_code)
    if not location_group:
        raise HTTPException(status_code=404, detail="The location_group with this id does not exist.")
    verify_replacement(location_group_in)

    #修改bug code唯一校验
    if location_group_in.replacement_worker is not None:
        if location_group_in.requested_primary_worker is None:
            raise HTTPException(status_code=400, detail=f"requested_primary_worker must be valid if replacement_worker is present")
        if location_group_in.requested_primary_worker.code  == location_group_in.replacement_worker.code:
            raise HTTPException(status_code=400, detail=f"requested_primary_worker can not be same as replacement_worker!")


    location_group = update(db_session=db_session, location_group=location_group, location_group_in=location_group_in)
    return location_group


@router.delete("/{location_group_code}")
def delete_location(*, db_session: Session = Depends(get_db), location_group_code: str):
    """
    Delete a location_group.
    """
    location_group = get(db_session=db_session, code=location_group_code)
    if not location_group:
        raise HTTPException(status_code=404, detail="The location_group with this id does not exist.")
    delete(db_session=db_session, code=location_group_code)



@router.delete("/delete_by_requested_primary_worker_code/{requested_primary_worker_code}")
def delete_location_group_by_requested_primary_worker_code(*, db_session: Session = Depends(get_db), requested_primary_worker_code: str):
    """
    Delete a location_group.
    """
    try:
        delete_by_requested_primary_worker_code(db_session=db_session, requested_primary_worker_code=requested_primary_worker_code)
    except Exception as e:
        return JSONResponse({"status":400, "detail":f"{requested_primary_worker_code} locations_group delete error"})
    else:
        return JSONResponse({"status":200, "detail":f"{requested_primary_worker_code} locations_group delete success"})
