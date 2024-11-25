from copy import deepcopy
import math
from dispatch.common.utils.kandbox_clear_data import clear_all_worker_jobs_in_team
# from dispatch.contrib.e6yun.core import E6YunCore
from dispatch.job.models import Job, JobCreate, JobPlanningStatusUpdate, UnplannedJobPagination
from dispatch.order.models  import OrderCreate
from dispatch.org.enums import OrganizationType
from dispatch.plugins.kandbox_planner.env.env_enums import KandboxPlannerPluginType
from dispatch.planner_env.optimizer_models import OptimizerRequest, OptimizerResponese
from dispatch.worker import service as worker_service
from dispatch.job import service as job_service
from dispatch.order import service as order_service
from dispatch.planner_env import planner_service
from sqlalchemy.orm.attributes import flag_modified

from dispatch.job import service as jobService
import logging
# from fastapi.encoders import jsonable_encoder
from dispatch.config import DATA_START_DAY, DISPATCH_VERSION, KANDBOX_DATETIME_FORMAT_ISO
# from dispatch.plugins.kandbox_planner.data_adapter.kafka_adapter import KafkaAdapter
from dispatch.plugins.kandbox_planner.env.env_enums import (
    ActionType,
    ActionScoringResultType,
    AppointmentStatus,
    JobPlanningStatus,
    KafkaMessageType,
    KandboxMessageSourceType,
    KandboxMessageTopicType,
    OrderCreateResultStatusType,
    PlannerType,
    TimeSlotType,
    WorkerStatusUpdateType,
)
from dispatch.plugins.kandbox_planner.env.env_models import (
    ActionDict,
    ActionEvaluationScore,
    ConfirmAssignmentInput,
    ConfirmJobsResult,
    GetEnvJobsInput,
    JobInSlotResult, 
    OrderCreationResult,
    ReplanJobInput,
    ReplanOrderInput,
    # SingleEnvStepResult,
    # WorkingTimeSlot,
    # WorkerCodeSchedle,
    OrderCreationResultSchedule,
    EnvAction,
)

import json
from datetime import datetime, timedelta
from typing import Dict, List

import asyncio


from dispatch.org import service as org_service

# from arrow.util import total_seconds
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Cookie, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

# from dispatch.cloudmarket.instance import tablestore_service
from dispatch import config
from dispatch.auth.models import DispatchUser
from dispatch.auth.service import get_current_user
from dispatch.team import service as team_service
from dispatch.database import SessionLocal, get_db
from dispatch.plugins.kandbox_planner.util.kandbox_date_util import get_current_day_string
from dispatch.planner_env.planner_service import (
    check_job_travel_minutes,
    get_active_planner,
    get_appt_dict_from_redis,
    reset_planning_window_for_team,
    run_batch_optimizer,
    run_simple_optimizer,
    update_worker_begin_shift,
    update_worker_end_shift,
    # update_worker_update_location,
    get_finished_job_service,
    trance_data_finished
)

from dispatch.planner_plugin import service as service_plugin_service

from dispatch.cloudmarket.instance import service as instance_service
from dispatch.cloudmarket.instance.views import router as isinstance_router

from dispatch.planner_env.planner_models import (
    GenericJobPredictActionInput,
    GenericJobPredictActionOutput,
    GenericJobAction,
    GenericJobCommitActionInput,
    GenericRequestResult,
    JobTravelMinutes,
    JobTravelMinutesOutput,
    LockedSlot,
    LockedSlotOutput,
    GenericJobCommitActionInput,
    GenericJobCommitOutput,
    ResetPlanningWindowResult,
    RunOptimizerOverUnplannedInput,
    SingleJobDropCheckInput,
    SingleJobDropCheckInputNew,
    SingleJobDropCheckOutput,
    PLANNER_ERROR_MESSAGES,
    ResetPlanningWindowInput,
    RunBatchInput,
    TeamEnvInput,
    WorkerStatusUpdateInput,
    DevEnvKeyRequest,
)
from dispatch.config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, redis_pool
import redis
from dispatch.database_util.service import common_parameters
from dispatch.config import WORKER_COLOR_ITER
import concurrent.futures

# from multiprocessing import Pool
# process_pool = Pool(5)

import time

import traceback
from dispatch.job.service import (
    get_by_code as job_get_by_code,
    delete as job_delete,
    update_job_planning_status,
)
from dispatch.database_util.service import get_schema_session

planner_router = APIRouter()
redis_conn = redis.Redis(connection_pool=redis_pool)

log = logging.getLogger(__name__)


def consume_cpu(steps = 1_000_000):
    import random
    _start_time = time.time()

    a=random.randint(1,10)
    # print(idx.start, idx.step, idx.start)
    for i in range(steps*a):
        b=a*a % 1000000
    return (time.time() - _start_time)

def test_multi_process():
    _start_time = time.time()
    # _a, sec = consume_cpu()
    # res = list(process_pool.apply_async(consume_cpu, args=(1000_000,)) for _ in range(3))
    # results = [r.get() for r in res]
    all_times = []
    nbr_workers = 8
    PRIMES = [1000_0000 for _ in range(nbr_workers)]
    with concurrent.futures.ProcessPoolExecutor(max_workers=nbr_workers) as executor:
            # for number, prime in zip(PRIMES, executor.map(consume_cpu, PRIMES)):
            #     print('%d is prime: %s' % (number, prime))
            results = executor.map(consume_cpu, PRIMES)
            for res in results:
                all_times.append(res)

    total_sec = (time.time() - _start_time)
    print(f"--- {3} steps, total{total_sec} seconds, results = {all_times} ---")







## ================================================================== ##






@planner_router.post(
    "/reset_planning_window/",
    response_model=ResetPlanningWindowResult, 
    summary="Reset planning window",
)
def reset_planning_window(
    request_in: ResetPlanningWindowInput,
    team_code: str = Query("1", alias="team_code"),
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    
    # org_code = current_user.org_code
    team = team_service.get_by_code(db_session=db_session, code=request_in.team_code)
    if team is None:
        raise HTTPException(
            status_code=400,
            detail=f"The team code you requested is not in your organization.",
        )
    if team.org_id != current_user.org_id:
        raise HTTPException(
            status_code=400,
            detail=f"The team code you requested is not in your organization...",
        )
    if team.flex_form_data.get("reset_dataset", "none") == 'riyadh':
        org = org_service.get(db_session=db_session, org_id=current_user.org_id)
        if org is None:
            raise HTTPException(status_code=400, detail="Organization does not exist")
        if org.org_type != OrganizationType.POC:
            raise HTTPException(status_code=400, detail="Only POC Organization can reset data in teams. Please consider removing reset_dataset setting ...")
        
        # clear_all_worker_jobs_in_team(
        #     db_session=db_session, 
        #     org_code = org.code, 
        #     team_id = team.id
        # )

    env = get_active_planner(
        # db_session = db_session,
        org_id=team.org_id,
        team_id=team.id,
        force_reload=True,
    )
    result = env.reset_env(db_session=db_session, delete_existing_slot=True)
    env = get_active_planner(
        # db_session = db_session,
        org_id=team.org_id,
        team_id=team.id,
        force_reload=True,
    )
    result_info = {"status": str(result), "config": env.config}

    # Refresh local cache, TODO, why twice? 2023-12-21 18:16:00
    _ = get_active_planner(
        org_id=team.org_id,
        team_id=team.id,
        force_reload=False,
    )
    
    # if team.flex_form_data.get("reset_dataset", "none") == 'riyadh':
    #     env = get_active_planner(org_id=current_user.org_id, team_id=team.id)
    #     nbr_initial_steps = int(env.config.get("nbr_initial_steps", 10))
    #     for i in range(nbr_initial_steps):
    #         res = env.step()
    #         if not res.has_unplanned:
    #             break
    #         if res.action is None:
    #             # break
    #             print("res.action is None!")
    #         elif res.action.action_type != ActionType.FLOATING: 
    #             # break
    #             print("res.action.action_type != ActionType.FLOATING!")
    #         log.info(f"step {i}: ") # {res}
    #     if True: # not res.has_unplanned:
    #         print("Env Finished!")
    #         print(f"Finished after {i} orders, statistics {env.summerize_worker_job_stat()} ...")

            
    #     result_info["env_step_result"] = res # .json()

    # else:
    #     result_info["env_step_result"] = SingleEnvStepResult(
    #         has_unplanned=False,
    #         current_datetime = datetime.now(),
    #         current_step = 0,
    #     ) #.json()

    return result_info
    # return JSONResponse(content=jsonable_encoder(result_info), status_code=200)




@planner_router.post(
    "/run_batch_optimizer/",
    summary="Run batch optimizer",
)
def run_batch_optimizer_func(
    request_in: RunBatchInput,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """
    Run batch optimizer. It invokes the batch agent pre-configured in the env and execute the optimization in current planning window.
    """
    log.info(f"run_batch_optimizer:received: {request_in.json()}")
    team = team_service.get_by_code(db_session=db_session, code=request_in.team_code)
    if team is None:
        raise HTTPException(
            status_code=400,
            detail="The team code you requested is not in your organization.",
        )
    if team.org_id != current_user.org_id:
        raise HTTPException(
            status_code=400,
            detail="The team code you requested is not in your organization...",
        )
    try:
        result_info = run_batch_optimizer(
            org_id=team.org_id,
            team_id=team.id,
            db_session = db_session, 
            batch_request=request_in
        )
    except Exception as e:
        import traceback

        log.error(traceback.format_exc())
        log.error(f"run_batch_optimizer error {str(e)}")
        result_info = {"status": "Error"}
        # , "jobs_dispatched": 0
        # redis_conn.delete/set("run_batch_" + current_user.id.__str__())
    return JSONResponse(result_info)



@planner_router.post(
    "/replan_job/",
    response_model=OrderCreationResult,
    summary="Reject and Replan one job.",
)
def replan_job(
    request_in: ReplanJobInput,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    request_as_order = ReplanOrderInput(
        order_code=request_in.job_code,
        planner_type=PlannerType.SINGLE,
        allow_same_worker=request_in.allow_same_worker,
        target_worker=request_in.target_worker,
        overwrite_max_orders_limit=request_in.overwrite_max_orders_limit,
        commit_new_plan=request_in.commit_new_plan,
        unplan_existing=request_in.unplan_existing,
    )
    return replan_order_func(request_as_order, current_user, db_session)


@planner_router.post(
    "/replan_order/",
    response_model=OrderCreationResult,
    summary="Reject and Replan one order.",
)
def replan_order(
    request_in: ReplanOrderInput,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    return replan_order_func(request_in, current_user, db_session)


def replan_order_func(
    request_in: ReplanOrderInput,
    current_user: DispatchUser,
    db_session: Session,
):
    log.info(f"replan_order:received: {request_in.json()}")

    if request_in.target_worker is None:
        worker_whitelist = [] 
    else:
        worker_whitelist = [request_in.target_worker]
    
    if request_in.planner_type == PlannerType.PICKDROP :
        order = order_service.get(db_session=db_session, code=request_in.order_code)
        if not order:
            raise HTTPException(status_code=404, detail="The order with this code does not exist.")
        if len(order.job_order_rel) == 0:
            log.error(f"no job found in order {order.code}")
            res = OrderCreationResult(status=OrderCreateResultStatusType.CREATED_BUT_DISPATCH_FAILED,                 
                                                order = order,
                                                scheduled_slots = None
                                            )
            log.info(f"replan_order:sending:no_job_found:{res.json()}")
            return res
        env = get_active_planner(org_id=current_user.org_id, team_id=order.team.id)
        if env.get_real_time_agent().planner_type != request_in.planner_type:
            raise HTTPException(status_code=400, detail="Wrong planner type.")

        worker_blacklist = []
        worker_code = None
        if order.job_order_rel[0].planning_status in (JobPlanningStatus.IN_PLANNING, JobPlanningStatus.PLANNED, ):
            worker_code = order.job_order_rel[0].scheduled_primary_worker_code
            if not request_in.allow_same_worker:
                worker_blacklist = [worker_code]

        _todo_job_list,_ = env.unplan_job_list(
            target_job_list=order.job_order_rel,
            worker_code=worker_code,
            db_session=db_session, 
            commit_ex_slot=True,
            )

        res = planner_service.replan_order(
            db_session = db_session,
            env = env, order = order, db_job_list = _todo_job_list, worker_blacklist=worker_blacklist,
            worker_whitelist = worker_whitelist,
            overwrite_max_orders_limit = request_in.overwrite_max_orders_limit,
            )
        log.info(f"replan_order:sending: {order.code} {res.status, res.worker_code, res.scheduled_slots}")
        return res
        
    elif request_in.planner_type == PlannerType.SINGLE:
        job = job_service.get(db_session=db_session, code=request_in.order_code)
        if not job:
            raise HTTPException(status_code=404, detail="The job with this code does not exist.")

        env = get_active_planner(org_id=current_user.org_id, team_id=job.team.id)
        if env.get_real_time_agent().planner_type != request_in.planner_type:
            raise HTTPException(status_code=400, detail="Wrong planner type.")



        worker_blacklist = []
        worker_code = None
        if job.planning_status in (JobPlanningStatus.IN_PLANNING, JobPlanningStatus.PLANNED, ):
            worker_code = job.scheduled_primary_worker_code
            if not request_in.allow_same_worker:
                worker_blacklist = [worker_code]

        _, solved_ex_slot = env.unplan_job_list(
            target_job_list=[job],
            worker_code=worker_code,
            db_session=db_session, 
            )

        res = planner_service.replan_job(
            db_session = db_session,
            env = env, 
            db_job= job, 
            auto_commit= request_in.commit_new_plan, 
            worker_blacklist=worker_blacklist,
            worker_whitelist = worker_whitelist,
            overwrite_max_orders_limit = request_in.overwrite_max_orders_limit,
            ex_slot=solved_ex_slot,
            )
        

        log.info(f"replan_order:sending: {job.code} {res.status, res.worker_code, res.scheduled_slots}")
        return res


def check_worker_status_input(wsi:WorkerStatusUpdateInput):
    if wsi.action_type == WorkerStatusUpdateType.UPDATE_LOCATION:
        if wsi.start_longitude is None or wsi.start_latitude is None:
            raise HTTPException(
                status_code=400,
                detail="start long/lat must be provided for UPDATE_LOCATION.",
            )
    elif wsi.action_type == WorkerStatusUpdateType.ACCUM_ITEMS:
        if not wsi.accum_items:
            raise HTTPException(
                status_code=400,
                detail="no accum_items.",
            )
        if len(wsi.accum_items) == 0:
            raise HTTPException(
                status_code=400,
                detail="accum_items has no elements.",
            )

    elif wsi.action_type in (WorkerStatusUpdateType.BEGIN_SHIFT, WorkerStatusUpdateType.END_SHIFT):
        if wsi.start_longitude is None or wsi.start_latitude is None:
            raise HTTPException(
                status_code=400,
                detail="start/end long/lat and shift date must be provided for shift operations.",
            )
    else:
        raise HTTPException(
                status_code=400,
                detail="Unknown action type.",
            )


@planner_router.post(
    "/update_worker_status",
    response_model=GenericRequestResult, 
    summary="Update worker status",
)
def update_worker_status(
    request_in: WorkerStatusUpdateInput,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """
    Update worker status. This API can update worker location or shift in real time. Only three actions are allowed:
    1. "update_location"
    2. "begin_shift"
    3. "end_shift"
    """
    log.info(f"update_worker_status:received: {request_in.json()}")
    check_worker_status_input(request_in)
    worker = worker_service.get_by_code(db_session=db_session, code=request_in.worker_code)
    if worker is None:
        raise HTTPException(
            status_code=400,
            detail="The worker code does not exist.",
        )
    if worker.org_id != current_user.org_id:
        raise HTTPException(
            status_code=400,
            detail="The worker does not exist in your organization...",
        )

    env = get_active_planner(
        org_id=worker.org_id,
        team_id=worker.team_id,
    )
    if request_in.shift_start_datetime is not None:
        start_minutes = env.env_encode_from_datetime_to_minutes(request_in.shift_start_datetime)
    else:
        start_minutes = env.get_env_planning_horizon_start_minutes()
    curr_slots = env.get_working_slot_list(
        worker_code=worker.code,
        start_minutes = start_minutes, 
        end_minutes=start_minutes+request_in.shift_duration_minutes,
        active_only=True
        )
    
    res = False
    if len(curr_slots) > 0:
        if request_in.action_type == WorkerStatusUpdateType.BEGIN_SHIFT:
            return GenericRequestResult(
                errorNumber = 40001,
                errorDescription = "The requested shift conflicts with existing shifts"
            )
        elif request_in.action_type == WorkerStatusUpdateType.END_SHIFT:
            res = update_worker_end_shift(
                env = env, 
                db_session = db_session,
                worker=worker,
                curr_slots = curr_slots,
                request_in=request_in, 
                )
        elif request_in.action_type == WorkerStatusUpdateType.UPDATE_LOCATION:
            res = env.update_slot_start_location(
                worker_code = curr_slots[0].worker_code, 
                longitude = request_in.start_longitude,
                latitude = request_in.start_latitude,
                accum_items = {}
            )
        elif request_in.action_type == WorkerStatusUpdateType.ACCUM_ITEMS:
            slot = curr_slots[0]
            for k,v in request_in.accum_items.items():
                try:
                    v_num = int(v)
                    slot.accum_items[k] = v_num
                except:
                    return GenericRequestResult(
                        errorNumber = 40001,
                        errorDescription = f"Quantity of accum items can not be parsed: {k}:{v}."
                    )
            res = env.add_single_working_time_slot(slot, update_ops=["accum_items"]) 
        
    else:
        if request_in.action_type == WorkerStatusUpdateType.END_SHIFT:
            return GenericRequestResult(
                errorNumber = 40001,
                errorDescription = "The requested shift does not exist"
            )

        if request_in.action_type == WorkerStatusUpdateType.BEGIN_SHIFT:
            res = update_worker_begin_shift(
                env = env, 
                db_session = db_session,
                worker=worker,
                request_in=request_in, 
                )
        elif request_in.action_type in (WorkerStatusUpdateType.UPDATE_LOCATION, WorkerStatusUpdateType.ACCUM_ITEMS):
            return GenericRequestResult(
                errorNumber = 40001,
                errorDescription = "No active slots to update location."
            )
        else:
            return GenericRequestResult(
                errorNumber = 40001,
                errorDescription = "Wrong action type"
            )

    if res:
        return GenericRequestResult(
                errorNumber = 0,
                errorDescription = "Worker Status Updated."
            )
    else:
        return GenericRequestResult(
            errorNumber = 40001,
            errorDescription = "Error when update worker status"
        )





@planner_router.post(
    "/get_env_jobs/",
    response_model=Dict[str, List[JobInSlotResult]],
    summary="Get jobs from a planning env.",
)
def get_env_jobs(
    request_in: GetEnvJobsInput,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """
    Get Env Jobs, on all or some workers. This retrives only inplanning or planned jobs assigned to a group of workers. If you set reset_start_datetime == true, this api also reset worker's start time to current time, i.g. shift all jobs to start from now on.
    """
    team = team_service.get_by_code(db_session=db_session, code=request_in.team_code)
    if team is None:
        raise HTTPException(
            status_code=400,
            detail=f"The team code you requested is not in your organization.",
        )
    if team.org_id != current_user.org_id:
        raise HTTPException(
            status_code=400,
            detail=f"The team code you requested is not in your organization...",
        )

    area_code_filter = []
    if request_in and request_in.area_codes:
        if len(request_in.area_codes) > 0:
            area_code_filter = request_in.area_codes.split(config.SEPERATOR_FLEX_0) 


    worker_code_filter = []
    if request_in and request_in.worker_codes:
        if len(request_in.worker_codes) > 0:
            worker_code_filter = request_in.worker_codes.split(config.SEPERATOR_FLEX_0) 

    env = get_active_planner( 
        org_id=current_user.org_id, team_id=team.id
    )
    result_info = env.get_env_jobs( 
        area_code_list=area_code_filter,
        worker_code_list=worker_code_filter,
        reset_start_datetime=request_in.reset_start_datetime,
        active_only = request_in.active_only,
    ) 
    return result_info


#########################################
@planner_router.get(
    "/get_planner_worker_job_dataset/",
    summary="Get the env dataset.",
)
async def get_worker_job_dataset(
    # response: Response,
    env_key: str = Cookie(default=None),
    team_id: int = Query(0, alias="team_id"),
    worker_code_list_str: str = Query("ALL", alias="worker_code_list"),
    start_day: str = Query(None, alias="start_day"),
    end_day: str = Query(None, alias="end_day"),
    force_reload: bool = Query(False, alias="force_reload"),
    active_only: bool = Query(True, alias="active_only"),
    include_finished: bool = Query(False, alias="include_finished"),
    set_inplanning_to_planned: bool = Query(False, alias="set_inplanning_to_planned"),
    current_user: DispatchUser = Depends(get_current_user),
): 
    """
    Retrieve a dataset of workers and jobs, in one planner env. This is mainly for planner UI usage."""
    if not team_id:
        return JSONResponse({})
    try:
        if worker_code_list_str == "ALL" or worker_code_list_str is None:
            worker_code_list = []
        else:
            worker_code_list = []
            for w in worker_code_list_str.split(","):
                if len(w) > 1:
                    worker_code_list.append(w)
            if len(worker_code_list) < 1:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid worker code list = {worker_code_list_str} ",
                )
        # 如果set_inplanning_to_planned为true
        if set_inplanning_to_planned:
            force_reload = True
            db_session = get_schema_session(org_code=current_user.org_code)
            update_job_planning_status(
                db_session, 
                update_job_data = JobPlanningStatusUpdate(
                team_id = team_id,
                planning_status = "I",
                update_planning_status = "P",
                worker_code_list = worker_code_list,
                start_datetime = start_day,
                end_datetime = end_day
                ))

        planner = get_active_planner(
            org_id=current_user.org_id,
            team_id=team_id,
            force_reload=force_reload,
        )

        if start_day is None:  # request_in.
            # start_day = get_current_day_string()
            # start_time = datetime.strptime(start_day, config.KANDBOX_DATE_FORMAT)
            start_time = planner.env_start_datetime
            end_time = planner.env_decode_from_minutes_to_datetime((planner.get_env_planning_horizon_end_minutes()))
            # end_time = start_time + timedelta(
            #     days=int(planner.config["nbr_of_days_planning_window"])
            # )
        else:
            start_time = datetime.strptime(start_day, config.KANDBOX_DATE_FORMAT)
            end_time = datetime.strptime(end_day, config.KANDBOX_DATE_FORMAT)

        # planner["planner_env"].reload_data_from_db_adapter(
        #     planner["planner_env"].env_start_datetime,
        #     end_datetime=planner["planner_env"].env_decode_from_minutes_to_datetime(
        #         planner["planner_env"].get_env_planning_horizon_end_minutes()
        #     ),
        # )

        # planner["planner_env"]._reset_data()
        # planner["planner_env"].replay_env()

        res = planner.get_solution_dataset(
            start_time, end_time, worker_code_list=worker_code_list,active_only =active_only
        )

        
        workers_data = res.get("workers_data",None)
        worker_color_data = {}
        if workers_data:
            db_session = get_schema_session(org_code=current_user.org_code)
            worker_list_temp = [worker[3] for worker in workers_data]
            workers_ = worker_service.getworker_name_by_code_list(db_session=db_session,code_list=worker_list_temp)
            for worker in workers_:
                if "live_map_color" in worker[2]:
                    worker_color_data[worker[0]] = worker[2]["live_map_color"]
                else:
                    worker_color_data[worker[0]] = next(WORKER_COLOR_ITER)
        res["worker_color_data"] = worker_color_data
        # background_tasks.add_task(background_env_sync, 30, 2)
        if include_finished:
            # 查询已完成状态的数据 , 直接从 db 里面 捞 , 改 redis 有点复杂
            start_time = datetime.strptime(start_day, config.KANDBOX_DATE_FORMAT)

            end_time = datetime.strptime(end_day, config.KANDBOX_DATE_FORMAT)
            planned_jobs_data = res["workers_data"]
            worker_index = {pj[3]:pj[0] for pj in planned_jobs_data}



            data = get_finished_job_service(planner, current_user.org_id ,  team_id, worker_code_list,start_time,end_time)
            finished_job = trance_data_finished(data,worker_index)

            if finished_job:
                finished_job.extend(res["planned_jobs_data"])
                res["planned_jobs_data"] = finished_job
            res["finished_jobs_data"]=finished_job
        else:
            res["finished_jobs_data"]=[]
        response = JSONResponse(res)
        day_str = datetime.strftime(datetime.now(), config.KANDBOX_DATE_FORMAT)
        env_key = f"env_{current_user.org_id}_{team_id}"
        # print(f"env reloaded, cookie = {env_key}")
        response.set_cookie(
            key="env_key",
            value=env_key,
            secure=True,  # if using https and not http
            expires=60 * 60,  # * 60 1 hour in seconds
        )



        return response
    except Exception as e:
        print(f"An exception occurred{e}")
        log.error(traceback.format_exc())
    return JSONResponse({})






#########################################


@planner_router.post(
    "/confirm_assignment/",
    response_model=ConfirmJobsResult,
    summary="Confirm assignments for a worker.",
)
def confirm_assignment_view(
    request_in: ConfirmAssignmentInput,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """
    Get Env Jobs, on all or some workers. This retrives only inplanning or planned jobs assigned to a group of workers. If you set reset_start_datetime == true, this api also reset worker's start time to current time, i.g. shift all jobs to start from now on.
    """
    log.info(f"confirm_assignment:received: {request_in.dict()}")

    worker = worker_service.get(db_session=db_session, code=request_in.worker_code)
    if not worker:
        raise HTTPException(status_code=400, detail="The worker with code {} does not exist.".format(request_in.worker_code))

    env = get_active_planner( 
        org_id=current_user.org_id, team_id=worker.team_id
    )
    result_info = env.confirm_assignment(request_in = request_in ) 
    log.info(f"confirm_assignment:sending: {result_info}")
    return result_info




#########################################
@planner_router.get(
    "/get_unplanned_jobs/",
    summary="Retrieve unplanned jobs in a team.",
    response_model=UnplannedJobPagination
)
def get_unplanned_jobs(
    env_key: str = Cookie(default=None),
    team_id: int = Query(0, alias="team_id"), # 默认为 0 , 即页面不传参数
    current_user: DispatchUser = Depends(get_current_user),
    common: dict = Depends(common_parameters),
    db_session: Session = Depends(get_db),
):
    if not team_id:
        return {"total":0,"items":[],"not_find_code":[]}
    
    log.debug(f"get_unplanned_jobs: team_id = {team_id}, cookie = {env_key}")
    # org_code = current_user.org_code  # "0"  # current_user.org_code
    env = get_active_planner(
        # db_session=common["db_session"],
        org_id=current_user.org_id, team_id=team_id
    )
    start_dt = env.env_decode_from_minutes_to_datetime(
        env.get_env_start_minutes() #  - env.nbr_minutes_backward_unplanned_jobs # 2024-07-27 11:19:05 发现减了两次
    )
    end_dt = env.env_decode_from_minutes_to_datetime(env.get_env_planning_horizon_end_minutes())
    res = job_service.get_unplanned_jobs(
        db_session=db_session,
        start_dt = start_dt,
        end_dt = end_dt,
        team_id = team_id,
        page_number=common["page"], 
        items_per_page=common["items_per_page"],
        sort_by= common["sort_by"],
        descending = common["descending"],
        query_str = common['query_str'],
        nbr_minutes_backward_unplanned_jobs=env.nbr_minutes_backward_unplanned_jobs
    )

    
    return res # JSONResponse(res)

@planner_router.get(
    "/get_planner_env_config/",
    summary="get current env config as a dictionary", 
)
def get_planner_env_config( 
    team_id: int = Query(1, alias="team_id"), 
    current_user: DispatchUser = Depends(get_current_user),
): 
    # result = None 
    # org_id=current_user.org_id
    planner = get_active_planner(
        org_id=current_user.org_id,
        team_id=team_id,
        force_reload=False,
    )
     
    return JSONResponse(   {
        "status": 200,
        "result": planner.config, 
    } )


## ================================================================== ##

@planner_router.post(
    "/hello",
    summary="healthcheck test in every 5 seconds.",
)
def hello():  # current_user: DispatchUser = Depends(get_current_user),
    """
    Refresh the env with all the information from kafka.
    """
    # test_multi_process()

    result_dict = {
        "status": 200,
        "version": str(DISPATCH_VERSION), 
    } 
    return JSONResponse(result_dict)


# async def background_env_sync(refresh_count: int, interval_seconds:int) -> None:
# for r_i in range(refresh_count):
#     print("sleeping")
#     await asyncio.sleep(interval_seconds)
#     print(f"awake for work - hello r_i = {r_i}")
# print("background_env_sync_all is done")



@planner_router.post(
    "/single_job_drop_check/",
    summary="(Alpha, Unstable): To validate all rules over a single job in the current team env",
    response_model=SingleJobDropCheckOutput,
)
def single_job_drop_check(
    request_in: SingleJobDropCheckInput,  #
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    # team_code = current_user.team_id
    # There is no team_id in user

    # if not request_in.start_day:
    #     if request_in.end_day:
    #         raise HTTPException(
    #             status_code=400, detail=f"The start_day and end_day must pair.",
    #         )
    #     request_in.start_day = DATA_START_DAY
    #     request_in.end_day = "20201024"
    # else:
    #     if not request_in.end_day:
    #         raise HTTPException(
    #             status_code=400, detail=f"The start_day and end_day must pair.",
    #         )

    # org_code = current_user.org_code

    # if len(request_in.scheduled_primary_worker_code) < 1:
    #     raise HTTPException(
    #         status_code=400, detail=f"Empty request_in.scheduled_primary_worker_code is not allowed.",
    #     )

    # TODO verify team exist in org
    rl_env = get_active_planner(org_id=current_user.org_id, team_id=request_in.team_id)

    job = job_service.get_by_code(db_session=db_session, code = request_in.job_code)
    if not job:
        raise HTTPException(
            status_code=400,
            detail=f"The job (with job_code ={request_in.job_code}) does not exists.",
        )

    scheduled_worker_codes = [
        request_in.scheduled_primary_worker_code
    ] + request_in.scheduled_secondary_worker_codes
    # for worker_code in scheduled_worker_codes:
    #     if worker_code not in rl_env.workers_dict.keys():
    #         raise HTTPException(
    #             status_code=400,
    #             detail=f"The worker_code ({worker_code}) does not exists.",
    #         )

    scheduled_start_minutes = rl_env.env_encode_from_datetime_to_minutes(
        request_in.scheduled_start_datetime.replace(tzinfo=None)
    )
    one_job_action = ActionDict(
            order= None,
            jobs = [job], # [ self.env_encode_single_job_db(j) for j in job_list],
            action_type=ActionType.JOB_FIXED,
            scheduled_worker_codes=scheduled_worker_codes,
            scheduled_start_minutes=scheduled_start_minutes,
            scheduled_duration_minutes=request_in.scheduled_duration_minutes,
            is_forced_action = False,
        )
    result_info = SingleJobDropCheckOutput(
        status_code=ActionScoringResultType.OK,
        score=0,
        travel_time=15,
        messages=[],
    )

    for rule in rl_env.get_job_rule_set():
        rule_checked = rule.evalute_action_normal(env=rl_env, action=one_job_action)

        rule_checked.score_type = rule.title

        # rule_checked_dict = dataclasses.asdict(rule_checked)
        result_info.messages.append(rule_checked)  # rule_checked_dict

        if (rule_checked.score < 1) & (result_info.status_code == ActionScoringResultType.OK):
            result_info.status_code = ActionScoringResultType.WARNING
        if rule_checked.score == -1:
            result_info.status_code = ActionScoringResultType.ERROR
    return result_info
    # return JSONResponse(result_info)


@planner_router.get(
    "/get_locked_slots/",
    response_model=LockedSlotOutput,
    summary="(Alpha, Unstable): Get a list of locked slots.",
)
def get_locked_slots(    
    current_user: DispatchUser = Depends(get_current_user),
):
    planner = get_active_planner(org_id=current_user.org_id, team_id=current_user.team_id)
    rl_env = planner["planner_env"]

    all_slots = []
    lock_prefix = "{}/env_lock/slot/".format(rl_env.team_env_key)
    for lock_slot_code in rl_env.redis_conn.scan_iter(f"{lock_prefix}*"):
        slot_code_str = lock_slot_code.decode("utf-8").split(lock_prefix)[1]
        appt_code = rl_env.redis_conn.get(lock_slot_code)
        # slot_code_str = slot_code.decode("utf-8")
        # s = slot_code_str.split("_")
        w, s_t, e_t = rl_env.slot_server._decode_slot_code_info(slot_code_str)
        start_datetime = rl_env.env_decode_from_minutes_to_datetime(s_t)
        end_datetime = rl_env.env_decode_from_minutes_to_datetime(e_t)
        all_slots.append(
            LockedSlot(
                worker_code=w,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                appt_code=appt_code,
            )
        )

    return LockedSlotOutput(errorNumber=0, lockedSlots=all_slots)



@planner_router.post(
    "/virtual_job_predict/",
    response_model=GenericJobPredictActionOutput,
    summary="(Beta, Unstable): Get a list of recommendations for a single job",
)
def virtual_job_predict(
    request_in: JobCreate,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    log.info(f"virtual_job_predict:received: {request_in.json()}")
    if (not request_in.team.code):
        raise HTTPException(
            status_code=400,
            detail=f"The team code is missing.",
        )

    team = team_service.get_by_code(
        db_session=db_session,
        code=request_in.team.code)
    if not team:
        raise HTTPException(
            status_code=400,
            detail=f"The team code {request_in.team.code} does not exist.",
        )

    team_id = team.id

    virtual_job  = Job(**request_in.dict(exclude={
            "team", "flex_form_data","requested_items", "target_worker", "overwrite_max_orders_limit","is_appointment"
            }),
            team=team,
            flex_form_data=request_in.flex_form_data,
            requested_items = request_in.requested_items,
        )

    env_action = EnvAction(
            order=None,
            jobs = [virtual_job], # [ self.env_encode_single_job_db(j) for j in job_list],
            action_type = ActionType.TODO,
            worker_blacklist = [],
            worker_whitelist = [],
            overwrite_max_orders_limit = False,
        )
    env = get_active_planner(org_id=current_user.org_id, team_id=team_id)
    return do_predict(env, db_session, env_action,)

@planner_router.post(
    "/virtual_order_predict/",
    response_model=GenericJobPredictActionOutput,
    summary="(Beta, Unstable): Get a list of recommendations for an order",
)
def virtual_order_predict(
    order_in: OrderCreate,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    log.info(f"virtual_order_predict:received: {order_in.json()}") 
    if (not order_in.team.code):
        raise HTTPException(
            status_code=400,
            detail="The team code are missing.",
        )
        
    order = order_service.get(db_session=db_session , code = order_in.code)
    if order:
        raise HTTPException(
            status_code=400,
            detail="The order code already exists, please change order code and retry",
        )
    

    team = team_service.get_by_code(
        db_session=db_session, 
        code=order_in.team.code)
    if not team:
        raise HTTPException(
            status_code=400,
            detail="The team code does not exist.",
        )
    team_id = team.id
    env = get_active_planner(org_id=current_user.org_id, team_id=team_id)
    
    env_action = env.create_virtual_order(
        db_session=db_session,
        order_in=order_in)
    return do_predict(env, db_session, env_action,)



def do_predict(
    env, db_session, order_action, 
):
    rl_agent = env.get_real_time_agent()
    if len(order_action.jobs) == 2:
        expected_planner_type = PlannerType.PICKDROP
    else:
        expected_planner_type = PlannerType.SINGLE
    if rl_agent.planner_type != expected_planner_type:
        raise HTTPException(
            status_code=400,
            detail=f"The team is configured with agent: {rl_agent.slug}, which is not compatible with {str(expected_planner_type)}.",
        )
    
    new_action, reason_info = rl_agent.predict_action(
                    env = env,
                    todo_action = order_action,
                    db_session = db_session
                )
    
    result_list = []
    if new_action.action_type not in [ActionType.DELAY_BLOCKED,ActionType.TODO]:
        target_slot = new_action.scheduled_slots[0]
        if len(new_action.jobs) == 2:
            the_job_code = new_action.jobs[1].code
        else:
            the_job_code = new_action.jobs[0].code

        _jobs = [] 
        the_job = None       
        for job_i, job in enumerate(target_slot.assigned_jobs):
            # print(new_action.scheduled_slots[0].assigned_jobs[job_i].scheduled_start_minutes)
            if job.code == the_job_code:
                the_job = job
            _jobs.append(job.to_result(env=env))
            
        if not the_job:
            raise HTTPException(
            status_code=500,
            detail=f"Failed to parse the scheduled job from result {_jobs}",
        )

        # result_list =  env.mutate_get_job_by_action_virtual_order_predict(new_action)

        scheduled_start_datetime = env.env_decode_from_minutes_to_datetime(
            input_minutes=the_job.scheduled_start_minutes
        )
        scheduled_duration_minutes = the_job.scheduled_start_minutes

        result_list.append(GenericJobAction(
            order_code = new_action.order.code if new_action.order else None,
            job_code = the_job_code,
            scheduled_worker_codes = [target_slot.worker_code],
            scheduled_duration_minutes = scheduled_duration_minutes,
            scheduled_start_datetime = scheduled_start_datetime,
            score=new_action.score,
            cost =round(new_action.score, 2) if new_action.score > 0.1 else new_action.score,
            score_detail=reason_info,
            scheduled_slots=[_jobs],
        ))

    errorNumber = 0
    errorDescription = None
    errorDetails = None
    if len(result_list) < 1:
        errorNumber = PLANNER_ERROR_MESSAGES["NO_SLOT"][0]
        errorDescription = "No slot found"
        errorDetails = reason_info
        

    return GenericJobPredictActionOutput(
        errorNumber=errorNumber, 
        errorDescription=errorDescription, 
        recommendations=result_list,
        errorDetails=errorDetails
    )
    
    

@planner_router.post(
    "/generic_job_predict_actions/",
    response_model=GenericJobPredictActionOutput,
    summary="(Depcrecated): Get a list of recommendations for a single job",
)
def generic_job_predict_actions(
    request_in: GenericJobPredictActionInput,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """
    Returns recommended slots for a given job.  The start time already excluded the initial travel time. Those slots will be locked for a few minutes .

    """
    # return JSONResponse(content= {
    #     "errorNumber": 40001,
    #     "errorDescription": "ok",
    #     "recommendations": [
    #         {
    #             "increased_minutes": 32,
    #             "scheduled_datetime": "2023-09-21 10:23:01",
    #             "driver": "SB9Ontario",
    #         },
    #         {
    #             "increased_minutes": 11,
    #             "scheduled_datetime": "2023-09-21 10:13:01",
    #             "driver": "SB8Chino",
    #         }
    #     ]
    # })

    # org_code = current_user.org_code  # "0"  #
    if (not request_in.team_id) and (not request_in.team_code):
        raise HTTPException(
            status_code=400,
            detail="The team id and code are missing.",
        )

    team_id = request_in.team_id
    if not team_id:
        team = team_service.get_by_code(db_session=db_session, code=request_in.team_code)
        team_id = team.id


    env = get_active_planner(org_id=current_user.org_id, team_id=team_id)

    act = env.gen_action_4_existing_job(db_session=db_session, job_code=request_in.job_code)
    return do_predict(env, db_session, act,)


@planner_router.post(
    "/generic_job_commit/",
    response_model=GenericJobCommitOutput,
    summary="(Alpha, Unstable): commit one job action.",
)
def generic_job_commit(
    request_in: GenericJobCommitActionInput,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    job = job_service.get_by_code(db_session=db_session, code=request_in.job_code)
    if not job:
        raise HTTPException(status_code=404, detail=f"The order with code {request_in.job_code} does not exist.")

    team_id = job.team_id # request_in.team_id

    env = get_active_planner(org_id=current_user.org_id, team_id=team_id)
    if job.planning_status in (JobPlanningStatus.IN_PLANNING,  ): # JobPlanningStatus.PLANNED,
        # action_type = ActionType.UNPLAN
        _,_ = env.unplan_job_list(
            target_job_list=[job],
            worker_code=job.scheduled_primary_worker_code,
            db_session=db_session, 
        )
        if  request_in.planning_status == "U":
            return GenericJobCommitOutput(errorNumber=0, errorDescription="OK")
        
    else:
        if  request_in.planning_status == "U":
            return GenericJobCommitOutput(errorNumber=40001, errorDescription=f"current job planning status {job.planning_status} can not be unplanned.")


    action_type = ActionType.FLOATING
    if request_in.scheduled_start_datetime is None:
        return GenericJobCommitOutput(
            errorNumber=PLANNER_ERROR_MESSAGES["WRONG_DATE_INPUT"][0],
            errorDescription=f"scheduled_start_datetime can not be None.",
        )
    if request_in.planning_status == "F":
        action_type = ActionType.FINISHED
    elif request_in.fixed_flag:
        action_type = ActionType.JOB_FIXED

    job_in_slot = env.env_encode_single_job_db(job = job)
    job_in_slot.scheduled_start_minutes = env.env_encode_from_datetime_to_minutes(
        request_in.scheduled_start_datetime.replace(tzinfo=None)
    ) 


    worker_code = request_in.scheduled_worker_codes[0]
    working_slot_list = env.get_working_slot_list(
        worker_code=worker_code,active_only=False,
        start_minutes = job_in_slot.scheduled_start_minutes - 1, 
        end_minutes = job_in_slot.scheduled_start_minutes + 1,
    )


    if len(working_slot_list) == 0:
        return GenericJobCommitOutput(
            errorNumber=PLANNER_ERROR_MESSAGES["WRONG_DATE_INPUT"][0],
            errorDescription=f"worker is not active.",
        )
    _slot = working_slot_list[0]
    job_i = 0
    while job_i < len(_slot.assigned_jobs):
        if _slot.assigned_jobs[job_i].scheduled_start_minutes < job_in_slot.scheduled_start_minutes:
            job_i += 1
        else:
            break
    _slot.assigned_jobs = _slot.assigned_jobs[0:job_i] + [job_in_slot] +  _slot.assigned_jobs[job_i:] 
    if str(env.config.get("generic_job_commit_auto_tsp", 1)) == "1":
        _slot.assigned_jobs = env.solve_tsp_slot_assigned_jobs(
            assigned_jobs=_slot.assigned_jobs)

    _slot.job_change_count += 1
    env.add_single_working_time_slot(slot = _slot)

    curr_job = job
    curr_job.scheduled_start_datetime = request_in.scheduled_start_datetime.replace(tzinfo=None)
    curr_job.planning_status =  JobPlanningStatus.IN_PLANNING 
    curr_job.scheduled_primary_worker_code = worker_code
    db_session.add(curr_job)
    db_session.commit()
    log.info(
        f"JOB:{curr_job.code}:SLOT:{_slot.slot_code}: job is changed to new time: {curr_job.scheduled_start_datetime}"
    )

    errorNumber = 0
    errorDescription = "OK"
    return GenericJobCommitOutput(errorNumber=errorNumber, errorDescription=errorDescription)
    # except Exception as e:
    #     print(f"An exception occurred{e}")
    #     import traceback

    #     log.error(traceback.format_exc())

    # return GenericJobCommitOutput(errorNumber=0, errorDescription="error")
@planner_router.get(
    "/get_scheduled_slots_by_worker/{worker_code}",
    response_model=OrderCreationResultSchedule,
    summary="(Alpha, Unstable): get scheduled slots by worker.",
)
def get_scheduled_slots_by_worker(
    worker_code: str,
    db_session: Session = Depends(get_db),
):
    log.info(f"get_scheduled_slots_by_worker:received: {worker_code}")
    worker = worker_service.get_by_code(db_session=db_session, code=worker_code)
    if worker is None:
        raise HTTPException(
            status_code=400,
            detail=f"The worker code does not exist.",
        )
        
    env = get_active_planner(
        org_id=worker.org_id,
        team_id=worker.team_id,
    )

    start_minutes = env.get_env_planning_horizon_start_minutes()
        
    curr_slots = env.get_working_slot_list(
        worker_code=worker.code,
        start_minutes = start_minutes, 
        end_minutes= start_minutes + 1, # 时间间隔 1 minutes 
        active_only=True
    )
        
    _jobs = []
    for curr_slots in curr_slots:
        for job_i, job in enumerate(curr_slots.assigned_jobs):
            _jobs.append(job.to_result(env=env))
    return OrderCreationResultSchedule( 
        worker_code = worker_code, 
        scheduled_slots = _jobs
    )
    
    
    


@planner_router.post(
    "/refresh_planning_window/",
    response_model=ResetPlanningWindowResult, 
    summary="(Deprecated): refresh planning window for all workers. Use reset function directly",
)
def refresh_planning_window(
    request_in: ResetPlanningWindowInput,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    
    team = team_service.get_by_code(db_session=db_session, code=request_in.team_code)
    if team is None:
        raise HTTPException(
            status_code=400,
            detail=f"The team code you requested is not in your organization.",
        )
    if team.org_id != current_user.org_id:
        raise HTTPException(
            status_code=400,
            detail=f"The team code you requested is not in your organization...",
        )

    planner = get_active_planner(
        org_id=team.org_id,
        team_id=team.id,
    )
    planner.mutate_refresh_planning_window(db_session=db_session)

    result_info = {"status": "OK", "config": planner.config}
    return result_info


@planner_router.post(
    "/set_horizon_start_minutes/",
    response_model=ResetPlanningWindowResult, 
    summary="(Beta, Unstable): Only used for testing purpose. Do not use it in Prod env. THis is to set planning horizon start minutes",
)
def env_set_horizon_start_minutes(
    request_in: TeamEnvInput,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    
    team = team_service.get(db_session=db_session, team_id=request_in.team_id)
    if team is None:
        raise HTTPException(
            status_code=400,
            detail=f"The team code you requested is not in your organization.",
        )
    if team.org_id != current_user.org_id:
        raise HTTPException(
            status_code=400,
            detail=f"The team code you requested is not in your organization...",
        )

    planner = get_active_planner(
        org_id=team.org_id,
        team_id=team.id,
    )
    if (request_in.start_datetime < planner.env_start_datetime) or (
        request_in.start_datetime > planner.env_decode_from_minutes_to_datetime((planner.get_env_planning_horizon_end_minutes()))):
        raise HTTPException(
            status_code=400,
            detail="The requested datetime is out of planning window...",
        )

    result = planner.set_horizon_start_minutes(start_datetime=request_in.start_datetime)

    # result_info = {"status": result, "config": None}
    return ResetPlanningWindowResult(
        status = result, config = None
    )





@planner_router.post(
    "/run_batch_optimizer_over_unplanned/",
    summary="(Alpha, Unstable): run_batch_optimizer_over_unplanned",
)
def run_batch_optimizer_over_unplanned(    
    planning_request: RunOptimizerOverUnplannedInput,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    org_code = current_user.org_code
    team = team_service.get_by_code(db_session=db_session, code=planning_request.team_code)
    if team is None:
        raise HTTPException(
            status_code=400,
            detail=f"The team code you requested is not in your organization.",
        )
    if team.org_id != current_user.org_id:
        raise HTTPException(
            status_code=400,
            detail=f"The team code you requested is not in your organization...",
        )
    redis_conn.set("run_batch_over_unplanned_" + current_user.id.__str__(), "1")    
    redis_conn.expire("run_batch_over_unplanned_" + current_user.id.__str__(), 60)
    try:
        planner = get_default_active_planner(org_code=org_code, team_id=team.id)
        rl_env = planner["planner_env"]
        rl_env.load_unplanned_jobs()

        flag = planner["batch_optimizer"].dispatch_jobs(env=rl_env, rl_agent=planner["planner_agent"], target_job_list=planning_request.target_job_list)
        log.info(f"Finished dispatching {len(rl_env.jobs_dict)} ")
        if not flag or flag == False:
            result_info = {"status": "Error", "jobs_dispatched": 0}
        else:
            result_info = {"status": "OK", "jobs_dispatched": len(rl_env.jobs_dict)}

    except Exception as e:        
        import traceback
        log.error(traceback.format_exc())
        log.error(f"run_batch_optimizer {e}")
        result_info = {"status": "Internal Error", "jobs_dispatched": 0}
    redis_conn.delete("run_batch_over_unplanned_" + current_user.id.__str__())
    return JSONResponse(result_info)


@planner_router.get(
    "/get_frontend_routing_plugin/",
    summary="(Beta, Unstable): get_frontend_routing_plugin. This is used for planner UI.",
)
async def get_planed_jobs(
    db_session: Session = Depends(get_db),
    team_id: int = Query(None, alias="team_id"), 
    current_user: DispatchUser = Depends(get_current_user),
):
    if not team_id:
        raise HTTPException(status_code=400, detail="team_id  is required")

    team = team_service.get(db_session=db_session, team_id=team_id)
    if team is None:
        raise HTTPException(
            status_code=400,
            detail=f"The team code you requested is not in your organization.",
        )
    if team.org_id != current_user.org_id:
        raise HTTPException(
            status_code=400,
            detail=f"The team code you requested is not in your organization...",
        )



    agents = service_plugin_service.get_by_service_id_and_type(
        db_session=db_session,
        service_id=team.service_id,
        service_plugin_type=KandboxPlannerPluginType.kandbox_frontend_routing_adapter,
    )
    if agents.count() != 1:
        raise HTTPException(
            status_code=400,
            detail=f"Wrong configuration, failed to identify exactly one agent for env: {team_id}. Got: agents.count() = {agents.count()}",
        )

    agent_config = {
        "slug":agents[0].plugin.slug,
        "config":agents[0].config,
    }
    
    return JSONResponse(agent_config)


@planner_router.get(
    "/get_planed_jobs/",
    summary="(Alpha, Unstable): get_planed_jobs history planed data. ",
)
async def get_planed_jobs(
    db_session: Session = Depends(get_db),
    team_id: int = Query(None, alias="team_id"),
    start_datatime: str = Query(None, alias="start_datatime"),
    end_datatime: str = Query(None, alias="end_datatime"),
):

    if not team_id:
        raise HTTPException(status_code=400, detail="team_id  is required")

    start_time = datetime.strptime(start_datatime, config.KANDBOX_DATETIME_FORMAT_ISO_SPACE)
    end_time = datetime.strptime(end_datatime, config.KANDBOX_DATETIME_FORMAT_ISO_SPACE)
    all_workers = worker_service.get_by_team(db_session=db_session, team_id=team_id)
    all_jobs = jobService.get_by_team_and_status(
        db_session=db_session,
        team_id=team_id,
        start_time=start_time,
        end_time=end_time,
        planning_status_list=[
            JobPlanningStatus.PLANNED,
            JobPlanningStatus.IN_PLANNING,
            JobPlanningStatus.FINISHED,
        ],
    )  # JobPlanningStatus.CANCELLED,

    res = []
    for worker in all_workers:
        _data = {
            "id": worker.code,
            "name": worker.code,
            "gtArray": [],
        }
        for job in all_jobs:
            if worker.code != job.scheduled_primary_worker_code:
                continue
            start = datetime.strftime(
                job.scheduled_start_datetime, config.KANDBOX_DATETIME_FORMAT_ISO_SPACE
            )
            end = datetime.strftime(
                job.scheduled_start_datetime + timedelta(minutes=job.scheduled_duration_minutes),
                config.KANDBOX_DATETIME_FORMAT_ISO_SPACE,
            )

            _data["gtArray"].append({"id": job.code, "name": job.code, "start": start, "end": end})
        res.append(_data)
    return JSONResponse(res)


from dispatch.config import e6yun_config_dict

@planner_router.get(
    "/get_worker_free_items/{worker_code}",
    response_model=GenericRequestResult,
    summary="(Alpha, Unstable): Get current free items for a worker",
)
async def get_worker_free_items(
    worker_code: str,
    db_session: Session = Depends(get_db),
    current_user: DispatchUser = Depends(get_current_user),
):

    worker = worker_service.get_by_code(db_session=db_session, code=worker_code)
    if worker_code is None:
        raise HTTPException(
            status_code=400,
            detail=f"The worker code does not exist.",
        )
    if worker.org_id != current_user.org_id:
        raise HTTPException(
            status_code=400,
            detail=f"The worker does not exist in your organization...",
        )

    env = get_active_planner(
        org_id=worker.org_id,
        team_id=worker.team_id,
    )

    start_minutes = env.get_env_planning_horizon_start_minutes()
    curr_slots = env.get_working_slot_list(
        worker_code=worker.code,
        start_minutes = start_minutes,
        end_minutes=start_minutes+1,
        active_only=True
        )

    res = False
    if len(curr_slots) > 0:
        # item_key = env.get_env_slot_free_items_key(slot_code=curr_slots[0].slot_code)
        free_dict = [
            {"item_code": k, "qty": v}  for k,v in curr_slots[0].free_items.items() if float(v) > 0 and not k.startswith('__')
        ]

        return GenericRequestResult(
            errorNumber = 200,
            errorDescription = "OK",
            data = {"free_items": free_dict}

        )
    else:
        return GenericRequestResult(
            errorNumber = 40001,
            errorDescription = "The requested worker does not have active shift"
        )


    if res:
        return GenericRequestResult(
                errorNumber = 0,
                errorDescription = "Shift updated."
            )
    else:
        return GenericRequestResult(
            errorNumber = 40001,
            errorDescription = "Error when update worker status"
        )




@planner_router.get(
    "/get_job_free_times/{job_code}",
    summary="(Alpha, Unstable): Get task allowed shift time window",
)
async def get_job_free_times(
    job_code: str,
    db_session: Session = Depends(get_db),
    current_user: DispatchUser = Depends(get_current_user),
):

    org_code = current_user.org_code
    job = job_get_by_code(db_session=db_session, code=job_code)
    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")
    team_id = job.team_id

    rl_env = get_active_planner(org_id=current_user.org_id, team_id=team_id)
    res = get_free_time(rl_env, job_code)
    return JSONResponse(res)


def get_free_time(rl_env, job_code):

    res = {"status": "OK", "result": []}
    env_start_datetime = rl_env.env_start_datetime
    weekday = env_start_datetime.weekday()
    if job_code not in rl_env.jobs_dict.keys():
        raise HTTPException(
            status_code=400,
            detail=f"The job (with job_code ={job_code}) does not exists in env.",
        )
    job_dict = rl_env.jobs_dict[job_code]
    job_location = [job_dict.location.geo_longitude, job_dict.location.geo_latitude]
    worker_code = job_dict.scheduled_worker_codes[0]

    worker_dict = rl_env.workers_dict[worker_code]
    worker_start_minutes = (
        worker_dict.curr_slot.start_minutes + worker_dict.weekly_working_slots[weekday][0][0]
    )
    worker_end_minutes = (
        worker_dict.curr_slot.start_minutes + worker_dict.weekly_working_slots[weekday][0][1]
    )
    worker_location = worker_dict.curr_slot.start_location[:2]

    job_list = [
        (_job_code, job_obj.scheduled_start_minutes)
        for _job_code, job_obj in rl_env.jobs_dict.items()
        if worker_code in job_obj.scheduled_worker_codes and job_code != _job_code
    ]

    if job_list:
        job_list_sorted = sorted(job_list, key=lambda k: k[1], reverse=True)
        last_job_code = job_list_sorted[0][0]

        last_job = rl_env.jobs_dict[last_job_code]
        last_job_location = [last_job.location.geo_longitude, last_job.location.geo_latitude]
        requested_duration_minutes = last_job.requested_duration_minutes

        new_time = math.ceil(
            rl_env.travel_router.get_travel_minutes_2locations(last_job_location, job_location) / 1
        )
        start_time_min = (
            last_job.scheduled_start_minutes + new_time + requested_duration_minutes
            if last_job.scheduled_start_minutes + new_time + requested_duration_minutes
            < worker_end_minutes
            else -1
        )
        end_time_min = worker_end_minutes
    else:
        new_time = math.ceil(
            rl_env.travel_router.get_travel_minutes_2locations(worker_location, job_location) / 1
        )
        start_time_min = (
            worker_start_minutes + new_time
            if worker_start_minutes + new_time < worker_end_minutes
            else -1
        )
        end_time_min = worker_end_minutes
    start_time = (
        rl_env.env_decode_from_minutes_to_datetime(start_time_min) if start_time_min != -1 else -1
    )
    end_time = (
        rl_env.env_decode_from_minutes_to_datetime(end_time_min) if end_time_min != -1 else -1
    )
    if start_time == -1:
        res["status"] = "ERROR"
    else:
        res = {"status": "OK", "result": [str(start_time), str(end_time)]}
    return res


# @planner_router.post(
#     "/planner_job_update/",
#     summary="update planned job message.",
#     response_model=SingleJobDropCheckOutput,
# )
# def planner_job_update(
#     request_in: SingleJobDropCheckInputNew,  #
#     current_user: DispatchUser = Depends(get_current_user),
#     db_session: Session = Depends(get_db),
# ):
#     """
#     {
#     "job_code": "20220303_ym2022022518",
#     "scheduled_start_datetime": "2022-03-03T13:59:19+08:00",
#     "categoryIndex": 0,
#     "team_id": 19,
#     "start_day": "20220303",
#     "end_day": "20220304",
#     }

#     IN_PLANNING = "I"
#     UNPLANNED = "U"
#     PLANNED = "P"
#     CANCELLED = "C"
#     FINISHED = "F"

#     """
#     """
#     ● 前一天的订单可以更改司机和时间
#     ● 当天 
#         ● 不可更改司机
#         ● 装车时间前  可以修改时间，可以删除订单
#         ● 装车时间后  啥都不能改
#     """

#     """
#     删除 最好 彻底删除job 包括env数据
#     """
#     result_info = SingleJobDropCheckOutput(
#         status_code=ActionScoringResultType.OK,
#         score=0,
#         travel_time=0,
#         messages=[],
#     )
#     org_code = current_user.org_code
#     job = job_get_by_code(db_session=db_session, code=request_in.job_code)
#     if not job:
#         raise HTTPException(status_code=404, detail="The requested job does not exist.")
#     team_id = job.team_id

#     rl_env = get_active_planner(org_id=current_user.org_id, team_id=team_id)
#     env_start_day = rl_env.config["env_start_day"]
#     today_str = datetime.strftime(
#         request_in.scheduled_start_datetime.replace(tzinfo=None), config.KANDBOX_DATE_FORMAT
#     )
#     today_datetime_str = datetime.strftime(
#         request_in.scheduled_start_datetime.replace(tzinfo=None),
#         config.KANDBOX_DATETIME_FORMAT_ISO_SPACE,
#     )

#     res = get_free_time(rl_env, request_in.job_code)
#     if (
#         res["status"] == "OK"
#         and today_datetime_str < res["result"][0]
#         or today_datetime_str > res["result"][1]
#     ):
#         result_info.status_code = ActionScoringResultType.ERROR
#         result_info.messages.append(f'Time is not within the allowed time window {res["result"]}.')
#         return result_info

#     if request_in.job_code not in rl_env.jobs_dict.keys():
#         raise HTTPException(
#             status_code=400,
#             detail=f"The job (with job_code ={request_in.job_code}) does not exists in env.",
#         )
#     job_dict = rl_env.jobs_dict[request_in.job_code]

#     if (
#         job_dict.planning_status == JobPlanningStatus.UNPLANNED
#         and request_in.planning_status == JobPlanningStatus.IN_PLANNING
#     ):
#         result_info.status_code = ActionScoringResultType.ERROR
#         result_info.messages.append(
#             "The current task has not been scheduled, please call interface /jobs/{job_code} to modify."
#         )
#         return result_info

#     if env_start_day == today_str:
#         # 当天

#         e6yun = E6YunCore(appkey=None, appsecret=None, config_dict=e6yun_config_dict)
#         data = [request_in.job_code]
#         res = e6yun.get_order_detail(data)
#         if res["code"] == 1 and len(res["result"]) > 0:
#             order = res["result"][0]
#             # 确认交货时间
#             confirmDeliveryTime = order["confirmDeliveryTime"]
#             if confirmDeliveryTime:
#                 result_info.status_code = ActionScoringResultType.ERROR
#                 result_info.messages.append(
#                     "The order has already been confirmDelivery and cannot be modified."
#                 )
#         else:
#             result_info.status_code = ActionScoringResultType.ERROR
#             result_info.messages.append("The current order is not on e6yun.")
#         e6yun = None

#         if result_info.status_code != ActionScoringResultType.OK:
#             return result_info

#     scheduled_worker_codes = job_dict.scheduled_worker_codes
#     for worker_code in scheduled_worker_codes:
#         if worker_code not in rl_env.workers_dict.keys():
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"The worker_code ({worker_code}) does not exists.",
#             )

#     scheduled_start_minutes = rl_env.env_encode_from_datetime_to_minutes(
#         request_in.scheduled_start_datetime.replace(tzinfo=None)
#     )

#     one_job_action_dict = ActionDict(
#         is_forced_action=False,
#         job_code=request_in.job_code,
#         action_type=ActionType.JOB_FIXED,
#         scheduled_worker_codes=scheduled_worker_codes,
#         scheduled_start_minutes=scheduled_start_minutes,
#         scheduled_duration_minutes=job_dict.scheduled_duration_minutes,
#         # slot_code_list =
#     )

#     for rule in rl_env.rule_set:
#         rule_checked = rule.evalute_action_normal(env=rl_env, action_dict=one_job_action_dict)

#         rule_checked.score_type = rule.title

#         # rule_checked_dict = dataclasses.asdict(rule_checked)
#         result_info.messages.append(rule_checked)  # rule_checked_dict

#         if (rule_checked.score < 1) & (result_info.status_code == ActionScoringResultType.OK):
#             result_info.status_code = ActionScoringResultType.WARNING
#         if rule_checked.score == -1:
#             result_info.status_code = ActionScoringResultType.ERROR

#     if result_info.status_code != "OK":
#         return result_info

#     # commit action

#     one_job_action_dict = ActionDict(
#         is_forced_action=False,
#         job_code=request_in.job_code,
#         action_type=ActionType.UNPLAN
#         if request_in.planning_status == "U"
#         else ActionType.FLOATING,
#         scheduled_worker_codes=scheduled_worker_codes,
#         scheduled_start_minutes=scheduled_start_minutes,
#         scheduled_duration_minutes=job_dict.scheduled_duration_minutes,
#     )

#     internal_result_info = rl_env.mutate_update_job_by_action_dict(
#         a_dict=one_job_action_dict, post_changes_flag=True
#     )

#     if internal_result_info.status_code != ActionScoringResultType.OK:
#         result_info.status_code = ActionScoringResultType.ERROR
#         result_info.messages.append(str(internal_result_info))

#     return result_info


# @planner_router.delete(
#     "/delete_planned_job/{job_code}",
#     summary="delete_planned_job.",
# )
# def delete_planned_job(
#     job_code: str,
#     current_user: DispatchUser = Depends(get_current_user),
#     db_session: Session = Depends(get_db),
# ):
#     return_data = {
#         "status": "OK",
#         "message": "",
#     }
#     org_code = current_user.org_code
#     job = job_get_by_code(db_session=db_session, code=job_code)
#     if not job:
#         raise HTTPException(status_code=404, detail="The requested job does not exist.")

#     scheduled_primary_worker = deepcopy(job.scheduled_primary_worker.code)

#     rl_env = get_active_planner(org_id=current_user.org_id, team_id=team_id)

#     e6yun = E6YunCore(appkey=None, appsecret=None, config_dict=e6yun_config_dict)
#     data = [job_code]
#     res = e6yun.get_order_detail(data)
#     if res["code"] == 1 and len(res["result"]) > 0:
#         order = res["result"][0]
#         # 确认交货时间
#         confirmDeliveryTime = order["confirmDeliveryTime"]
#         if confirmDeliveryTime:
#             return_data["status"] = ActionScoringResultType.ERROR
#             return_data[
#                 "message"
#             ] = "The order has already been confirmDelivery and cannot be modified."
#     else:
#         return_data["status"] = ActionScoringResultType.ERROR
#         return_data["message"] = "The current order is not on e6yun."
#     e6yun = None

#     if return_data["status"] != ActionScoringResultType.OK:
#         return JSONResponse(return_data)

#     job_delete(db_session=db_session, job_code=job.code)
#     # delete_job_to_kafka(
#     #     job=job,
#     #     scheduled_primary_worker=scheduled_primary_worker,
#     #     message_type=KafkaMessageType.DELETE_JOB,
#     #     rl_env=rl_env,
#     # )

#     # resetwindow
#     try:
#         result_info, _ = reset_planning_window_for_team(
#             org_code=org_code,
#             team_id=job.team_id,
#         )
#     except Exception as e:
#         import traceback

#         log.error(traceback.format_exc())

#     return JSONResponse(return_data)


# def delete_job_to_kafka(job: Job, scheduled_primary_worker, message_type, rl_env):
#     kafka_server = rl_env.kafka_server
#     scheduled_start_minutes = rl_env.env_encode_from_datetime_to_minutes(
#         job.scheduled_start_datetime
#     )
#     msg = {
#         "message_type": message_type,
#         "message_source_type": KandboxMessageSourceType.ENV,
#         "message_source_code": "USER.Web",
#         "payload": [
#             {
#                 "job_code": job.code,
#                 "scheduled_worker_codes": [scheduled_primary_worker],
#                 "scheduled_start_minutes": scheduled_start_minutes,
#             }
#         ],
#     }
#     kafka_server.process_env_message(msg=msg, auto_replay_in_process=True)


# @planner_router.post(
#     "/checkJobTravelMinutes/",
#     summary="checkJobTravelMinutes.",
#     response_model=JobTravelMinutesOutput,
# )
# def checkJobTravelMinutes(
#     request_in: JobTravelMinutes,
#     current_user: DispatchUser = Depends(get_current_user),
#     db_session: Session = Depends(get_db),
# ):
#     org_code = current_user.org_code
#     team = team_service.get(db_session=db_session, team_id=request_in.team_id)
#     if team is None:
#         raise HTTPException(
#             status_code=400,
#             detail=f"The team code you requested is not in your organization.",
#         )
#     if team.org_id != current_user.org_id:
#         raise HTTPException(
#             status_code=400,
#             detail=f"The team code you requested is not in your organization...",
#         )
#     try:
#         start_time = request_in.scheduled_start_datetime[0:19]  # .split("+")[0]
#         result_info = check_job_travel_minutes(
#             db_session=db_session,
#             org_code=org_code,
#             team_id=team.id,
#             job_code=request_in.job_code,
#             worker_code=request_in.scheduled_primary_worker_code,
#             start_datetime=datetime.strptime(start_time, KANDBOX_DATETIME_FORMAT_ISO),
#         )
#     except Exception as e:
#         import traceback

#         log.error(traceback.format_exc())
#         log.error(f"checkJobTravelMinutes {e}")
#     return result_info


@isinstance_router.post(
    "/run_optimizer", 
    response_model=OptimizerResponese,
    summary = "(Alpha, Unstable): run a simple optimization without storing the data"
)
def run_simple_optimizer_view(
    request_in: OptimizerRequest,
):
    """
    run an optimizer directly without saving jobs to team and env
    """
    # 校验token
    token = request_in.token
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_session = SessionLocal()
    response_result = None
    try:
        instance = instance_service.get_by_instance_id(
            db_session=db_session, instance_id=request_in.ak
        )
        if instance.instance_status != "1":
            return OptimizerResponese(
                state="failure",
                msg="instance can not be used!",
                planned_data=[],
                not_planned_data=[],
            )

        instance_api_info = instance_service.get_api_info(
            db_session=db_session, instance_id=request_in.ak
        )
        if instance_api_info is None:
            return OptimizerResponese(
                state="failure", msg="sku does not exist!", planned_data=[], not_planned_data=[]
            )
        log.info(f"[{now}]  instance_api_info: {instance_api_info.__dict__}")
        list_job_dict = [_job.code for _job in request_in.jobs]
        token_check_result = instance_service.check_token_simple_optimizer(
            ak=request_in.ak,
            jobs_str=json.dumps(list_job_dict),
            token=token,
            sk=instance_api_info.api_sk,
            now=now,
        )
        if not token_check_result:
            return OptimizerResponese(
                state="failure",
                msg="token verification failed!",
                planned_data=[],
                not_planned_data=[],
            )

        response_result = run_simple_optimizer(
            db_session=db_session,
            ak_id=request_in.ak,
            jobs=request_in.jobs,
            start_datetime=request_in.start_datetime,
            end_datetime=request_in.end_datetime,
            depot=request_in.depot,
        )
        # 异步上传执行记录到tablestore
        # TODO, 重新整理计费API
        log_nlp_api_add(
                instance_id=request_in.ak,
                request_param=json.dumps(
                    {
                        "ak": request_in.ak,
                        "jobs": [job.dict() for job in request_in.jobs],
                        "start_datetime": str(request_in.start_datetime),
                        "end_datetime": str(request_in.end_datetime),
                        "depot": request_in.depot.dict(),
                    }
                ),
                response_result=json.dumps(
                    {
                        "msg": response_result.msg,
                        "not_planned_data": [job.code for job in response_result.not_planned_data],
                        "planned_data": [
                            (job.code, str(job.scheduled_start_datetime))
                            for job in response_result.planned_data
                        ],
                        "state": response_result.state,
                    }
                ),
                status=response_result.state,
            ) 

    except Exception as e:
        log.error(f"{now} run_optimizer error: {e}")
        return OptimizerResponese(
            state="failure", msg="server error", planned_data=[], not_planned_data=[]
        )
    finally:
        db_session.close()

    return response_result

