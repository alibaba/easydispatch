import math
import threading
import redis

from dispatch.cloudmarket.instance.config import REDIS_API_COUNT_KEY, REDIS_API_LOCK_KEY, REDIS_API_ORDER_KEY
from dispatch.database_util.service import get_schema_session
from dispatch.job.models import JobCreate
from dispatch.logs import service as logService
from dispatch.logs.models import LogCreate
from dispatch.org.models import Organization
from dispatch.plugins.kandbox_planner.env.env_enums import ActionScoringResultType, ActionType, EnvRunModeType, JobPlanningStatus, OrderCreateResultStatusType, TimeSlotType
# from fastapi import HTTPException 


from builtins import KeyError
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import time
import random
from fastapi.encoders import jsonable_encoder

# from prompt_toolkit.log import logger
# , ONCALL_PLUGIN_SLUG
from dispatch.config import MAX_TRANSACTION_RETRY, SIMPLE_OPTIMIZER_CONFIG, SQLALCHEMY_DATABASE_URI, FIVE_GMAX_ADMIN_ACCOUNT


from dispatch.job import service as job_service

from dispatch.database import SessionLocal
from dispatch.plugins.base import plugins
from dispatch.plugins.kandbox_planner.env.env_enums import KandboxPlannerPluginType
from dispatch.plugins.kandbox_planner.env.env_models import EnvAction, NoAvailableSlots, OrderCreationResult, ReplanOrderInput, SlotModifedException, WorkingTimeSlot
# from dispatch.plugins.kandbox_planner.data_adapter.kplanner_db_adapter import KPlannerDBAdapter
from dispatch.plugins.kandbox_planner.util.cache_dict import CacheDict
from dispatch.planner_env.optimizer_models import OptimizerResponese, SimpleLocation
from dispatch.planner_env.planner_models import JobTravelMinutesOutput, WorkerStatusUpdateInput 
from dispatch.planner_plugin import service as service_plugin_service
from dispatch.route import service as service_route_service
from dispatch.planner_plugin.models import ServicePlugin

from dispatch.job import service as jobService
# from dispatch.worker.models import WorkerCreate
from dispatch.cloudmarket.instance import service as instance_service
from dispatch.cloudmarket.sku import service as sku_service
from dispatch.cloudmarket.mearsurement import service as mearsurement_service
from dispatch.cloudmarket.mearsurement.models import Mearsurement
from dispatch.auth import service as auth_service

from ..planner_service.models import  Service, ServiceCreate, ServiceUpdate
from sqlalchemy.orm.attributes import flag_modified

# from dispatch.plugins.kandbox_planner.env.kprl_env_rllib_history_affinity import (
#     KPlannerHistoryAffinityTopNGMMEnv,
# )

# from dispatch.plugins.kandbox_planner.agent.kprl_agent_rllib_ppo import KandboxAgentRLLibPPO
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util

from dispatch.common.utils.kandbox_clear_data import clear_team_data_for_redispatching

from dispatch.plugins.kandbox_planner.env.configurable_dispatch_env import ConfigurableDispatchEnv 

env_classes = {
    "logged_configurable_env":None,
    "configurable_dispatch_env": ConfigurableDispatchEnv
}


import dispatch.config as config
import logging
from threading import Lock

lock = Lock()

log = logging.getLogger(__name__)


planners_dict = CacheDict(cache_len=config.MAX_NBR_PLANNERS_IN_DICT)  # planners[(org_id,team_id,start_day)]= the_planner
planners_seq_dict = dict()

from dispatch.config import redis_pool, REDIS_HOST, REDIS_PORT, REDIS_PASSWORD,REDIS_DB
if REDIS_PASSWORD == "":
    redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=None,db=REDIS_DB)
else:
    redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,db=REDIS_DB)


# import asyncio

planners_dict_lock = threading.Lock()
# planners_dict_lock = asyncio.Lock()
"""
def get(*, db_session, service_id: int) -> Optional[Service]:
    return db_session.query(Service).filter(Service.id == service_id).first()


def get_by_external_id(*, db_session, external_id: str) -> Optional[Service]:
    return db_session.query(Service).filter(Service.external_id == external_id).first()


def get_all(*, db_session):
    return db_session.query(Service)


def get_all_by_status(*, db_session, is_active: bool):
    return db_session.query(Service).filter(Service.is_active.is_(is_active))

"""


def update_service_plugin_config(*, db_session, service_plugin_id: int, new_config_dict: dict) -> Service:
    # query the db to find service_plugin with type env_proxy
    service_plugin = (
        db_session.query(ServicePlugin).filter(ServicePlugin.id == service_plugin_id).one_or_none()
    )

    if not service_plugin:
        # We get information about the plugin
        raise KeyError(f"Can not find service plugin by ID: {service_plugin_id}")

    # service_plugin_config =  service_plugin
    if not service_plugin.config:
        print("Env config Error, should not be None")
        service_plugin.config = {}

    for field in new_config_dict:
        service_plugin.config[field] = new_config_dict[field]
        # https://stackoverflow.com/questions/42559434/updates-to-json-field-dont-persist-to-db
        flag_modified(service_plugin, "config")

    db_session.add(service_plugin)
    db_session.commit()
    return service_plugin


def auto_exec_rl_planner_over_unplanned(planner=None):
    env = planner["planner_env"]
    # observation = env._get_observation_numerical()
    # done = (env.current_job_i >= len(env.jobs))

    done = not (env._move_to_next_unplanned_job())
    for step_index in range(len(env.jobs)):
        if done:
            break
        if env.jobs[env.current_job_i].job_code in config.DEBUGGING_JOB_CODE_SET:
            print("pause for config.DEBUGGING_JOB_CODE_SET")
        action_list = planner["planner_agent"].predict_action_list()

        _observation, _reward, done, _info = env.step(action_list[0])

        b_dict = planner["planner_env"].decode_action_into_dict(action_list[0])
        log.debug(b_dict)

    # env.commit_changed_jobs()


def load_planner(org_id: int, team_id: int, ):
    # org_dict_session.rollback()
    org_dict_session = get_schema_session(org_code="default")
    org_data = org_dict_session.query(Organization).filter(Organization.id == org_id).first()
    org_dict_session.close()

    org_db_session = get_schema_session(org_code=org_data.code)

    if REDIS_PASSWORD == "":
        new_redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=None,db=REDIS_DB)
    else:
        new_redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,db=REDIS_DB)

    # env_slug = org_data.org_setting.get("env_slug", "configurable_dispatch_env")
    env = ConfigurableDispatchEnv( # env_classes[env_slug]
        org_id = org_id, 
        team_id = team_id, 
        db_session = org_db_session, 
        redis_conn = new_redis_conn
    )
    return env




def get_finished_job_service(env, org_id ,  team_id, worker_code,start_time,end_time):
    org_dict_session = get_schema_session(org_code="default")
    org_data = org_dict_session.query(Organization).filter(Organization.id == org_id).first()
    org_dict_session.close()
    org_db_session = get_schema_session(org_code=org_data.code)
    ## 查询 worker XXX 有多少 Jobs   start < x < end  I F
    day_jobs = job_service.get_jobs_worker_days(
        db_session = org_db_session,
        start_datetime = start_time,
        end_datetime = end_time,
        team_id = team_id,
        worker_code  = worker_code,
        include_unplanned = False,
        include_inplanning = False,
        include_finished=True,
    )
    return day_jobs

# def set_planner(org_id: int, team_id: int):

#     team = db_session.query(Team).filter(Team.id == team_id).first()
#     service = db_session.query(Service).filter(Service.id == team.service_id).one_or_none()
#     if not service:
#         raise Exception(f"service is null,{team.service_id}")
#     rules = service_plugin_service.get_by_service_id_and_type(
#         db_session=db_session,
#         service_id=service.id,
#         service_plugin_type=KandboxPlannerPluginType.kandbox_rule,
#     )

#     env_rules = []
#     for rule_plugin_record in rules:
#         rule_plugin = plugins.get_class(rule_plugin_record.plugin.slug)
#         env_rules.append(rule_plugin(config=rule_plugin_record.config))  # json.loads

#     worker_check_rules_plugins = service_plugin_service.get_by_service_id_and_type(
#         db_session=db_session,
#         service_id=service.id,
#         service_plugin_type=KandboxPlannerPluginType.kandbox_worker_check_rule,
#     )
#     worker_check_rules = []
#     for rule_plugin_record in worker_check_rules_plugins:
#         rule_plugin = plugins.get_class(rule_plugin_record.plugin.slug)
#         worker_check_rules.append(rule_plugin(config=rule_plugin_record.config))  # json.loads

#     service_id = team.service_id
#     envs = service_plugin_service.get_by_service_id_and_type(
#         db_session=db_session,
#         service_id=service_id,
#         service_plugin_type=KandboxPlannerPluginType.configurable_kandbox_env,
#     )

#     if envs.count() != 1:  # len(envs) != 1:
#         raise HTTPException(
#             status_code=404,
#             detail=f"service:{team.planner_service.code} ,Wrong configuration, failed to identify not exactly one env proxy",
#         )
#     env_config = envs[0].plugin.config.copy()
#     if envs[0].config is not None:
#         env_config.update(envs[0].config)
#     # if "env_config" in team.flex_form_data.keys():

#     env_config.update(team.flex_form_data)
#     team_holiday_days = env_config.get("team_holiday_days", None)
#     if team_holiday_days is not None:
#         if len(team_holiday_days) > 0:
#             env_config["team_holiday_days"] = team_holiday_days.split(";")

#     env_config["team_holiday_days"] = json.dumps(list(set(org_data.work_calendar["statutory_holidays"] + team_holiday_days)))
#     env_config["promotional_working_days"]=json.dumps(org_data.work_calendar["promotional_working_days"])


#     env_config["nbr_of_days_planning_window"] = env_config["planning_working_days"]
#     # env_config = (
#     #     envs[0].config if envs[0].config is not None else envs[0].plugin.config
#     # )  #  json.loads()
#     env_config["org_id"] = org_data.id
#     env_config["team_id"] = team_id
#     if start_day != config.DEFAULT_START_DAY:
#         env_config["env_start_day"] = start_day
#         env_config["nbr_of_days_planning_window"] = nbr_of_days_planning_window
#     # this blocks rules_slug_config_list from env.
#     # env_config["rules"] = env_rules --> rule_set
#     env_config["worker_check_rules"] = worker_check_rules

#     env_config["service_plugin_id"] = envs[0].id
#     # routing
#     routing_plug_list = service_plugin_service.get_by_service_id_and_type(
#         db_session=db_session,
#         service_id=service_id,
#         service_plugin_type=KandboxPlannerPluginType.kandbox_routing_adapter,
#     )
#     routing_config = {}
#     if routing_plug_list:
#         routing_plugin = plugins.get(routing_plug_list[0].plugin.slug)
#         routing_config = routing_plug_list[0].config
#         if "route_service_code" in routing_config:
#             route_list = service_route_service.get_by_code(
#                 db_session=db_session, code=routing_config.get("route_service_code")
#             )
#             if route_list:
#                 routing_config["osrm_url"] = route_list[0].url
#     else:
#         routing_plugin = plugins.get("kanbox_planner_routing_haversine_proxy")

#     if REDIS_PASSWORD == "":
#         redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=None)
#     else:
#         redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)
#     try:
#         travel_router = routing_plugin(
#             env=routing_config if routing_plug_list and routing_plug_list[0].config else {},
#             redis_conn=redis_conn,
#         )
#     except Exception as e:
#         log.error(f"Failed to initiate travel_route {(e)}, routing_plugin = {routing_plugin}")
#         travel_router = None
    
#     # env_config["travel_router"] = travel_router
#     # env 添加 token ，调用app端api，call back job  使用，
#     user_list = auth_service.get_by_org_team_role(db_session=db_session,org_id=org_id,team_id=team_id,role="Owner")
#     if user_list:
#         user = user_list[0]
#     else:
#         user = auth_service.get_by_email(db_session=db_session, email=FIVE_GMAX_ADMIN_ACCOUNT)    
#     token = user.token if user else ''
#     env_config["token"] = token

#     env_proxy_plugin = plugins.get(envs[0].plugin.slug)
#     new_env = env_proxy_plugin( # ).get_env(
#         config=env_config,
#         redis_conn=redis_conn, 
#         db_session=db_session, 
#         rule_set = env_rules, 
#         travel_router= travel_router
#         )

#     # w, d = new_env.load_transformed_workers()
#     # print(w.count().max(), d)

#     agents = service_plugin_service.get_by_service_id_and_type(
#         db_session=db_session,
#         service_id=service_id,
#         service_plugin_type=KandboxPlannerPluginType.kandbox_agent,
#     )
#     if agents.count() != 1:
#         raise Exception("Wrong configuration, failed to identify exactly one agent")

#     agent_config = agents[0].config  # json.loads()

#     agent_cls = plugins.get_class(agents[0].plugin.slug)
#     new_agent = agent_cls(config=agent_config, env_config=env_config, env=new_env)
#     new_agent.load_model(env_config=env_config)

#     # ================================================================================
#     planner = {"planner_env": new_env, "planner_agent": new_agent, "db_session": db_session}
#     # Batch is optional and attach it if defined
#     batch_optimizers = service_plugin_service.get_by_service_id_and_type(
#         db_session=db_session,
#         service_id=service_id,
#         service_plugin_type=KandboxPlannerPluginType.kandbox_batch_optimizer,
#     )
#     if batch_optimizers.count() > 1:
#         raise Exception("Wrong configuration, failed to identify not exactly one batch_optimizer")
#     elif batch_optimizers.count() == 1:
#         agent_config = batch_optimizers[0].config  # json.loads()
#         batch_optimizer_cls = plugins.get_class(batch_optimizers[0].plugin.slug)
#         new_batch_optimizer = batch_optimizer_cls(
#             config=agent_config  # , kandbox_env=planner["planner_env"]
#         )
#         planner["batch_optimizer"] = new_batch_optimizer

#     # TODO:
#     # observation = new_env.reset()
#     if "replay" not in new_env.config.keys():
#         new_env.config["replay"] = False
#         new_env.config["auto_predict_unplanned"] = False

#     if new_env.config["replay"]:
#         # new_env.reset()   # replay_env already includes it
#         new_env.run_mode = EnvRunModeType.REPLAY
#         # new_env.replay_env()  # This is repeated, since it is already replay-ed in init
#         log.debug("Replayed Env skipped: team_id={} ...".format(team_id))
#         new_env.run_mode = EnvRunModeType.PREDICT
#     # else:
#     #     raise ValueError("Must replay for loading")

#     if new_env.config["auto_predict_unplanned"]:
#         log.debug("auto_predict_unplanned Env: {}, started ...".format(team_id))
#         auto_exec_rl_planner_over_unplanned(planner)
#     return planner


# 2023-01-12 23:04:16, deprecated. Pls use only get_active_planner
# def get_default_active_planner(
#     org_code: str,
#     org_id: int,
#     team_id: int,
#     force_reload: bool = False,
# ):
#     db_session = get_schema_session(org_code=org_code)
#     planner = get_active_planner(
#         db_session = db_session,
#         org_id=org_id,
#         team_id=int(team_id),
#         # start_day=config.DEFAULT_START_DAY,
#         # nbr_of_days_planning_window=-1,
#         force_reload=force_reload,
#     )

#     return planner


def trance_data_finished(data,worker_index):

    workercode_list = list(set([line.scheduled_primary_worker_code for line in data ]))
    worker_seq = dict(zip(workercode_list,[0 for l in workercode_list]))
    list_result = []
    for line in data:

        scheduled_primary_worker_code = line.scheduled_primary_worker_code

        if scheduled_primary_worker_code not in worker_index:
            max_index = max(worker_index.values())
            worker_index[scheduled_primary_worker_code] = max_index + 1


        scheduled_worker_index = worker_index[scheduled_primary_worker_code]

        scheduled_start_datetime = line.scheduled_start_datetime.isoformat()
        scheduled_end_datetime = (line.scheduled_start_datetime + timedelta(minutes=line.scheduled_duration_minutes)).isoformat()

        job_code = line.code
        job_type = "F"
        scheduled_travel_minutes_before = 0

        scheduled_travel_prev_code = "_"
        conflict_level=0
        geo_longitude = line.geo_longitude
        geo_latitude = line.geo_latitude

        changed_flag=0

        worker_seq[scheduled_primary_worker_code] += 1
        job_seq = worker_seq[scheduled_primary_worker_code]

        list_result.append([
            scheduled_worker_index,
            scheduled_start_datetime,
            scheduled_end_datetime,
            job_code,job_type,scheduled_travel_minutes_before,scheduled_travel_prev_code,conflict_level,
            scheduled_primary_worker_code,geo_longitude,geo_latitude,changed_flag,job_seq
        ])
    return list_result

def get_active_planner(
    *,
    # db_session,
    org_id: int,
    team_id: int,
    # start_day: str,
    # end_day: str = None,
    # nbr_of_days_planning_window: int = None,
    force_reload: bool = False,
) -> ConfigurableDispatchEnv:
    # if not nbr_of_days_planning_window:
    #     nbr_of_days_planning_window = date_util.days_between_2_day_string(
    #         start_day=start_day, end_day=end_day
    #     )
    org_id = int(org_id)
    team_id = int(team_id)
    # 2023-12-19 18:24:58, it did not fix the memory leak problem, disabled. Hopefully when python version upgrades, the memory leak will be fixed.
    th_ident = 0 # threading.current_thread().ident

    with planners_dict_lock:
        # async with planners_dict_lock:
        if (org_id, team_id, th_ident, ) in planners_dict.keys():
            if force_reload:
                log.warning(f"force_reload, be careful since this destroys the env from memory... {(org_id, team_id, th_ident) }")
                del planners_dict[(org_id, team_id, th_ident)]
                log.info(
                    f"force_reload==True, and orig_planner is removed from cache for org_id={org_id}, team_id={team_id}, key = {(org_id, team_id, th_ident)}"
                )
            else:
                old_seq = planners_seq_dict.get((org_id, team_id),b'-1')
                curr_seq = redis_conn.hget(f"{{{org_id}_{team_id}}}:e:cfg", "update_seq")
                if curr_seq != old_seq:
                    log.warning(f"Env {(org_id, team_id) } has a different old_seq {old_seq} from redis, latest curr_seq is {curr_seq}. Env is purged and reloaded ...")
                    del planners_dict[(org_id, team_id, th_ident)]
        
        if (org_id, team_id, th_ident,) not in planners_dict.keys():
            planners_dict[(org_id, team_id, th_ident,)] = load_planner(org_id=org_id,team_id=team_id,)
            planners_seq_dict[(org_id, team_id,)] = str.encode(str(int(planners_dict[(org_id, team_id, th_ident,)].config.get("update_seq",-1))))
            # log.info(f"planner_re_created for org_id={org_id}, team_id={team_id}, key = {(org_id, team_id, th_ident)}, len = {len(planners_dict)}")
        # else:
        #     log.info(
        #         f"planner_reused from cache for org_id={org_id}, team_id={team_id}, key = {(org_id, team_id, th_ident)}, len = {len(planners_dict)}"
        #     )
        active_planner = planners_dict[(org_id, team_id, th_ident,)]
        
        return active_planner
    # return None



def get_appt_dict_from_redis(appt_id: str) -> dict:

    appt_on_redis = redis_conn.hgetall(
        "{}{}".format(config.APPOINTMENT_ON_REDIS_KEY_PREFIX, appt_id)
    )

    return appt_on_redis


def get_appt_code_list_from_redis() -> List:

    res_appt_list = []
    for key in redis_conn.scan_iter(match=f"{config.APPOINTMENT_ON_REDIS_KEY_PREFIX}*"):
        job_code = key.decode("utf-8").split(config.APPOINTMENT_ON_REDIS_KEY_PREFIX)[1]
        res_appt_list.append(job_code)
    return res_appt_list


def reset_planning_window_for_team(org_id, team_id):
    # print("skipped reset_planning_window_for_team")
    # return
    team_env_key = "{{{}_{}}}".format(org_id, team_id)
    # redis_conn.delete(env_cfg_key)
    deleted_list = []
    for key in redis_conn.scan_iter(f"{team_env_key}:*"):
        deleted_list.append(key)
        redis_conn.delete(key)
    log.info(f"all existings keys are deleted from env {team_env_key}. Deleted list: {deleted_list}")

    planner = get_active_planner(
        # db_session = db_session,
        org_id=org_id,
        team_id=team_id,
        force_reload=True,
    )

    result_info = {"status": "OK", "config": planner.config}
    return result_info, planner



def update_worker_begin_shift(
        env, db_session, worker, 
        request_in: WorkerStatusUpdateInput):
    if int(env.config.get("slot_by_shift_start", 0)) != 1:
        log.error("update_worker_begin_shift is prohibitted by slot_by_shift_start != 1")
        return False
    worker.geo_longitude = request_in.start_longitude
    worker.geo_latitude = request_in.start_latitude 
    worker.is_shift_started = True
    worker.shift_start_datetime = request_in.shift_start_datetime
    db_session.add(worker)
    db_session.commit()

    start_minutes = env.env_encode_from_datetime_to_minutes(request_in.shift_start_datetime)
    end_minutes = start_minutes+request_in.shift_duration_minutes


    # env.mutate_add_working_slot(
    #     worker, start_minutes, end_minutes
    # )
    # new_slot = WorkingTimeSlot(
    #         slot_code=f"{worker.code}_{int(start_minutes)}",
    #         slot_type = TimeSlotType.FLOATING,
    #         worker_code=worker.code,
    #         available_free_minutes = request_in.shift_duration_minutes,
    #         start_minutes=start_minutes,
    #         end_minutes=start_minutes+request_in.shift_duration_minutes,
    #         start_longitude=request_in.start_longitude,
    #         start_latitude=request_in.start_latitude,
    #         end_longitude=request_in.end_longitude,
    #         end_latitude=request_in.end_latitude,
    #         assigned_jobs = [],
    #     )
    # env.add_single_working_time_slot(new_slot)

    return True


def update_worker_end_shift(
        env: ConfigurableDispatchEnv, db_session, worker, curr_slots,
        request_in: WorkerStatusUpdateInput):

    if int(env.config.get("slot_by_shift_start", 0)) != 1:
        log.error("update_worker_end_shift is prohibitted by slot_by_shift_start != 1")
        return False

    worker.geo_longitude = request_in.start_longitude
    worker.geo_latitude = request_in.start_latitude 
    worker.is_shift_started = False
    worker.is_active = False
    db_session.add(worker)
    db_session.commit()

    for slot in curr_slots: 
        env.delete_single_working_time_slot(slot.worker_code, 60*int(slot.start_minutes))

    return True


# def update_worker_update_location(
#         env, db_session, worker, slot,
#         request_in: WorkerStatusUpdateInput):

#     worker.geo_longitude = request_in.start_longitude
#     worker.geo_latitude = request_in.start_latitude 
#     db_session.add(worker)
#     db_session.commit()

#     # slot.start_longitude=request_in.start_longitude
#     # slot.start_latitude=request_in.start_latitude
#     # env.add_single_working_time_slot(slot)

#     env.update_slot_start_location(
#         worker_code = slot.worker_code, 
#         longitude = request_in.start_longitude, 
#         latitude = request_in.start_latitude,
#     )

#     return True

# from dispatch.contrib.uupaotui.processor.util import do_cprofile
# @do_cprofile('/tmp/run_batch_optimizer.profile.out')
def run_batch_optimizer(org_id, team_id, db_session, batch_request = None):

    # clear_team_data_for_redispatching(org_id, team_id)
    # result_info, rl_env = reset_planning_window_for_team(org_id, team_id)
    job_redis_lock_key = "{{{}_{}}}:lock:run_batch".format(org_id, team_id)
    rl_env = get_active_planner(
            # db_session = db_session,
            org_id=org_id,
            team_id=team_id,
            force_reload=True,
        )
    try:
        with redis_conn.lock(
            job_redis_lock_key,
            timeout=rl_env.batch_optimizer_lock_seconds,
            blocking_timeout=rl_env.batch_optimizer_lock_seconds//2
        ) as lock:
            opti = rl_env.get_batch_optimizer()
            flag = opti.dispatch_jobs(env=rl_env, db_session = db_session, batch_request=batch_request)
            if not flag or flag is False:
                result_info = {"status": "Error"} # , "jobs_dispatched": 0
            else:
                rl_env.sync_env_config_incr({
                    "last_batch_run_datetime": datetime.strftime(
                        rl_env.get_env_planning_horizon_start_datetime(),
                        config.KANDBOX_DATETIME_FORMAT_ISO,
                    )
                })
                result_info = {"status": "OK"} # , "jobs_dispatched": 0
            return result_info
    except redis.exceptions.LockNotOwnedError:
        log.warning(f"Dispatching took longer than expected the {rl_env.batch_optimizer_lock_seconds} seconds")
        return {"status": "Finished_but_too_long"} # , "jobs_dispatched": 0

def check_job_travel_minutes(db_session , org_id, team_id,job_code, worker_code,start_datetime):

    planner = get_default_active_planner(org_id,team_id,False)
    planner_env = planner['planner_env']

    planning_working_days = planner_env.config['planning_working_days']
    start_time = planner_env.env_start_datetime
    end_time =  start_time + timedelta(days=planning_working_days)
    all_jobs = jobService.get_by_team_and_req_time(db_session=db_session, team_id=team_id, start_time=start_time, end_time=end_time) 

    job_list = [i for i in all_jobs if i.code ==job_code]
    if not job_list:
        result_info = JobTravelMinutesOutput(travel=0)    
        return result_info
    cur_job = job_list[0]
    cur_start_datetime = start_datetime
    cur_day =cur_start_datetime.date()
    cur_location = [cur_job.location.geo_longitude , cur_job.location.geo_latitude]
    pre_location = {
                    "log":planner_env.workers_dict[worker_code].weekly_start_gps[0][0],
                    "lat":planner_env.workers_dict[worker_code].weekly_start_gps[0][1]
                    }
    time_location_list = []
    for job in all_jobs:
        
        if  job.planning_status=='U' or worker_code != job.scheduled_primary_worker.code or job.code ==job_code:
            continue        
        # check same day 
        _start_datetime = job.scheduled_start_datetime
        _day =_start_datetime.date()
        if cur_day !=_day:
            continue
        
        if cur_start_datetime.timestamp() > _start_datetime.timestamp():
            _location = {
                    "log":job.location.geo_longitude,
                    "lat":job.location.geo_latitude
                    }
            time_location_list.append((str(_start_datetime) , _location))
    if  time_location_list:
        time_location_list_sorted = sorted(time_location_list,key= lambda k : k[0],reverse= True)
        pre_location = time_location_list_sorted[0][1]
    
    travel_minutes = planner_env.travel_router.get_travel_minutes_2locations([pre_location['log'] , pre_location['lat']],cur_location)
    print( [pre_location['log'] , pre_location['lat']],cur_location, math.ceil(travel_minutes))
    result_info = JobTravelMinutesOutput(travel=math.ceil(travel_minutes))
    
    return result_info




def run_simple_optimizer(db_session ,ak_id:str, jobs:List[JobCreate] ,start_datetime:datetime,end_datetime:datetime,depot:SimpleLocation) ->OptimizerResponese:
    """
    simple optimizer , not save data 
    """

    try:
        state = "success"
        msg = ""
        planned_data = []
        not_planned_data = []
        instance = instance_service.get_by_instance_id(db_session=db_session, instance_id=ak_id)
        if not instance or instance.instance_status != "1":
            msg =  "instance can not be used"
            state = "failure"   

        sku_info = sku_service.get_by_sku_id(db_session=db_session,sku_id=instance.sku_id)
        if not sku_info:
            msg =  "sku_info can not be None"
            state = "failure"              
        
        if not sku_info.config or "router_plugin" not in sku_info.config or "api_optimizer_plugin" not in sku_info.config:
            msg =  "sku_info.config is empty or incomplete !"
            state = "failure"  
        
        if state=='failure':
            result_data = OptimizerResponese(state =state, msg = msg, planned_data = planned_data, not_planned_data = not_planned_data)
            return result_data 
        
        simple_optimizer_data = sku_info.config
        # simple_optimizer_data = json.loads(SIMPLE_OPTIMIZER_CONFIG)
        routing_config = {}
        if simple_optimizer_data["router_plugin"]:
            routing_plugin = plugins.get(simple_optimizer_data["router_plugin"]["slug"])
            routing_config = simple_optimizer_data["router_plugin"]["config"]

            if routing_config["url"]:
                routing_config["osrm_url"] = routing_config["url"]
        else:
            routing_plugin = plugins.get("kanbox_planner_routing_haversine_proxy")

        redis_conn = redis.Redis(connection_pool=redis_pool)
        travel_router = routing_plugin(env=routing_config, redis_conn=redis_conn)

        if simple_optimizer_data["api_optimizer_plugin"]:
            optimizer_plugin = plugins.get(simple_optimizer_data["api_optimizer_plugin"]["slug"])
            optimizer_adapter_service = optimizer_plugin(config={})
            planned_data ,not_planned_data, msg = optimizer_adapter_service.run_optimizer(jobs,start_datetime,end_datetime,travel_router,depot)
            if not planned_data:
                state = "failure"
                logService.create(db_session=db_session, log_in=LogCreate(
                    title="run_simple_optimizer fun error", category='SimpleOptimizer', content=msg, org_id=-1, team_id=-1))
                log.error(
                    f"run_simple_optimizer failed ,{msg}")
            else:
                # 如果该job执行成功，记录redis 统计次数
                # 上锁
                identifier = instance_service.acquire_lock(cli=redis_conn, lockname=REDIS_API_LOCK_KEY + ak_id)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                available_order_len = instance_service.remove_empty_order(
                    db_session=db_session, instance_id=ak_id, instance=instance, now=now
                )
                if available_order_len <= 0:
                    msg =  "instance can not be used!"
                    state = "failure"
                    planned_data = []
                    not_planned_data = []
                    log.error(
                        f"instance can not be used,{ak_id}")
                else:
                    now_hour = (
                        datetime.now()
                        .astimezone(timezone(timedelta(hours=+8)))
                        .strftime("%Y%m%d %H")
                    )
                    instance_service.redis_lua(
                        redis_order_key=REDIS_API_ORDER_KEY + ak_id,
                        redis_count_key=REDIS_API_COUNT_KEY + now_hour + "_" + ak_id,
                    )
                # 释放锁
                instance_service.release_lock(cli=redis_conn, lockname=REDIS_API_LOCK_KEY + ak_id, identifier=identifier)

        else:
            msg =  "not find simple_optimizer plug!"
            state = "failure"
            log.error(
                f"not find simple_optimizer plug,{KandboxPlannerPluginType.kandbox_simple_optimizer}")

        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        log.error(f"run_simple_optimizer error{e} ")

    log.info(f"run_simple_optimizer request,all job:{len(jobs)}, succeed{len(planned_data)} ,failure:{len(not_planned_data)} ,{KandboxPlannerPluginType.kandbox_simple_optimizer}")
    result_data = OptimizerResponese(state =state, msg = msg, planned_data = planned_data, not_planned_data = not_planned_data)
    return result_data


# from dispatch.contrib.uupaotui.processor.util import do_cprofile
# @do_cprofile('/tmp/replan_order_profile.16observed.out')
def replan_order(
    # request_in: ReplanOrderInput,
    db_session,
    env: ConfigurableDispatchEnv, order, db_job_list, 
    worker_blacklist = [],
    worker_whitelist = [],
    overwrite_max_orders_limit: bool = False,
):
    # trx_i = 0
    failed_reasons = []
    for trx_i in range(MAX_TRANSACTION_RETRY):
        reason_info = {}
        try:
            order_action = env.gen_action_from_order(
                order, job_list = db_job_list, worker_blacklist = worker_blacklist,
                worker_whitelist = worker_whitelist,
                overwrite_max_orders_limit = overwrite_max_orders_limit,
                )
            try:
                new_action,reason_info  = env.get_real_time_agent().predict_action(
                    env = env,
                    todo_action = order_action,
                    db_session = db_session
                )
            except NoAvailableSlots as e:
                log.info(f"NoAvailableSlots, Dispatching Failed on order {order.code}, horizon: {env.get_env_planning_horizon_start_minutes()}")
                # failed_action_codes.append(ac)
                return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_BUT_DISPATCH_FAILED,                 
                                            order = order,
                                            scheduled_slots = None,
                                            reason_info = reason_info
                                        )


            if new_action.action_type == ActionType.TODO: 
                log.info(f"ActionType_is_TODO, Dispatching Failed on order {order.code} for unknown reason, horizon: {env.get_env_planning_horizon_start_minutes()}")
                _res_slot = None
                if new_action.scheduled_slots is not None:
                    if len(new_action.scheduled_slots) > 0:
                        _res_slot = []  # new_action.scheduled_slots
                return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_BUT_DISPATCH_FAILED,                 
                                            order = order,
                                            scheduled_slots = _res_slot,
                                            reason_info = reason_info
                                        )
            elif new_action.action_type == ActionType.DELAY_BLOCKED:
                log.info(f"ActionType_is_DELAY_BLOCKED, retry {trx_i} times. Dispatching Failed on order {order.code}, horizon: {env.get_env_planning_horizon_start_minutes()}")
                failed_reasons.append("DELAY_BLOCKED")
                continue

            _jobs = []
            slot = new_action.scheduled_slots[0]
            for job_i, job in enumerate(slot.assigned_jobs):
                # print(new_action.scheduled_slots[0].assigned_jobs[job_i].scheduled_start_minutes)
                _jobs.append(job.to_result(env=env))
            if not order.auto_commit:
                return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_AND_DISPATCHED,                 
                                        order = order,
                                        worker_code = slot.worker_code,
                                        scheduled_slots = _jobs,
                                        reason_info = reason_info
                                    )
            # TODO, 记录所有排班，包括上面失败的尝试。
            res = env.mutate_update_job_by_action(new_action, db_session)
            
            if res.status_code == ActionScoringResultType.OK:
                from dispatch.event import service as event_service
                for _job in new_action.jobs:
                    msg = f"DISPATCH SUCCESS, planning_status={_job.planning_status}, requested_start_datetime={_job.requested_start_datetime}"
                    # log.info(msg)
                    event_service.log_job_event(
                        db_session=db_session,
                        planning_status=_job.planning_status,
                        job_code = _job.code,
                        source="Dispatch User Success",
                        description=msg,
                        job=_job,
                    )
                
                
                log.info(f"order {(order.code, order.flex_form_data, )} is committed into env with action (worker_blacklist, worker_whitelist, overwrite_max_orders_limit = {(new_action.worker_blacklist, new_action.worker_whitelist, new_action.overwrite_max_orders_limit)}. scheduled_slots === { new_action.scheduled_slots }")  
                return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_AND_COMMITTED,                 
                                            order = order,
                                            worker_code = slot.worker_code,
                                            scheduled_slots = _jobs,
                                            reason_info = reason_info
                                        )
            else:
                log.info(f"CREATED_BUT_COMMIT_FAILED: order {order.code} is created with failed action {new_action}")
                return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_BUT_COMMIT_FAILED,                 
                                            order = order,
                                            worker_code = slot.worker_code,
                                            scheduled_slots = _jobs,
                                            reason_info = reason_info 
                                        )

        except SlotModifedException:
            # another client must have changed 'slot' between the time we started Watching it.
            # Retry by generating a new action.
            sleep_seconds = 0.1*random.randint(1,5)*trx_i
            log.warning(f"SlotModifedException:order:{order.code}: Transaction interrupted {trx_i} times. I will retry after {sleep_seconds} seconds.")
            # continue
            failed_reasons.append(f"SlotModifed-{trx_i}-{sleep_seconds}")
            time.sleep(sleep_seconds)

    # if trx_i >= MAX_TRANSACTION_RETRY:
    log.error(f"failed to add slot, trx_i = {trx_i} reached MAX_TRANSACTION_RETRY {MAX_TRANSACTION_RETRY}. failed_reasons = {failed_reasons}")
    return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_BUT_DISPATCH_FAILED,                 
                                order = order,
                                scheduled_slots = None,
                                reason_info = reason_info 
                            )

def replan_job(
    # request_in: ReplanOrderInput,
    db_session,
    env: ConfigurableDispatchEnv, 
    db_job, 
    auto_commit = True,
    worker_blacklist = [],
    worker_whitelist = [],
    overwrite_max_orders_limit: bool = False,
    is_appointment: bool = False,
    ex_slot = None
):
    # trx_i = 0
    failed_reasons = []
    todo_job_action = EnvAction(
            order= None,
            jobs = [db_job], 
            action_type = ActionType.TODO,
            worker_blacklist = worker_blacklist,
            worker_whitelist = worker_whitelist,
            overwrite_max_orders_limit = overwrite_max_orders_limit,
            is_appointment = is_appointment,
        )
    for trx_i in range(MAX_TRANSACTION_RETRY):
        reason_info = {}
        try:
            try:
                new_action ,reason_info = env.get_real_time_agent().predict_action(
                    env = env,
                    todo_action = todo_job_action,
                    db_session = db_session
                )
            except NoAvailableSlots as e:
                log.info(f"NoAvailableSlots, Dispatching Failed on order {db_job.code}, horizon: {env.get_env_planning_horizon_start_minutes()}")
                # failed_action_codes.append(ac)
                return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_BUT_DISPATCH_FAILED,                 
                                            order = None,
                                            jobs = [db_job], 
                                            scheduled_slots = None,
                                            reason_info = reason_info
                                        )


            if new_action.action_type == ActionType.TODO: 
                log.info(f"ActionType_is_TODO, Dispatching Failed on order {db_job.code} for unknown reason, horizon: {env.get_env_planning_horizon_start_minutes()}")
                _res_slot = None
                if new_action.scheduled_slots is not None:
                    if len(new_action.scheduled_slots) > 0:
                        _res_slot = []
                
                return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_BUT_DISPATCH_FAILED,                 
                                            order = None,
                                            jobs = [db_job], 
                                            scheduled_slots = _res_slot,
                                            reason_info = reason_info
                                        )
            elif new_action.action_type == ActionType.DELAY_BLOCKED:
                log.info(f"ActionType_is_DELAY_BLOCKED, retry {trx_i} times. Dispatching Failed on order {db_job.code}, horizon: {env.get_env_planning_horizon_start_minutes()}")
                failed_reasons.append("DELAY_BLOCKED")
                continue

            _jobs = []
            slot = new_action.scheduled_slots[0]
            if ex_slot is not None:
                if ex_slot.slot_code not in [s.slot_code for s in new_action.scheduled_slots]:
                    new_action.scheduled_slots.append(ex_slot)
            for job_i, job in enumerate(slot.assigned_jobs):
                # print(new_action.scheduled_slots[0].assigned_jobs[job_i].scheduled_start_minutes)
                _jobs.append(job.to_result(env=env))
            if not auto_commit:
                return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_AND_DISPATCHED,                 
                                        order = None,
                                        jobs=[db_job],
                                        worker_code = slot.worker_code,
                                        scheduled_slots = _jobs
                                    )
            # TODO, 记录所有排班，包括上面失败的尝试。
            res = env.mutate_update_job_by_action(new_action, db_session)
            _jobs =  sorted(_jobs, key=lambda j:j.scheduled_start_datetime)
            if res.status_code == ActionScoringResultType.OK:
                _s = new_action.scheduled_slots[0]
                log.info(f"order {(db_job.code, db_job.flex_form_data, )} is committed_into_env.  worker_blacklist={new_action.worker_blacklist}, worker_whitelist={new_action.worker_whitelist}, overwrite_max_orders_limit = {new_action.overwrite_max_orders_limit}. scheduled_slots = { (_s.slot_code, int(_s.end_minutes), _s.start_longitude, _s.start_latitude, _s.slot_type.value, ) }. len_jobs = {len(_s.assigned_jobs)}, Jobs = {[(j.code, j.scheduled_start_minutes) for j in _s.assigned_jobs]}")  
                
                _changed_slots = {_s.worker_code: _jobs}
                if ex_slot is not None:
                    _changed_slots[ex_slot.worker_code] = [
                        _j.to_result(env=env) for _j in ex_slot.assigned_jobs
                    ]
                return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_AND_COMMITTED,                 
                                            order = None,
                                            worker_code = slot.worker_code,
                                            scheduled_slots = _jobs,
                                            changed_slots = _changed_slots,
                                            reason_info = reason_info
                                        )
            else:
                log.info(f"CREATED_BUT_COMMIT_FAILED: order {db_job.code} is created with failed action {new_action}")
                return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_BUT_COMMIT_FAILED,                 
                                            order = None,
                                            worker_code = slot.worker_code,
                                            scheduled_slots = _jobs,
                                            reason_info = reason_info
                                        )

        except SlotModifedException:
            # another client must have changed 'slot' between the time we started Watching it.
            # Retry by generating a new action.
            sleep_seconds = 0.1*random.randint(1,5)*trx_i
            log.warning(f"SlotModifedException:order:{db_job.code}: Transaction interrupted {trx_i} times. I will retry after {sleep_seconds} seconds.")
            # continue
            failed_reasons.append(f"SlotModifed-{trx_i}-{sleep_seconds}")
            time.sleep(sleep_seconds)

    # if trx_i >= MAX_TRANSACTION_RETRY:
    log.error(f"failed to add slot, trx_i = {trx_i} reached MAX_TRANSACTION_RETRY {MAX_TRANSACTION_RETRY}. failed_reasons = {failed_reasons}")
    return OrderCreationResult(status=OrderCreateResultStatusType.CREATED_BUT_DISPATCH_FAILED,                 
                                order = None,
                                scheduled_slots = None,
                                reason_info = reason_info
                            )

