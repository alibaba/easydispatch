from copy import copy
import json
# from dispatch.job.rule import e6yun_job_create
from dispatch.org import service as org_service

# from dispatch.auth.views import auth_router

from dispatch.common.utils.encryption import check_edit_job_token
from dispatch.database import get_db
from dispatch.org import service as orgService
from collections import defaultdict

from typing import List
from dispatch.config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import true
from dispatch import worker
from dispatch.worker import service as worker_service

from dispatch.enums import Visibility
from dispatch.auth.models import DispatchUser
from dispatch.auth.service import get_current_user
from dispatch.database_util.service import common_parameters, search_filter_sort_paginate


from dispatch.auth.models import UserRoles
from dispatch.plugins.kandbox_planner.env.env_enums import JobPlanningStatus, JobLifeCycleStatus, JobLifeCycleStatus_SEQUENCE, JobType
from dispatch.planner_env.planner_service import get_active_planner
from dispatch.job.models import JobUpdateWorkerUpdate,JobCreate, JobPagination, JobRead, JobReadResponese, JobUpdate, JobLifeCycleUpdate,JobWorkerChange,JobRelated,JobRelatedUpdate
from dispatch.job.service import job_batch_change_worker,set_job_related,create, delete, get, get_by_team, update, get_by_code, get_by_org_id_count, update_life_cycle_info ,get_all,get_job_by_worker,get_reschedule_times
from dispatch.team.service import get as get_team
from dispatch.plugins.kandbox_planner.util.kandbox_util import from_item_list_to_dict
from dispatch.depot import service as depot_service
from dispatch.item import service as item_service
from dispatch.item_inventory import service as inventory_service
from dispatch.item_inventory_event import service as inventory_event_service
from dispatch.job_biz import service as job_biz_service
from dispatch.problem import service as problem_service
from dispatch.delivery_info import service as delivery_info_service
from dispatch.auth import service as auth_service 
from dispatch.exceptions import InvalidConfiguration

import logging

from dispatch.worker.models import WorkerCreate

log = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/", response_model=JobPagination
)
def get_jobs(*, common: dict = Depends(common_parameters)):
    """
    """
    # 根据时间降序
    if not common["sort_by"]:
        common["sort_by"] = ["scheduled_start_datetime"]
    else:
        common["sort_by"].append("created_at")

    if not common["descending"]:
        common["descending"] = [True]
    else:
        common["descending"].append(True)
    
    common["fields"].append("job_type")
    common["values"].append("event")
    common["ops"].append("==")

    all_job =  search_filter_sort_paginate(model="Job", **common)
    # items = []
    # for job in all_job['items']:
    #     job_biz = job_biz_service.get_by_job_code(db_session=common['db_session'],id = job.code)
    #     team = job.team
    #     location = job.location
    #     job_read = JobRead(**job.__dict__, job_track_status=job_biz.job_track_status if job_biz else '')
    #     items.append(job_read)

    # all_job['items'] = items
    return all_job


@router.get("/{job_code}", response_model=JobRead, summary="Retrieve a single job.")
def get_job(
    *,
    db_session: Session = Depends(get_db),
    job_code: str,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve details about a specific job.
    """
    job = get(db_session=db_session, job_code=job_code)
    if not job:
        raise HTTPException(status_code=404, detail="The requested worker absence does not exist.")

    return job


@router.post("/", response_model=JobReadResponese, summary="Create a new job.")
# @e6yun_job_create(option='create')
def create_job(
    *,
    db_session: Session = Depends(get_db),
    job_in: JobCreate,
    current_user: DispatchUser = Depends(get_current_user),
    background_tasks: BackgroundTasks,
):
    """
    Create a new job.
    """
    job_in.job_type = JobType.ABSENCE
        
    try:
        org_service.verify_status(db_session=db_session, org_id=current_user.org_id)
        # limit max job
        org_data = orgService.get(db_session=db_session, org_code=current_user.org_code)
        if not org_data:
            raise HTTPException(status_code=400, detail="org not exists")
        max_nbr_job = org_data.max_nbr_jobs

        job_all_count = get_by_org_id_count(db_session=db_session, org_id=current_user.org_id)
        if job_all_count >= max_nbr_job:
            raise HTTPException(status_code=400, detail="Org Reached the upper limit")

        job_in.org_id = current_user.org_id
        job = get_by_code(db_session=db_session, code=job_in.code)
        if job:
            return {
                "state": -1,
                "msg": "The job with this code already exists.",
                "data": job
            }
        if job_in.requested_skills:
            job_in.flex_form_data['requested_skills'] = job_in.requested_skills
        if job_in.requested_items:
            job_in.flex_form_data['requested_items'] = job_in.requested_items

        job = create(
            db_session=db_session, org_code=current_user.org_code,
            current_user = current_user,
            # requested_primary_worker=WorkerCreate(code = job_in.requested_primary_worker_code),
            **job_in.dict(exclude={"target_worker","overwrite_max_orders_limit","is_appointment"})
            )


        # background_tasks.add_task(job_create_flow, job_code=job.code)
        # call  and worker which has been changed event

        # TODO, only when auto_planning 
        return {
            "state": 1,
            "msg": "The job add succeed",
            "data": job
        }
    except Exception as e:
        return {
            "state": -1,
            "msg": f"add job error,{e}",
            "data": None
        }


# @auth_router.put("/update_job_no_token/{job_code}", response_model=JobRead, summary="Update an existing job.")
# def update_job_no_token(
#     *,
#     db_session: Session = Depends(get_db),
#     job_code: str,
#     job_in: JobUpdate,
#     background_tasks: BackgroundTasks,
# ):
#     """
#     Update an worker job.
#     """
#     org_id = int(job_in.org_id)
#     org_obj = orgService.get(db_session=db_session, org_id=org_id)
#     job = get(db_session=db_session, job_code=job_code)
#     if not job:
#         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
#                             detail="The requested job does not exist.")
#     token = job_in.token
#     flag = check_edit_job_token(job.code, token)    
#     if not flag:
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
#                             detail="Permission verification failed.")

#     if job.planning_status == JobPlanningStatus.FINISHED:
#         raise HTTPException(status_code=404, detail="Finish (F) job can not be updated.")
#     if job_in.requested_skills:
#         job_in.flex_form_data['requested_skills'] = job_in.requested_skills
#     if job_in.requested_items:
#         job_in.flex_form_data['requested_items'] = job_in.requested_items

#     if job_in.planning_status == JobPlanningStatus.FINISHED:
#         if job.planning_status == JobPlanningStatus.UNPLANNED:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST, detail="Unplanned job can be changed to Finished (F).")
#         # I will deduct items from
#         item_list = job.flex_form_data.get("requested_items", [])
#         if len(item_list) > 0:
#             item_dict = from_item_list_to_dict(item_list)

#             depot = depot_service.get_default_depot(db_session=db_session)
#             depot_code = depot.code
#             for item_code in item_dict.keys():
#                 item = item_service.get_by_code(db_session=db_session, code=item_code)
#                 inv = inventory_service.get_by_item_depot(
#                     db_session=db_session,
#                     item_id=item.id,
#                     depot_id=depot.id,
#                     org_id=org_id
#                 ).first()
#                 inv.allocated_qty -= item_dict[item_code]
#                 if inv.allocated_qty < 0:
#                     inv.curr_qty += inv.allocated_qty
#                     inv.allocated_qty = 0
#                 if inv.curr_qty < 0:
#                     e_msg = f"Not enough inventory for item: {item_code}, depot: {depot_code}, org.id: {org_id}"
#                     # log.error(e_msg)
#                     raise HTTPException(status_code=404, detail=e_msg)
#                 db_session.add(inv)
#                 inventory_event_service.log(
#                     db_session=db_session,
#                     source="Web",
#                     description=f"Finished/Deducted {item_dict[item_code]} {item_code} from depot: {depot_code}",
#                     item_code=item_code,
#                     depot_code=depot_code,
#                     item_id=item.id,
#                     depot_id=depot.id
#                 )
#             db_session.commit()
#     # previous_job = JobRead.from_orm(job)

#     # NOTE: Order matters we have to get the previous state for change detection
#     job = update(db_session=db_session, job=job, job_in=job_in, org_code=org_obj.code)

#     return job




@router.put("/{job_code}", response_model=JobRead, summary="Update an existing job.")
# @e6yun_job_create(option='update')
def update_job(
    *,
    db_session: Session = Depends(get_db),
    job_code: str,
    job_in: JobUpdate,
    current_user: DispatchUser = Depends(get_current_user),
    background_tasks: BackgroundTasks,
):
    """
    Update an worker job.
    """
    job_in.org_id = current_user.org_id
    job = get(db_session=db_session, code=job_code)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")
    # 修改bug，增加code唯一校验
    # job_verify = get_verify(db_session=db_session, job_code=job_code, job_code=job_in.code)
    # if job_verify:
    #     raise HTTPException(status_code=404, detail="The requested job with this code has exist.")
    if job.planning_status == JobPlanningStatus.FINISHED:
        raise HTTPException(status_code=404, detail="Finish (F) job can not be updated.")
    if job_in.requested_skills:
        job_in.flex_form_data['requested_skills'] = job_in.requested_skills
    if job_in.requested_items:
        job_in.flex_form_data['requested_items'] = job_in.requested_items

    if job_in.planning_status == JobPlanningStatus.FINISHED:
        if job.planning_status == JobPlanningStatus.UNPLANNED:
            raise HTTPException(
                status_code=404, detail="Unplanned job can be changed to Finished (F).")
        # I will deduct items from
        item_list = job.flex_form_data.get("requested_items", [])
        if len(item_list) > 0:
            item_dict = from_item_list_to_dict(item_list)

            depot = depot_service.get_default_depot(db_session=db_session)
            depot_code = depot.code
            for item_code in item_dict.keys():
                item = item_service.get_by_code(db_session=db_session, code=item_code)
                inv = inventory_service.get_by_item_depot(
                    db_session=db_session,
                    item_id=item.id,
                    depot_id=depot.id,
                    org_id=current_user.org_id
                ).first()
                inv.allocated_qty -= item_dict[item_code]
                if inv.allocated_qty < 0:
                    inv.curr_qty += inv.allocated_qty
                    inv.allocated_qty = 0
                if inv.curr_qty < 0:
                    e_msg = f"Not enough inventory for item: {item_code}, depot: {depot_code}, org.id: {current_user.org_id}"
                    # log.error(e_msg)
                    raise HTTPException(status_code=404, detail=e_msg)
                db_session.add(inv)
                inventory_event_service.log(
                    db_session=db_session,
                    source="Web",
                    description=f"Finished/Deducted {item_dict[item_code]} {item_code} from depot: {depot_code}",
                    item_code=item_code,
                    depot_code=depot_code,
                    item_id=item.id,
                    depot_id=depot.id
                )
            db_session.commit()
    # previous_job = JobRead.from_orm(job)
    old_job_code = copy(job_in.code)
    # NOTE: Order matters we have to get the previous state for change detection
    job = update(db_session=db_session, job=job, job_in=job_in, org_code=current_user.org_code,current_user = current_user)

    log.info(f"job {job.code} is updated by user: {current_user.email}")
    #change job code to reload env 
    # if old_job_code ==job.code:         
    #         try:
    #             get_default_active_planner( org_code= current_user.org_code, team_id=job.team_id, force_reload=True)
    #         except Exception as e:
    #             log.error(e)
    return job


@router.delete("/{job_code}", summary="Delete a worker absence.")
def delete_job(*, db_session: Session = Depends(get_db), job_code: str,
               current_user: DispatchUser = Depends(get_current_user)):
    """
    Delete an worker job.
    """
    job = get(db_session=db_session, code=job_code)
    if not job:
        raise HTTPException(status_code=404, detail="The requested absence does not exist.")
    delete(db_session=db_session, code=job.code)
    log.info(f"job {job.code} is deleted by user: {current_user.email}")
    # try:
    #     get_default_active_planner( org_code= current_user.org_code, team_id=job.team_id, force_reload=True)
    # except Exception as e:
    #     log.error(e)
    return True

