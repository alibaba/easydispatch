from copy import copy
import json
from dispatch.common.utils.string_checker import check_job_code_str
# from dispatch.job.rule import e6yun_job_create
from dispatch.org import service as org_service
# from fastapi import status
# import redis
# from dispatch.auth.views import auth_router
# import math
import random
from dispatch.common.utils.encryption import check_edit_job_token
from dispatch.database import get_db
from dispatch.org import service as orgService
from collections import defaultdict
import string
from typing import List
from dispatch.config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, MAX_NBR_JOBS_PER_CALL
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Cookie
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import true

from dispatch.plugins.kandbox_planner.env.env_models import OrderCreationResult
from dispatch.worker import service as worker_service

from dispatch.enums import Visibility
from dispatch.auth.models import DispatchUser
from dispatch.worker.models import Worker

from dispatch.auth.service import get_current_role, get_current_user
from dispatch.database_util.service import common_parameters, search_filter_sort_paginate


from dispatch.auth.models import UserRoles
from dispatch.plugins.kandbox_planner.env.env_enums import (
    JobPlanningStatus,
    JobLifeCycleStatus,
    JobLifeCycleStatus_SEQUENCE,
    OrderCreateResultStatusType,
)
from dispatch.planner_env.planner_service import get_active_planner, replan_job
from .models import JobUpdateWorkerUpdate,JobCreate, JobPagination, JobRead, JobReadResponese, JobUpdate, JobLifeCycleUpdate,JobWorkerChange,JobRelated,JobRelatedUpdate,JobBatchSearch
from .service import job_batch_change_worker, search_filter_paginate_job,set_job_related,create, delete, get, get_by_team, update, get_by_code, get_by_org_id_count, update_life_cycle_info ,get_all,get_job_by_worker,get_reschedule_times
from dispatch.team.service import get as get_team
from dispatch.plugins.kandbox_planner.util.kandbox_util import from_item_list_to_dict
from dispatch.depot import service as depot_service
from dispatch.item import service as item_service
from dispatch.item_inventory import service as inventory_service
from dispatch.item_inventory_event import service as inventory_event_service
from dispatch.job_biz import service as job_biz_service
from dispatch.job import service as job_service

from dispatch.order import service as order_service
from dispatch.problem import service as problem_service
from dispatch.delivery_info import service as delivery_info_service
from dispatch.auth import service as auth_service
from dispatch.exceptions import InvalidConfiguration
from datetime import datetime
from dispatch.cloudmarket.job_event import  service as job_event_service

import logging
log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=JobPagination)
def get_jobs(*, env_key: str = Cookie(default=None), common: dict = Depends(common_parameters), current_user: DispatchUser = Depends(get_current_user),db_session: Session = Depends(get_db),):
    """ """
    # 根据时间降序
    if not common["sort_by"]:
        common["sort_by"] = ["scheduled_primary_worker_code"]
    else:
        common["sort_by"].append("created_at")

    if not common["descending"]:
        common["descending"] = [True]
    else:
        common["descending"].append(True)

    # if common["items_per_page"] < 0 or common["items_per_page"] > MAX_NBR_JOBS_PER_CALL:
    #     raise HTTPException(status_code=400, detail=f"items per page value is too large, values must be (1 - {MAX_NBR_JOBS_PER_CALL}) ...")

    # 针对不是Job的表进行处理,scheduled_primary_worker需要特殊处理
    # for item in ['external_order_code', 'job_track_status', 'scheduled_primary_worker']
    # if common["sort_by"]

    if current_user.role == "Worker":
        
        w = db_session.query(Worker).filter(Worker.dispatch_user_id == current_user.id).one_or_none()
        if w: 
            print(common)
            if "scheduled_primary_worker_code" not in common["fields"]:
                common["fields"].append("scheduled_primary_worker_code")
                common["ops"].append("==")
                # TODO, to fix,  email isnot code
                common["values"].append(current_user.email)

    # 下面的common 也有 db_ssession , 重复传值 db_session 就报错了 
    all_job = search_filter_sort_paginate(
        # db_session = db_session,
        model="Job", 
        **common
    )
    return all_job

    json_all_job = jsonable_encoder(all_job)
    response = JSONResponse(content=json_all_job)
    if env_key is None or env_key[0:3] != "env":
        env_key = f"job_{random.randint(1000, 9000)}"
        # print(f"job rebalance, cookie = {env_key}")
        response.set_cookie(
            key="env_key",
            value=env_key,
            secure=True,  # if using https and not http
            expires=60 * 2,  # * 60 1 hour in seconds
        )

    # test by JobRead(**all_job["items"][0].__dict__)
    return response


# @auth_router.get(
#     "/get_job_no_token/{job_code}/{token}", response_model=JobRead, summary="Retrieve a single job."
# )
# def get_job_no_token(
#     *,
#     db_session: Session = Depends(get_db),
#     job_code: str,
#     token: str,
# ):
#     """
#     Retrieve details about a specific job.
#     """
#     job = get(db_session=db_session, code=job_code)
#     flag = check_edit_job_token(job.code, token)
#     if not flag:
#         raise HTTPException(status_code=400, detail="Permission verification failed.")
#     if not job:
#         raise HTTPException(status_code=404, detail="The requested job does not exist.")

#     return job


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
    job = get(db_session=db_session, code=job_code)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

    return job


@router.post("/", response_model=OrderCreationResult, summary="Create a new job.")
def create_job(
    *,
    db_session: Session = Depends(get_db),
    job_in: JobCreate,
    current_user: DispatchUser = Depends(get_current_user),
    # background_tasks: BackgroundTasks,
):
    """
    Create a new job.
    """
    log.info(f"create_job:received: {job_in.json()}")

    if job_in.geo_longitude is None or job_in.geo_latitude is None:
        if job_in.location is None:
            raise HTTPException(status_code=400, detail="job.geo_longitude/latitude and job.location can not be all empty.")
        job_in.geo_longitude = job_in.location.geo_longitude
        job_in.geo_latitude = job_in.location.geo_latitude
    if job_in.job_type == "pickup" and not job_in.code.endswith("-p"):
        raise HTTPException(
                status_code=400,
                detail=f"Job code {job_in.code} has a wrong name, the job_code must end with -p ",
            )
            
    if not check_job_code_str(job_in.code):
        raise HTTPException(status_code=400, detail="Job code is invalid")

    job = get_by_code(db_session=db_session, code=job_in.code)
    if job:
       raise HTTPException(status_code=400, detail=f"The job with this code ({job_in.code}) already exists.")  

    # try:
    org_service.verify_status(db_session=db_session, org_id=current_user.org_id)
    # limit max job
    org_data = orgService.get(db_session=db_session, org_code=current_user.org_code)
    if not org_data:
        raise HTTPException(status_code=400, detail="The organization failed...")
    
    job_all_count = get_by_org_id_count(db_session=db_session, org_id=current_user.org_id)
    if job_all_count >= org_data.max_nbr_jobs:
        # return {"state": -1, "msg": f"Number of jobs Reached the upper limit", "data": None}
        raise HTTPException(status_code=400, detail=f"Number of jobs reached the upper limit {org_data.max_nbr_jobs}. You can deleted old jobs or upgrade your plan to continue ...")

    job_in.org_id = current_user.org_id

    if job_in.requested_skills:
        job_in.flex_form_data["requested_skills"] = job_in.requested_skills
    if job_in.requested_items:
        job_in.flex_form_data["requested_items"] = job_in.requested_items


    orig_job_dict = {k:v for k,v in job_in.dict().items() if k not in (
        "overwrite_max_orders_limit", "is_appointment")} # "target_worker",
    job = create(
        db_session=db_session,
        org_code=current_user.org_code,
        current_user=current_user,
        **orig_job_dict,
    )

    # background_tasks.add_task(job_create_flow, job_code=job.code)

    if not job.auto_planning:
        return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_BUT_NOT_DISPATCHED,                 
                                order = None,
                                jobs = [job],
                                scheduled_slots = None
                            )

    env = get_active_planner(
        org_id=current_user.org_id, team_id=job.team_id
    )

    worker_whitelist = [] 
    # if "requested_worker_only" in job_in.flex_form_data:
    if str(job_in.flex_form_data.get("requested_worker_only","1")) == "1":
            if job_in.requested_primary_worker is not None:
                worker_whitelist = [job_in.requested_primary_worker.code]

    res = replan_job(
        db_session = db_session,env = env, db_job = job,
        worker_whitelist = worker_whitelist,
        overwrite_max_orders_limit = job_in.overwrite_max_orders_limit,
        is_appointment = job_in.is_appointment,
        )
    # log.info(f"create_order:sending: {res.json()}") # TODO, this reports 500 :(
    log.info(f"create_job:sending:{job.code}: {res.status, res.worker_code, res.scheduled_slots}")
    return res
    

    return {"state": 1, "msg": "The job add succeed", "data": job}
    # except Exception as e:
    #     if len(str(e)) < 2:
    #         err_msg = e.detail
    #     else:
    #         err_msg = str(e)
    #     return {
    #         "state": -1,
    #         "msg": f"add job error,{err_msg}",
    #         "data": None
    #     }




# @auth_router.put(
#     "/update_job_no_token/{job_code}", response_model=JobRead, summary="Update an existing job."
# )
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
#     job = get(db_session=db_session, code=job_code)
#     if not job:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST, detail="The requested job does not exist."
#         )
#     token = job_in.token
#     flag = check_edit_job_token(job.code, token)    
#     if not flag:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED, detail="Permission verification failed."
#         )

#     if job.planning_status == JobPlanningStatus.FINISHED:
#         raise HTTPException(status_code=404, detail="Finish (F) job can not be updated.")
#     if job_in.requested_skills:
#         job_in.flex_form_data["requested_skills"] = job_in.requested_skills
#     if job_in.requested_items:
#         job_in.flex_form_data["requested_items"] = job_in.requested_items

#     if job_in.planning_status == JobPlanningStatus.FINISHED:
#         if job.planning_status == JobPlanningStatus.UNPLANNED:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Unplanned job can be changed to Finished (F).",
#             )
#         # I will deduct items from
#         item_list = job.flex_form_data.get("requested_items", [])
#         if len(item_list) > 0:
#             item_dict = from_item_list_to_dict(item_list)

#             depot = depot_service.get_default_depot(db_session=db_session)
#             depot_code = depot.code
#             for item_code in item_dict.keys():
#                 item = item_service.get_by_code(db_session=db_session, code=item_code)
#                 inv = inventory_service.get_by_item_depot(
#                     db_session=db_session, item_id=item.id, depot_id=depot.id, org_id=org_id
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
#                     depot_id=depot.id,
#                 )
#             db_session.commit()
#     # previous_job = JobRead.from_orm(job)

#     # NOTE: Order matters we have to get the previous state for change detection
#     job = update(db_session=db_session, job=job, job_in=job_in, org_code=org_obj.code)

#     return job



@router.post("/update_job_life_cycle", response_model=JobRead, summary="Update life cycle of an existing job.")
def update_job_life_cycle(
    *,
    db_session: Session = Depends(get_db), 
    job_in: JobLifeCycleUpdate,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    update_job_life_cycle. for workers to update only fulfillment information.
    """
    job_in.update_source = f"{job_in.update_source}, email: {current_user.email}"
    log.info(f"update_job_life_cycle:received: {job_in.json()}")

    
   
    job = None
    
    list_job =[]
    flag = job_in.job_type # 默认= False , 外卖业务
    flex_form_data = job_in.flex_form_data

    
        
    if job_in.code[-2:] =="-d" and not flag:
        
        job_type = job_in.code[-2:]
        all_job = job_service.get_all_by_order_code(db_session=db_session, order_code=job_in.code.rstrip(job_type))
        
        log.info(f"all_job={all_job} ")
        pjob = list(filter(lambda x: x.code[-2:]=="-p",all_job))
        djob = list(filter(lambda x: x.code[-2:]=="-d",all_job))
        
        log.info(f"update_job_life_cycle : pjob_ {pjob} djob_{djob}")
        if not(pjob and pjob[0].life_cycle_status == job_in.life_cycle_status and pjob[0].planning_status ==job_in.life_cycle_status):
            
            try:
                
                job = update_life_cycle_info(
                        db_session=db_session,
                        job_in=job_in,
                        current_user = current_user,
                        job = pjob[0],
                        flex_form_data  = flex_form_data

                        
                        
                )
            except Exception as e:
                log.error(f"update_job_life_cycle is ERROR {str(e)}")
            else:
                list_job.append(job)
        job = update_life_cycle_info(
                    db_session=db_session,
                    job_in=job_in,
                    current_user = current_user,
                    job = djob[0]
            )
        list_job.append(job)
            

    if not job_in.code[-2:] =="-d" or flag:
        job = update_life_cycle_info(
                    db_session=db_session,
                    job_in=job_in,
                    current_user = current_user,
                    )
        list_job.append(job)

    for job_temp in list_job:
        # if job_temp.auto_planning:

        if job_in.life_cycle_status == JobLifeCycleStatus.FINISHED:
            env = get_active_planner(org_id=current_user.org_id, team_id=job_temp.team_id)
            if job_temp.scheduled_primary_worker_code is None:
                log.warning(f"job {job_temp.code} status {job_temp.planning_status}+{job_temp.life_cycle_status} did not save into env because scheduled_primary_worker_code is None")
                continue
            if job_temp.scheduled_start_datetime is None:
                log.error(f"job({job_temp.code}){job_temp.planning_status}+{job_temp.life_cycle_status}.scheduled_start_datetime should not be none!")
                job_temp.scheduled_start_datetime = datetime.now()
            env.mutate_finish_job_in_slot(worker_code=job_temp.scheduled_primary_worker_code,
                                        job_code=job_temp.code,
                                        start_minutes=env.env_encode_from_datetime_to_minutes(job_temp.scheduled_start_datetime),
                                        longitude = job_temp.geo_longitude, latitude=job_temp.geo_latitude
                                        )
        else:
            log.warning(f"job {job_in.code} did not save into env because of status {job_in.life_cycle_status}")
    else:
        log.warning(f"job {job_in.code} did not save into env")
    return job

@router.put("/{job_code}", response_model=JobRead, summary="Update an existing job.")
def update_job(
    *,
    db_session: Session = Depends(get_db),
    job_code: str,
    job_in: JobUpdate,
    current_user: DispatchUser = Depends(get_current_user),
    background_tasks: BackgroundTasks,
):
    """
    Update a job.
    """
    job_in.org_id = current_user.org_id
    job = get(db_session=db_session, code=job_code)
    prev_status = job.planning_status

    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

    if job_in.geo_longitude is None or job_in.geo_latitude is None:
        if job_in.location is None:
            raise HTTPException(status_code=406, detail=f"job.geo_longitude/latitude and  job.location can not all be empty.")
        job_in.geo_longitude = job_in.location.geo_longitude
        job_in.geo_latitude = job_in.location.geo_latitude

    if job_in.code != job.code:
        raise HTTPException(status_code=406, detail="job code can not be changed!")

    if job.planning_status == JobPlanningStatus.FINISHED:
        raise HTTPException(status_code=406, detail="Finish (F) job can not be updated.")

    if (job_in.planning_status == JobPlanningStatus.FINISHED) or (job_in.life_cycle_status == JobPlanningStatus.UNPLANNED):
        job_in.planning_status = JobPlanningStatus.FINISHED
        job_in.life_cycle_status = JobPlanningStatus.FINISHED
        # (job.planning_status == JobPlanningStatus.UNPLANNED):
        # raise HTTPException(
        #         status_code=404, detail="Unplanned job can not be changed to Finished (F)."
        #     )



    if job_in.requested_skills:
        job_in.flex_form_data["requested_skills"] = job_in.requested_skills
    if job_in.requested_items:
        job_in.flex_form_data["requested_items"] = job_in.requested_items

    job = update(
        db_session=db_session,
        job=job,
        job_in=job_in,
        org_code=current_user.org_code,
        current_user=current_user,
    )


    if job.auto_planning:
        if prev_status == JobPlanningStatus.UNPLANNED and job_in.planning_status == JobPlanningStatus.IN_PLANNING:
            log.warning("job api should not update u2i, call planner api instead")
            return job
        if prev_status in (JobPlanningStatus.IN_PLANNING, JobPlanningStatus.PLANNED) and job_in.planning_status == JobPlanningStatus.FINISHED:
            env = get_active_planner(org_id=current_user.org_id, team_id=job.team_id)
            env.mutate_finish_job_in_slot(worker_code=job.scheduled_primary_worker_code,
                                          job_code=job.code,
                                          start_minutes=env.env_encode_from_datetime_to_minutes(job.scheduled_start_datetime),
                                          longitude = job.geo_longitude, latitude=job.geo_latitude
                                          )

    if prev_status in (JobPlanningStatus.IN_PLANNING, JobPlanningStatus.PLANNED) and (
        job_in.planning_status in (JobPlanningStatus.UNPLANNED, ) #  JobPlanningStatus.FINISHED, 
    ):
        try:
            env = get_active_planner(org_id=current_user.org_id, team_id=job.team_id)
            js, slot = env.unplan_job_list( 
                target_job_list = [job], 
                db_session=db_session, 
                commit_ex_slot = True) 
            log.info(f"unplanned job from env: {job.code}")
        except :
            log.warning(f"Failed to update job in env {job.code}")

    if False and job_in.planning_status == JobPlanningStatus.FINISHED:
        # I will deduct items from inventory and worker
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
                    org_id=current_user.org_id,
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
                    depot_id=depot.id,
                )
            db_session.commit()
    # previous_job = JobRead.from_orm(job)
    # old_job_code = copy(job_in.code)
    # NOTE: Order matters we have to get the previous state for change detection
    # if (
    #     job_in.scheduled_primary_worker
    #     and job_in.scheduled_primary_worker.dispatch_user
    #     and (
    #         not job.scheduled_primary_worker
    #         or job_in.scheduled_primary_worker.code != job.scheduled_primary_worker.code
    #     )
    # ):
    #     try:
    #         user = auth_service.get_by_email(db_session=db_session, email=current_user.email)
    #         in_worker = worker_service.get_by_code(db_session=db_session,code = job_in.scheduled_primary_worker.code)
    #         data = job_batch_change_worker(
    #             worker_code=in_worker.code ,dispatch_user_id=in_worker.dispatch_user.id,
    #             job_code_list= [job.code],user_id=user.id,
    #             token=user.token)
    #     except InvalidConfiguration as e:
    #         raise HTTPException(status_code=400, detail=str(e))


    return job




@router.delete(
        "/delete_job_and_job_event/{job_code}", 
        summary="Delete an job and related events.")
def delete_job_and_job_event_interface(*, 
    db_session: Session = Depends(get_db), 
    job_code: str="",
    current_user: DispatchUser = Depends(get_current_user)
    ):
    return delete_job_and_job_event(db_session, job_code, current_user)
    
def delete_job_and_job_event(
    db_session: Session = Depends(get_db), 
    job_code: str="",
    current_user: DispatchUser = Depends(get_current_user)
    ):
    """
    To delete all job_event and the job 
    """
    job = get(db_session=db_session, code=job_code)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")
    if job.order_code is not None:
        raise HTTPException(status_code=404, detail="The job belongs to an order, please go delete order.")


    order_code = job_code.split('-')[0]
    all_job_events = job_event_service.get_all_by_order_code(db_session=db_session, order_code= order_code )
    for job_events in all_job_events:
        db_session.delete(job_events) 
    db_session.commit()
    slots = {}
    # if job.auto_planning:
    if job.planning_status in ("I","P"):
            env = get_active_planner(org_id=current_user.org_id, team_id=job.team_id)
            js, slot = env.unplan_job_list( 
                target_job_list = [job], 
                db_session=db_session, commit_ex_slot = True) 
            if slot:
                slots[ slot.worker_code] =  [
                        _j.to_result(env=env).dict() for _j in slot.assigned_jobs
                    ] 
            else:
                log.warning(f"job {job.code} is in { job.planning_status} status but failed to unplan from env")
    delete(db_session=db_session, code=job.code)
    return JSONResponse({
        "status":200,
        "detail":"delete job success",
        "changed_slots": slots
        })





@router.delete("/{job_code}", summary="Delete an job.")
def delete_job(*, db_session: Session = Depends(get_db), job_code: str,
               current_user: DispatchUser = Depends(get_current_user)):
    """
    Delete a job. This is same as delete_job_and_job_event
    """
    return delete_job_and_job_event(db_session, job_code, current_user)
    job = get(db_session=db_session, code=job_code)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")
    delete(db_session=db_session, code=job.code)
    env = get_active_planner(org_id=current_user.org_id, team_id=job.team_id)
    env.mutate_finish_job_in_slot(worker_code=job.scheduled_primary_worker_code,
                                    job_code=job.code,
                                    start_minutes=env.env_encode_from_datetime_to_minutes(job.scheduled_start_datetime),
                                    longitude = job.geo_longitude, latitude=job.geo_latitude
                                    )

    return True


# @router.get("/live_map/job_list", summary="get live map job data.")
# def get_job_live_map(
#     *,
#     team_id: int = Query(1, alias="team_id"),
#     db_session: Session = Depends(get_db),
#     worker_code: str = None,
#     current_user: DispatchUser = Depends(get_current_user),
# ):
#     """
#     Retrieve details about a specific job.
#     """
#     team = get_team(db_session=db_session, team_id=team_id)
#     job_address_flag = team.flex_form_data.get("job_address_flag", True) if team else True
#     job = get_by_team(db_session=db_session, team_id=team_id)
#     if not job:
#         raise HTTPException(status_code=404, detail="The requested job does not exist.")

#     job_mapping = defaultdict(list)
#     job_data_list = []
#     for _job in job:
#         if worker_code:
#             if not((_job.scheduled_primary_worker and _job.scheduled_primary_worker.code == worker_code) or
#                    (_job.requested_primary_worker and _job.requested_primary_worker.code == worker_code)):
#                 continue
#         if job_address_flag:
#             job_mapping[_job.code] = [_job.code]
#             continue
#         if "composite" == _job.job_type and _job.flex_form_data.get("included_job_codes"):
#             job_mapping[_job.code] = _job.flex_form_data["included_job_codes"]
#     i = 0
#     for composite_code, include_code in job_mapping.items():
#         try:
#             _job_list = [i for i in job if i.code in include_code]
#             location_from = _job_list[0].location if len(_job_list) > 0 else None
#             location_to = _job_list[1].location if len(_job_list) > 1 else None
#             job_data_list.append({
#                 "code": _job_list[0].code,
#                 "location_code_from": f"{location_from.code if location_from else 'None' }_{i}",
#                 "location_code_to": f"{location_to.code if location_to else 'None'}_{i}",
#                 "position_from": {"lat": location_from.geo_latitude if location_from else -1, "lng": location_from.geo_longitude if location_from else -1},
#                 "position_to": {"lat": location_to.geo_latitude if location_to else -1, "lng": location_to.geo_longitude if location_to else -1},
#                 "tooltip": _job_list[0].code,
#                 "visible_to": True if location_to else False,
#                 "visible_from": True if location_from else False,
#             })
#             i += 1
#         except:
#             pass

#     return {"job_data_list": job_data_list, "job_address_flag": job_address_flag}


# @router.get("/live_map/job_pick_drop", summary="get live map job data.")
# def get_job_live_map(
#     *,
#     team_id: int = Query(1, alias="team_id"),
#     start_day: str = Query(None, alias="start_day"),
#     end_day: str = Query(None, alias="end_day"),
#     db_session: Session = Depends(get_db),
#     current_user: DispatchUser = Depends(get_current_user),
# ):
#     """
#     Retrieve details about a specific job.
#     """
#     planner = get_active_planner(org_id=current_user.org_id, team_id=team_id)
#     env = planner["planner_env"]
#     jobs_dict = sorted(env.jobs_dict.items(), key=lambda items: items[1].scheduled_start_minutes)
#     if start_day is None:  # request_in.
#         start_day = '20200101'
#         end_day = '21200101'
#     start_time = datetime.strptime(start_day, config.KANDBOX_DATE_FORMAT)
#     end_time = datetime.strptime(end_day, config.KANDBOX_DATE_FORMAT)
#     start_minutes = env.env_encode_from_datetime_to_minutes(start_time)
#     end_minutes = env.env_encode_from_datetime_to_minutes(end_time)


#     workers_dict = env.workers_dict
#     if not jobs_dict or not workers_dict:
#         return {"job_data_list": [], "job_address_flag": False}

#     all_data = []
#     for worker_code, worker_obj in workers_dict.items():
#         start_location = worker_obj.curr_slot.start_location
#         end_location = worker_obj.curr_slot.end_location
#         worker_code = worker_obj.worker_code
#         type = worker_obj.flex_form_data.get("vehicle_type", "car")
#         _location = f"{start_location.geo_latitude},{start_location.geo_longitude}"
#         i = random.randint(0, 9)
#         position = {
#             "lat": start_location.geo_latitude + 0.0001 * i,
#             "lng": start_location.geo_longitude + 0.0001 * i,
#         }
#         worker_data = {
#             "code": worker_code,
#             "worker_obj": {
#                 "code": worker_code,
#                 "org_id": current_user.org_id,
#             },
#             "position": position,
#             "visible": True,
#             "tooltip": f"{worker_code},{type}",
#             "kpi": {
#                 "total_duration": {
#                     "color": "green",
#                     "value": 0,
#                 },
#                 "jobs_number": {
#                     "color": "green",
#                     "value": 0,
#                 },
#                 "late_delivery": {
#                     "color": "green",
#                     "value": 0,
#                 },
#             },
#             "jobs": [],
#         }
#         i = 1
#         total_duration = 0
#         late_delivery = 0
#         pre_location = start_location
#         location_set = []
#         for job_index, job_list in enumerate(jobs_dict, start=1):
#             job_obj = job_list[1]
#             if (
#                 job_obj.planning_status == JobPlanningStatus.UNPLANNED
#                 or worker_code not in job_obj.scheduled_worker_codes
#             ):
#                 continue
#             location = job_obj.location
#             if "composite" in job_obj.job_code:
#                 continue
#             type = "pick" if "pick" in job_obj.job_code else "drop"
#             _location = f"{location.geo_latitude},{location.geo_longitude}"
#             if _location in location_set:
#                 position = {
#                     "lat": location.geo_latitude + 0.0001,
#                     "lng": location.geo_longitude + 0.0001,
#                 }
#             else:
#                 position = {"lat": location.geo_latitude, "lng": location.geo_longitude}
#             job_data = {
#                 "index": i,
#                 "code": job_obj.job_code,
#                 "position": position,
#                 "visible": True,
#                 "type": type,
#                 "tooltip": f"{job_obj.job_code},,index:{i}",
#             }
#             location_set.append(f"{position['lat']},{position['lng']}")
#             worker_data["jobs"].append(job_data)
#             i += 1
#             travel_minutes = env.travel_router.get_travel_minutes_2locations(
#                 [pre_location.geo_longitude, pre_location.geo_latitude],
#                 [location.geo_longitude, location.geo_latitude],
#             )
#             total_duration += job_obj.requested_duration_minutes + travel_minutes
#             if job_index == len(jobs_dict):
#                 back_minutes = env.travel_router.get_travel_minutes_2locations(
#                     [location.geo_longitude, location.geo_latitude],
#                     [end_location.geo_longitude, end_location.geo_latitude],
#                 )
#                 total_duration += back_minutes

#             pre_location = location
#             if (
#                 "drop" in job_obj.job_code
#                 and job_obj.scheduled_start_minutes > job_obj.requested_start_minutes
#             ):
#                 late_delivery += 1
#         worker_data["kpi"]["total_duration"]["value"] = f"{math.ceil(total_duration)} min"
#         worker_data["kpi"]["jobs_number"]["value"] = len(worker_data["jobs"])
#         worker_data["kpi"]["late_delivery"]["value"] = late_delivery
#         if worker_data["jobs"]:
#             all_data.append(worker_data)

#     return {"job_data_list": all_data, "job_address_flag": False}


@router.post("/batch_search/", response_model=JobPagination)
def batch_search(
    *,
    db_session: Session = Depends(get_db),
    bartch_search_param: JobBatchSearch,
    common: dict = Depends(common_parameters),
    current_user: DispatchUser = Depends(get_current_user),
    role: UserRoles = Depends(get_current_role),
):
    query_param = bartch_search_param.query_param
    scheduled_primary_worker = bartch_search_param.worker_code
    planning_status = bartch_search_param.planning_status
    page = bartch_search_param.page
    items_per_page = bartch_search_param.itemsPerPage
    # sort_by=bartch_search_param.sortBy
    # descending=bartch_search_param.descending
    
    
    if not common["sort_by"]:
        common["sort_by"] = ["scheduled_primary_worker_code"]
    else:
        common["sort_by"].append("created_at")

    if not common["descending"]:
        common["descending"] = [True]
    else:
        common["descending"].append(True)

    query_str = query_param.strip() if query_param else ""
    if "\n" in query_str or "\t" in query_str:
        order_code_list = [i for i in query_str.split() if i]
    else:
        order_code_list = [i for i in query_str.split(" ") if i]

    if order_code_list:
        common["fields"].append('code')
        common["ops"].append('in')
        common["values"].append(order_code_list)
    
    if scheduled_primary_worker:
        common["fields"].append('scheduled_primary_worker_code')
        common["ops"].append('==')
        common["values"].append(scheduled_primary_worker)
    if planning_status :
        list_planning_status = []
        for line in ["I","U","F"]:
            if line in planning_status:
                list_planning_status.append(line)
        if list_planning_status:
            common["fields"].append('planning_status')
            common["ops"].append('in')
            common["values"].append(list_planning_status)
        
            
        
    all_job = search_filter_sort_paginate(

        model="Job", 
        **common
    )
    
    return all_job


# @router.post("/batch_search/", response_model=JobPagination)
# def batch_search(
#     *,
#     db_session: Session = Depends(get_db),
#     bartch_search_param: JobBatchSearch,
#     current_user: DispatchUser = Depends(get_current_user),
#     role: UserRoles = Depends(get_current_role),
# ):
#     """ """
#     query_param = bartch_search_param.query_param
#     scheduled_primary_worker = bartch_search_param.worker_code
#     planning_status = bartch_search_param.planning_status
#     page = bartch_search_param.page
#     items_per_page = bartch_search_param.itemsPerPage
#     sort_by=bartch_search_param.sortBy
#     descending=bartch_search_param.descending

#     query_str = query_param.strip() if query_param else ""
#     if "\n" in query_str or "\t" in query_str:
#         order_code_list = [i for i in query_str.split() if i]
#     else:
#         order_code_list = [i for i in query_str.split(" ") if i]

#     # 搜索过滤分页查询job
#     worker_code = None
#     if 'all' in planning_status:
#         planning_status = []
#     if scheduled_primary_worker:
#         worker_data = worker_service.get_by_code(db_session=db_session,code=scheduled_primary_worker)
#         worker_code = worker_data.code if worker_data else None
#     return_data = search_filter_paginate_job(
#         db_session=db_session,worker_code=worker_code,
#         job_track_status=planning_status,external_order_code=order_code_list, 
#         page=page,items_per_page=items_per_page,
#         current_user=current_user,role=role)

#     result_order_code_list = order_service.find_external_order_code(db_session = db_session,external_order_code=order_code_list)
#     return_data['not_find_code'] = [code for code in order_code_list if code not in result_order_code_list]

#     items = []
#     for item in return_data["items"]:
#         job = item.Job
#         customer_address = item.customer_address
#         customer_zipcode = item.customer_zipcode
#         job_type = item.job_type
#         job_track_status = item.job_track_status
#         external_order_code = item.external_order_code
#         team = job.team
#         location = job.location
#         scheduled_primary_worker = job.scheduled_primary_worker
#         events = job.events
#         requested_primary_worker = job.requested_primary_worker
#         job.job_track_status = job_track_status if job_track_status else ""
#         if job_type in ["pickUp", "backToSc"]:
#             if job and job.location:
#                 job.customer_address = job.location.geo_address_text
#         else:
#             job.customer_address = customer_address
#         job.customer_zipcode = customer_zipcode
#         job.external_order_code = external_order_code
#         items.append(job)
#     return_data["items"] = items
#     return return_data


@router.get("/job_related/", response_model=JobRelated,
            summary = "(Deprecated): To get related information for a job")
def job_related(*, db_session: Session = Depends(get_db),  job_code: str = Query(1, alias="job_code"),
    current_user: DispatchUser = Depends(get_current_user)):
    """
    Get some order messate
    """
    """
    id: int
    order_code: str
    order_code: Optional[str] =None,
    job_biz_job_type: Optional[str] =None,
    job_biz_job_status: Optional[str] =None,
    problem_reason_code:Optional[str] =None,
    customer_address:Optional[str] =None,
    """
    return_data = {
        "id":job_code,
        "order_code":-1,
        "order_code":None,
        "job_biz_job_type":None,
        "job_biz_job_status":None,
        "problem_reason_code":None,
        "customer_address":None,
    }
    job_biz = job_biz_service.get_by_job_code(db_session=db_session,job_code = job_code)
    if  job_biz:
        return_data['order_code'] = job_biz.fk_order_code
        return_data['order_code'] = job_biz.order_code
        return_data['job_biz_job_type'] = job_biz.job_type
        return_data['job_biz_job_status'] = job_biz.job_status
        return_data['job_track_status'] = job_biz.job_track_status
        
        # pickUp
        # backToSc
        if job_biz.job_type in ['pickUp','backToSc']:
            job_data = get(db_session=db_session,code=job_code)
            if job_data and job_data.location:
                return_data["customer_address"] = job_data.location.geo_address_text
        else:
            delivery_info = delivery_info_service.get_by_order_code(
                db_session=db_session, id=job_biz.fk_order_code
            )
            if delivery_info:
                return_data["customer_address"] = delivery_info.customer_address

        user = auth_service.get_by_email(db_session=db_session, email=current_user.email)

        allow_change_time_window_list = get_reschedule_times(job_biz_id=job_biz.id,user_id=user.id,token=user.token)
        if allow_change_time_window_list:            
            return_data['allow_change_time_window_list'] = allow_change_time_window_list

    problem_data = problem_service.get_by_job_code(db_session=db_session,job_code = job_code)

    if problem_data:        
        return_data['problem_reason_code'] = problem_data.reason_code

    problem_data = problem_service.get_by_job_code(db_session=db_session, job_code=job_code)

    if problem_data:
        return_data["problem_reason_code"] = problem_data.reason_code

    return JobRelated(**return_data)



@router.put("/related/{job_code}", summary = "(Deprecated): To update related information for a job")
def update_job_related(
    *, db_session: Session = Depends(get_db), job_code: str, job_related_in: JobRelatedUpdate,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Update a order.
    """    
    job = get(db_session=db_session, code=job_code)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_code} does not exist.")
    
    user = auth_service.get_by_email(db_session=db_session, email=current_user.email)
    job_biz = job_biz_service.get_by_job_code(db_session=db_session,job_code = job.code)
    try:
        if job_biz:
            flag = set_job_related(
                db_session=db_session,
                job=job,
                job_biz=job_biz,
                job_related_in=job_related_in,
                user_id=user.id,
                token=user.token,
            )
        pass
    except InvalidConfiguration as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "msg": "succeed",
        "flag": True,
    }


@router.post("/changeWorker/", summary = "(Alpha, unstable): To change assigned worker for a job")
def batch_change_worker(
    *,
    db_session: Session = Depends(get_db),
    data_in: JobUpdateWorkerUpdate,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Update a order.
    """
    user = auth_service.get_by_email(db_session=db_session, email=current_user.email)
    worker_data = worker_service.get(db_session=db_session, code=data_in.worker_code)
    if not worker_data or not worker_data.dispatch_user:
        raise HTTPException(
            status_code=400,
            detail="The target worker does not exist, or does not have a proper login account.",
        )
    try:
        data = job_batch_change_worker(
            worker_code=data_in.worker_code ,dispatch_user_id=worker_data.dispatch_user.id,
            job_code_list= data_in.job_code_list,user_id=user.id,token=user.token)
    except InvalidConfiguration as e:
        raise HTTPException(status_code=400, detail=str(e))

    for job_code in data_in.job_code_list:
        job = job_biz_service.get_by_job_code(db_session=db_session, id=job_code)
        order_service.set_order_scheduled_primary_worker(
            db_session=db_session, 
            order_code=job.fk_order_code,
            worker_id=data_in.worker_id,
            linked_job_code=job_code,
            source = user.email
        )

    return data

@router.post("/update_job_life_cycle_for_app", response_model=JobRead, summary="Update life cycle of an existing job.")
def update_job_life_cycle_for_app(
    *,
    db_session: Session = Depends(get_db),
    job_in: JobLifeCycleUpdate,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    update_job_life_cycle for app. for workers to update only fulfillment information.
    """
    job_in.update_source = f"{job_in.update_source}, email: {current_user.email}"
    log.info(f"update_job_life_cycle:received: {job_in.json()}")

    job = None

    list_job = []

    flag = job_in.job_type  # 默认= False , 外卖业务

    flex_form_data = job_in.flex_form_data

    if "-" in job_in.code[-2:]:

        job = job_service.get(db_session=db_session, code=job_in.code)
        try:
            job = update_life_cycle_info(
                db_session=db_session,
                job_in=job_in,
                current_user=current_user,
                job=job,
                flex_form_data=flex_form_data
            )
        except Exception as e:
            log.error(f"update_job_life_cycle is ERROR {str(e)}")
        else:
            list_job.append(job)

    for job_temp in list_job:
        if job_temp.auto_planning:
            env = get_active_planner(org_id=current_user.org_id, team_id=job_temp.team_id)
            if job_in.life_cycle_status == JobLifeCycleStatus.FINISHED:
                if job_temp.scheduled_start_datetime is None:
                    log.error(f"job({job.code}).scheduled_start_datetime should not be none!")
                    job_temp.scheduled_start_datetime = datetime.now()
                env.mutate_delete_job_in_slot(worker_code=job_temp.scheduled_primary_worker_code,
                                              job_code=job_temp.code,
                                              start_minutes=env.env_encode_from_datetime_to_minutes(job_temp.scheduled_start_datetime),
                                              longitude=job_temp.geo_longitude, latitude=job_temp.geo_latitude
                                              )

    return job

