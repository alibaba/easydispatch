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
    TeamClear,
)
from .service import create, delete, get, get_by_code, get_by_org_id_count, update, get_all
from ..job.service import get_team_id

from dispatch.planner_env.planner_service import get_active_planner,reset_planning_window_for_team
from starlette.responses import JSONResponse
from dispatch.config import DISPATCH_JWT_SECRET
from dispatch.common.utils.kandbox_clear_data import clear_all_worker_jobs_in_team


import logging
log = logging.getLogger(__name__)


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

    team = get_by_code(db_session=db_session, code=team_contact_in.code)
    if team:
        raise HTTPException(status_code=400, detail="The team with this code already exists.")

    team_contact_in.org_id = current_user.org_id
    # if team_contact_in.planner_service is not None:
    #     team_contact_in.planner_service.org_id = current_user.org_id
    if "team_geo_longitude" not in team_contact_in.flex_form_data:
        team_contact_in.flex_form_data["team_geo_longitude"] = team_contact_in.geo_longitude
        team_contact_in.flex_form_data["team_geo_latitude"] = team_contact_in.geo_latitude
    if team_contact_in.geo_longitude > 73.5393 and team_contact_in.geo_longitude < 134.38898 and (
        team_contact_in.geo_latitude > 16.81 and team_contact_in.geo_latitude < 52.65): 
            team_contact_in.flex_form_data["tile_server"] = "autonavi"
    else:
        team_contact_in.flex_form_data["tile_server"] = "osm"

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

@router.get("/code/{team_code}", response_model=TeamRead)
def get_team_by_code(*, db_session: Session = Depends(get_db), team_code: str):
    """
    Get a team.
    """
    team = get_by_code(db_session=db_session, code=team_code)
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
    log.info(f"update_team:received: {team_contact_in.json()}")

    if not team_contact_in.flex_form_data:
        raise HTTPException(status_code=400, detail="The team flex_form_data is missing.")

    team_contact_in.org_id = current_user.org_id
    team = get(db_session=db_session, team_id=team_id)
    if not team:
        raise HTTPException(status_code=404, detail="The team with this id does not exist.")
    team = update(db_session=db_session, team_contact=team, team_contact_in=team_contact_in)
    if team is None:
        raise HTTPException(status_code=404, detail="Failed to update team. Does Team ID match?")

    if "team_geo_longitude" not in team_contact_in.flex_form_data:
        team_contact_in.flex_form_data["team_geo_longitude"] = team_contact_in.geo_longitude
        team_contact_in.flex_form_data["team_geo_latitude"] = team_contact_in.geo_latitude

    realtime_env_update_flag = str(team_contact_in.flex_form_data.get("realtime_env_update_flag", "1")) == '1'
    # 2024-06-30 05:17:31 disabled.
    reset_when_update = False #  str(team_contact_in.flex_form_data.get("reset_when_update", "0")) == '1'
    if realtime_env_update_flag:
        env = get_active_planner(org_id=team.org_id, team_id=team.id)
        # 2023-05-12 23:22:04, update redis after saving in DB, and boost update_seq
        # env._parse_env_config()
        env.sync_env_config(team_contact_in.flex_form_data, is_reset=reset_when_update)

    return team


@router.delete("/{team_id}", response_model=TeamRead)
def delete_team(*, db_session: Session = Depends(get_db), team_id: int):
    """
    Delete a team.
    """
    team = get(db_session=db_session, team_id=team_id)
    if not team:
        raise HTTPException(status_code=404, detail=f"The team with id {team_id} does not exist.")
    # 修改bug team_id作为外键关联job，存在对应job时，删除失败
    job_list = get_team_id(db_session=db_session,team_id=team_id)
    if job_list:
        raise HTTPException(status_code=404, detail="A team containing jobs can not be deleted.")
    delete(db_session=db_session, team_id=team_id)
    return TeamRead(id=team_id)




# @router.post("/clear_team_data", response_model=TeamRead)
# def clear_team_data(*, db_session: Session = Depends(get_db), team_clear: TeamClear,current_user: DispatchUser = Depends(get_current_user)):
#     """
#     Delete a team worker job data 
#     """
#     if team_clear.secret_key != DISPATCH_JWT_SECRET:
#         raise HTTPException(status_code=404, detail="This is a dangerous operation, please contact the developer ")
#     if current_user.role!="Owner":
#         raise HTTPException(status_code=404, detail="This is a dangerous operation, please contact the developer ")
#     try:
#         all_teams = get_all(db_session=db_session).all()
#         # team = get(db_session=db_session, team_id=current_user.default_team_id)
#         if len(all_teams) < 1:
#             raise HTTPException(status_code=404, detail="The team with this id does not exist.")
#         for team in all_teams:
#             org = orgService.get(db_session=db_session,org_id=current_user.org_id)
#             if not org:
#                 raise HTTPException(status_code=404, detail="The org with this id does not exist.")
#             clear_all_worker_jobs_in_team(db_session=db_session, org_code=org.code,team_id=team.id)
#             reset_planning_window_for_team(org.id , team.id)
#             print(f"cleared data for org {org.code} team {team.id}")

#     except Exception as e:
#         raise HTTPException(status_code=404, detail="clear_team_data is error")
#     else:
#         return JSONResponse({"status":200, "detail":f"clear_team_data is success"})
