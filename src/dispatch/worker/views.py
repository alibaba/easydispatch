import copy
from dispatch.common.utils.string_checker import check_worker_code_str
from dispatch.plugins.kandbox_planner.env.env_models import WorkingTimeSlot
# from dispatch.zulip_server.core import get_zulip_client_by_org_id
from dispatch.location.models import Location
import random
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from dispatch.auth.models import DispatchUser, UserRegister, UserRoles
from dispatch.auth.service import get_current_user
from dispatch.plugins.kandbox_planner.env.env_enums import (
    KafkaMessageType,
    KandboxMessageSourceType,
)
from dispatch.planner_env.planner_service import (
    get_active_planner, 
)
from dispatch.team import service as team_service
from dispatch.database_util.service import common_parameters, search_filter_sort_paginate
from dispatch.database import get_db
from dispatch.org import service as org_service
from dispatch.auth import service as auth_service

from .models import (
    Worker,
    WorkerCreate,
    WorkerPagination,
    WorkerRead,
    WorkerUpdate,
    WorkerUpdateBusinessHour,
)
import psycopg2
from .service import (
    check_zulip_user_id,
    get_by_org_id,
    get_count_by_active,
    create,
    delete,
    get,
    get_by_code_org_id,
    get_by_org_id_count,
    get_by_team,
    get_by_code,
    update, 
    update_business_hour,
    create_dipatch_core_user,
)

from dispatch.job import service as job_service 
import logging
from dispatch.config import WORKER_COLOR_ITER 
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=WorkerPagination)
def get_workers(*, common: dict = Depends(common_parameters)):

    return search_filter_sort_paginate(model="Worker", **common)


@router.get("/{worker_code}", response_model=WorkerRead)
def get_worker(*, db_session: Session = Depends(get_db), worker_code: str):
    """
    Get a worker.
    """
    worker = get(db_session=db_session, code=worker_code)
    if not worker:
        raise HTTPException(status_code=404, detail="The worker with this id does not exist.")
    return worker


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
    Retrieve workers.
    """

    return {
        "items": db_session.query(Worker)
        .filter(Worker.org_id == current_user.org_id, Worker.code.like(f"%{query_str}%"))
        .limit(10)
        .all(),
        "itemsPerPage": 0,
        "page": 1,
        "total": 0,
    }


@router.post("/", response_model=WorkerRead)
def create_worker(
    *,
    db_session: Session = Depends(get_db),
    worker_in: WorkerCreate,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Create a worker.
    """
    
    
    org_service.verify_status(db_session=db_session, org_id=current_user.org_id)
    if not check_worker_code_str(worker_in.code):
        raise HTTPException(status_code=400, detail="Worker code is invalid")

    # limit max
    org_data = org_service.get(db_session=db_session, org_code=current_user.org_code)
    if not org_data:
        raise HTTPException(status_code=500, detail="Internal error, orgnization does not exists")

    if worker_in.skills:
        worker_in.flex_form_data["skills"] = worker_in.skills
    # if worker_in.loaded_items:
    #     if "accum_items" not in worker_in.flex_form_data:
    #         worker_in.flex_form_data["accum_items"] = worker_in.loaded_items
        
    # 迭代器 , 选取 worker live_map_color , cycle 循环
    # TODO, allow customer to fill in color. Fill in random only when missing.
    if "live_map_color" not in worker_in.flex_form_data:
        worker_color = next(WORKER_COLOR_ITER)
        worker_in.flex_form_data['live_map_color'] = worker_color
    
    job_all_count = get_by_org_id_count(db_session=db_session, org_id=current_user.org_id)
    if job_all_count >= org_data.max_nbr_workers:
        raise HTTPException(status_code=400, detail=f"Number of Workers reached the limit {org_data.max_nbr_workers}. You can deleted some workers or upgrade your plan to continue ...")
    worker_in.org_id = current_user.org_id
    worker = get_by_code_org_id(
        db_session=db_session, code=worker_in.code, org_id=current_user.org_id
    )
    # add worker
    if worker:
        raise HTTPException(status_code=400, detail=f"The worker with code {worker_in.code} already exists.")

    team = team_service.get_by_code(db_session=db_session, code=worker_in.team.code)
    if not team:
        raise HTTPException(
            status_code=400, detail=f"Specified team (code = {worker_in.team.code}) does not exists"
        )

    if worker_in.geo_longitude is None or worker_in.geo_latitude is None:
        if worker_in.location  is None:
            raise HTTPException(status_code=400, detail=f"worker.geo_longitude/latitude and  worker.location can not all be Empty")
        worker_in.geo_longitude = worker_in.location.geo_longitude
        worker_in.geo_latitude = worker_in.location.geo_latitude
        
    # use zulip
    # zulip_user_id = worker_in.flex_form_data.get("zulip_user_id", None)
    # result = None
    # zulip_dict = get_zulip_client_by_org_id(current_user.org_id)
    # if zulip_dict and zulip_user_id and worker_in.team.flex_form_data.get("use_zulip", False):
    #     flag, worker_code = check_zulip_user_id(
    #         db_session=db_session, zulip_user_id=zulip_user_id, team_id=team.id
    #     )
    #     if not flag:
    #         raise HTTPException(
    #             status_code=400, detail=f"The worker zulip_user_id already exists in {worker_code}"
    #         )
    #     zulip_core = zulip_dict["client"]
    #     result = zulip_core.update_add_subscribe_user_group(
    #         worker_in, org_code=current_user.org_code, team_code=team.code, flag=True
    #     )
    # if result and result["result"] != "success":
    #     raise HTTPException(status_code=400, detail=f"{result['msg']}")

    # create default account for worker
    regist_flag = str(worker_in.flex_form_data.get("regist_default_account", "0")) == "1"
    mobile_phone = worker_in.flex_form_data.get("mobile_phone", None)
    login_password = worker_in.flex_form_data.get("login_password", mobile_phone)
    worker_role = worker_in.flex_form_data.get("worker_role", UserRoles.WORKER)
    if regist_flag and mobile_phone:
        mobile_phone = str(mobile_phone)
        user_data = auth_service.get_by_email(db_session=db_session, email=mobile_phone)
        if user_data:
            raise HTTPException(status_code=400, detail=f"account already exists.  {mobile_phone}")
        user = UserRegister(
            email=mobile_phone,
            password=login_password,
            role=worker_role,
            org_id=org_data.id,
            org_code=org_data.code,
            en_code=None,
            is_active=True,
            is_org_owner=True,
            is_team_owner=True,
            default_team_id=team.id,
            # import_sample_data=False,
        )
        in_user = auth_service.create(db_session=db_session, user_in=user)
        worker_in.dispatch_user = in_user
    try:
        worker = create(db_session=db_session, worker_in=worker_in)
    except psycopg2.errors.UniqueViolation as e:
        raise HTTPException(status_code=400, detail="Duplication error.")

    # post worker change to planning env
    if worker.auto_planning and worker.is_shift_started:
        log.error("Not implemented, worker.auto_planning ")

        # env = get_active_planner(org_id=current_user.org_id, team_id=worker.team_id)
        # new_slot = WorkingTimeSlot(
        #     slot_code=f"{worker_code}_{int(start_minutes)}",
        #     slot_type = TimeSlotType.FLOATING,
        #     worker_code=curr_worker_dict["worker_code"],
        #     available_free_minutes = new_slot_available_minutes,
        #     start_minutes=start_minutes,
        #     end_minutes=end_minutes,
        #     start_longitude=curr_worker_dict["start_x"],
        #     start_latitude=curr_worker_dict["start_y"],
        #     end_longitude=curr_worker_dict["start_x"],
        #     end_latitude=curr_worker_dict["start_y"],
        #     assigned_jobs = [],
        # )
        # env.add_single_working_time_slot(new_slot)

    return worker

from sqlalchemy.orm.attributes import set_attribute
  
from sqlalchemy.orm.attributes import flag_modified
@router.post("/update_worker_info", response_model=WorkerRead)
def update_worker_info(
    *,
    db_session: Session = Depends(get_db),
    worker_in: dict,
    current_user: DispatchUser = Depends(get_current_user),
):
    # print(worker_in)
    log.info(f"update_worker_info:received: {worker_in}")
    if "code" not in worker_in:
        raise HTTPException(status_code=400, detail="The worker code must be included.")

    worker = get(db_session=db_session, code=worker_in["code"])
    if not worker:
        raise HTTPException(status_code=400, detail="The worker with code {} does not exist.".format(worker_in["code"]))
    # worker_data = copy.deepcopy(worker.__dict__)
    # for key, value in worker_in.__dict__.items():
    #     worker_data[key] = value
    # worker_in = WorkerUpdate(**worker_data)
    update_slot_flag = False
    # deactive_worker_flag = False
    for key, value in worker_in.items():
        if key in ["code"]:
            continue
        if key in ("team", "team_id"):
            raise HTTPException(status_code=400, detail="The team can not be modified.")

        if key == "flex_form_data":
            worker.flex_form_data.update(value)
            flag_modified(worker, key)
        else:
            set_attribute(worker, key, value)
            if key in ("business_hour", "is_active"):
                flag_modified(worker, key)
                update_slot_flag = True
                continue
        

        # elif key ==  and (not value):
        #     deactive_worker_flag = True
        #     flag_modified(worker, key)
        #     update_slot_flag = True
        #     continue

    db_session.add(worker)
    db_session.commit()

    delete_existing_slot = False
    # flex_form_data = worker.get("flex_form_data",{})
    if "delete_existing_slot" in worker.flex_form_data:
        delete_existing_slot = str(worker.flex_form_data["delete_existing_slot"]) == "1"
            


    if update_slot_flag and worker.auto_planning:
        env_refresh_worker( 
            db_session=db_session,
            worker=worker,
            current_user=current_user,
            delete_existing_slot = delete_existing_slot,
            delete_kmedoid = False
        )
        log.info(f"Worker {worker.code}) is updated in env succesfully!")
    else:
        log.warning(f"Worker is updated without auto planning {worker_in}")

    return worker



@router.put("/{worker_code}/update_business_hour", response_model=WorkerRead)
def update_worker_bussiness_hour(
    *,
    db_session: Session = Depends(get_db),
    worker_code: str,
    worker_in: WorkerUpdateBusinessHour,
    current_user: DispatchUser = Depends(get_current_user),
):
    worker_in.org_id = current_user.org_id
    if worker_code != worker_in.code:
        raise HTTPException(status_code=400, detail="The worker code must match.")

    return update_business_hour(db_session,worker_in.code,worker_in.business_hour)


@router.put("/{worker_code}", response_model=WorkerRead)
def update_worker(
    *,
    db_session: Session = Depends(get_db),
    worker_code: str,
    worker_in: WorkerUpdate,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Update a worker.
    """
    worker_in.org_id = current_user.org_id
    if worker_code != worker_in.code:
        raise HTTPException(status_code=400, detail="The worker code must match.")

    worker = get(db_session=db_session, code=worker_code)
    if not worker:
        raise HTTPException(status_code=404, detail="The worker with this id does not exist.")

    if worker_in.geo_longitude is None or worker_in.geo_latitude is None:
        if worker_in.location  is None:
            raise HTTPException(status_code=400, detail=f"worker.geo_longitude/latitude and  worker.location can not all be Empty")
        worker_in.geo_longitude = worker_in.location.geo_longitude
        worker_in.geo_latitude = worker_in.location.geo_latitude
    # code_change = False
    if worker_in.code != worker.code:
        raise HTTPException(status_code=400, detail="Worker code can not be changed!")
        # code_change = True

    # team_change = False
    # if worker.team and worker_in.team.code != worker.team.code:
    #     team_change = True

    # change_active = False
    # if worker_in.is_active != worker.is_active:
    #     change_active = True
    #     count = get_count_by_active(db_session=db_session, is_active=True)
    #     if count < 2 and not worker_in.is_active:
    #         raise HTTPException(status_code=404, detail="There must be a normal worker.")


    # 不需要code唯一校验 -- 2022-12-06 22:18:03 改成了code作为主键
    if worker_in.skills:
        worker_in.flex_form_data["skills"] = worker_in.skills
        
    org_data = org_service.get(db_session=db_session, org_code=current_user.org_code)
    team = team_service.get_by_code(db_session=db_session, code=worker_in.team.code)

    create_dipatch_core_user( db_session , worker_in,org_data,team)
 
    # if worker_in.loaded_items:
    #     worker_in.flex_form_data["loaded_items"] = worker_in.loaded_items

    # team = team_service.get_by_code(db_session=db_session, code=worker_in.team.code)

    # # use zulip
    # zulip_user_id = worker_in.flex_form_data.get("zulip_user_id", None)
    # old_user_id = worker.flex_form_data.get("zulip_user_id", None)
    # result = None
    # zulip_dict = get_zulip_client_by_org_id(current_user.org_id)
    # if (
    #     zulip_dict
    #     and zulip_user_id
    #     and zulip_user_id != old_user_id
    #     and worker_in.team.flex_form_data.get("use_zulip", False)
    # ):
    #     flag, worker_code = check_zulip_user_id(
    #         db_session=db_session, zulip_user_id=zulip_user_id, team_id=team.id
    #     )
    #     if not flag:
    #         raise HTTPException(
    #             status_code=400, detail=f"The worker zulip_user_id already exists in {worker_code}"
    #         )

    #     zulip_core = zulip_dict["client"]
    #     result = zulip_core.update_add_subscribe_user_group(
    #         worker_in, org_code=current_user.org_code, team_code=team.code, flag=True
    #     )
    # if result and result["result"] != "success":
    #     raise HTTPException(status_code=400, detail=f"{result['msg']}")

    # create default account for worker
    # regist_flag = worker_in.flex_form_data.get("regist_default_account", False)
    # mobile_phone = worker_in.flex_form_data.get("mobile_phone", None)
    # if regist_flag and mobile_phone:
    #     mobile_phone = str(mobile_phone)
    #     if worker.dispatch_user:
    #         if worker.dispatch_user.email != mobile_phone:
    #             in_user = auth_service.update_email_password(
    #                 db_session=db_session,
    #                 user_id=worker.dispatch_user.id,
    #                 email=mobile_phone,
    #                 password=mobile_phone,
    #             )
    #             worker_in.dispatch_user = in_user
    #     else:
    #         user = UserRegister(
    #             email=mobile_phone,
    #             password=mobile_phone,
    #             role=UserRoles.WORKER,
    #             org_id=current_user.org_id,
    #             org_code=current_user.org_code,
    #             en_code=None,
    #             is_active=True,
    #             is_org_owner=True,
    #             is_team_owner=True,
    #             default_team_id=team.id,
    #             import_sample_data=False,
    #         )
    #         in_user = auth_service.create(db_session=db_session, user_in=user)
    #         worker_in.dispatch_user = in_user

    worker = update(db_session=db_session, worker=worker, worker_in=worker_in)

    # post worker change to planning env
    if worker.auto_planning:
        env_refresh_worker( 
            db_session,
            worker,
            current_user,
            # delete_existing_slot = True,
        )
    return worker


def env_refresh_worker( 
    db_session, worker, current_user, delete_existing_slot = False, delete_kmedoid=True,
):
    env = get_active_planner(org_id=current_user.org_id, team_id=worker.team_id) 
    if not worker.is_active:
        env.delete_working_slot_4_worker(
            worker_code=worker.code, purge_stale_slots=False
        )
        return
    start_datetime = env.env_decode_from_minutes_to_datetime(
        env.get_env_planning_horizon_start_minutes() - 240 # 4个小时之内的
    )
    end_datetime = env.env_decode_from_minutes_to_datetime(
        env.get_env_planning_horizon_end_minutes()
    )
    day_jobs = job_service.get_jobs_worker_days(
        db_session=db_session,
        start_datetime = start_datetime, 
        end_datetime = end_datetime,
        worker_code = worker.code,
        include_unplanned = False,
        include_inplanning = True,
    )
            
    env.mutate_refresh_working_slots_4_worker(
        worker = worker,
        day_jobs = day_jobs,
        delete_existing_slot = delete_existing_slot,
        delete_kmedoid=delete_kmedoid)



@router.delete("/{worker_code}")
def delete_worker(
    *,
    db_session: Session = Depends(get_db),
    worker_code: str,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Delete a worker.
    """
    
    worker = get(db_session=db_session, code=worker_code)
    if not worker:
        raise HTTPException(status_code=404, detail="The worker with this code does not exist.")
    # 修改bug，当worker_code在job表的scheduled_primary_worker_code或requested_primary_worker_code 时会有外键，此时直接删除worker会报错
    job_list = job_service.get_first_by_worker_code(db_session=db_session, worker_code=worker_code)
    if job_list:
        raise HTTPException(status_code=404, detail="This worker has at least one job and cannot delete.")
    old_email_id = None
    if worker.dispatch_user:
            old_email_id = worker.dispatch_user.id
    delete(db_session=db_session, code=worker_code)
    if old_email_id:
        # 判断更改的 mobile ,是就删除之前的，
        auth_service.delete(db_session=db_session, id=old_email_id)
        

    return JSONResponse({"status":200,'detail': f"{worker_code=}  delete success"})
    # use zulip
    zulip_dict = get_zulip_client_by_org_id(current_user.org_id)
    if zulip_dict:
        zulip_core = zulip_dict["client"]
        team = team_service.get(db_session=db_session, team_id=worker.team_id)
        worker.team = team
        zulip_core.update_add_subscribe_user_group(
            worker, org_code=current_user.org_code, team_code=worker.team.code, flag=False
        )


# @router.get("/all/worker_list")
# def worker_list(*, team_id: int = Query(1, alias="team_id"), db_session: Session = Depends(get_db)):
#     """
#     Retrieve worker contacts.
#     """
#     data = get_by_team(db_session=db_session, team_id=team_id)

#     return_data = []
#     for worker in data:
#         lass_than_5min = random.randint(75, 85)
#         min5_min10 = random.randint(15, 100 - lass_than_5min)
#         more_than_10min = 100 - lass_than_5min - min5_min10
#         cater_rate = random.randint(80, 100)
#         monthly_jobs_completed = random.randint(10, 300)
#         cater_rate_color = "green"
#         if cater_rate < 90:
#             cater_rate_color = "red"
#         elif cater_rate < 95:
#             cater_rate_color = "orange"
#         monthly_jobs_completed_color = "green"
#         if cater_rate < 50:
#             monthly_jobs_completed_color = "red"
#         elif cater_rate < 150:
#             monthly_jobs_completed_color = "orange"
#         if not worker.location or not worker.location.geo_latitude:
#             continue
#         return_data.append(
#             {
#                 "id": worker.code,
#                 "position": {
#                     "lat": worker.location.geo_latitude,
#                     "lng": worker.location.geo_longitude,
#                 },
#                 "tooltip": worker.code,
#                 "visible": True,
#                 "kpi": {
#                     "cater_rate": {
#                         "color": cater_rate_color,
#                         "value": f"{cater_rate}%",
#                     },
#                     "passenger_waiting_lt_5min": {
#                         "color": "green",
#                         "value": f"{lass_than_5min}%",
#                     },
#                     "passenger_waiting_min5_min10": {
#                         "color": "orange",
#                         "value": f"{min5_min10}%",
#                     },
#                     "passenger_waiting_gt_10min": {
#                         "color": "red",
#                         "value": f"{more_than_10min}%",
#                     },
#                     "monthly_jobs_completed": {
#                         "color": monthly_jobs_completed_color,
#                         "value": f"{monthly_jobs_completed}",
#                     },
#                 },
#             }
#         )
#     return return_data


def post_worker_to_env(message_dict, org_code, team_id, code_change):

    planner = get_active_planner(org_code=org_code, team_id=team_id)
    rl_env = planner["planner_env"]
    # kafka_server = rl_env.kafka_server

    if code_change:
        rl_env.reload_data_from_db_adapter(
            rl_env.env_start_datetime,
            end_datetime=rl_env.env_decode_from_minutes_to_datetime(
                rl_env.get_env_planning_horizon_end_minutes()
            ),
        )
        rl_env._reset_data()
    else:

        message_type = (
            KafkaMessageType.CREATE_WORKER
            if not rl_env.workers_dict.get(message_dict["code"])
            else KafkaMessageType.UPDATE_WORKER
        )

        msg = {
            "message_type": message_type,
            "message_source_type": KandboxMessageSourceType.ENV,
            "message_source_code": "USER.Web",
            "payload": [message_dict],
        }
        # kafka_server.process_env_message(msg=msg, auto_replay_in_process=False)


# def transfrom_worker_data(worker_obj, team):
#     if not worker_obj.location:
#         mean_long = (
#             team.flex_form_data.get("longitude_diff_max", 0)
#             + team.flex_form_data.get("longitude_diff_min", 0)
#         ) / 2
#         mean_lat = (
#             team.flex_form_data.get("latitude_diff_max", 0)
#             + team.flex_form_data.get("latitude_diff_min", 0)
#         ) / 2
#         location = Location(
#             code="central_loc",
#             geo_longitude=mean_long,
#             geo_latitude=mean_lat,
#             geo_address_text="central_loc",
#         )
#         worker_obj.location = location
#     _worker_dict = {}
#     _worker_dict["flex_form_data"] = worker_obj.flex_form_data
#     _worker_dict["business_hour"] = worker_obj.business_hour
#     _worker_dict["location_code"] = worker_obj.location.code
#     _worker_dict["job_history_feature_data"] = {}
#     _worker_dict["geo_longitude"] = worker_obj.location.geo_longitude
#     _worker_dict["geo_latitude"] = worker_obj.location.geo_latitude
#     _worker_dict["worker_code"] = worker_obj.code
#     _worker_dict["is_active"] = worker_obj.is_active
#     _worker_dict["code"] = worker_obj.code
#     _worker_dict["worker_obj"] = worker_obj
#     _worker_dict["id"] = int(worker_obj.id)

#     return _worker_dict


# @router.post("/save_batch_worker/", response_model=List[WorkerRead])
# def create_batch_worker(
#     *,
#     db_session: Session = Depends(get_db),
#     worker_in_list: List[WorkerCreate],
#     current_user: DispatchUser = Depends(get_current_user),
# ):
#     """
#     Create a new worker.
#     """
#     org_service.verify_status(db_session=db_session, org_id=current_user.org_id)

#     # limit max
#     org_data = org_service.get(db_session=db_session, org_code=current_user.org_code)
#     if not org_data:
#         raise HTTPException(status_code=400, detail="org not exists")
#     max_nbr_worker = org_data.max_nbr_workers
#     job_all_count = get_by_org_id_count(db_session=db_session, org_id=current_user.org_id)
#     if job_all_count + len(worker_in_list) >= max_nbr_worker:
#         raise HTTPException(status_code=400, detail="Worker Reached the upper limit")

#     origin_worker_list = get_by_org_id(db_session=db_session, org_id=current_user.org_id)
#     origin_worker_code_list = [worker.code for worker in origin_worker_list]

#     in_wroker_code_list = [worker.code for worker in worker_in_list]
#     intersection_list = list(set(origin_worker_code_list).intersection(set(in_wroker_code_list)))
#     if intersection_list:
#         raise HTTPException(
#             status_code=404,
#             detail=f"This worker with this code already exists. {intersection_list}",
#         )

#     create_worker_list = []
#     for worker_in in worker_in_list:
#         if worker_in.skills:
#             worker_in.flex_form_data["skills"] = worker_in.skills
#         if worker_in.loaded_items:
#             worker_in.flex_form_data["loaded_items"] = worker_in.loaded_items

#         worker_in.org_id = current_user.org_id

#         team = team_service.get_by_code(db_session=db_session, code=worker_in.team.code)

#         # use zulip
#         zulip_user_id = worker_in.flex_form_data.get("zulip_user_id", None)
#         result = None
#         zulip_dict = get_zulip_client_by_org_id(current_user.org_id)
#         if zulip_dict and zulip_user_id and worker_in.team.flex_form_data.get("use_zulip", False):
#             flag, worker_code = check_zulip_user_id(
#                 db_session=db_session, zulip_user_id=zulip_user_id, team_id=team.id
#             )
#             if not flag:
#                 raise HTTPException(
#                     status_code=400,
#                     detail=f"The worker zulip_user_id already exists in {worker_code}",
#                 )
#             zulip_core = zulip_dict["client"]
#             result = zulip_core.update_add_subscribe_user_group(
#                 worker_in, org_code=current_user.org_code, team_code=team.code, flag=True
#             )
#         if result and result["result"] != "success":
#             raise HTTPException(status_code=400, detail=f"{result['msg']}")

#         # create default account for worker
#         regist_flag = worker_in.flex_form_data.get("regist_default_account", False)
#         mobile_phone = worker_in.flex_form_data.get("mobile_phone", None)
#         if regist_flag and mobile_phone:
#             mobile_phone = str(mobile_phone)
#             user_data = auth_service.get_by_email(db_session=db_session, email=mobile_phone)
#             if user_data:
#                 raise HTTPException(
#                     status_code=400, detail=f"account already exists.  {mobile_phone}"
#                 )
#             user = UserRegister(
#                 email=mobile_phone,
#                 password=mobile_phone,
#                 role=UserRoles.WORKER,
#                 org_id=org_data.id,
#                 org_code=org_data.code,
#                 en_code=None,
#                 is_active=True,
#                 is_org_owner=True,
#                 is_team_owner=True,
#                 default_team_id=team.id,
#                 # import_sample_data=False,
#             )
#             in_user = auth_service.create(db_session=db_session, user_in=user)
#             worker_in.dispatch_user = in_user
#         worker = create(db_session=db_session, worker_in=worker_in)

#         create_worker_list.append(worker)
#         # change to env
#         if current_user.org_code and team.id:
#             message_dict = transfrom_worker_data(worker, team)
#             post_worker_to_env(message_dict, current_user.org_code, team.id, False)
#     return create_worker_list
