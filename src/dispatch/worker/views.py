from dispatch.zulip_server.core import ZulipCore, get_zulip_client_by_org_id
from dispatch.location.models import Location
from dispatch.org import service as orgService
import random
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from dispatch.auth.models import DispatchUser
from dispatch.auth.service import get_current_user
from dispatch.plugins.kandbox_planner.env.env_enums import KafkaMessageType, KandboxMessageSourceType
from dispatch.service.planner_service import get_default_active_planner
from dispatch.team import service as team_service
from dispatch.org import service as org_service
from dispatch.database import get_db
from dispatch.database_util.service import common_parameters, search_filter_sort_paginate

from .models import (
    Worker,
    WorkerCreate,
    WorkerPagination,
    WorkerRead,
    WorkerUpdate,
)
from .service import check_zulip_user_id, create, delete, get, get_by_code_org_id, get_by_org_id_count, get_by_team, get_by_code, get_count_by_active, update

router = APIRouter()


@router.get("/", response_model=WorkerPagination)
def get_workers(*, common: dict = Depends(common_parameters)):
    """
    """
    return search_filter_sort_paginate(model="Worker", **common)


@router.get("/select/", response_model=WorkerPagination)
def select_workers(
    db_session: Session = Depends(get_db),
    page: int = 1,
    items_per_page: int = Query(5, alias="itemsPerPage"),
    query_str: str = Query(None, alias="q"),
    sort_by: List[str] = Query(None, alias="sortBy[]"),
    descending: List[bool] = Query(None, alias="descending[]"),
    fields: List[str] = Query([], alias="fields[]"),
    ops: List[str] = Query([], alias="ops[]"),
    values: List[str] = Query([], alias="values[]"),
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve worker contacts.
    """

    return {
        "items": db_session.query(Worker).filter(Worker.org_id == current_user.org_id, Worker.code.like(f'%{query_str}%')).limit(10).all(),
        "itemsPerPage": 0,
        "page": 1,
        "total": 0,
    }


@router.post("/", response_model=WorkerRead)
def create_worker(*, db_session: Session = Depends(get_db), worker_in: WorkerCreate,
                  current_user: DispatchUser = Depends(get_current_user)):
    """
    Create a new worker contact.
    """
    # limit max
    org_data = orgService.get(db_session=db_session, org_code=current_user.org_code)
    if not org_data:
        raise HTTPException(status_code=400, detail="org not exists")
    max_nbr_worker = org_data.max_nbr_workers

    if worker_in.skills:
        worker_in.flex_form_data['skills'] = worker_in.skills
    if worker_in.loaded_items:
        worker_in.flex_form_data['loaded_items'] = worker_in.loaded_items
    job_all_count = get_by_org_id_count(db_session=db_session, org_id=current_user.org_id)
    if job_all_count >= max_nbr_worker:
        raise HTTPException(status_code=400, detail="Worker Reached the upper limit")
    worker_in.org_id = current_user.org_id
    worker = get_by_code_org_id(db_session=db_session,
                                code=worker_in.code, org_id=current_user.org_id)

    team = team_service.get_by_code(db_session=db_session, code=worker_in.team.code)

    # use zulip
    zulip_user_id = worker_in.flex_form_data.get("zulip_user_id", None)
    result = None
    zulip_dict = get_zulip_client_by_org_id(current_user.org_id)
    if zulip_dict and zulip_user_id and worker_in.team.flex_form_data.get('use_zulip', False):
        flag, worker_code = check_zulip_user_id(db_session=db_session,
                                                zulip_user_id=zulip_user_id, team_id=team.id)
        if not flag:
            raise HTTPException(
                status_code=400, detail=f"The worker zulip_user_id already exists in {worker_code}")
        zulip_core = zulip_dict['client']
        result = zulip_core.update_add_subscribe_user_group(
            worker_in, org_code=current_user.org_code, team_code=team.code, flag=True)
    if result and result['result'] != 'success':
        raise HTTPException(
            status_code=400, detail=f"{result['msg']}")
    # add worker
    if worker:
        raise HTTPException(status_code=400, detail="The worker with this code already exists.")
    worker = create(db_session=db_session, worker_in=worker_in)

    # change to env
    if current_user.org_code and team.id:
        message_dict = transfrom_worker_data(worker, team)
        post_worker_to_env(message_dict, current_user.org_code, team.id, False)

    return worker


@router.get("/{worker_id}", response_model=WorkerRead)
def get_worker(*, db_session: Session = Depends(get_db), worker_id: int):
    """
    Get a worker contact.
    """
    worker = get(db_session=db_session, worker_id=worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="The worker with this id does not exist.")
    return worker


@router.put("/{worker_id}", response_model=WorkerRead)
def update_worker(
    *,
    db_session: Session = Depends(get_db),
    worker_id: int,
    worker_in: WorkerUpdate, current_user: DispatchUser = Depends(get_current_user)
):
    """
    Update a worker contact.
    """
    worker_in.org_id = current_user.org_id
    worker = get(db_session=db_session, worker_id=worker_id)
    code_change = False
    if worker_in.code != worker.code:
        code_change = True
    change_active = False
    if worker_in.is_active != worker.is_active:
        change_active = True
        count = get_count_by_active(db_session=db_session, is_active=True)
        if count < 2 and not worker_in.is_active:
            raise HTTPException(status_code=404, detail="There must be a normal worker.")

    if not worker:
        raise HTTPException(status_code=404, detail="The worker with this id does not exist.")
    if worker_in.skills:
        worker_in.flex_form_data['skills'] = worker_in.skills
    if worker_in.loaded_items:
        worker_in.flex_form_data['loaded_items'] = worker_in.loaded_items

    team = team_service.get_by_code(db_session=db_session, code=worker_in.team.code)
    # use zulip
    zulip_user_id = worker_in.flex_form_data.get("zulip_user_id", None)
    old_user_id = worker.flex_form_data.get("zulip_user_id", None)
    result = None
    zulip_dict = get_zulip_client_by_org_id(current_user.org_id)
    if zulip_dict and zulip_user_id and zulip_user_id != old_user_id and worker_in.team.flex_form_data.get('use_zulip', False):
        flag, worker_code = check_zulip_user_id(db_session=db_session,
                                                zulip_user_id=zulip_user_id, team_id=team.id)
        if not flag:
            raise HTTPException(
                status_code=400, detail=f"The worker zulip_user_id already exists in {worker_code}")

        zulip_core = zulip_dict['client']
        result = zulip_core.update_add_subscribe_user_group(
            worker_in, org_code=current_user.org_code, team_code=team.code, flag=True)
    if result and result['result'] != 'success':
        raise HTTPException(
            status_code=400, detail=f"{result['msg']}")

    worker = update(
        db_session=db_session,
        worker=worker,
        worker_in=worker_in
    )
    if current_user.org_code and team.id:
        message_dict = transfrom_worker_data(worker, team)
        post_worker_to_env(message_dict, current_user.org_code,
                           team.id, any([code_change, change_active]))
    return worker


@router.put("/worker_code/{worker_code}", response_model=WorkerRead)
def update_worker_by_code(
    *,
    db_session: Session = Depends(get_db),
    worker_code: str,
    worker_in: WorkerUpdate, current_user: DispatchUser = Depends(get_current_user)
):
    """
    Update a worker contact.
    """
    worker_in.org_id = current_user.org_id
    worker = get_by_code(db_session=db_session, code=worker_code)
    code_change = False
    if worker_in.code != worker.code:
        code_change = True
    change_active = False
    if worker_in.is_active != worker.is_active:
        change_active = True
        count = get_count_by_active(db_session=db_session, is_active=True)
        if count < 2 and not worker_in.is_active:
            raise HTTPException(status_code=404, detail="There must be a normal worker.")

    if not worker:
        raise HTTPException(status_code=404, detail="The worker with this id does not exist.")
    if worker_in.requested_skills:
        worker_in.flex_form_data['requested_skills'] = worker_in.requested_skills

    team = team_service.get_by_code(db_session=db_session, code=worker_in.team.code)
    # use zulip
    zulip_user_id = worker_in.flex_form_data.get("zulip_user_id", None)
    old_user_id = worker.flex_form_data.get("zulip_user_id", None)
    result = None

    zulip_dict = get_zulip_client_by_org_id(current_user.org_id)
    if zulip_dict and zulip_user_id and zulip_user_id != old_user_id and worker_in.team.flex_form_data.get('use_zulip', False):
        flag, worker_code = check_zulip_user_id(db_session=db_session,
                                                zulip_user_id=zulip_user_id, team_id=team.id)
        if not flag:
            raise HTTPException(
                status_code=400, detail=f"The worker zulip_user_id already exists in {worker_code}")
        zulip_core = zulip_dict['client']
        result = zulip_core.update_add_subscribe_user_group(
            worker_in, org_code=current_user.org_code, team_code=team.code, flag=True)

    if result and result['result'] != 'success':
        raise HTTPException(
            status_code=400, detail=f"{result['msg']}")
    worker = update(
        db_session=db_session,
        worker=worker,
        worker_in=worker_in,
    )
    if current_user.org_code and team.id:
        message_dict = transfrom_worker_data(worker, team)
        post_worker_to_env(message_dict, current_user.org_code,
                           team.id, any([code_change, change_active]))
    return worker


@router.delete("/{worker_id}")
def delete_worker(*, db_session: Session = Depends(get_db), worker_id: int, current_user: DispatchUser = Depends(get_current_user)):
    """
    Delete a worker contact.
    """
    worker = get(db_session=db_session, worker_id=worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="The worker with this id does not exist.")

    delete(db_session=db_session, worker_id=worker_id)
    # use zulip
    zulip_dict = get_zulip_client_by_org_id(current_user.org_id)
    if zulip_dict:
        zulip_core = zulip_dict['client']
        team = team_service.get(db_session=db_session, team_id=worker.team_id)
        worker.team = team
        zulip_core.update_add_subscribe_user_group(
            worker, org_code=current_user.org_code, team_code=worker.team.code, flag=False)


@router.get("/all/worker_list")
def worker_list(*,
                team_id: int = Query(1, alias="team_id"),
                db_session: Session = Depends(get_db)):
    """
    Retrieve worker contacts.
    """
    data = get_by_team(db_session=db_session, team_id=team_id)

    return_data = []
    for worker in data:
        lass_than_5min = random.randint(75, 85)
        min5_min10 = random.randint(15, 100 - lass_than_5min)
        more_than_10min = 100 - lass_than_5min - min5_min10
        cater_rate = random.randint(80, 100)
        monthly_jobs_completed = random.randint(10, 300)
        cater_rate_color = "green"
        if cater_rate < 90:
            cater_rate_color = "red"
        elif cater_rate < 95:
            cater_rate_color = "orange"
        monthly_jobs_completed_color = "green"
        if cater_rate < 50:
            monthly_jobs_completed_color = "red"
        elif cater_rate < 150:
            monthly_jobs_completed_color = "orange"
        if not worker.location or not worker.location.geo_latitude:
            continue
        return_data.append({
            "id": worker.code,
            "position": {"lat": worker.location.geo_latitude, "lng": worker.location.geo_longitude},
            "tooltip": worker.code,
            "visible": True,
            "kpi": {
                "cater_rate": {
                    "color": cater_rate_color,
                    "value": f"{cater_rate}%",
                },
                "passenger_waiting_lt_5min": {
                    "color": "green",
                    "value": f"{lass_than_5min}%",
                },
                "passenger_waiting_min5_min10": {
                    "color": "orange",
                    "value": f"{min5_min10}%",
                },
                "passenger_waiting_gt_10min": {
                    "color": "red",
                    "value": f"{more_than_10min}%",

                },
                "monthly_jobs_completed": {
                    "color": monthly_jobs_completed_color,
                    "value": f"{monthly_jobs_completed}",
                },
            }
        })
    return return_data


def post_worker_to_env(message_dict, org_code, team_id, code_change):

    planner = get_default_active_planner(org_code=org_code, team_id=team_id)
    rl_env = planner["planner_env"]
    kafka_server = rl_env.kafka_server

    if code_change:
        rl_env.reload_data_from_db_adapter(
            rl_env.env_start_datetime,
            end_datetime=rl_env.env_decode_from_minutes_to_datetime(
                rl_env.get_env_planning_horizon_end_minutes())
        )
        rl_env._reset_data()
    else:

        message_type = KafkaMessageType.CREATE_WORKER if not rl_env.workers_dict.get(
            message_dict['code']) else KafkaMessageType.UPDATE_WORKER

        msg = {
            "message_type": message_type,
            "message_source_type": KandboxMessageSourceType.ENV,
            "message_source_code": "USER.Web",
            "payload": [message_dict],
        }
        kafka_server.process_env_message(msg=msg, auto_replay_in_process=False)


def transfrom_worker_data(worker_obj, team):
    if not worker_obj.location:
        mean_long = (team.flex_form_data.get("geo_longitude_max", 0) +
                     team.flex_form_data.get("geo_longitude_min", 0)) / 2
        mean_lat = (team.flex_form_data.get("geo_latitude_max", 0) +
                    team.flex_form_data.get("geo_latitude_min", 0)) / 2
        location = Location(
            location_code='central_loc',
            geo_longitude=mean_long,
            geo_latitude=mean_lat,
            geo_address_text='central_loc'
        )
        worker_obj.location = location
    _worker_dict = {}
    _worker_dict['flex_form_data'] = worker_obj.flex_form_data
    _worker_dict['business_hour'] = worker_obj.business_hour
    _worker_dict['location_code'] = worker_obj.location.location_code
    _worker_dict['job_history_feature_data'] = {}
    _worker_dict['geo_longitude'] = worker_obj.location.geo_longitude
    _worker_dict['geo_latitude'] = worker_obj.location.geo_latitude
    _worker_dict['worker_code'] = worker_obj.code
    _worker_dict['is_active'] = worker_obj.is_active
    _worker_dict['code'] = worker_obj.code
    _worker_dict['worker_obj'] = worker_obj
    _worker_dict['id'] = int(worker_obj.id)

    return _worker_dict
