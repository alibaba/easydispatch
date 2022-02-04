from dispatch.org import service as orgService
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from dispatch.auth.models import DispatchUser, UserRoles
from dispatch.auth.service import get_current_user

from dispatch.database import get_db
from dispatch.database_util.service import common_parameters, search_filter_sort_paginate

from .models import (
    TeamCreate,
    TeamRead,
    TeamUpdate,
    TeamPagination,
)
from .service import create, delete, get, get_by_code, get_by_org_id_count, update

router = APIRouter()


@router.get("/", response_model=TeamPagination)
def get_teams(*, common: dict = Depends(common_parameters)):
    """
    """
    return search_filter_sort_paginate(model="Team", **common)


@router.post("/", response_model=TeamRead)
def create_team(*, db_session: Session = Depends(get_db), team_contact_in: TeamCreate,
                current_user: DispatchUser = Depends(get_current_user)):
    """
    Create a new team. All jobs and workers must be assigned to one team.
    """
    # limit max
    org_data = orgService.get(db_session=db_session, org_code=current_user.org_code)
    if not org_data:
        raise HTTPException(status_code=400, detail="org not exists")
    max_nbr_teams = org_data.max_nbr_teams

    job_all_count = get_by_org_id_count(db_session=db_session, org_id=current_user.org_id)
    if job_all_count >= max_nbr_teams:
        raise HTTPException(status_code=400, detail="Team Reached the upper limit")

    if current_user.role == UserRoles.WORKER:
        raise HTTPException(status_code=400, detail="No create permission")

    team_contact_in.org_id = current_user.org_id
    if team_contact_in.planner_service is not None:
        team_contact_in.planner_service.org_id = current_user.org_id

    team = get_by_code(db_session=db_session, code=team_contact_in.code)
    if team:
        raise HTTPException(status_code=400, detail="The team with this email already exists.")
    team = create(db_session=db_session, team_contact_in=team_contact_in)
    return team


@router.get("/{team_id}", response_model=TeamRead)
def get_team(*, db_session: Session = Depends(get_db), team_id: int):
    """
    Get a team.
    """
    team = get(db_session=db_session, team_id=team_id)
    if not team:
        raise HTTPException(status_code=404, detail="The team with this id does not exist.")
    return team


@router.put("/{team_id}", response_model=TeamRead)
def update_team(
    *,
    db_session: Session = Depends(get_db),
    team_id: int,
    team_contact_in: TeamUpdate,
    current_user: DispatchUser = Depends(get_current_user)
):
    """
    Update a team.
    """
    team_contact_in.org_id = current_user.org_id
    team = get(db_session=db_session, team_id=team_id)
    if not team:
        raise HTTPException(status_code=404, detail="The team with this id does not exist.")
    team = update(db_session=db_session, team_contact=team, team_contact_in=team_contact_in)
    return team


@router.delete("/{team_id}", response_model=TeamRead)
def delete_team(*, db_session: Session = Depends(get_db), team_id: int):
    """
    Delete a team.
    """
    team = get(db_session=db_session, team_id=team_id)
    if not team:
        raise HTTPException(status_code=404, detail="The team with this id does not exist.")

    delete(db_session=db_session, team_id=team_id)
    return None
