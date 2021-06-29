import logging

from sqlalchemy.sql.elements import Null
from dispatch.config import DATA_START_DAY
from dispatch.plugins.kandbox_planner.env.env_enums import (
    ActionType,
    ActionScoringResultType,
    AppointmentStatus,
)
from dispatch.plugins.kandbox_planner.env.env_models import ActionDict, ActionEvaluationScore
import json
from datetime import datetime, timedelta
from typing import List
import asyncio
import re
import time

from arrow.util import total_seconds
from fastapi import APIRouter, Body, Depends, HTTPException, Query, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from dispatch import config
from dispatch.auth.models import DispatchUser
from dispatch.auth.service import get_current_user
from dispatch.team import service as team_service
from dispatch.database import get_db, search_filter_sort_paginate
from dispatch.plugins.kandbox_planner.util.kandbox_date_util import get_current_day_string
from dispatch.service.planner_service import (
    get_default_active_planner,
    get_appt_dict_from_redis,
    reset_planning_window_for_team,
    run_batch_optimizer
)
from dispatch.team.models import Team, TeamUpdate
from dispatch.service.planner_models import (
    GenericJobPredictActionInput,
    GenericJobPredictActionOutput,
    GenericJobAction,
    GenericJobCommitActionInput,
    LockedSlot, LockedSlotOutput, GenericJobCommitActionInput, GenericJobCommitOutput,
    SingleJobDropCheckInput,
    SingleJobDropCheckOutput,
    PLANNER_ERROR_MESSAGES,
    ResetPlanningWindowInput

)


import dataclasses

planner_router = APIRouter()


log = logging.getLogger(__name__)


@planner_router.post(
    "/hello", summary="healthcheck test in every 5 seconds.",
)
def hello():  # current_user: DispatchUser = Depends(get_current_user),
    """
    Refresh the env with all the information from kafka.
    """

    team_id = 2
    org_code = "0"

    planner = get_default_active_planner(org_code=org_code, team_id=team_id)
    rl_env = planner["planner_env"]

    result_dict = {
        "status": 200,
        "env_inst_code": rl_env.env_inst_code,
        "window_offset": rl_env.kafka_input_window_offset,
        "slot_offset": rl_env.kafka_slot_changes_offset,
    }
    # log.info(
    #     f"env= MY_2, datetime = {datetime.now()}, window_offset = {rl_env.kafka_input_window_offset},slot_offset = { rl_env.kafka_slot_changes_offset},  "
    # )
    return JSONResponse(result_dict)


# async def background_env_sync(refresh_count: int, interval_seconds:int) -> None:
    # for r_i in range(refresh_count):
    #     print("sleeping")
    #     await asyncio.sleep(interval_seconds)
    #     print(f"awake for work - hello r_i = {r_i}")
    # print("background_env_sync_all is done")


#########################################
@planner_router.get(
    "/get_planner_worker_job_dataset/",
    summary="Retrieve a dataset of workers and jobs, in one planner env.",
)
async def get_worker_job_dataset(
    # background_tasks: BackgroundTasks,
    team_id: int = Query(1, alias="team_id"),
    start_day: str = Query(None, alias="start_day"),
    end_day: str = Query(None, alias="end_day"),
    force_reload: bool = Query(False, alias="force_reload"),
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    # print(f"force_reload = {force_reload}")
    org_code = current_user.org_code
    planner = get_default_active_planner(org_code=org_code, team_id=team_id)

    if start_day is None:  # request_in.
        start_day = get_current_day_string()
        start_time = datetime.strptime(start_day, config.KANDBOX_DATE_FORMAT)
        end_time = start_time + timedelta(
            days=planner["planner_env"].config["nbr_of_days_planning_window"]
        )
    else:
        start_time = datetime.strptime(start_day, config.KANDBOX_DATE_FORMAT)
        end_time = datetime.strptime(end_day, config.KANDBOX_DATE_FORMAT)

    # TODO verify team exist in org
    # planner["planner_env"].replay_env()

    res = planner["planner_env"].get_solution_dataset(start_time, end_time)

    # background_tasks.add_task(background_env_sync, 30, 2)
    return JSONResponse(res)


#########################################
@planner_router.get(
    "/get_planner_score_stats/",
    summary="Retrieve planner scores.",
)
def get_planner_score_stats(
    team_id: int = Query(2, alias="team_id"),
    current_user: DispatchUser = Depends(get_current_user),
):
    org_code = current_user.org_code  # "0"  # current_user.org_code
    planner = get_default_active_planner(org_code=org_code, team_id=team_id)

    res = planner["planner_env"].get_planner_score_stats()
    return JSONResponse(res)


@planner_router.post(
    "/single_job_drop_check/",
    summary="single_job_drop_check.",
    response_model=SingleJobDropCheckOutput,
)
def single_job_drop_check(
    request_in: SingleJobDropCheckInput,  #
    current_user: DispatchUser = Depends(get_current_user),
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

    org_code = current_user.org_code

    # if len(request_in.scheduled_primary_worker_id) < 1:
    #     raise HTTPException(
    #         status_code=400, detail=f"Empty request_in.scheduled_primary_worker_id is not allowed.",
    #     )

    # TODO verify team exist in org
    planner = get_default_active_planner(org_code=org_code, team_id=request_in.team_id)
    rl_env = planner["planner_env"]

    if request_in.job_code not in rl_env.jobs_dict.keys():
        raise HTTPException(
            status_code=400,
            detail=f"The job (with job_code ={request_in.job_code}) does not exists in env.",
        )

    scheduled_worker_codes = [request_in.scheduled_primary_worker_id] + \
        request_in.scheduled_secondary_worker_ids
    for worker_code in scheduled_worker_codes:
        if worker_code not in rl_env.workers_dict.keys():
            raise HTTPException(
                status_code=400, detail=f"The worker_code ({worker_code}) does not exists.",
            )

    scheduled_start_minutes = rl_env.env_encode_from_datetime_to_minutes(
        request_in.scheduled_start_datetime.replace(tzinfo=None)
    )

    one_job_action_dict = ActionDict(
        is_forced_action=False,
        job_code=request_in.job_code,
        action_type=ActionType.JOB_FIXED,
        scheduled_worker_codes=scheduled_worker_codes,
        scheduled_start_minutes=scheduled_start_minutes,
        scheduled_duration_minutes=request_in.scheduled_duration_minutes,
        # slot_code_list =
    )

    result_info = SingleJobDropCheckOutput(
        status_code=ActionScoringResultType.OK, score=0, travel_time=15, messages=[],
    )

    for rule in rl_env.rule_set:
        rule_checked = rule.evalute_action_normal(env=rl_env, action_dict=one_job_action_dict)

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
    summary="Get a list of locked slots.",
)
def get_locked_slots(
):
    org_code = "0"  # current_user.org_code
    team_id = 2
    planner = get_default_active_planner(org_code=org_code, team_id=team_id)
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
        all_slots.append(LockedSlot(worker_code=w, start_datetime=start_datetime,
                         end_datetime=end_datetime, appt_code=appt_code))

    return LockedSlotOutput(errorNumber=0, lockedSlots=all_slots)


@planner_router.post(
    "/generic_job_predict_actions/",
    response_model=GenericJobPredictActionOutput,
    summary="Get a list of recommendations.",
)
def generic_job_predict_actions(
    request_in: GenericJobPredictActionInput,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    """
    Returns recommended slots for a given job.  The start time already excluded the initial travel time. Those slots will be locked for a few minutes .

    """

    org_code = current_user.org_code  # "0"  #

    team_id = request_in.team_id

    planner = get_default_active_planner(org_code=org_code, team_id=team_id)
    rl_env = planner["planner_env"]
    rl_agent = planner["planner_agent"]
    # TODO, check later.
    rl_agent.config["nbr_of_actions"] = 5
    rl_agent.use_naive_search_for_speed = True

    if request_in.job_code not in rl_env.jobs_dict.keys():
        return GenericJobPredictActionOutput(
            errorNumber=PLANNER_ERROR_MESSAGES["JOB_NOT_EXIST_IN_ENV"][0],
            errorDescription=f"The JOB (id={request_in.job_code}) is in the system but does not exist in env with team_id={team_id}.",
            recommendations=[],
        )
    res = rl_agent.predict_action_dict_list(job_code=request_in.job_code)

    result_list = []
    for index, a_dict in enumerate(res):

        scheduled_start_datetime = rl_env.env_decode_from_minutes_to_datetime(
            input_minutes=a_dict.scheduled_start_minutes
        )
        result_list.append(
            GenericJobAction(
                scheduled_worker_codes=a_dict.scheduled_worker_codes,
                scheduled_duration_minutes=a_dict.scheduled_duration_minutes,
                scheduled_start_datetime=scheduled_start_datetime,
                score=a_dict.score,
                score_detail=a_dict.score_detail,
            )
        )

    errorNumber = 0
    errorDescription = None
    if len(result_list) < 1:
        errorNumber = PLANNER_ERROR_MESSAGES["NO_SLOT"][0]
        errorDescription = "No slot found"

    return GenericJobPredictActionOutput(
        errorNumber=errorNumber, errorDescription=errorDescription, recommendations=result_list
    )


@planner_router.post(
    "/generic_job_commit/",
    response_model=GenericJobCommitOutput,
    summary="commit one job action.",
)
def generic_job_commit(
    request_in: GenericJobCommitActionInput,
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):

    org_code = current_user.org_code  # "0"  #

    team_id = request_in.team_id

    planner = get_default_active_planner(org_code=org_code, team_id=team_id)
    rl_env = planner["planner_env"]

    if request_in.job_code not in rl_env.jobs_dict.keys():
        return GenericJobCommitOutput(
            errorNumber=PLANNER_ERROR_MESSAGES["JOB_NOT_EXIST_IN_ENV"][0],
            errorDescription=f"The JOB (id={request_in.job_code}) is in the system but does not exist in env with team_id={team_id}.",
        )

    scheduled_start_minutes = rl_env.env_encode_from_datetime_to_minutes(
        request_in.scheduled_start_datetime.replace(tzinfo=None)
    )

    one_job_action_dict = ActionDict(
        is_forced_action=False,
        job_code=request_in.job_code,
        action_type=ActionType.UNPLAN if request_in.planning_status == 'U' else ActionType.FLOATING,
        scheduled_worker_codes=request_in.scheduled_worker_codes,
        scheduled_start_minutes=scheduled_start_minutes,
        scheduled_duration_minutes=request_in.scheduled_duration_minutes,
    )

    internal_result_info = rl_env.mutate_update_job_by_action_dict(
        a_dict=one_job_action_dict, post_changes_flag=True
    )

    if internal_result_info.status_code != ActionScoringResultType.OK:
        errorNumber = 40001
        errorDescription = str(internal_result_info)
    else:
        errorNumber = 0
        errorDescription = "OK"

    return GenericJobCommitOutput(
        errorNumber=errorNumber, errorDescription=errorDescription
    )


@planner_router.post(
    "/reset_planning_window/",
    summary="reset_planning_window.",
)
def reset_planning_window(
    request_in: ResetPlanningWindowInput,
    team_code: str = Query("1", alias="team_code"),
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    org_code = current_user.org_code
    team = team_service.get_by_code(db_session=db_session, code=request_in.team_code)
    if team is None:
        raise HTTPException(
            status_code=400, detail=f"The team code you requested is not in your organization.",
        )
    if team.org_id != current_user.org_id:
        raise HTTPException(
            status_code=400, detail=f"The team code you requested is not in your organization...",
        )
    result_info, _ = reset_planning_window_for_team(
        org_code=org_code,
        team_id=team.id,)

    return JSONResponse(result_info)


@planner_router.post(
    "/run_batch_optimizer/",
    summary="run_batch_optimizer.",
)
def run_batch_optimizer_view(
    request_in: ResetPlanningWindowInput,
    team_code: str = Query("1", alias="team_code"),
    current_user: DispatchUser = Depends(get_current_user),
    db_session: Session = Depends(get_db),
):
    org_code = current_user.org_code
    team = team_service.get_by_code(db_session=db_session, code=request_in.team_code)
    if team is None:
        raise HTTPException(
            status_code=400, detail=f"The team code you requested is not in your organization.",
        )
    if team.org_id != current_user.org_id:
        raise HTTPException(
            status_code=400, detail=f"The team code you requested is not in your organization...",
        )
    result_info = run_batch_optimizer(
        org_code=org_code,
        team_id=team.id,)

    return JSONResponse(result_info)
