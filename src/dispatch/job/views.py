from fastapi import status
import redis
from dispatch.auth.views import auth_router
import math
import random
from dispatch.common.utils.encryption import check_edit_job_token
from dispatch.database import get_db
from dispatch.org import service as orgService
from collections import defaultdict
import string
from typing import List
from dispatch.config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import true
from dispatch import worker

from dispatch.enums import Visibility
from dispatch.auth.models import DispatchUser
from dispatch.auth.service import get_current_user
from dispatch.database_util.service import common_parameters, search_filter_sort_paginate


from dispatch.auth.models import UserRoles
from dispatch.plugins.kandbox_planner.env.env_enums import JobPlanningStatus, JobLifeCycleStatus, JobLifeCycleStatus_SEQUENCE
from dispatch.service.planner_service import get_default_active_planner
from .models import JobCreate, JobPagination, JobRead, JobReadResponese, JobUpdate, JobLifeCycleUpdate
from .service import create, delete, get, get_by_team, update, get_by_code, get_by_org_id_count, update_life_cycle_info
from dispatch.team.service import get as get_team
from dispatch.plugins.kandbox_planner.util.kandbox_util import from_item_list_to_dict
from dispatch.depot import service as depot_service
from dispatch.item import service as item_service
from dispatch.item_inventory import service as inventory_service
from dispatch.item_inventory_event import service as inventory_event_service

router = APIRouter()


@router.get(
    "/", response_model=JobPagination
)
def get_jobs(*, common: dict = Depends(common_parameters)):
    """
    """
    # 根据时间降序
    if not common["sort_by"]:
        common["sort_by"] = ["scheduled_primary_worker_id"]
    else:
        common["sort_by"].append("created_at")

    if not common["descending"]:
        common["descending"] = [True]
    else:
        common["descending"].append(True)
    return search_filter_sort_paginate(model="Job", **common)


@auth_router.get("/get_job_no_token/{job_id}/{token}", response_model=JobRead, summary="Retrieve a single job.")
def get_job_no_token(
    *,
    db_session: Session = Depends(get_db),
    job_id: int,
    token: str,
):
    """
    Retrieve details about a specific job.
    """
    job = get(db_session=db_session, job_id=job_id)
    flag = check_edit_job_token(job.id, token)
    if not flag:
        raise HTTPException(status_code=400, detail="Permission verification failed.")
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

    return job


@router.get("/{job_id}", response_model=JobRead, summary="Retrieve a single job.")
def get_job(
    *,
    db_session: Session = Depends(get_db),
    job_id: str,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve details about a specific job.
    """
    job = get(db_session=db_session, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

    return job


@router.post("/", response_model=JobReadResponese, summary="Create a new job.")
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
    try:
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

        job = create(db_session=db_session, org_code=current_user.org_code, **job_in.dict())

        # background_tasks.add_task(job_create_flow, job_id=job.id)

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


@auth_router.put("/update_job_no_token/{job_id}", response_model=JobRead, summary="Update an existing job.")
def update_job_no_token(
    *,
    db_session: Session = Depends(get_db),
    job_id: str,
    job_in: JobUpdate,
    background_tasks: BackgroundTasks,
):
    """
    Update an worker job.
    """
    org_id = int(job_in.org_id)
    org_obj = orgService.get(db_session=db_session, org_id=org_id)
    job = get(db_session=db_session, job_id=job_id)
    token = job_in.token
    flag = check_edit_job_token(job.id, token)
    if not flag:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Permission verification failed.")
    if not job:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="The requested job does not exist.")

    if job.planning_status == JobPlanningStatus.FINISHED:
        raise HTTPException(status_code=404, detail="Finish (F) job can not be updated.")
    if job_in.requested_skills:
        job_in.flex_form_data['requested_skills'] = job_in.requested_skills
    if job_in.requested_items:
        job_in.flex_form_data['requested_items'] = job_in.requested_items

    if job_in.planning_status == JobPlanningStatus.FINISHED:
        if job.planning_status == JobPlanningStatus.UNPLANNED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Unplanned job can be changed to Finished (F).")
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
                    org_id=org_id
                ).first()
                inv.allocated_qty -= item_dict[item_code]
                if inv.allocated_qty < 0:
                    inv.curr_qty += inv.allocated_qty
                    inv.allocated_qty = 0
                if inv.curr_qty < 0:
                    e_msg = f"Not enough inventory for item: {item_code}, depot: {depot_code}, org.id: {org_id}"
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

    # NOTE: Order matters we have to get the previous state for change detection
    job = update(db_session=db_session, job=job, job_in=job_in, org_code=org_obj.code)

    return job


@router.put("/update_job_life_cycle/{job_id}", response_model=JobRead, summary="Update life cycle of an existing job.")
def update_job_life_cycle(
    *,
    db_session: Session = Depends(get_db),
    job_id: str,
    job_in: JobLifeCycleUpdate,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    update_job_life_cycle. for workers to update only fulfillment information.
    """
    # job_in.org_id = current_user.org_id
    job = get(db_session=db_session, job_id=job_id)

    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

    if JobLifeCycleStatus_SEQUENCE[job.life_cycle_status] > JobLifeCycleStatus_SEQUENCE[job_in.life_cycle_status]:
        raise HTTPException(
            status_code=404, detail=f"life cycle status {job.life_cycle_status} --> {job_in.life_cycle_status} is not allowed. ")

    update_life_cycle_info(
        db_session=db_session,
        job_in=job_in,
    )

    return job


@router.put("/{job_id}", response_model=JobRead, summary="Update an existing job.")
def update_job(
    *,
    db_session: Session = Depends(get_db),
    job_id: str,
    job_in: JobUpdate,
    current_user: DispatchUser = Depends(get_current_user),
    background_tasks: BackgroundTasks,
):
    """
    Update an worker job.
    """
    job_in.org_id = current_user.org_id
    job = get(db_session=db_session, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

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
                    e_msg = f"Not enough inventory for item: {item_code}, depot: {depot_code}, org.id: {self.org_id}"
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

    # NOTE: Order matters we have to get the previous state for change detection
    job = update(db_session=db_session, job=job, job_in=job_in, org_code=current_user.org_code)

    return job


@router.post("/{job_id}/join", summary="Join an job.")
def join_job(
    *,
    db_session: Session = Depends(get_db),
    job_id: str,
    current_user: DispatchUser = Depends(get_current_user),
    background_tasks: BackgroundTasks,
):
    """
    Join an worker job.
    """
    job = get(db_session=db_session, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

    background_tasks.add_task(
        job_add_or_reactivate_participant_flow, current_user.code, job_id=job.id
    )


@router.delete("/{job_id}", summary="Delete an job.")
def delete_job(*, db_session: Session = Depends(get_db), job_id: str):
    """
    Delete an worker job.
    """
    job = get(db_session=db_session, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")
    delete(db_session=db_session, job_id=job.id)
    return True


@router.get("/metric/forecast/{job_type}", summary="Get job forecast data.")
def get_job_forecast(*, db_session: Session = Depends(get_db), job_type: str):
    """
    Get job forecast data.
    """
    return make_forecast(db_session=db_session, job_type=job_type)


@router.get("/live_map/job_list", summary="get live map job data.")
def get_job_live_map(
    *,
    team_id: int = Query(1, alias="team_id"),
    db_session: Session = Depends(get_db),
    worker_code: str = None,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve details about a specific job.
    """
    team = get_team(db_session=db_session, team_id=team_id)
    job_address_flag = team.flex_form_data.get('job_address_flag', True) if team else True
    job = get_by_team(db_session=db_session, team_id=team_id)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

    job_mapping = defaultdict(list)
    job_data_list = []
    for _job in job:
        if worker_code:
            if not((any([i for i in _job.scheduled_secondary_workers if i.code == worker_code])) or
                    (_job.scheduled_primary_worker and _job.scheduled_primary_worker.code == worker_code) or
                   (_job.requested_primary_worker and _job.requested_primary_worker.code == worker_code)):
                continue
        if job_address_flag:
            job_mapping[_job.code] = [_job.code]
            continue
        if 'composite' == _job.job_type and _job.flex_form_data.get('included_job_codes'):
            job_mapping[_job.code] = _job.flex_form_data['included_job_codes']
    i = 0
    for composite_code, include_code in job_mapping.items():
        try:
            _job_list = [i for i in job if i.code in include_code]
            location_from = _job_list[0].location if len(_job_list) > 0 else None
            location_to = _job_list[1].location if len(_job_list) > 1 else None
            job_data_list.append({
                "id": _job_list[0].code,
                "location_code_from": f"{location_from.location_code if location_from else 'None' }_{i}",
                "location_code_to": f"{location_to.location_code if location_to else 'None'}_{i}",
                "position_from": {"lat": location_from.geo_latitude if location_from else -1, "lng": location_from.geo_longitude if location_from else -1},
                "position_to": {"lat": location_to.geo_latitude if location_to else -1, "lng": location_to.geo_longitude if location_to else -1},
                "tooltip": _job_list[0].code,
                "visible_to": True if location_to else False,
                "visible_from": True if location_from else False,
            })
            i += 1
        except:
            pass

    return {"job_data_list": job_data_list,
            "job_address_flag": job_address_flag
            }


@router.get("/live_map/job_pick_drop", summary="get live map job data.")
def get_job_live_map(
    *,
    team_id: int = Query(1, alias="team_id"),
    db_session: Session = Depends(get_db),
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve details about a specific job.
    """
    org_code = current_user.org_code

    planner = get_default_active_planner(org_code=org_code, team_id=team_id)
    env = planner['planner_env']
    jobs_dict = sorted(env.jobs_dict.items(), key=lambda items: items[1].scheduled_start_minutes)
    workers_dict = env.workers_dict
    if not jobs_dict or not workers_dict:
        raise HTTPException(status_code=404, detail="env job and worker is not exist.")

    all_data = []
    for worker_code, worker_obj in workers_dict.items():
        start_location = worker_obj.curr_slot.start_location
        end_location = worker_obj.curr_slot.end_location
        worker_code = worker_obj.worker_code
        type = worker_obj.flex_form_data.get('vehicle_type', 'car')
        _location = f"{start_location.geo_latitude},{start_location.geo_longitude}"
        i = random.randint(0, 9)
        position = {"lat": start_location.geo_latitude + 0.0001 * i,
                    "lng": start_location.geo_longitude + 0.0001 * i}
        worker_data = {
            "code": worker_code,
            "worker_obj": {
                "code": worker_code,
                "org_id": current_user.org_id,
            },
            "position": position,
            "visible": True,
            "tooltip": f"{worker_code},{type}",
            "kpi": {
                "total_duration": {
                    "color": "green",
                    "value": 0,
                },
                "jobs_number": {
                    "color": "green",
                    "value": 0,
                },
                "late_delivery": {
                    "color": "green",
                    "value": 0,
                }
            },
            "jobs": []
        }
        i = 1
        total_duration = 0
        late_delivery = 0
        pre_location = start_location
        location_set = []
        for job_index, job_list in enumerate(jobs_dict, start=1):
            job_obj = job_list[1]
            if job_obj.planning_status == JobPlanningStatus.UNPLANNED or worker_code not in job_obj.scheduled_worker_codes:
                continue
            location = job_obj.location
            if 'composite' in job_obj.job_code:
                continue
            type = 'pick' if 'pick' in job_obj.job_code else 'drop'
            _location = f"{location.geo_latitude},{location.geo_longitude}"
            if _location in location_set:
                position = {"lat": location.geo_latitude + 0.0001,
                            "lng": location.geo_longitude + 0.0001}
            else:
                position = {"lat": location.geo_latitude,
                            "lng": location.geo_longitude}
            job_data = {
                "index": i,
                "code": job_obj.job_code,
                "position": position,
                "visible": True,
                "type": type,
                "tooltip": f"{job_obj.job_code},,index:{i}"
            }
            location_set.append(f"{position['lat']},{position['lng']}")
            worker_data['jobs'].append(job_data)
            i += 1
            travel_minutes = env.travel_router.get_travel_minutes_2locations(
                [pre_location.geo_longitude, pre_location.geo_latitude],
                [location.geo_longitude, location.geo_latitude],
            )
            total_duration += job_obj.requested_duration_minutes + travel_minutes
            if job_index == len(jobs_dict):
                back_minutes = env.travel_router.get_travel_minutes_2locations(
                    [location.geo_longitude, location.geo_latitude],
                    [end_location.geo_longitude, end_location.geo_latitude],
                )
                total_duration += back_minutes

            pre_location = location
            if 'drop' in job_obj.job_code and job_obj.scheduled_start_minutes > job_obj.requested_start_minutes:
                late_delivery += 1
        worker_data['kpi']['total_duration']["value"] = f"{math.ceil(total_duration)} min"
        worker_data['kpi']['jobs_number']["value"] = len(worker_data['jobs'])
        worker_data['kpi']['late_delivery']["value"] = late_delivery
        if worker_data['jobs']:
            all_data.append(worker_data)

    return {"job_data_list": all_data, "job_address_flag": False}
