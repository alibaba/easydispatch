import threading
from fastapi import HTTPException
import pytz
import sqlalchemy
from sqlalchemy import or_, and_, func
import json
from datetime import datetime, timedelta
import time
import copy
from typing import Dict, List
from itertools import combinations
from sklearn_extra.cluster import KMedoids
import numpy as np
import pandas as pd
import redis
# from redis.exceptions import LockError
import logging
import socket
# from redis.exceptions import LockNotOwnedError
from sqlalchemy.orm.attributes import flag_modified

from dispatch.config import (DEFAULT_AREA_CODE, DEFAULT_TEAM_TIMEZONE, KANDBOX_DATETIME_FORMAT_GTS_SLOT, MATCHING_LONG_LAT_PRECISION,   MAX_MINUTES_PER_TECH, LONG_LAT_PRECISION, MINUTES_PRECISION, 
    REDIS_JOB_QUEUE_OPTIMIZER, REDIS_JOB_QUEUE_REALTIME,
    SEPERATOR_TOP_0, SEPERATOR_TOP_1, SEPERATOR_FLEX_0, SEPERATOR_FLEX_1, 
    SEPERATOR_TOP_2,SEPERATOR_TOP_3,
    day_seq2day_str, JOBINSLOT_REQUESTED_WORKER
    )
from dispatch.order.models import Order, OrderRead
from dispatch.org.models import Organization
# from dispatch.plugins.kandbox_planner.env.configurable_slot_server import (
#     ConfigurableSlotServer 
# )
from intervaltree import Interval, IntervalTree

from dispatch.database_util.org_config import (
    default_team_flex_form_data,
    default_rust_env_config_data,
)
# import dispatch.plugins.kandbox_planner.env.env_redis_key as env_redis_key
# from dispatch.plugins.base import plugins
# TODO, seems odd, 2021-11-29 18:56:57, duan,
# from dispatch.main import  app
# from dispatch.common.utils.cli import install_plugins
# install_plugins()

from dispatch.location.models import Location
from dispatch.plugins.kandbox_planner.travel_time_plugin import HaversineTravelTime1
from dispatch.planner_service.models import Service
from dispatch.team.models import Team
from dispatch.worker.models import Worker
from dispatch.job.models import Job, JobPlanningInfoUpdate

from dispatch.worker import service as worker_service
from dispatch.job import service as job_service
from dispatch.order import service as order_service
from dispatch.team import service as team_service
from dispatch.event import service as event_service
from dispatch.planner_plugin import service as service_plugin_service

from dispatch.plugins.base import plugins

import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util
import dispatch.config as kandbox_config

from dispatch.plugins.kandbox_planner.env.env_models import (
    ConfirmAssignmentInput,
    EnvAction,
    SlotModifedException,
    WorkingTimeSlot,
    LocationTuple,
    JobLocation,
    # Worker,
    # Job,
    # BaseJob,
    # Appointment,
    # Absence,
    ActionDict,
    SingleJobCommitInternalOutput,
    ActionEvaluationScore,
    JobLocationBase,
    RecommendedAction,
    RecommendationCommitInternalOutput,
    JobInSlot,
)
from dispatch.plugins.kandbox_planner.env.env_enums import *
from dispatch.plugins.kandbox_planner.env.env_enums import (
    EnvRunModeType,
    JobPlanningStatus,
    ActionType,
    ActionScoringResultType,
    JobType,
)
from dispatch.planner_env.planner_models import SingleJobDropCheckOutput
from dispatch.config import (
    NBR_OF_OBSERVED_WORKERS,
    MINUTES_PER_DAY,
    MAX_NBR_OF_JOBS_PER_DAY_WORKER,
    SCORING_FACTOR_STANDARD_TRAVEL_MINUTES,
    DATA_START_DAY,
    MIN_START_MINUTES_FROM_NOW,
    UU_API_TOKEN,
    UU_API_URL,
)
# from scipy.stats import multivariate_normal
from dispatch.plugins.kandbox_planner.util.kandbox_util import (
    min_max_normalize,
    min_max_denormalize,
    parse_item_str,
    parse_item_from_str,
    try_bytes_to_str,
    encode_job_code2rustenv,
    encode_job_flex_form2rustenv,
    check_geo_range,
)
import requests

from dispatch.plugins.kandbox_planner.util.kandbox_date_util import extract_minutes_from_datetime
from dispatch.plugins.bases.kandbox_planner import ConfigurableKandboxEnvPlugin, KandboxPlannerPluginType

from dispatch.plugins.kandbox_planner.planner_engine.jobs_in_slots_planner_shared_head_tail import (
    NaivePlannerJobsInSlots,
)

from dispatch.plugins.kandbox_planner.planner_engine.optimizer_shared_jobs_in_slots import (
    OptimizerJobsInSlots,
)
from dispatch.plugins.kandbox_planner.planner_engine.jobs_in_slots_nearest_neighbour import (
    NearestNeighbourPlannerJobsInSlots,
)
# from dispatch.team.service import get_or_add_redis_team_flex_data
from dispatch.plugins.kandbox_planner.planner_engine.jobs_in_slots_weighted_nearest_neighbour import (
    WeightedNearestNeighbourPlannerJobsInSlots,
)

from dispatch.plugins.kandbox_planner.planner_engine.jobs_in_slots_ortools_routing import (
    OrtoolsRoutingPlannerJobsInSlots,
)

inner_slot_planner_cls_dict = {
    # kandbox_inner_planner_ortools_routing
    "ortools_routing": OrtoolsRoutingPlannerJobsInSlots,
    "nearest_neighbour": NearestNeighbourPlannerJobsInSlots,
    "weighted_nearest_neighbour": WeightedNearestNeighbourPlannerJobsInSlots,
    "head_tail": NaivePlannerJobsInSlots,
    "opti": OptimizerJobsInSlots,
}

from dispatch.worker import service as worker_service
from dispatch.job import service as job_service
from dispatch.team import service as team_service

#

# from dispatch.plugins.kandbox_planner.env.recommendation_server import RecommendationServer


# from src.dispatch.contrib.uupaotui.processor.core import order_pool

# This version works on top of json input and produce json out
# Observation: each worker has multiple working_time=days, then divided by slots, each slot with start and end time,

# import holidays

hostname = socket.gethostname()
SLUG_NAME = "configurable_dispatch_env"
log = logging.getLogger(SLUG_NAME)

# RULE_PLUGIN_DICT = {
#     "kandbox_rule_within_working_hour": KandboxRulePluginWithinWorkingHour,
#     "kandbox_rule_sufficient_travel_time": KandboxRulePluginSufficientTravelTime,
#     "kandbox_rule_requested_skills": KandboxRulePluginRequestedSkills,
#     "kandbox_rule_lunch_break": KandboxRulePluginLunchBreak,
#     #
# }

def row2dict(row):
    d = {}
    for column in row.__table__.columns:
        d[column.name] = getattr(row, column.name) # str()

    return d

class ConfigurableDispatchEnv(ConfigurableKandboxEnvPlugin):
    """
    This is an env to have common interface on team, worker and jobs.
    """

    title = "configurable dispatch env"
    slug = SLUG_NAME
    description = "configurable dispatch env, backed by redis."

    default_config = copy.deepcopy(default_team_flex_form_data)
    default_config.update(default_rust_env_config_data)

    config_form_spec = {
        "type": "object",
        "properties": {
        },
    }

    def purge_env(self):
        deleted_list = []
        for key in self.redis_conn.scan_iter(f"{{{self.team_env_key}}}:e:*"):
            deleted_list.append(key)
            self.redis_conn.delete(key)
        log.info(f"all existings keys are deleted from env {self.team_env_key}. Deleted list: {deleted_list}")


    def reset_env(self, db_session, delete_existing_slot = False):
        # Shoukd I Remove previous leftover slots first? yes
        self.purge_env()
        # This initialize the env dataset in redis for this envionrment.
        # all subsequent env operations should read from this .
        org_data = db_session.query(Organization).filter(Organization.id == self.org_id).first()
        if not org_data:
            raise ValueError(f"orgnization not found, id: {self.org_id}")

        team = db_session.query(Team).filter(Team.id == self.team_id).one_or_none()
        if not team:
            raise ValueError(f"team not found,id: {self.team_id}, org:{(org_data.code, org_data.id)}")


        env_config = team.flex_form_data
        if "team_geo_longitude" not in env_config:
            env_config["team_geo_longitude"] = team.geo_longitude
            env_config["team_geo_latitude"] = team.geo_latitude

        if "horizon_start_minutes" in env_config:
            log.error("you should not specify horizon_start_minutes, filtering it out")
            env_config.pop("horizon_start_minutes")
        service = db_session.query(Service).filter(Service.id == team.service_id).one_or_none()
        if not service:
            raise ValueError(f"service is null,id: {team.service_id}, team:{self.team_id}")

        rules = service_plugin_service.get_by_service_id_and_type(
            db_session=db_session,
            service_id=team.service_id,
            service_plugin_type=KandboxPlannerPluginType.kandbox_rule,
        )
        env_rules = []
        for rule_plugin_record in rules:
            # rule_plugin = plugins.get_class(rule_plugin_record.plugin.slug)
            # env_rules.append(rule_plugin(config=rule_plugin_record.config))  # json.loads
            rule_plugin = {
                "slug":rule_plugin_record.plugin.slug,
                "config":rule_plugin_record.config,
            }
            env_rules.append(rule_plugin)  # json.loads
        self.redis_conn.set(
            self.get_env_job_rule_set_key(),
            json.dumps(env_rules)
        )


        statutory_holidays = org_data.work_calendar["statutory_holidays"]

        team_holiday_days = env_config.get("team_holiday_days", None)
        env_config_team_holiday_days = {}
        if team_holiday_days is not None:
            if len(team_holiday_days) > 0:
                env_config_team_holiday_days = {
                    d:{"isOpen":False} for d in team_holiday_days.split(";")
                }
        statutory_holidays.update(env_config_team_holiday_days)
        # keep statutory_holidays seperated from team_holiday_days, 2023-12-21 18:49:49
        # env_config["team_holiday_days"] = json.dumps(statutory_holidays)
        env_config["promotional_working_days"]=json.dumps(org_data.work_calendar["promotional_working_days"])
        env_config["org_code"] = org_data.code
        env_config["org_id"] = org_data.id
        env_config["team_id"] = team.id

        self.config.update(env_config)
        if "update_seq" in self.config:
            log.warning("update_seq should not be set in config, must start from 1")
        # redis start from 0, python start from 1.
        self.config["update_seq"] = 1
        # self.update_seq = 0
        if self.config["horizon_start_datetime"] < self.config["env_start_datetime"]:
            self.config["horizon_start_datetime"] = self.config["env_start_datetime"]

        self.env_start_datetime = datetime.strptime(
                self.config["env_start_datetime"], kandbox_config.KANDBOX_DATETIME_FORMAT_ISO
            )  
          
        self.config["data_start_day"] = datetime.strftime(self.env_start_datetime - timedelta(days=kandbox_config.DATA_START_BACK_DAYS), kandbox_config.KANDBOX_DAY_FORMAT_ISO) 
        self.data_start_datetime = datetime.strptime(self.config["data_start_day"], kandbox_config.KANDBOX_DAY_FORMAT_ISO)
        self.config["data_start_seconds"] = int((self.data_start_datetime - datetime(1970,1,1,0,0,0)).total_seconds())
        self.timezone = pytz.timezone(self.config.get("timezone", DEFAULT_TEAM_TIMEZONE))
        _tz_now  = datetime.now(self.timezone)
        self.config["utc_offset_seconds"] = int(_tz_now.utcoffset().total_seconds())

        self._parse_env_config()

        self.sync_env_config(flex_form_data = {}, is_reset = True)
        # self.redis_conn.hset(self.get_env_config_key(), mapping=self.config)

        # # This initialize the env dataset in redis for this envionrment.
        # # all subsequent env replay_env should read from this .
        # self.sync_rust_env_config()


        # initialize the key on redis
        _default_area_id = self.get_or_set_area_code2id("default")

        routing_plug_list = service_plugin_service.get_by_service_id_and_type(
            db_session=db_session,
            service_id=team.service_id,
            service_plugin_type=KandboxPlannerPluginType.kandbox_routing_adapter,
        ) 
        if routing_plug_list:
            routing_config = {
                "slug":routing_plug_list[0].plugin.slug,
                "config":routing_plug_list[0].config,
            }
        else:

            # 1.	Travel time formula is defined as GPS straight line distance *1.5/ (40 KM/Hour), minimum 10 minutes. Those numbers like 1.5, 40, 10 minutes,
            # self.config["travel_speed_km_hour"] = self.config["flex_form_data"]["travel_speed_km_hour"]
            # self.config["travel_min_minutes"] = self.config["flex_form_data"]["travel_min_minutes"]
            default_routing_config = {
                "travel_max_minutes": 180,  # 3 Hours
                "travel_speed_km_hour": 20,
                "travel_min_minutes": 1,
                "travel_mode":"driving",
            }
            routing_config = {
                "slug":"kanbox_planner_routing_haversine_proxy",
                "config":default_routing_config,
            }

        self.redis_conn.set(
            self.get_env_travel_router_config_key(),
            json.dumps(routing_config)
        )

        agents = service_plugin_service.get_by_service_id_and_type(
            db_session=db_session,
            service_id=team.service_id,
            service_plugin_type=KandboxPlannerPluginType.kandbox_agent,
        )
        if agents.count() != 1:
            raise ValueError(f"Wrong_configuration_agent, failed to identify exactly one <kandbox_agent={KandboxPlannerPluginType.kandbox_agent}> for env: {self.team_env_key}. Got: agents.count() = {agents.count()}")

        agent_config = {
            "slug":agents[0].plugin.slug,
            "config":agents[0].config,
        }
        self.redis_conn.set(
            self.get_env_real_time_agent_config_key(),
            json.dumps(agent_config)
        )

        # ================================================================================
        # planner = {"planner_env": new_env, "planner_agent": new_agent, "db_session": db_session}
        # Batch is optional and attach it if defined
        batch_optimizers = service_plugin_service.get_by_service_id_and_type(
            db_session=db_session,
            service_id=team.service_id,
            service_plugin_type=KandboxPlannerPluginType.kandbox_batch_optimizer,
        )
        if batch_optimizers.count() != 1:
            raise ValueError(f"Wrong_configuration_batch, failed to identify exactly one batch_optimizer for env {self.team_env_key}")
        agent_config = {
            "slug":batch_optimizers[0].plugin.slug,
            "config":batch_optimizers[0].config,
        }
        self.redis_conn.set(
            self.get_env_batch_optimizer_config_key(),
            json.dumps(agent_config)
        )

        self.mutate_refresh_planning_window(
            db_session, 
            delete_existing_slot = delete_existing_slot,
            today_start_date = self.env_start_datetime,
            )
        
        return True


    def __init__(self, org_id, team_id, redis_conn, db_session, config={}):
        self.config = copy.deepcopy(self.default_config)
        if config:
            self.config.update(config) 
        self.area_id2code_dict = {}
        self.job_rule_set = None
        self.worker_rule_set = None
        self.travel_router = None

        self.inner_slot_heur = None
        self.inner_slot_opti = None
        self.real_time_agent = None
        self.batch_optimizer = None
        self.horizon_start_minutes = None

        #
        # each worker and job is a internally saved as dataclass object. They are transformed from a dict in database, or kafka.
        #
        start_env_bootup_datetime = datetime.now()
        self.org_id = int(org_id)
        self.team_id = int(team_id)
        # This team_env_key uniquely identify this Env by starting date and team key. Multiple instances on different servers share same key.
        self.team_env_key =self.get_team_env_key()

        self.redis_conn = redis_conn
        # 2022-12-13 12:07:46, duan, I will include all db functions to env itself, and remove db_adapter soon.
        # log.info("env is creating db_adapter by itslef, not injected.")
        
        # 2023-02-17 13:20:19, No more slot server. The env handles all redis interactions.
        # self.slot_server = ConfigurableSlotServer(env=self, redis_conn=self.redis_conn)

        # env_inst_code is a code for an env Instance, which **globally**, uniquely identify one instance on a shared Env
        self.env_inst_code = "{}:{}".format(self.team_env_key, hostname)
        
        _lock_key = self.get_env_lock_key()
        # log.debug(f"env = {self.env_inst_code}, Trying to get lock over the env key ({_lock_key}) to applying messages")
        flag = True

        with self.redis_conn.lock(
            _lock_key, timeout=60 * 3, blocking_timeout=3
        ):
            flag = False
            # global_env_config = self.redis_conn.hgetall(env_redis_key.get_env_config_key(self.team_env_key))
            env_config_key = self.get_env_config_key()
            if self.redis_conn.exists(env_config_key):
                saved_config = self.redis_conn.hgetall(env_config_key)
                for k, v in saved_config.items():
                    self.config[k.decode('utf8')] = v.decode('utf8')
                self._parse_env_config()
            else:
                self.reset_env(db_session=db_session)

        # self.reload_horizon_start_minutes()

        if flag:
            log.error(f"Failed get a lock {_lock_key} for reloading env")
        # log.debug(f"env = {self.env_inst_code}, Done with redis lock to applying messages")

        self.haversine_travel_router = HaversineTravelTime1(env=self.config)
        if self.initial_plugin_loading_flag:
            try:
                _ = self.get_real_time_agent()
                _ = self.get_travel_router()
                _ = self.get_batch_optimizer()
                _ = self.get_job_rule_set()
            except Exception as e:
                log.error(f"error during initial plugin loading: {str(e)}")

        self.env_bootup_datetime = datetime.now()
        log.info(f"{SLUG_NAME} __init__done__ {self.team_env_key}, thread: {threading.current_thread().ident}, elapsed: {(self.env_bootup_datetime - start_env_bootup_datetime).total_seconds()}, config: {self.config} ")
        
        return

        # TODO, the opti should be plugin as well.
        self.inner_slot_heur = inner_slot_planner_cls_dict[self.config["inner_slot_planner"]](
            env=self
        )
        self.inner_slot_opti = inner_slot_planner_cls_dict["opti"](env=self)


    def _parse_env_config(self):
        self.timezone = pytz.timezone(self.config.get("timezone", DEFAULT_TEAM_TIMEZONE))
        # if "data_start_day" in self.config.keys():
        self.data_start_datetime = datetime.strptime(self.config["data_start_day"], kandbox_config.KANDBOX_DAY_FORMAT_ISO)

        if "env_start_datetime" in self.config:
            self.env_start_datetime = datetime.strptime(
                self.config["env_start_datetime"], kandbox_config.KANDBOX_DATETIME_FORMAT_ISO
            )
        elif "env_start_day" in self.config:
            log.error("Do_not_use_env_start_day")
            self.env_start_datetime = datetime.strptime(
                self.config["env_start_day"], kandbox_config.KANDBOX_DATE_FORMAT
            )
        else:
            # raise ValueError("env_start_datetime is not found in team.flex_form_data")
            raise HTTPException(status_code=400, detail="env_start_datetime is not found in team.flex_form_data")

        if str(self.config.get("fixed_horizon_flag", '0')) == '1':
            new_horizon_start_datetime = datetime.strptime(self.config["horizon_start_datetime"],kandbox_config.KANDBOX_DATETIME_FORMAT_ISO,)
            self.horizon_start_minutes=self.env_encode_from_datetime_to_minutes(new_horizon_start_datetime) 
            if self.horizon_start_minutes < 0:
                # raise ValueError("Negative_horizon_start_minutes is not allowed.")
                raise HTTPException(status_code=400, detail="Negative horizon_start_minutes is not allowed. horizon_start_minutes must be greater than env_start_datetime.")

            self.config["horizon_start_seconds"] = self.env_encode_from_datetime_to_seconds(new_horizon_start_datetime)
        else:
            self.horizon_start_minutes = None
            self.config["fixed_horizon_flag"] = "0"
            self.config["horizon_start_seconds"] = 0

        self.nbr_minutes_backward_unplanned_jobs = int(self.config.get(
            "nbr_minutes_backward_unplanned_jobs", 0))
        self.nbr_minutes_planning_windows_duration = int(self.config.get(
            "nbr_minutes_planning_windows_duration", 1440))
        self.nbr_minutes_backward_planning_window  = int(self.config.get(
            "nbr_minutes_backward_planning_window", -1440))
        self.batch_optimizer_lock_seconds = int(self.config.get(
            "batch_optimizer_lock_seconds", 30))


        self.kmedoid_includes_start_flag = str(self.config.get("kmedoid_includes_start_flag", '1')) == '1'
        # self.always_load_slot_pos = str(self.config.get("always_load_slot_pos", "1"))  == "1"
        self.initial_plugin_loading_flag = str(self.config.get("initial_plugin_loading_flag", "1"))  == "1"


        self.team_geo_longitude = float(self.config.get("team_geo_longitude", 103.5))
        self.team_geo_latitude = float(self.config.get("team_geo_latitude", 1.5))

        self.longitude_max = self.team_geo_longitude + float(self.config.get("longitude_diff_max", 1))
        self.longitude_min = self.team_geo_longitude - float(self.config.get("longitude_diff_min", 1))
        self.latitude_max = self.team_geo_latitude + float(self.config.get("latitude_diff_max", 1)) 
        self.latitude_min = self.team_geo_latitude - float(self.config.get("latitude_diff_min", 1))


    # def __del__(self):
    #     print(f'Destructor_called {SLUG_NAME}, env: {self.team_env_key}, {self} is deleted, thread: {threading.current_thread().ident}')
    #     if self.real_time_agent is not None:
    #         print(f'Destructor__{SLUG_NAME} is deleting real_time_agent: {self.real_time_agent}')
    #         del self.real_time_agent 
    #     if self.travel_router is not None:
    #         del self.travel_router

    def get_job_rule_set(self):
        if self.job_rule_set is None:
            self.job_rule_set = []
            rules = json.loads(self.redis_conn.get(self.get_env_job_rule_set_key()))
            for rule_plugin_record in rules:
                rule_plugin = plugins.get_class(rule_plugin_record["slug"])
                self.job_rule_set.append(rule_plugin(config=rule_plugin_record["config"]))  # json.loads
        return self.job_rule_set

        # self.rule_set_worker_check = []
        # if "worker_check_rules" in env_config.keys():
        #     self.rule_set_worker_check = env_config["worker_check_rules"]
        #     env_config.pop("worker_check_rules", None)

    def get_travel_router(self):
        if self.travel_router is None:
            router_cfg = json.loads(self.redis_conn.get(self.get_env_travel_router_config_key()))
            router_plugin = plugins.get_class(router_cfg["slug"])
            self.travel_router=router_plugin(config=router_cfg["config"])

            log.info(
                f"Initiated travel router: {router_cfg['slug']} for env: {self.env_inst_code} with config : {router_cfg['config']}"
            )
        return self.travel_router

    def get_real_time_agent(self):
        if self.real_time_agent is None:
            cfg = json.loads(self.redis_conn.get(self.get_env_real_time_agent_config_key()))
            plugin = plugins.get_class(cfg["slug"])
            # plugin = 
            self.real_time_agent=plugin(config=cfg["config"])
            self.real_time_agent.config.update(self.config)
            # self.real_time_agent.load_model()

            log.info(
                f"Initiated real_time_agent: {self.real_time_agent.slug} for env: {self.env_inst_code}"
            )
        return self.real_time_agent

    def get_batch_optimizer(self):
        if self.batch_optimizer is None:
            cfg = json.loads(self.redis_conn.get(self.get_env_batch_optimizer_config_key()))
            plugin = plugins.get_class(cfg["slug"])
            self.batch_optimizer=plugin(config=cfg["config"])
            self.batch_optimizer.config.update(self.config)

            log.info(
                f"Initiated batch_optimizer: {self.batch_optimizer.slug} for env: {self.env_inst_code}"
            )
        return self.batch_optimizer





    @property
    def horizon_start_minutes(self):
        return self._horizon_start_minutes

    @horizon_start_minutes.setter
    def horizon_start_minutes(self, value):
        self._horizon_start_minutes = value
        # print('announcing _horizon_start_minutes change')

    def reload_data_from_db_adapter_TODEL(self, start_datetime, end_datetime):
        if self.config.get("sample_history", False):
            self.kp_data_adapter.sample_history_data_from_db(
                start_datetime,
                end_datetime,
                job_generation_max_count=self.config.get("job_generation_max_count", 30),
                nbr_observed_slots=self.config.get("nbr_observed_slots", 7),
            )
        else:
            self.kp_data_adapter.reload_data_from_db(start_datetime, end_datetime)

    def dispatch_jobs_in_slots(self, working_time_slots=[]):
        # This func calls default inner slot planner.
        return self.inner_slot_heur.dispatch_jobs_in_slots(working_time_slots)

    def get_datetime_now(self) -> int:
        time_now = datetime.now(tz=self.timezone).replace(tzinfo=None)
        return time_now 

    def get_env_start_minutes(self) -> int:
        return self.env_encode_from_datetime_to_minutes(self.env_start_datetime)

    def get_env_start_minutes_rounded(self) -> int:
        return (self.env_encode_from_datetime_to_minutes(self.env_start_datetime) // 1440) * 1440

    def get_env_planning_horizon_start_datetime(self) -> int:
        return self.env_decode_from_minutes_to_datetime(self.get_env_planning_horizon_start_minutes())

    def get_env_planning_horizon_start_minutes(self) -> int:
        #  worker_code, start_minutes, end_minutes, slot_type,  worker_code,start_minutes, end_minutes, slot_type
        begin_skip_minutes = int(self.config.get("begin_skip_minutes", 0))

        if self.horizon_start_minutes is not None:
            return self.horizon_start_minutes + begin_skip_minutes

        # Env starts from now on
        # return int((datetime.now() - self.data_start_datetime).total_seconds() / 60)

        return (
            int((self.get_datetime_now() - self.data_start_datetime).total_seconds() / 60)
            + begin_skip_minutes
        )

    def get_env_planning_horizon_end_minutes(self) -> int:
        #  worker_code, start_minutes, end_minutes, slot_type,  worker_code,start_minutes, end_minutes, slot_type
        return self.env_encode_from_datetime_to_minutes(self.env_start_datetime) + self.nbr_minutes_planning_windows_duration

    def get_start_gps_for_worker_day(self, w: Worker, day_seq: int) -> LocationTuple:
        return w.weekly_start_gps[self.env_encode_day_seq_to_weekday(day_seq)]

    def get_end_gps_for_worker_day(self, w: Worker, day_seq: int) -> LocationTuple:
        return w.weekly_end_gps[self.env_encode_day_seq_to_weekday(day_seq)]

    def get_worker_available_overtime_minutes(self, worker_code: str, day_seq: int) -> int:
        worker = self.workers_dict[worker_code]
        available_overtime_list = []
        for limit_days_key in worker.overtime_limits.keys():
            if day_seq in limit_days_key:
                total_overtime = sum([worker.used_overtime_minutes[dsq] for dsq in limit_days_key])
                available_overtime_list.append(
                    worker.overtime_limits[limit_days_key] - total_overtime
                )
        if len(available_overtime_list) < 1:
            return 0
        available_overtime = min(available_overtime_list)
        return available_overtime

    def get_worker_floating_slots(self, worker_code: str, query_start_minutes: int) -> List:
        overlap_slots = self.slot_server.get_overlapped_slots(
            worker_code=worker_code,
            start_minutes=0,
            end_minutes=MAX_MINUTES_PER_TECH,
        )
        floating_slots = []
        for a_slot in overlap_slots:  #
            if self.slot_server.get_time_slot_key(a_slot) in kandbox_config.DEBUGGING_SLOT_CODE_SET:
                log.debug("debug atomic_slot_delete_and_add_back")

            if (a_slot.slot_type == TimeSlotType.FLOATING) or (
                a_slot.start_overtime_minutes + a_slot.end_overtime_minutes > 0
            ):
                if a_slot.start_minutes - query_start_minutes < 0:
                    continue
                # if worker_code == "MY|D|3|CT29":
                #     print("pause")
                floating_slots.append(
                    [
                        a_slot.start_minutes - query_start_minutes,
                        a_slot.end_minutes - query_start_minutes,
                        a_slot.start_overtime_minutes,
                        a_slot.end_overtime_minutes,
                    ]
                )
        return floating_slots



    def env_encode_day_seq_to_weekday(self, day_seq: int) -> int:
        today_start_date = self.data_start_datetime + timedelta(days=day_seq)
        return (today_start_date.weekday() + 1) % 7

    def env_encode_from_datetime_to_minutes(self, input_datetime: datetime) -> int:
        assigned_start_minutes = int(
            (input_datetime - self.data_start_datetime).total_seconds() / 60
        )
        return assigned_start_minutes

    def env_encode_from_datetime_to_seconds(self, input_datetime: datetime) -> int:
        return int((input_datetime - self.data_start_datetime).total_seconds())
    def env_encode_from_datetime_to_day_seq(self, input_datetime: datetime) -> int:
        the_minutes = self.env_encode_from_datetime_to_minutes(input_datetime)
        return int(the_minutes / MINUTES_PER_DAY)

    def env_encode_from_datetime_to_day_with_validation(self, input_datetime: datetime) -> int:
        #  worker_code, start_minutes, end_minutes, slot_type,  worker_code,start_minutes, end_minutes, slot_type

        the_minutes = self.env_encode_from_datetime_to_minutes(input_datetime)
        # I removed 10 seconds from end of window.
        if (the_minutes < self.get_env_planning_horizon_start_minutes()) or (
            the_minutes >= self.get_env_planning_horizon_end_minutes()
        ):
            raise ValueError("Out of Planning Window")

        return int(the_minutes / MINUTES_PER_DAY)

    def env_decode_from_minutes_to_datetime(self, input_minutes: int) -> datetime:
        #  worker_code, start_minutes, end_minutes, slot_type,  worker_code,start_minutes, end_minutes, slot_type
        assigned_start_datetime = self.data_start_datetime + timedelta(minutes=input_minutes)
        return assigned_start_datetime

    def env_decode_from_minutes_to_hhmm_str(self, input_minutes: int) -> str:
        #  worker_code, start_minutes, end_minutes, slot_type,  worker_code,start_minutes, end_minutes, slot_type
        h_m = int(input_minutes % 1440)
        h = str(h_m // 60).zfill(2) + ":" + str(h_m % 60).zfill(2)
        return h

    def env_decode_from_day_seq_to_datetime(self, day_seq: int) -> datetime:
        #  worker_code, start_minutes, end_minutes, slot_type,  worker_code,start_minutes, end_minutes, slot_type
        assigned_start_datetime = self.env_decode_from_minutes_to_datetime(day_seq * 1440)
        return assigned_start_datetime

    def get_encode_shared_duration_by_planning_efficiency_factor(
        self, requested_duration_minutes: int, nbr_workers: int
    ) -> int:

        factor = self.efficiency_dict[nbr_workers]
        return int(requested_duration_minutes * factor / nbr_workers)

    def from_time_window_flex_form_to_list(self, flex_form, env_start_diff = None):
        if env_start_diff is None:
            env_start_diff = self.get_env_start_minutes_rounded()
        
        item_list = []
        if "service_window" in flex_form:
            item_str_list = flex_form["service_window"].split(SEPERATOR_FLEX_0)
            env_start, env_end = (self.get_env_start_minutes(), self.get_env_planning_horizon_end_minutes())
            for item_str in item_str_list:
                if len(item_str) < 3:
                    log.info(f"from_time_window_str_to_list: Failed to parse: {item_str}")
                    continue
                try:
                    tw = item_str.split(SEPERATOR_FLEX_1)
                    if len(tw) != 2:
                        log.info(f"from_time_window_str_to_list: Failed to parse: {item_str}")
                        continue

                    _tw_start = self.env_encode_from_datetime_to_minutes(
                        datetime.strptime(tw[0], KANDBOX_DATETIME_FORMAT_GTS_SLOT)
                    )
                    _tw_end = self.env_encode_from_datetime_to_minutes(
                        datetime.strptime(tw[1], KANDBOX_DATETIME_FORMAT_GTS_SLOT)
                    )

                    # _tw_end = int(tw[1]) + env_start_diff
                    if _tw_start >= env_end or _tw_end < env_start:
                        log.debug(f"from_time_window_str_to_list: outside_of_planning_window: {item_str}")
                        continue
                    if _tw_start >= _tw_end:
                        log.warning(f"from_time_window_str_to_list: Wrong data: {item_str}")
                        continue

                    item_list.append( (_tw_start - env_start_diff, _tw_end - env_start_diff)) 
                except Exception as e:
                    log.warning(f"from_time_window_str_to_list: internal_error: {item_str}, {str(e)}")


            return item_list

        tw_str = flex_form.get("time_window_list", "__")
        if tw_str is None or tw_str == "__" or len(tw_str) < 2:
            # No tw, get start and end
            return item_list
        item_str_list = tw_str.split(SEPERATOR_FLEX_0)
        for item_str in item_str_list:
            if len(item_str) < 3:
                print(f"from_time_window_str_to_list: Failed to parse: {item_str}")
                continue
            try:
                tw = item_str.split(SEPERATOR_FLEX_1)
                _tw_start = int(tw[0]) - env_start_diff
                _tw_end = int(tw[1]) - env_start_diff
                if _tw_start >= _tw_end:
                    print(f"from_time_window_str_to_list: Wrong data: {item_str}")
                    continue
                item_list.append( (_tw_start, _tw_end)) 
            except Exception as e:
                print(f"from_time_window_str_to_list: internal_error: {item_str}, {str(e)}")

        return item_list
    # print(f"from_time_window_str_to_list: tested as : {from_time_window_str_to_list('1,2; 5,9')}")



    def mutate_replay_jobs_single_working_day(self, day_seq: int):
        start_dt = self.env_decode_from_minutes_to_datetime(day_seq * 1440)
        end_dt = self.env_decode_from_minutes_to_datetime( (day_seq + 1) * 1440)
        jobs = self.kp_data_adapter.get_inplanning_jobs(
            start_datetime=start_dt, end_datetime=end_dt
        )
        for job in jobs:
            if job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
                log.debug(f"mutate_replay_jobs_single_working_day: DEBUGGING_JOB_CODE_SET {job.job_code}")
            if action_dict.scheduled_duration_minutes < self.get_env_planning_horizon_start_minutes():
                log.error(
                    f"JOB:{job.job_code}:scheduled_duration_minutes = {job.scheduled_duration_minutes} < {self.get_env_planning_horizon_start_minutes()} , not allowed, skipped from replay"
                )
                continue

            action_dict = self.gen_action_dict_from_job(job=job, is_forced_action=True)
            info = self.mutate_update_job_by_action_dict(
                a_dict=action_dict, post_changes_flag=False
            )

            if info.status_code != ActionScoringResultType.OK:
                log.error(
                    f"Error in job replay , but it will continue. code= {job.job_code},  info: {info} "
                )


    def replay_appointment_to_redis(self):
        # local_loader.load_batch_local_appointment_TODO(env=self)
        for appt_code, value in self.kp_data_adapter.appointment_db_dict.items():

            appt = self.env_encode_single_appointment(value)

            self.mutate_create_appointment(appt, auto_replay=True)
            self.recommendation_server.search_for_recommendations(job_code=appt.job_code)
            log.info(f"APPT:{appt.job_code}: SUCCESSFULLY replayed one appointment")

    def replay_worker_absence_to_redis(self):
        for absence_code in self.kp_data_adapter.absence_db_dict:
            job = self.env_encode_single_absence(self.kp_data_adapter.absence_db_dict[absence_code])
            absence_job = self.mutate_create_worker_absence(job, auto_replay=True)

    def load_transformed_workers(self):

        # start_date =  self.data_start_datetime

        w = []
        # w_dict = {}
        #
        # index = 0
        for wk, worker in self.kp_data_adapter.workers_db_dict.items():
            active_int = 1 if worker["is_active"] else 0
            if active_int != 1:
                log.debug(
                    f"worker { worker['id']} is not active, maybe it shoud be skipped from loading? "
                )
                # TODO
                # included for now , since maybe job on it?
                continue
            # worker_dict = worker.__dict__
            # if type(worker_dict["location"]) != dict:
            #     worker_dict["location"] = worker.location.__dict__

            w_r = self.env_encode_single_worker(worker)
            w.append(w_r)

            # w_dict[w_r.worker_code] = index
            # index += 1

        sorted_workers = sorted(w, key=lambda x: x.worker_code)
        return sorted_workers

    def env_encode_single_appointment(self, appointment=None):
        assigned_start_minutes = self.env_encode_from_datetime_to_minutes(
            appointment["scheduled_start_datetime"]
        )

        job_form = appointment["flex_form_data"]

        try:
            abs_location = self.locations_dict[appointment["code"]]
        except:
            included_job_code = appointment["included_job_codes"][0]
            if included_job_code not in self.jobs_dict.keys():
                log.error(
                    f"{appointment['appointment_code']}: I failed to find the job by code=  {included_job_code}, and then failed to find the Location. Skipped this appointment"
                )
                #
                return
                # abs_location = None  # TODO?
            else:
                abs_location = self.jobs_dict[included_job_code].location

        requested_skills = {}

        scheduled_worker_codes = []
        for jc in job_form["included_job_codes"]:
            if jc not in self.jobs_dict.keys():
                log.error(
                    f"missing included_job_codes, appointment_code= {appointment['appointment_code']}, job_code={jc} "
                )
                return None
            if self.jobs_dict[jc].planning_status != JobPlanningStatus.UNPLANNED:
                # Keep last one for now
                scheduled_worker_codes = self.jobs_dict[jc].scheduled_worker_codes
        if len(scheduled_worker_codes) < 1:
            #
            log.debug(
                f"APPT:{appointment['appointment_code']}:Only u status in appt? I will take requested. "
            )
            scheduled_worker_codes.append(self.jobs_dict[jc].requested_primary_worker_code)

        requested_day_minutes = int(assigned_start_minutes / 1440) * 1440

        appt_job = Job(
            job_code=appointment["appointment_code"],
            job_type=JobType.APPOINTMENT,
            job_schedule_type=JobScheduleType.FIXED_SCHEDULE,  # job_seq: 89, job['job_code']
            planning_status=JobPlanningStatus.PLANNED,
            location=abs_location,
            requested_skills=requested_skills,
            #
            scheduled_worker_codes=scheduled_worker_codes,
            scheduled_start_minutes=assigned_start_minutes,
            scheduled_duration_minutes=appointment["scheduled_duration_minutes"],
            #
            requested_start_min_minutes=(job_form["ToleranceLower"] * 1440) + requested_day_minutes,
            requested_start_max_minutes=(job_form["ToleranceUpper"] * 1440) + requested_day_minutes,
            requested_start_minutes=requested_day_minutes,
            requested_time_slots=[],  # job["requested_time_slots"]
            #
            requested_primary_worker_code=requested_primary_worker_code,
            requested_duration_minutes=appointment["scheduled_duration_minutes"],
            flex_form_data=job_form,
            included_job_codes=job_form["included_job_codes"],
            new_job_codes=[],
            searching_worker_candidates=[],
            appointment_status=job_form["appointment_status"],
            #
            is_active=True,
            is_auto_planning=False,
        )
        self.set_searching_worker_candidates(appt_job)

        return appt_job

    def load_transformed_appointments(self):
        a = []
        a_dict = {}
        #
        index = 0
        for _, appointment in self.kp_data_adapter.appointments_db_dict.items():
            a_r = self.env_encode_single_appointment(appointment)
            a.append(a_r)

            a_dict[a_r.appointment_code] = index
            index += 1

        return a

    def _convert_availability_slot(self, x_str, prev_available_slots):
        orig_slot = x_str.split(";")
        the_result = []  # copy.copy(prev_available_slots)
        for slot in orig_slot:
            if (slot is None) or len(slot) < 1:
                continue
            start_time = datetime.strptime(
                slot.split("_")[0], kandbox_config.KANDBOX_DATETIME_FORMAT_GTS_SLOT
            )
            end_time = datetime.strptime(
                slot.split("_")[1], kandbox_config.KANDBOX_DATETIME_FORMAT_GTS_SLOT
            )

            start_minutes = self.env_encode_from_datetime_to_minutes(start_time)
            end_minutes = self.env_encode_from_datetime_to_minutes(end_time)
            the_result.append((start_minutes, end_minutes))
        # if len(prev_available_slots) < 1:
        # TODO, i take new one simply as Last Known. Is it Right? 2021-02-20 10:01:44
        return the_result

        # prev_tree= IntervalTree.from_tuples(prev_available_slots)
        # curr_tree = IntervalTree.from_tuples(the_result)
        # new_result = [(s[0], s[1]) for s in list(prev_tree)]
        # return new_result

    # def _convert_lists_to_slots(self, input_list: list, job):
    #     orig_loc = self.locations_dict[job["code"]]

    #     CONSTANT_JOB_LOCATION = JobLocationBase(
    #         geo_longitude=orig_loc.geo_longitude,
    #         geo_latitude=orig_loc.geo_latitude,
    #         location_type=LocationType.HOME,
    #         code=orig_loc.code,
    #         # historical_serving_worker_distribution=None,
    #         # avg_actual_start_minutes=0,
    #         # avg_days_delay=0,
    #         # stddev_days_delay=0,
    #         # available_slots=tuple(),  # list of [start,end] in linear scale
    #         # rejected_slots=job["rejected_slots"],
    #     )
    #     job_available_slots = []

    #     for slot in sorted(list(input_list), key=lambda x: x[0]):

    #         wts = WorkingTimeSlot(
    #             slot_type=TimeSlotType.FLOATING,
    #             start_minutes=slot[0],
    #             end_minutes=slot[1],
    #             prev_slot_code=None,
    #             next_slot_code=None,
    #             start_location=CONSTANT_JOB_LOCATION,
    #             end_location=CONSTANT_JOB_LOCATION,
    #             worker_code="_",
    #             available_free_minutes=0,
    #             assigned_job_codes=[],
    #         )

    #         job_available_slots.append(wts)
    #     return job_available_slots

    def mutate_create_replenish_job(
        self,
        slot: WorkingTimeSlot,
        total_accum_items: Dict,
        total_requested_items: Dict,
    ) -> Job:
        """It follow those steps:
        1. summarize all item requirements from all jobs allocated to this slot
        2. Find which depot has enough stock.
        3. Allocate those items from inventory, i.e. from items in depot from curr_qty to allocated_qty.
        """
        if slot is None:
            log.error("mutate_create_replenish_job: slot is None")
            return None
        for jc in slot.assigned_job_codes:
            if jc.split("-")[-1] == "R":
                log.warning(f"replenishment job ({jc}) already exists ...")
                self.kp_data_adapter.update_replenish_job(
                    job=self.jobs_dict[jc], total_requested_items=total_requested_items
                )
                return self.jobs_dict[jc]
        depot_key = list(self.depots_dict.keys())[0]
        inventory_dict = self.kp_data_adapter.get_depot_item_inventory_dict(
            depot_id=self.depots_dict[depot_key]["id"],
            requested_items=list(total_requested_items.keys()),
        )
        depot_location = self.depots_dict[depot_key]["location"]
        items_to_load = dict(total_requested_items)
        for k in inventory_dict.keys():
            if inventory_dict.get(k, 0) - total_requested_items[k] < 0:
                log.warning(f"mutate_create_replenish_job: not enough inventory for item: {k}")
                return None
            # I will load all jobs requests. Current stock are treated as safe stock...
            # items_to_load -= total_accum_items

        requested_worker_code = slot.worker_code
        scheduled_worker_codes = [requested_worker_code]
        requested_start_minutes = (
            slot.start_minutes
        )  # self.get_env_planning_horizon_start_minutes()
        min_minutes = requested_start_minutes - 144000
        max_minutes = requested_start_minutes + 1440000
        net_avail_slots = [
            [
                -144000,
                1440000,
            ]
        ]
        new_job = Job(
            job_code=f"{requested_worker_code}-{requested_start_minutes}-R",
            job_type=JobType.REPLENISH,
            job_schedule_type=JobScheduleType.NORMAL,
            planning_status=JobPlanningStatus.IN_PLANNING,
            location=depot_location,
            requested_skills=[],
            #
            scheduled_worker_codes=scheduled_worker_codes,
            scheduled_start_minutes=requested_start_minutes,
            scheduled_duration_minutes=10,
            #
            requested_start_min_minutes=min_minutes,
            requested_start_max_minutes=max_minutes,
            requested_start_minutes=requested_start_minutes,
            requested_time_slots=[[0, 0]],
            requested_primary_worker_code=requested_worker_code,
            requested_duration_minutes=10,
            #
            requested_items=items_to_load,
            #
            available_slots=net_avail_slots,
            flex_form_data={"depot_code": depot_key},
            searching_worker_candidates=[],
            included_job_codes=[],
            new_job_codes=[],
            appointment_status=AppointmentStatus.NOT_APPOINTMENT,
            #
            is_active=True,
            is_appointment_confirmed=False,
            is_auto_planning=False,
            priority=1,
        )
        self.jobs.append(new_job)
        new_job.job_index = len(self.jobs) - 1
        self.jobs_dict[new_job.job_code] = new_job

        new_slot = self.slot_server.get_slot(
            redis_handler=self.redis_conn,
            slot_code=self.slot_server.get_time_slot_key(slot),
        )
        new_slot.assigned_job_codes = [new_job.job_code] + new_slot.assigned_job_codes
        self.slot_server.set_slot(slot=new_slot)
        new_job_dict = self.env_decode_single_job_to_dict(new_job)
        self.kp_data_adapter.create_new_job(new_job_dict)

        return new_job

    def env_encode_single_job_db(self, job: Job) -> JobInSlot:  # from db dict object to dataclass object
        # try:
            if job.requested_start_datetime is None:
                _requested_start = datetime.now()
            else:
                _requested_start = job.requested_start_datetime
            _requested_start_minutes = self.env_encode_from_datetime_to_minutes(_requested_start)

            if job.planning_status == JobPlanningStatus.UNPLANNED or job.scheduled_start_datetime is None:
                start_minutes = _requested_start_minutes
            else:
                start_minutes = self.env_encode_from_datetime_to_minutes(job.scheduled_start_datetime)
            _requested_items = {}
            # 本来想每个job一个key，独立存储到redis，后来觉得没有必要，在jobinslot里面编码存储就够了。
            # for k,v in self.redis_conn.hscan_iter(
            #     self.get_env_job_info_key(job.code), 
            #     match='P:*'
            # ):
            #     # print((k,v))
            #     _k = k.decode('utf-8').split(":")[1]
            #     _requested_items[_k] = float(v)
            
            if job.requested_items:
                #  None 的时候会 ERROR 
                # for ri in job.requested_items:
                #     if len(ri.split(":")) != 2:
                #         continue
                #     name, qty = ri.split(":")
                #     _requested_items[name] = int(qty)

                # 2024-08-18 16:11:32, job.requested_items is deprecated. Now try to use job.flex_form_data.accum_items
                # Here is only for back compatability
                job.flex_form_data.update({"accum_items":SEPERATOR_FLEX_0.join(job.requested_items)})

            if job.requested_primary_worker_code is not None:
                job.flex_form_data[JOBINSLOT_REQUESTED_WORKER] = job.requested_primary_worker_code
            return JobInSlot(
                scheduled_start_minutes = start_minutes,
                code = job.code,
                geo_longitude = job.geo_longitude,
                geo_latitude = job.geo_latitude,
                prev_travel = -1,
                scheduled_duration_minutes=job.requested_duration_minutes,
                tolerance_end_minutes = _requested_start_minutes + job.tolerance_end_minutes,
                flex_form_data = job.flex_form_data,
            )
        # except:
        #     log.error("error env_encode_single_job_db")
        #     raise ValueError(f"env_encode_single_job_db error on job {job.code}")



    # def env_encode_single_job_dict(self, job: dict) -> Job:  # from db dict object to dataclass object
    #     if job is None:
    #         log.error("env_encode_single_job_dict: job is None")
    #         return
    #     if job["code"] in kandbox_config.DEBUGGING_JOB_CODE_SET:
    #         log.debug(f"debug {kandbox_config.DEBUGGING_JOB_CODE_SET}")

    #     flex_form_data = job["flex_form_data"]

    #     if pd.isnull(job["requested_start_datetime"]):
    #         log.error("requested_start_datetime is null, not allowed")
    #         return None
    #     if pd.isnull(job["requested_duration_minutes"]):
    #         log.error("requested_duration_minutes is null, not allowed")
    #         return None

    #     assigned_start_minutes = 0
    #     scheduled_duration_minutes = 0
    #     if job["planning_status"] in (JobPlanningStatus.PLANNED, JobPlanningStatus.IN_PLANNING):
    #         try:
    #             assigned_start_minutes = int(
    #                 (job["scheduled_start_datetime"] - self.data_start_datetime).total_seconds()
    #                 / 60
    #             )
    #             scheduled_duration_minutes = job["scheduled_duration_minutes"]
    #         except Exception as ve:
    #             log.error(f"Data error: failed to convert scheduled_start_datetime, job = {job}")
    #             return None

    #     requested_start_minutes = int(
    #         (job["requested_start_datetime"] - self.data_start_datetime).total_seconds() / 60
    #     )
    #     min_minutes = requested_start_minutes
    #     max_minutes = requested_start_minutes
    #     if "tolerance_start_minutes" in flex_form_data.keys():
    #         min_minutes = requested_start_minutes + (flex_form_data["tolerance_start_minutes"])
    #     if "tolerance_end_minutes" in flex_form_data.keys():
    #         max_minutes = requested_start_minutes + (flex_form_data["tolerance_end_minutes"])

    #     historical_serving_worker_distribution = {}
    #     if "job_history_feature_data" in job.keys():
    #         if job["job_history_feature_data"] and "historical_serving_worker_distribution" in job["job_history_feature_data"].keys():
    #             historical_serving_worker_distribution = job["job_history_feature_data"][
    #                 "historical_serving_worker_distribution"
    #             ]
    #     if "location" in job.keys():
    #         j_l_code = job["location"]["code"]
    #         j_l_long = job["location"]["geo_longitude"]
    #         j_l_lat = job["location"]["geo_latitude"]

    #         job["code"] = j_l_code  # for compatibility
    #     else:
    #         j_l_code = job["code"]
    #         j_l_long = job["geo_longitude"]
    #         j_l_lat = job["geo_latitude"]

    #     if j_l_code not in self.locations_dict.keys():
    #         job_location = JobLocation(
    #             geo_longitude=j_l_long,
    #             geo_latitude=j_l_lat,
    #             location_type=LocationType.JOB,
    #             code=j_l_code,
    #             historical_serving_worker_distribution=historical_serving_worker_distribution,
    #             avg_actual_start_minutes=0,
    #             avg_days_delay=0,
    #             stddev_days_delay=0,
    #             # rejected_slots=job["rejected_slots"],
    #         )
    #         self.locations_dict[job_location.code] = job_location
    #     else:
    #         _job_location = self.locations_dict[j_l_code]
    #         job_location = JobLocation(
    #             geo_longitude=_job_location.geo_longitude,
    #             geo_latitude=_job_location.geo_latitude,
    #             location_type=_job_location.location_type,
    #             code=_job_location.code,
    #             historical_serving_worker_distribution=historical_serving_worker_distribution,
    #             avg_actual_start_minutes=0,
    #             avg_days_delay=0,
    #             stddev_days_delay=0,
    #         )
    #     # if job_location.geo_longitude < 0:
    #     #     log.warning(
    #     #         f"Job {job['code']} has invalid location :  {job_location.code} with geo_longitude = {job_location.geo_longitude}"
    #     #     )
    #     if "requested_primary_worker" in job.keys():
    #         requested_primary_worker_code = job["requested_primary_worker"].get("code", None)
    #     else:
    #         requested_primary_worker_code = job.get("requested_primary_worker_code", None)

    #     if requested_primary_worker_code not in self.workers_dict.keys():
    #         # "W0"
    #         # requested_primary_worker_code = self.config["default_requested_primary_worker_code"]
    #         worker_code_list = list(self.workers_dict.keys())
    #         # if len(worker_code_list) < 1:

    #         worker_prob = [
    #             self.workers_dict[w].historical_job_location_distribution.pdf(job_location[0:2])
    #             for w in worker_code_list
    #         ]
    #         max_prob_i = np.argmax(worker_prob)
    #         log.debug(
    #             "Job {} has invalid requested worker code {}, and it is replaced by {}.".format(
    #                 job["code"], requested_primary_worker_code, worker_code_list[max_prob_i]
    #             )
    #         )
    #         requested_primary_worker_code = worker_code_list[max_prob_i]

    #     # prev_available_slots = [
    #     #     (s.start_minutes, s.end_minutes) for s in job_location.available_slots
    #     # ]

    #     net_avail_slots = [
    #         [
    #             self.get_env_planning_horizon_start_minutes(),
    #             self.get_env_planning_horizon_end_minutes(),
    #         ]
    #     ]
    #     # TODO duan, change job_location from tuple to dataclass.
    #     # job_location.available_slots.clear()

    #     job_available_slots = self._convert_lists_to_slots(net_avail_slots, job)
    #     # job_location.available_slots = sorted(list(net_avail_slots), key=lambda x: x[0])
    #     if "requested_skills" in job.keys():
    #         # requested_skills = {
    #         #     "skills": set(job["requested_skills"]),
    #         # }
    #         requested_skills = set(job["requested_skills"]) if job["requested_skills"] else set()

    #     else:
    #         requested_skills = set()
    #         # {
    #         #     "skills": set()
    #         # }
    #         log.warning(f"job({job['code']}) has no requested_skills")

    #     the_final_status_type = job["planning_status"]
    #     is_appointment_confirmed = False

    #     # if job_schedule_type == JobScheduleType.FIXED_SCHEDULE:
    #     #     is_appointment_confirmed = True

    #     if "included_job_codes" not in flex_form_data.keys():
    #         flex_form_data["included_job_codes"] = []

    #     scheduled_worker_codes = job.get("scheduled_worker_codes", [])
    #     # print(job["scheduled_primary_worker_code"])

    #     priority = 1
    #     if "priority" in flex_form_data.keys() and isinstance(flex_form_data["priority"], int):
    #         priority = flex_form_data["priority"]
    #     job_requested_items = flex_form_data.get("requested_items", [])
    #     parsed_requested_items = {}
    #     for item_str in job_requested_items:
    #         item_list = parse_item_str(item_str)
    #         parsed_requested_items[item_list[0]] = item_list[1]
    #     final_job = Job(
    #         job_code=job["code"],
    #         job_type=job["job_type"],  # JobType.JOB,
    #         job_schedule_type=JobScheduleType.NORMAL,
    #         planning_status=the_final_status_type,
    #         location=job_location,
    #         requested_skills=requested_skills,  # TODO
    #         #
    #         scheduled_worker_codes=scheduled_worker_codes,
    #         scheduled_start_minutes=assigned_start_minutes,
    #         scheduled_duration_minutes=scheduled_duration_minutes,
    #         #
    #         requested_start_min_minutes=min_minutes,
    #         requested_start_max_minutes=max_minutes,
    #         requested_start_minutes=requested_start_minutes,
    #         requested_time_slots=[[0, 0]],
    #         requested_primary_worker_code=requested_primary_worker_code,
    #         requested_duration_minutes=job["requested_duration_minutes"],
    #         #
    #         available_slots=job_available_slots,
    #         flex_form_data=flex_form_data,
    #         searching_worker_candidates=[],
    #         included_job_codes=flex_form_data["included_job_codes"],
    #         new_job_codes=[],
    #         appointment_status=AppointmentStatus.NOT_APPOINTMENT,
    #         #
    #         requested_items=parsed_requested_items,
    #         #
    #         is_active=job["is_active"],
    #         is_appointment_confirmed=is_appointment_confirmed,
    #         is_auto_planning=job["auto_planning"],
    #         priority=priority,
    #     )
    #     if self.config.get("set_searching_worker_candidates", True):
    #         self.set_searching_worker_candidates(final_job)
    #     else:
    #         final_job.searching_worker_candidates = []

    #     return final_job

    # def load_transformed_jobs(self):
    #     # TODO , need data_window
    #     # This function also alters self.locations_dict
    #     #

    #     w = []

    #     for k, row_dict in self.kp_data_adapter.jobs_db_dict.items():
    #         if row_dict["code"] in kandbox_config.DEBUGGING_JOB_CODE_SET:
    #             log.debug(
    #                 f"load_transformed_jobs Debug {str(kandbox_config.DEBUGGING_JOB_CODE_SET)} "
    #             )

    #         # if pd.isnull(row_dict["requested_primary_worker_code"]):
    #         #     continue
            
    #         # To skip cetain job type.
    #         env_job_type = row_dict["flex_form_data"].get('order_type','')
    #         if env_job_type == 'backToSc':
    #             continue


    #         job = self.env_encode_single_job_dict(job=row_dict)
    #         if job is not None:
    #             w.append(job)
    #     return w

    # def env_encode_single_absence(self, job: dict): #  -> Absence

    #     assigned_start_minutes = int(
    #         (job["scheduled_start_datetime"] - self.data_start_datetime).total_seconds() / 60
    #     )
    #     scheduled_primary_worker_code = job["code"]

    #     job_code = job["absence_code"]

    #     abs_location = LocationTuple(
    #         geo_longitude=job["geo_longitude"],
    #         geo_latitude=job["geo_latitude"],
    #         location_type=LocationType.HOME,
    #         code=f"evt_loc_{job_code}",
    #     )
    #     # loc = LocationTuple(loc_t[0], loc_t[1], LocationType.HOME, f"worker_loc_{worker['id']}",)
    #     return Absence(
    #         job_code=job_code,
    #         job_type=JobType.ABSENCE,
    #         job_schedule_type=JobScheduleType.FIXED_SCHEDULE,  # job_seq: 89, job['job_code']   "FS"
    #         planning_status=JobPlanningStatus.PLANNED,
    #         location=abs_location,
    #         requested_skills={},  # TODO
    #         #
    #         scheduled_worker_codes=[scheduled_primary_worker_code],
    #         scheduled_start_minutes=assigned_start_minutes,
    #         scheduled_duration_minutes=job["scheduled_duration_minutes"],
    #         #
    #         requested_start_min_minutes=0,
    #         requested_start_max_minutes=0,
    #         requested_start_minutes=0,
    #         requested_time_slots=[],
    #         #
    #         requested_primary_worker_code=scheduled_primary_worker_code,
    #         # requested_start_datetime=assigned_start_minutes,  # No day, no minutes
    #         requested_duration_minutes=job["scheduled_duration_minutes"],  # TODO remove plural?)
    #         searching_worker_candidates=[],
    #         included_job_codes=[],
    #         new_job_codes=[],
    #         available_slots=[],
    #         appointment_status=AppointmentStatus.NOT_APPOINTMENT,
    #         #
    #         is_active=True,
    #         is_replayed=False,
    #         is_auto_planning=False,
    #         flex_form_data=job["flex_form_data"],
    #     )

    def env_decode_single_job_to_dict(self, job):  # _for_training : BaseJob
        all_worker_codes = [
            self.workers_dict[wcode].worker_code for wcode in job.scheduled_worker_codes
        ]

        flex_form = copy.deepcopy(job.flex_form_data)
        flex_form["requested_items"] = []
        for k,v in job.requested_items.items():
            flex_form["requested_items"].append(f"{k}{SEPERATOR_FLEX_1}{v}")
        new_job = {
            # "id": self.jobs_dict[job.job_code].job_code,
            "job_type": job.job_type,
            "code": job.job_code,
            "name": job.job_code,
            "org_id": self.org_id,
            "planning_status": job.planning_status,
            "scheduled_start_datetime": None,
            "scheduled_duration_minutes": job.scheduled_duration_minutes,  # TODO remove plural
            "scheduled_primary_worker_code": all_worker_codes[0],
            "scheduled_secondary_worker_codes": all_worker_codes[1:],
            "scheduled_primary_worker": {"code": job.scheduled_worker_codes[0]},  # : WorkerCreate
            # #
            # "scheduled_secondary_workers": [
            #     {"code": wc} for wc in job.scheduled_worker_codes[1:]
            # ],  # : List[WorkerCreate] = #
            # "tags": [],
            "location": {"code": job.location.code},
            "flex_form_data": flex_form,
            # : WorkerCreate
            "requested_primary_worker": {"code": job.requested_primary_worker_code},
            "requested_start_datetime": self.env_decode_from_minutes_to_datetime(
                job.requested_start_minutes
            ),
            "requested_duration_minutes": job.requested_duration_minutes,
            "auto_planning": job.is_auto_planning,
        }
        if job.planning_status != JobPlanningStatus.UNPLANNED:
            new_job["scheduled_start_datetime"] = self.env_decode_from_minutes_to_datetime(
                job.scheduled_start_minutes
            )
        return new_job



    def confirm_assignment(self, request_in: ConfirmAssignmentInput):
        res = {"status":"Error", "env_jobs": {}}

        worker_slots_all = self.get_working_slot_list(
            worker_code=request_in.worker_code,
            active_only = True) 
        # 2024-05-26 10:12:56 # TODO, right now only active to find one, but in future we should allow furture
        if len(worker_slots_all) < 1:
            log.info(f"confirm_assignment: No active worker slots are found for worker {request_in.worker_code}")
            return res

        slot = worker_slots_all[0]
        if (not request_in.new_sequence 
            or len(request_in.new_sequence) != len(slot.assigned_jobs) 
            or len(request_in.new_sequence) < 2
        ):
            res["status"] = "Error, new sequence is not same length or is less than 2"
            log.warning("confirm_assignment: status {}".format(res["status"]))
            return res


        jobs_dict = {j.code:j for j in slot.assigned_jobs}
        new_job_set = set(request_in.new_sequence)
        new_job_list = []

        for jci,jc in enumerate(request_in.new_sequence):
            if jc != slot.assigned_jobs[jci].code:
                break
        else:
            res["status"] = "Error, job sequence not updated, operation aborted."
            return res

        for jc in request_in.new_sequence:
            if jc not in jobs_dict:
                res["status"] = "Error, job not found in this worker assignment"
                log.warning("confirm_assignment: status {}".format(res["status"]))
                return res
            else:
                new_job_set.remove(jc)
                new_job_list.append(jobs_dict[jc])

        all_locs = [[slot.start_longitude, slot.start_latitude]] + [
            [j.geo_longitude, j.geo_latitude] for j in new_job_list
        ]
        all_minutes = self.travel_router.get_travel_minutes_path(all_locs)
        curr_start = self.get_env_planning_horizon_start_minutes()
        for j_i, _j in enumerate(new_job_list):
            curr_start += all_minutes[j_i]
            _j.scheduled_start_minutes = curr_start
            curr_start += _j.scheduled_duration_minutes

        slot.assigned_jobs = new_job_list
        self.add_single_working_time_slot(
            slot=slot,
            update_ops = ["jobs"]
        ) 

        res["env_jobs"][slot.worker_code] = [
            _j.to_result(env=self).dict() for _j in slot.assigned_jobs
        ]  
        res["status"] = "OK"
        return res

    
    def get_env_batch_opti_jobs(self, db_session, start_datetime = None):
        if start_datetime is None:
            opti_start_datetime = self.env_decode_from_minutes_to_datetime(
                # env.get_env_planning_horizon_start_minutes() 
                self.get_env_start_minutes() 
                ) 
        else:
            opti_start_datetime = start_datetime
        opti_end_datetime = self.env_decode_from_minutes_to_datetime(
            self.get_env_planning_horizon_end_minutes()
        )
        day_jobs = job_service.get_jobs_worker_days( 
                    db_session=db_session,
                    start_datetime = opti_start_datetime, 
                    end_datetime = opti_end_datetime,
                    worker_code = None,
                    include_unplanned = True,
                    include_inplanning = True,
                    nbr_minutes_backward_unplanned_jobs = self.nbr_minutes_backward_unplanned_jobs # N个小时之内的,当前时间的前N个小时 
                )
        return day_jobs
        
    def get_env_jobs(
            self, 
            worker_code_list = [], 
            area_code_list=[], 
            reset_start_datetime: bool = False, 
            active_only: bool  = True):
        res = {}
        if len(worker_code_list) == 1:
            worker_slots_all = self.get_working_slot_list(
                worker_code=worker_code_list[0],
                active_only = active_only)
        else:
            worker_slots_all = self.get_working_slot_list(active_only = active_only)
        if len(worker_slots_all) < 1:
            log.info(f"get_env_jobs: No active worker slots are found, quitting at {datetime.now()}")
            return {}
        horizon = self.get_env_planning_horizon_start_minutes()
        for slot in worker_slots_all:
            if len(area_code_list) > 0:
                if slot.area_code not in area_code_list:
                    continue

            if len(worker_code_list) > 0:
                if slot.worker_code not in worker_code_list:
                    continue

            if slot.worker_code in res:
                # I will take only the first one
                continue  
            if reset_start_datetime:
                all_locs = [[slot.start_longitude, slot.start_latitude]] + [
                    [j.geo_longitude, j.geo_latitude] for j in slot.assigned_jobs
                ]
                all_minutes = self.travel_router.get_travel_minutes_path(all_locs)
                curr_start = self.get_env_planning_horizon_start_minutes()
                for j_i, _j in enumerate(slot.assigned_jobs):
                    curr_start += all_minutes[j_i]
                    _j.scheduled_start_minutes = curr_start
                    curr_start += _j.scheduled_duration_minutes
                self.add_single_working_time_slot(
                        slot=slot,
                        update_ops = ["jobs"]
                    ) 
            else:
                found_late_job = False
                for _j in slot.assigned_jobs:
                    if _j.scheduled_start_minutes < horizon:
                        found_late_job = True
                        break
                if found_late_job: 
                    new_jobs = self.solve_jobs_tsp(
                        assigned_jobs = slot.assigned_jobs, 
                        start_loc = [slot.start_longitude, slot.start_latitude], 
                        start_minutes = horizon,
                    )
                    slot.assigned_jobs = new_jobs
                    self.add_single_working_time_slot(
                        slot=slot,
                        update_ops = ["jobs"]
                    ) 
            if slot.worker_code not in res:
                res[slot.worker_code] = []
            res[slot.worker_code] = res[slot.worker_code] + [
                _j.to_result(env=self).dict() for _j in slot.assigned_jobs
            ]  
        return res
    def get_solution_dataset(self, query_start_datetime, query_end_datetime, worker_code_list = [],active_only=False):
        total_overtime_minutes = 0
        onsite_working_minutes = 0
        total_travel_minutes = 0
        qe = max(query_end_datetime, self.env_start_datetime+timedelta(days=1))
        qe_minutes = self.env_encode_from_datetime_to_minutes(query_end_datetime)


        workers_dimensions = [
            "index",
            "skills",
            "max_conflict_level",
            "worker_code",
            "geo_longitude",
            "geo_latitude",
            "slots",
            "selected_flag",
            "job_count",
        ]

        jobs_dimensions = [
            "scheduled_worker_index",
            "scheduled_start_datetime",  # _js
            "scheduled_end_datetime",  # _js datetime in javascript  MilliSecond.
            "job_code",
            "job_type",
            "scheduled_travel_minutes_before",
            "scheduled_travel_prev_code",
            "conflict_level",
            "scheduled_primary_worker_code",
            "geo_longitude",
            "geo_latitude",
            "changed_flag",
            "job_seq",
            # "prev_geo_longitude",
            # "prev_geo_latitude",
            # "prev_location_type",
        ]

        print(
            datetime.now(),
            "worker_job_dataset_json: Started transforming to dataset for web json... ",
        ) 

        # linear_free_slot = [[510, 610], [720, 840], [1440, 1640], [1840, 1940]]



        working_slot_list = []
        
        if worker_code_list:
            for wc in worker_code_list:
                working_slot_list += self.get_working_slot_list(worker_code=wc,active_only=active_only)
        else:
            working_slot_list=self.get_working_slot_list(worker_code=None,active_only=active_only)
        worker_seq = 0
        worker_dict = {}
        # 用于统计 woker 对应的job-code 
        worker_job_dict = {} 

        planned_jobs_list = []

        query_start_minutes = self.env_encode_from_datetime_to_minutes(query_start_datetime)
        for slot in working_slot_list:  
            if slot.start_minutes > qe_minutes:
                continue
            floating_slots = [
                slot.start_minutes - query_start_minutes, 
                slot.end_minutes - query_start_minutes,
                0, #float(slot_info[b"start_overtime_minutes"]),
                0, #float(slot_info[b"end_overtime_minutes"]),
            ]
            skill_str = "area_code:{}".format(slot.area_code)
            if len(slot.accum_items) > 0:
                si = 0
                skill_str = ""
                more_value = 0
                for k in slot.accum_items.keys():
                    if si > 8:
                        more_value += float(slot.accum_items[k]) # "More (...)"
                    else:
                        skill_str += f"{k}: {round(float(slot.accum_items[k]))} \n" # .decode('utf-8')
                    si += 1
                if more_value > 0:
                    skill_str += f"More (...): {round(float(more_value))}"

            if slot.worker_code not in worker_dict:
                worker_dict[slot.worker_code] = {
                    "geo_longitude": float(slot.start_longitude),
                    "geo_latitude": float(slot.start_latitude),
                    "slots":[floating_slots], 
                    "index":worker_seq,
                    "selected_flag": 0 ,
                    "worker_code": slot.worker_code,
                    "skills": skill_str,
                    "max_conflict_level": 1,
                    "job_count":len(slot.assigned_jobs),
                }
                worker_seq +=1
            else:
                worker_dict[slot.worker_code]["slots"].append(floating_slots) 
            
            total_overtime_minutes += slot.start_overtime_minutes + slot.end_overtime_minutes


            for j_i, j in enumerate(slot.assigned_jobs):
                scheduled_start_datetime = self.env_decode_from_minutes_to_datetime(j.scheduled_start_minutes)
                scheduled_end_datetime = scheduled_start_datetime + timedelta(
                    minutes=j.scheduled_duration_minutes
                )
                onsite_working_minutes += j.scheduled_duration_minutes
                total_travel_minutes += j.prev_travel
    
                scheduled_start_datetime_js = int(
                    time.mktime(scheduled_start_datetime.timetuple()) * 1000
                )
                scheduled_end_datetime_js = int(time.mktime(scheduled_end_datetime.timetuple()) * 1000)

                # plot_job_type = "I"

                if slot.worker_code not in worker_job_dict:
                    worker_job_dict[slot.worker_code] = [j.code]
                else:
                    worker_job_dict[slot.worker_code].append(j.code)
                new_job = {
                    "job_code": j.code,
                    # "job_type": "I",
                    "job_type": "{}_1_2_3_4_N".format(j.planning_status), # j["scheduled_share_status"]),
                    "scheduled_primary_worker_code": slot.worker_code,
                    "scheduled_worker_index": worker_dict[slot.worker_code]["index"],
                    "scheduled_start_datetime_js": scheduled_start_datetime_js,  # scheduled_start_datetime.isoformat(),
                    "scheduled_end_datetime_js": scheduled_end_datetime_js,  # scheduled_end_datetime.isoformat(),
                    "scheduled_start_datetime": scheduled_start_datetime.isoformat() if scheduled_start_datetime else None,
                    "scheduled_end_datetime": scheduled_end_datetime.isoformat() if scheduled_end_datetime else None,

                    "scheduled_duration_minutes": j.scheduled_duration_minutes,
                    "planning_status": "I",
                    "conflict_level": 0,  # j["conflict_level"],
                    "scheduled_travel_minutes_before": j.prev_travel, 
                    "scheduled_travel_prev_code": '_',
                    "geo_longitude": j.geo_longitude,
                    "geo_latitude": j.geo_latitude,
                    "changed_flag": 0, 
                    "job_seq": j_i +1,
                    # "planning_status": j.planning_status,
                }

                planned_jobs_list.append(new_job)

        current_step = 0
        # try:
        #     current_step = self.get_job_log_iloc()
        # except:
        #     pass
        planner_score_stats = {
            "overall_score": 0,
            "score": "{:.3f}".format(0),
            "total_travel_minutes": int(0),
            "inplanning_job_count": 0,
            # "unplanned_job_count": 0,
            # "visible_job_count": 0,
            "onsite_working_minutes": 0,
            "planning_window": f"{0} ~ {0}",
            "total_overtime_minutes": 0, 
            "current_datetime": str(self.env_decode_from_minutes_to_datetime(self.get_env_planning_horizon_start_minutes())),
            "current_step": current_step,
        }
                

        workers_list = worker_dict.values()
        new_df = pd.DataFrame(workers_list)
        df_count = new_df.count().max()
        if (pd.isnull(df_count)) or (df_count < 1):
            return {
                "workers_dimensions": workers_dimensions,
                "workers_data": [], 
                "jobs_dimensions": jobs_dimensions,
                "planned_jobs_data": [],
                # "all_jobs_in_env": [],  # all_jobs_in_env
                "start_time": query_start_datetime.isoformat(),
                "end_time": query_end_datetime.isoformat(),
                "planner_score_stats":planner_score_stats,
                "datetime_now": self.get_datetime_now().isoformat(),
                "data_start_datetime": self.data_start_datetime.isoformat(),
                "horizon_start_datetime": self.env_decode_from_minutes_to_datetime(self.get_env_planning_horizon_start_minutes()).isoformat(),
                "worker_job_dict": {},
                "last_batch_run_datetime": None

                # "team_longitude": -1,
                # "team_latitude": -1,
                # TODO: worker_time [[day_start, day_end], [day_start, day_end]], office_hours{[day_start, day_end, day_start, day_end, ...] }.
            }

            #
        # new_df.columns
        workers_data = new_df[workers_dimensions].values.tolist()
        # workers_dict_list = new_df[workers_dimensions].to_dict(orient="records")


        planned_jobs_data = []
 
        # inplanning_job_count = len(planned_jobs_list)
        planning_start = datetime.strftime(
            self.env_decode_from_minutes_to_datetime(self.get_env_planning_horizon_start_minutes()),
            "%m-%d",
        )
        planning_end = datetime.strftime(
            self.env_decode_from_minutes_to_datetime(self.get_env_planning_horizon_end_minutes()),
            "%m-%d",
        )


        if onsite_working_minutes <= 0:
            overall_score = 0
        else:
            
            # onsite_working_minutes 工作时间
            # over(message_spec, *, file=None)
            # overall_score = total_travel_minutes
            #  onsite_working_minutes ：站点停留时间 
            # total_travel_minutes 在路上的时间  
            # total_overtime_minutes / 总超时时间 
            overall_score = (
                (onsite_working_minutes / (total_travel_minutes + onsite_working_minutes))
                # + (inplanning_job_count / (inplanning_job_count + unplanned_job_count))
                - (total_overtime_minutes / onsite_working_minutes)
            )

        if len(planned_jobs_list) > 0:
            new_planned_job_df = pd.DataFrame(planned_jobs_list).fillna(0).sort_values(
                by=["scheduled_primary_worker_code","scheduled_start_datetime_js"])
            planned_jobs_data = new_planned_job_df[jobs_dimensions].values.tolist()

        planner_score_stats.update({
            "overall_score": overall_score,
            "score": "{:.3f}".format(overall_score),
            "total_travel_minutes": int(total_travel_minutes),
            "inplanning_job_count": len(planned_jobs_list),
            "onsite_working_minutes": onsite_working_minutes,
            "planning_window": f"{planning_start} ~ {planning_end}",
            "total_overtime_minutes": total_overtime_minutes, 
        })
        print(datetime.now(), "worker_job_dataset_json: Finished.")
        # team = self.get_team()
        # d is only to shorten the later on code, nothing special, same as qe before.
        d = self.env_start_datetime
        return {
            "workers_dimensions": workers_dimensions,
            "workers_data": workers_data,
            "jobs_dimensions": jobs_dimensions,
            "planned_jobs_data": planned_jobs_data, # new_planned_jobs_data,
            # To align windows to at least a day.
            "start_time": datetime(d.year, d.month, d.day,0,0,0).isoformat(), # query_start_datetime
            "end_time": datetime(qe.year, qe.month, qe.day,0,0,0).isoformat(),
            "planner_score_stats":planner_score_stats,
            "datetime_now": self.get_datetime_now().isoformat(),
            "data_start_datetime": self.data_start_datetime.isoformat(),
            "horizon_start_datetime": self.env_decode_from_minutes_to_datetime(self.get_env_planning_horizon_start_minutes()).isoformat(),
            "worker_job_dict": worker_job_dict,
            "last_batch_run_datetime": self.config["last_batch_run_datetime"],
            # "team_longitude": team.geo_longitude,
            # "team_latitude": team.geo_latitude,
        }

    def get_solution_dict(self, 
        # query_start_datetime, query_end_datetime, 
        worker_code_list = []):
        # query_start_minutes = self.env_encode_from_datetime_to_minutes(query_start_datetime)
        # query_end_minutes = self.env_encode_from_datetime_to_minutes(query_end_datetime)

        job_solution_list = []
        # In this loop, it first collects Only all (I/P) in/planned jobs, which are available from working time slots
        worker_dict = {}
        worker_seq = 0

        working_slot_list = []
        
        if worker_code_list:
            for wc in worker_code_list:
                working_slot_list += self.get_working_slot_list(worker_code=wc)
        else:
            working_slot_list=self.get_working_slot_list(worker_code=None)

        for slot in working_slot_list:  
            floating_slots = [
                slot.start_minutes, slot.end_minutes,
                0, #float(slot_info[b"start_overtime_minutes"]),
                0, #float(slot_info[b"end_overtime_minutes"]),
            ]

            if slot.worker_code not in worker_dict:
                worker_dict[slot.worker_code] = {
                    "geo_longitude": float(slot.start_longitude),
                    "geo_latitude": float(slot.start_latitude),
                    "slots":[floating_slots], 
                    "index":worker_seq
                }
                worker_seq +=1
            else:
                worker_dict[slot.worker_code]["slots"].append(floating_slots) 
                

            all_jobs_in_slot = slot.assigned_jobs #self.decode_working_slot_assigned_jobs()
            job_solution_list += all_jobs_in_slot


        # U-planned jobs are not included in the solution

        return worker_dict, job_solution_list

    def get_planner_score_stats(self, include_slot_details=False):

        assigned_job_stats = {}

        inplanning_job_index_set = set()
        shared_prev_jobs = {}
        total_travel_minutes = 0

        sorted_slot_codes = sorted(list(self.slot_server.time_slot_dict.keys()))
        pre_job_code = "__HOME"
        prev_slot = None
        current_worker_code = "NOT_EXIST"
        slot_details = {}
        # In this loop, it first collects Only all (I/P) in/planned jobs, which are available from working time slots
        for slot_code in sorted_slot_codes:
            # w_travel=[] # only for debugging purpose.
            # for work_time_i in  range(len( self.workers_dict[worker_code]['assigned_jobs'] ) ): # nth assigned job time unit.
            if slot_code in kandbox_config.DEBUGGING_SLOT_CODE_SET:
                log.debug(f"debug atomic_slot_delete_and_add_back {kandbox_config.DEBUGGING_SLOT_CODE_SET}")

            try:
                a_slot = self.slot_server.get_slot(self.redis_conn.pipeline(), slot_code, raise_exception=False)
                if a_slot is None:
                    continue
                job_code_list = [
                    code for code in a_slot.assigned_job_codes if code in self.jobs_dict
                ]
                the_assigned_codes = sorted(
                    job_code_list,
                    key=lambda jc: self.jobs_dict[jc].scheduled_start_minutes,
                )
            except Exception as ke:
                log.error(
                    f"unknown worker code during get_planner_score_stats, or unknown job codes to the env. slot_code = {slot_code}, error = {str(ke)}"
                )
                print(ke)
                continue

            if include_slot_details:
                slot_duration = a_slot.end_minutes - a_slot.start_minutes
                slot_details[slot_code] = {
                    "travel_n_duration": [],
                    "free_minutes": slot_duration,
                    "start_end_duration": [a_slot.start_minutes, a_slot.end_minutes, slot_duration],
                    "the_assigned_codes": the_assigned_codes,
                }

            current_start_loc = a_slot.start_location
            # if a_slot.worker_code != current_worker_code:
            #     current_start_loc = a_slot.start_location
            # elif (a_slot.slot_type == TimeSlotType.FLOATING) or (a_slot.prev_slot_code is None):
            #     current_start_loc = a_slot.start_location
            # if a_slot.slot_type in (TimeSlotType.JOB_FIXED, TimeSlotType.FLOATING):
            current_worker_code = a_slot.worker_code

            for assigned_index, assigned_job_code in enumerate(the_assigned_codes):
                assigned_job = self.jobs_dict[assigned_job_code]

                if assigned_job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
                    print(f"pause for debugging {kandbox_config.DEBUGGING_JOB_CODE_SET }")

                prev_travel_minutes = self.travel_router.get_travel_minutes_2locations(
                    current_start_loc,
                    assigned_job.location,
                )
                if include_slot_details:
                    slot_details[slot_code]["free_minutes"] -= (
                        prev_travel_minutes + assigned_job.requested_duration_minutes
                    )
                    slot_details[slot_code]["travel_n_duration"].append(
                        (prev_travel_minutes, assigned_job.requested_duration_minutes)
                    )

                if assigned_job_code in assigned_job_stats:
                    assigned_job_stats[assigned_job_code]["travel"] += prev_travel_minutes
                    total_travel_minutes += prev_travel_minutes
                else:
                    assigned_job_stats[assigned_job_code] = {
                        "travel": prev_travel_minutes,
                        "requested_duration_minutes": assigned_job.requested_duration_minutes,
                    }
                    total_travel_minutes += prev_travel_minutes
                # w_travel.append(prev_travel_minutes)

                inplanning_job_index_set.add(assigned_job.job_code)
                current_start_loc = assigned_job.location

            # At the end, calculate last job to slot ending location.
            if len(the_assigned_codes) > 0:
                ending_travel = self.travel_router.get_travel_minutes_2locations(
                    a_slot.end_location,
                    self.jobs_dict[the_assigned_codes[-1]].location,
                )
                total_travel_minutes += ending_travel
                # w_travel.append(ending_travel)
            # print(
            #    "_", " worker:", a_slot.worker_code, sum(w_travel), "detail: ", w_travel
            # )
        # In this loop, it collects Only U-planned jobs, which are not available from working time slots
        unplanned_job_count = 0
        for job_code, new_job in self.jobs_dict.items():
            if new_job.flex_form_data.get('order_type','')=='backToSc':
                continue
            if job_code in inplanning_job_index_set:
                continue
            if new_job.job_type == JobType.ABSENCE:
                continue

            if not new_job.is_active:  # events and appt can not be U anyway
                log.warning(f"job={ job_code} is skipped from solution because is_active == False")
                continue

            if new_job.planning_status == JobPlanningStatus.UNPLANNED:
                unplanned_job_count += 1
            elif new_job.planning_status in (JobPlanningStatus.FINISHED,):
                continue
            elif new_job.planning_status in (JobPlanningStatus.PLANNED,):
                if (
                    new_job.scheduled_start_minutes + new_job.scheduled_duration_minutes
                    < self.get_env_planning_horizon_start_minutes()
                ) | (new_job.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()):
                    log.warning(
                        f"solution skipped job_code={new_job.job_code}, minutes = {new_job.scheduled_start_minutes} not in planning window"
                    )
                    continue
                # else:
                #     log.error(f"Why not in slots? PLANNED, job_code = {job_code}")
            # else:
            #     log.error(f"Why not in slots? INPLANNING, job_code = {job_code}")
        onsite_working_minutes = sum(
            [assigned_job_stats[j]["requested_duration_minutes"] for j in assigned_job_stats]
        )
        inplanning_job_count = len(assigned_job_stats)
        planning_start = datetime.strftime(
            self.env_decode_from_minutes_to_datetime(self.get_env_planning_horizon_start_minutes()),
            "%m-%d",
        )
        planning_end = datetime.strftime(
            self.env_decode_from_minutes_to_datetime(self.get_env_planning_horizon_end_minutes()),
            "%m-%d",
        )

        total_overtime_minutes = 0
        for w in self.workers_dict.keys():
            total_overtime_minutes += sum(
                [
                    self.workers_dict[w].used_overtime_minutes[day_seq]
                    for day_seq in self.workers_dict[w].used_overtime_minutes.keys()
                ]
            )
        if inplanning_job_count + unplanned_job_count <= 0 or onsite_working_minutes <= 0:
            overall_score = 0
        else:
            overall_score = (
                (onsite_working_minutes / (total_travel_minutes + onsite_working_minutes))
                + (inplanning_job_count / (inplanning_job_count + unplanned_job_count))
                - (total_overtime_minutes / onsite_working_minutes)
            )

        planner_score_stats = {
            "overall_score": overall_score,
            "score": "{:.3f}".format(overall_score),
            "total_travel_minutes": int(total_travel_minutes),
            "inplanning_job_count": inplanning_job_count,
            "unplanned_job_count": unplanned_job_count,
            "onsite_working_minutes": onsite_working_minutes,
            "planning_window": f"{planning_start} ~ {planning_end}",
            "total_overtime_minutes": total_overtime_minutes,
            "slot_details": slot_details,
        }
        return planner_score_stats

    def get_planning_window_days_from_redis(self) -> set:
        days_on_redis = self.redis_conn.hgetall(self.get_env_planning_day_key())

        existing_working_days = set([int(di) for di in days_on_redis.keys()])
        return existing_working_days

    # **----------------------------------------------------------------------------
    # ## Extended functions
    # **----------------------------------------------------------------------------
    def set_horizon_start_minutes(self, start_datetime):
        if str(self.config.get("fixed_horizon_flag", '0')) != '1':
            log.warning(f"This env {self.team_env_key} does not_allow_set_horizon_start_minutes")
            return "ERROR"

        self.horizon_start_minutes = self.env_encode_from_datetime_to_minutes(
            start_datetime) #  + begin_skip_minutes + _start_diff
        self.redis_conn.hset(self.get_env_config_key(), "horizon_start_minutes", self.horizon_start_minutes)
        self.redis_conn.hset(self.get_env_config_key(), "horizon_start_datetime", datetime.strftime(start_datetime, kandbox_config.KANDBOX_DATETIME_FORMAT_ISO))

        rust_request = json.dumps({"horizon_start_seconds": str(int(self.horizon_start_minutes*60))})
        res = self.redis_conn.execute_command("s.config", self.get_env_slot_set_key(), rust_request)


        curr_seq = self.redis_conn.hincrby(self.get_env_config_key(), "update_seq", amount = 1) 
        # self.update_seq +=1
        self.config["update_seq"] = curr_seq

        log.info(f"Env {self.team_env_key} set_horizon_start_minutes_to {self.horizon_start_minutes}, {start_datetime}")
        return "OK"


    def _get_new_working_days(self, today_start_date = None) -> set:
        # Hold this value and do not call it multiple times in a loop

        if today_start_date is None:
            today_start_date = self.env_decode_from_minutes_to_datetime(
                self.get_env_planning_horizon_start_minutes()
            )
        planning_working_days = max((self.nbr_minutes_planning_windows_duration // 1440),1)

        # Now find out all current days in planning windows.
        new_working_days = set()
        promotional_working_days = set(json.loads(self.config.get("promotional_working_days","[]")))
        team_holiday_days = self.config.get("team_holiday_days","").split(";")
        week_day_str_list = self.config.get("weekly_working_days","")
        if len(week_day_str_list)> 0:
            weekly_working_days = {int(w) for w in week_day_str_list.split(";")}
        else:
            weekly_working_days = {1,2,3,4,5}

        for day_i in range(300):
            new_start_date = today_start_date + timedelta(days=day_i)
            day_seq = (new_start_date - self.data_start_datetime).days
            new_weekday = self.env_encode_day_seq_to_weekday(day_seq)
            new_start_minutes = self.env_encode_from_datetime_to_minutes(new_start_date)
            if len(new_working_days) >= planning_working_days:
                break
            if new_start_minutes > self.get_env_planning_horizon_end_minutes():
                break
            # 添加 大促日
            if  str(new_start_date.date()) in promotional_working_days:
                self.daily_working_flag[day_seq] = True
                new_working_days.add(day_seq)
                continue

            # 过滤org & team 里休息日 
            if str(new_start_date.date()) in team_holiday_days:
                continue
            if new_weekday in weekly_working_days:
                new_working_days.add(day_seq)
            if day_i % 100 == 20:
                log.warning(f"_get_new_working_days: {day_i} days tried.")

        # It may reduce several days of holidays
        return new_working_days

    def mutate_refresh_planning_window(
            self, 
            db_session, 
            today_start_date = None,
            delete_existing_slot = False,
            ) -> bool:
        if today_start_date is None:
            today_start_date = self.env_decode_from_minutes_to_datetime(
                self.get_env_planning_horizon_start_minutes()
            )
        # self._parse_env_config()

        existing_working_days = self.get_planning_window_days_from_redis()
        self.existing_working_days = existing_working_days

        horizon_day_seq = self.env_encode_from_datetime_to_day_seq(today_start_date)
        new_working_days = self._get_new_working_days(today_start_date)
        if len(new_working_days) < 1:
            log.error("There are no new working days, giving up mutate_refresh_planning_window")
            return False


        if new_working_days <= existing_working_days:
            log.warning(
                f"There is no change in planning day when it is called at {datetime.now()}). existing_working_days={existing_working_days}. Maybe we have passed a weekend?  "
            )
            # return False

        self.existing_working_days = new_working_days
        days_to_add = new_working_days - existing_working_days
        days_to_delete = existing_working_days - new_working_days
        if len(days_to_delete) > 0:
            self.redis_conn.hdel(self.get_env_planning_day_key(), *days_to_delete)
            log.info(
                    f"The planning days {days_to_delete} are purged out of planning window succesfully!"
                )
        # auto purge slots. No explict delete.
        
        # TODO, create a code api, do not parse all slots 2023-02-17 16:33:31
        for day_seq in days_to_add:
            today_start_date = self.data_start_datetime + timedelta(days=day_seq)
            today_start_date_str = datetime.strftime(
                today_start_date, kandbox_config.KANDBOX_DATE_FORMAT
            )

            self.redis_conn.hset(
                self.get_env_planning_day_key(),
                key=day_seq,
                value=f"{today_start_date_str}_{day_seq*1440}->{(day_seq+1)*1440}"
            )
        
        slots_changed = False
        workers = worker_service.get_all_active_in_team(
            db_session=db_session,
            team_id=self.team_id
        )
        workers_dict = {}
        for w in workers:
            workers_dict[w.code] = w
        self.delete_working_slot_not_in_list(workers_dict=workers_dict,)
        success = True
        for w in workers:
            try:
                start_datetime = min(self.env_decode_from_minutes_to_datetime(
                    self.get_env_planning_horizon_start_minutes() #  - self.nbr_minutes_backward_unplanned_jobs # 4个小时之内的,当前时间 的前四个小时
                    ), self.env_start_datetime
                )
                end_datetime = self.env_decode_from_minutes_to_datetime(
                    self.get_env_planning_horizon_end_minutes()
                )
                ## 查询 worker 有多少 Jobs   start < x < end 
                day_jobs = job_service.get_jobs_worker_days( 
                    db_session=db_session,
                    start_datetime = start_datetime, 
                    end_datetime = end_datetime,
                    team_id = self.team_id,
                    worker_code = w.code,
                    include_unplanned = False,
                    include_inplanning = True,

                )
                
                slots_changed = self.mutate_refresh_working_slots_4_worker(
                    worker = w,
                    working_days = new_working_days,
                    day_jobs = day_jobs,
                    delete_existing_slot = delete_existing_slot,
                    ) or slots_changed
            except:
                import traceback
                log.error(f"failed to mutate_refresh_working_slots_4_worker for worker {w.code}, details = {w._asdict()}")
                log.error(traceback.format_exc())
                success = False
            

        # if slots_changed:
        #     # TODO, why duplicated? 2023-12-21 18:52:43
        #     curr_seq = self.redis_conn.hincrby(self.get_env_config_key(), "update_seq", amount=1)
        #     log.info(f"env_seq = {curr_seq} is boosted for ({self.get_env_config_key()})  .  ")

        curr_seq = self.redis_conn.hincrby(self.get_env_config_key(), "update_seq", amount = 1) 
        # self.update_seq +=1
        self.config["update_seq"] = curr_seq
        # 2020-11-17 06:27:47
        # If planning window start with Sunday, new_working_days does not contain it, horizon_day_seq should still point to Sunday
        nbr_of_days_planning_window = max(new_working_days) - horizon_day_seq + 1
        # Update nbr_of_days_planning_window, which may be larger than specified self.config["DaysForPlanning"]
        log.info(f"Env=({self.get_env_config_key()}) is boosted with update_seq = {curr_seq}, nbr_of_days_planning_window = {nbr_of_days_planning_window}.")


        return success


    def mutate_refresh_working_slots_4_worker(
        self, worker, working_days = None, day_jobs = [],
        delete_existing_slot = False,
        delete_kmedoid = True
    ) -> bool:
        slots_to_delete = []
        with self.redis_conn.lock(
            self.get_env_worker_lock_key(worker_code = worker.code), timeout=60, blocking_timeout=60
        ) as lock:         
            if working_days is None:
                working_days = self.get_planning_window_days_from_redis()

            all_slot_code_dict = {}
            interval_tree_dict = {}
            slots_changed = False
            for s in self.get_working_slot_list(worker_code = worker.code, active_only = False):
                if delete_existing_slot:
                    slots_to_delete.append(s)
                else:
                    all_slot_code_dict[s.slot_code] = s
                    if s.worker_code not in interval_tree_dict:
                        interval_tree_dict[s.worker_code] = IntervalTree()
                    interval_tree_dict[s.worker_code].add(Interval(s.start_minutes, s.end_minutes, s))

            if worker.code in interval_tree_dict:
                interval_tree = interval_tree_dict[worker.code]
            else:
                interval_tree = IntervalTree()

            new_interval_list = []
            if int(self.config.get("slot_by_shift_start", 0)) == 1:
                if worker.shift_start_datetime is not None and worker.is_shift_started:
                    # Add the current shift if customer login and start an adhoc shift
                    log.info(f"worker { worker.code}:  Adding the current shift , requested by slot_by_shift_start")
                    curr_start_minutes = self.env_encode_from_datetime_to_minutes(worker.shift_start_datetime)
                    shift_duration = worker.shift_duration_minutes
                    if shift_duration is None:
                        shift_duration = int(self.config.get("shift_length_minutes", 480))
                    existing_slot = interval_tree[curr_start_minutes:curr_start_minutes+shift_duration]
                    if len(existing_slot) > 0:
                        log.info(f"current shift slot {worker.shift_start_datetime} for worker {worker.code} is duplicated and skipped, from slot_by_shift_start.")
                    else:
                        interval_tree.add(Interval(curr_start_minutes, curr_start_minutes+shift_duration, worker))
                        new_interval_list.append((curr_start_minutes, curr_start_minutes+shift_duration))

            if int(self.config.get("slot_by_business_hour", 0)) == 1:
                for day_seq in working_days:
                    _interval_list = self.get_working_interval_4_worker(worker = worker, day_seq=day_seq)
                    for interval in _interval_list:
                        existing_slot = interval_tree[interval[0]:interval[1]]
                        if len(existing_slot) > 0:
                            slot_key1 =self.get_env_slot_code(worker.code, start_minutes=int(interval[0])) 
                            if slot_key1 in all_slot_code_dict:
                                curr_slot = all_slot_code_dict[slot_key1]
                                if curr_slot.end_minutes!=interval[1]:
                                    c_s = all_slot_code_dict.pop(slot_key1)
                                    slots_to_delete.append(c_s)
                                    new_interval_list.append((interval[0], interval[1]))
                                    log.info(f"slot {interval} for worker {worker.code} has different end minutes {curr_slot.end_minutes}.")
                                else:
                                    log.info(f"slot {interval} for worker {worker.code} is duplicated with existing and is skipped, from slot_by_business_hour.")
                                    continue
                            else:
                                log.error(f"slot {interval} for worker {worker.code} does not match. It could be updating without deleting!!!")
                        else:
                            # Interval 生成的对应 第 0个 必须要小于 第1 个, 否则就是错的,有可能是 worker 的 busssiness_hour 时间错了,
                            # close 一定要大于 open
                            # wemart once opened
                            interval_tree.add(Interval(interval[0], interval[1], worker))
                            new_interval_list.append((interval[0], interval[1]))

            for slot in slots_to_delete:
                self.delete_single_working_time_slot(
                    worker=slot.worker_code,
                    start_seconds=slot.start_minutes*60,
                    delete_kmedoid=delete_kmedoid)
            if not worker.is_active:
                return slots_changed
            for interval in new_interval_list:
                slot_key =self.get_env_slot_code(worker.code, start_minutes=int(interval[0])) 

                if slot_key not in all_slot_code_dict:
                    slots_changed = True
                    s1=self.mutate_add_working_slot(
                        worker=worker, 
                        start_minutes=interval[0],
                        end_minutes=interval[1],
                        day_jobs = day_jobs,
                        )
                    all_slot_code_dict[slot_key] = s1
                    log.info(
                        f"A new slot {slot_key}) with interval minutes {interval} is added succesfully!"
                    )
            return slots_changed

    def get_working_interval_4_worker(
        self, worker, day_seq: int
    ) -> list:
        # w = worker
        # if w.geo_longitude is None or w.geo_latitude is None:
        #     log.error(f"Worker ({w.code}): w.geo_longitude is None or w.geo_latitude is None")
        #     return
        # I first calculate the working slot in this day
        today_start_date = self.data_start_datetime + timedelta(days=day_seq)
        today_start_minutes = self.env_encode_from_datetime_to_minutes(today_start_date)

        # min_day_seq = min(self.existing_working_days)

        today_weekday = self.env_encode_day_seq_to_weekday(day_seq)
        # 大促日期 添加
        # if not w.weekly_working_slots[today_weekday]:
        working_hour_list = []
        promotional = json.loads(self.config.get("promotional_working_days",'{}')).get(str(today_start_date.date()))
        if promotional:
            working_hour_list = promotional # [0]
        else:
            if day_seq2day_str[today_weekday] in worker.business_hour:
                working_hour_list = worker.business_hour[day_seq2day_str[today_weekday]] # [0]

        intervals = []
        for working_hour in working_hour_list:
            if "isOpen" not in working_hour:
                continue
            if not working_hour["isOpen"]:
                continue
            start_minutes = int(working_hour.get('open')[:2])*60 +int(working_hour.get('open')[2:]) + today_start_minutes
            end_minutes = int(working_hour.get('close')[:2])*60 +int(working_hour.get('close')[2:]) + today_start_minutes
            if end_minutes < start_minutes:
                end_minutes += 1440
            if end_minutes <= start_minutes:
                continue
            # events_interval = job_service.get_jobs_query_event_absence( 
            #     start_datetime=today_start_date,
            #     start_minutes=start_minutes,
            #     end_minutes=end_minutes,
            #     today_start_minutes=today_start_minutes,
            #     worker_code=worker.code
            #     )
            # intervals.extend(events_interval)
            if (end_minutes < self.get_env_planning_horizon_start_minutes()
            #    ) or(start_minutes >= self.get_env_planning_horizon_end_minutes()
            ):
                # Outside of planning window. Future should be created but past will be skipped. 2024-02-17 17:21:22
                continue
            intervals.append([start_minutes, end_minutes])
        # ADD here... 
        # read job table, find all event, and deduct events from internvals., and get new interval.

        return intervals



    def mutate_add_working_slot(
        self, worker, start_minutes, end_minutes, day_jobs
    ) -> WorkingTimeSlot:

        new_slot_available_minutes = end_minutes - start_minutes
        jobs_in_slot = []
        travel_minutes = []
        if len(day_jobs) > 0:
            prev_loc = [worker.geo_longitude, worker.geo_latitude]
            loc_list = [prev_loc]

            for job in day_jobs: 
                scheduled_start_minutes = self.env_encode_from_datetime_to_minutes(job.scheduled_start_datetime)
                if scheduled_start_minutes < start_minutes or end_minutes < scheduled_start_minutes:
                    continue
                if job.geo_longitude is None or job.geo_latitude is None:
                    if job.geo_longitude_loc  is None or job.geo_latitude_loc is None:
                        log.error(f"job {job.code} has no valid location, skipped from replaying ...")
                        continue
                    longitude = job.geo_longitude_loc
                    latitude = job.geo_latitude_loc
                else:
                    longitude = job.geo_longitude
                    latitude = job.geo_latitude
                
                loc_list.append([longitude, latitude])
                jobs_in_slot.append(job)
            
            # Use 1 call to get all travel minutes for all jobs.2023-01-10 18:22:32
            travel_minutes = self.get_travel_router().get_travel_minutes_path(loc_list)
            # prev_travel = 0

        jobs_zset = []
        for job_i, job in enumerate(jobs_in_slot): 
            duration = (job.requested_duration_minutes 
                if job.scheduled_duration_minutes is None
                else job.scheduled_duration_minutes)
            if duration is None:
                duration = 1
            prev_travel = travel_minutes[job_i]
            new_slot_available_minutes -= prev_travel+duration

            job_start_minutes = self.env_encode_from_datetime_to_minutes(job.scheduled_start_datetime)
            requested_minutes = self.env_encode_from_datetime_to_minutes(job.requested_start_datetime)
            
            a_job = JobInSlot (
                scheduled_start_minutes=job_start_minutes,
                code=job.code,
                geo_longitude=job.geo_longitude, 
                geo_latitude=job.geo_latitude, 
                scheduled_duration_minutes=duration,
                tolerance_end_minutes = requested_minutes + job.tolerance_end_minutes,
                prev_travel=prev_travel,
                planning_status=job.planning_status,
            )
            jobs_zset.append(a_job) 
        _nbr_order_ = int(worker.flex_form_data.get("max_nbr_order", 9999))
        _volume_ = int(worker.flex_form_data.get("capacity_volume", 999999))
        _weight_ = int(worker.flex_form_data.get("capacity_weight", 999999))
        accum_items = {
            "_volume_":_volume_,
            "_weight_":_weight_,
            "_nbr_order_": _nbr_order_, 
        }
        accum_items_str = worker.flex_form_data.get("accum_items", "") 
        
        accum_items.update(parse_item_from_str(
            accum_items_str, SEPERATOR_FLEX_0, SEPERATOR_FLEX_1)
        )
        skills = []
        skill_str = worker.flex_form_data.get("skills", "") 
        if len(skill_str) > 0:
            skills = skill_str.split(SEPERATOR_FLEX_0)

        _start_longitude = worker.geo_longitude
        _start_latitude = worker.geo_latitude
        _valid_start_from_away_flag  = False
        start_from_away_flag = str(self.config.get("start_from_away_flag", '0')) == '1'
        if start_from_away_flag:
            try:
                start_from_away_longitude = float(self.config["start_from_away_longitude"])
                start_from_away_latitude = float(self.config["start_from_away_latitude"])
                _valid_start_from_away_flag = True
            except:
                log.error("failed to get long/lat data when start_from_away_flag is true")
            if _valid_start_from_away_flag:
                _start_longitude = start_from_away_longitude
                _start_latitude = start_from_away_latitude

        new_slot = WorkingTimeSlot(
            slot_code = self.get_env_slot_code(worker.code, start_minutes),
            slot_type = "F",
            worker_code=worker.code,
            available_free_minutes = new_slot_available_minutes,
            job_change_count = 0,
            area_code = worker.flex_form_data.get("area_code",DEFAULT_AREA_CODE), 
            start_minutes=start_minutes,
            end_minutes=end_minutes,
            start_longitude=worker.geo_longitude,
            start_latitude=worker.geo_latitude,
            end_longitude=worker.flex_form_data.get("end_longitude", worker.geo_longitude),
            end_latitude=worker.flex_form_data.get("end_latitude", worker.geo_latitude),
            assigned_jobs = jobs_zset,
            max_nbr_order = _nbr_order_,
            capacity_volume = _volume_,
            capacity_weight = _weight_,
            accum_items = accum_items,
            skills = skills,
            free_items = {
                "_volume_":_volume_,
                "_weight_":_weight_,
                "_nbr_order_": _nbr_order_, 
            }
        )
        # worker_code, start_minutes: int, end_minutes: int, start_location, end_location, slot_type = "F", assigned_jobs=[]

        self.add_single_working_time_slot(new_slot,update_ops=["all"])
        return new_slot
        # team_env_key = self.team_env_key,
        
        # log.info(
        #     f"finished replay for worker {worker.code}, starting at {start_minutes},  with {len(jobs_zset)} jobs "
        # )


    # ***************************************************************
    # Mutation functions. Here they are not locked ... The lock will happen only when persisting to redis.
    # They are named as C-R-U-D, therefore Create will add the object to the ENV, Update will update existing one.
    # ***************************************************************

    def mutate_worker_add_overtime_minutes(
        self, worker_code: str, day_seq: int, net_overtime_minutes: int, post_changes_flag=False
    ) -> bool:
        added_successful = True
        if day_seq not in self.workers_dict[worker_code].used_overtime_minutes.keys():
            log.warning(
                f"rejected, day_seq={day_seq} not in self.workers_dict[{worker_code}].used_overtime_minutes.keys()"
            )
            return False

        self.workers_dict[worker_code].used_overtime_minutes[day_seq] += net_overtime_minutes

        if self.workers_dict[worker_code].used_overtime_minutes[day_seq] < 0:
            self.workers_dict[worker_code].used_overtime_minutes[day_seq] = 0
            added_successful = False

        for limit_days_key in self.workers_dict[worker_code].overtime_limits.keys():
            total_overtime = 0
            all_days_valid = True
            for dsq in limit_days_key:
                if dsq in self.workers_dict[worker_code].used_overtime_minutes.keys():
                    total_overtime += self.workers_dict[worker_code].used_overtime_minutes[dsq]
                else:
                    log.info(
                        f"day_seq={dsq} is not longer in self.workers_dict[{worker_code}].used_overtime_minutes.keys() = {self.workers_dict[worker_code].used_overtime_minutes}. I will remove limit_days_key = {limit_days_key}"
                    )
                    dsq_error = False
                    break
            if not all_days_valid:
                # del self.workers_dict[worker_code].overtime_limits[limit_days_key]
                continue

            if total_overtime > self.workers_dict[worker_code].overtime_limits[limit_days_key]:
                log.warning(
                    f"Overtime={total_overtime} is larger than limit for worker={worker_code}, key={limit_days_key}"
                )
                added_successful = False
        # if post_changes_flag:
        #     self.kafka_server.post_env_message(
        #         message_type=KafkaMessageType.UPDATE_WORKER_ATTRIBUTES,
        #         payload=[
        #             {
        #                 worker_code: {
        #                     "used_overtime_minutes": self.workers_dict[
        #                         worker_code
        #                     ].used_overtime_minutes
        #                 }
        #             }
        #         ],
        #     )

        # if worker_code == "MY|D|3|CT02":
        #     log.debug(
        #         f"{worker_code} - {net_overtime_minutes} = {self.workers_dict[worker_code].used_overtime_minutes}"
        #     )

        return added_successful

    # def mutate_create_worker(self, new_worker: Worker):
    #     # For now it does not trigger re-planning affected, 2020-10-25 10:09:19

    #     if new_worker.worker_code in self.workers_dict.keys():
    #         log.error(
    #             f"mutate_create_worker: error, worker already existed: {new_worker.worker_code}"
    #         )
    #         return False
    #         # raise ValueError("duplicate worker code '{0}' found".format(new_worker.worker_code))
    #     self.workers.append(new_worker)
    #     self.workers_dict[new_worker.worker_code] = new_worker
    #     self.workers_dict[new_worker.worker_code].worker_index = len(self.workers) - 1
    #     for day_seq in self.daily_working_flag.keys():
    #         self.get_working_interval_4_worker(
    #             worker_code=new_worker.worker_code, day_seq=day_seq
    #         )

    #     log.info(
    #         f"mutate_create_worker: successfully added worker, code = {new_worker.worker_code}"
    #     )

    def mutate_update_worker_coordinate(self, location_update_dict):
        # Worker_code -> [long, lat]
        if len(location_update_dict) < 1:
            return
        location_change_list = []
        # updated_set = set()
        for k, v in location_update_dict.items():
            location = self.workers_dict[k].curr_slot.start_location
            code = location.code
            # if code in updated_set:
            #     log.error(f"duplicated location ({code})for different workers ({k}) detected, aborting calc_worker_cluster_locations")
            #     return
            # updated_set.add(code)

            longi = round(v[0], 6)
            lati = round(v[1], 6)
            self.locations_dict[k] = JobLocationBase(
                longi,lati, 
                LocationType.HOME,
                code,
            )
            self.workers_dict[k].curr_slot.start_location = self.locations_dict[k]
            self.workers_dict[k].flex_form_data.update({
                "geo_longitude":longi,
                "geo_latitude":lati,
            })
            location_change_list.append({
                "worker_code":k,
                "geo_longitude":longi,
                "geo_latitude":lati,
            })
        self.kp_data_adapter.save_worker_coordinate(changed_workers=location_change_list)

        # self.kp_data_adapter.save_changed_locations(changed_locations=location_change_list)


    # def mutate_create_worker(self, new_worker: Worker):
    #     # For now it does not trigger re-planning affected, 2020-10-25 10:09:19

    #     if new_worker.worker_code in self.workers_dict.keys():
    #         log.error(
    #             f"mutate_create_worker: error, worker already existed: {new_worker.worker_code}"
    #         )
    #         return False
    #         # raise ValueError("duplicate worker code '{0}' found".format(new_worker.worker_code))
    #     self.workers.append(new_worker)
    #     self.workers_dict[new_worker.worker_code] = new_worker
    #     self.workers_dict[new_worker.worker_code].worker_index = len(self.workers) - 1
    #     for day_seq in self.daily_working_flag.keys():
    #         self.get_working_interval_4_worker(
    #             worker_code=new_worker.worker_code, day_seq=day_seq
    #         )

    #     log.info(
    #         f"mutate_create_worker: successfully added worker, code = {new_worker.worker_code}"
    #     )

    def mutate_update_worker(self, new_worker: Worker):
        # I assume it is Unplanned for now, 2020-04-24 07:22:53.
        # No replay
        if new_worker.worker_code not in self.workers_dict.keys():
            log.error(
                "mutate_update_worker: The worker code '{0}' is not found".format(
                    new_worker.worker_code
                )
            )
            return
            # raise ValueError("The worker code '{0}' is not found".format(new_worker.worker_code))
        w_idx = self.workers_dict[new_worker.worker_code].worker_index
        if self.workers[w_idx].worker_code != new_worker.worker_code:
            log.error(
                f"worker_index mismatch during mutate_update_worker {new_worker}. Failed to update"
            )
            # TODO, clean up and reset index.
            return
        self.workers_dict[new_worker.worker_code] = new_worker
        self.workers_dict[new_worker.worker_code].worker_index = w_idx
        self.workers[w_idx] = self.workers_dict[new_worker.worker_code]
        log.info(f"mutate_update_worker: success, worker is updated with new profile: {new_worker}")

    # def mutate_create_appointment(self, new_job, auto_replay=True): # : Appointment
    #     # I assume it is Unplanned for now, 2020-04-24 07:22:53.
    #     # No replay
    #     if new_job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
    #         log.debug(f"debug appt {kandbox_config.DEBUGGING_JOB_CODE_SET}")
    #     if new_job.job_code in self.jobs_dict.keys():
    #         log.warning(
    #             f"APPT:{new_job.job_code}: mutate_create_appointment, job already existed",
    #         )
    #         # raise ValueError("duplicate job code '{0}' found".format(new_job.job_code))
    #         return
    #         # new_job.job_index = job_index

    #     self.jobs.append(new_job)
    #     job_index = len(self.jobs) - 1
    #     new_job.job_index = job_index
    #     self.jobs_dict[new_job.job_code] = new_job

    #     if new_job.included_job_codes is None:
    #         new_job.included_job_codes = []

    #     # First return occupied slots from included jobs
    #     for existing_job_code in new_job.flex_form_data["included_scheduled_visit_ids"].split(";"):
    #         # remove the job from time slots
    #         # step current appointment.
    #         stripped_job_code = existing_job_code.strip()
    #         try:
    #             v = self.jobs_dict[stripped_job_code]

    #         except KeyError:
    #             print(
    #                 f"_get_appointment_form_dict: at least one visit is not found job_code={stripped_job_code.strip()}, ",
    #                 new_job.flex_form_data["all_verified"],
    #             )
    #             # new_job.flex_form_data["all_verified"] = False
    #             return False
    #         if stripped_job_code not in new_job.included_job_codes:
    #             new_job.included_job_codes.append(stripped_job_code)

    #         self.jobs_dict[stripped_job_code].is_active = False
    #         if self.jobs_dict[stripped_job_code].planning_status == JobPlanningStatus.UNPLANNED:
    #             # log.warn
    #             log.warning(
    #                 f"APPT:{new_job.job_code}:JOB:{stripped_job_code}: U status job () is included in appointment (). It is simply applied without modifying job."
    #             )
    #             continue
    #     # Then apply this appointment action
    #     # if False:
    #     # if not kandbox_config.DEBUG_ENABLE_APPOINTMENT_REPLAY:
    #     #     return
    #     if auto_replay:
    #         release_success, info = self.slot_server.release_job_time_slots(
    #             self.jobs_dict[stripped_job_code]
    #         )
    #         if not release_success:
    #             log.warning(
    #                 f"Error releasing job (code={stripped_job_code}) inside the appointment ({new_job.job_code}), but I will continue appointment replay ..."
    #             )
    #             # return False

    #         self.mutate_replay_appointment(job=new_job)

    #     self.redis_conn.hmset(
    #         "{}{}".format(kandbox_config.APPOINTMENT_ON_REDIS_KEY_PREFIX, new_job.job_code),
    #         {"rec_round": 0, "planning_status": "PENDING", "team_id": self.team_id},
    #     )

    # def mutate_replay_appointment(self, job: Appointment):
    #     if (job.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes()) or (
    #         job.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()
    #     ):
    #         log.warning(
    #             f"Start time of appointment ({job.job_code}={job.scheduled_start_minutes}) is out of planning window, skippped replaying"
    #         )
    #         return False
    #     action_dict = self.gen_action_dict_from_appointment(job)
    #     self.mutate_update_job_by_action_dict(a_dict=action_dict, post_changes_flag=False)

    #     return True
    #     # TODO, Third, trigger the heuristic search for recommendations

    # # There is no update_appointment. This should be done by API->commit
    # # def mutate_update_appointment(self, new_job):
    # # Deprecated 2020-12-16 20:57:17
    # # Reason: I keep original appt code for multiple times re-scheduling
    # def mutate_update_job_code__TODEL(self, old_job_code: str, new_job_code: str):
    #     # I assume it is Unplanned for now, 2020-04-24 07:22:53.
    #     # No replay
    #     if old_job_code not in self.jobs_dict.keys():
    #         # raise ValueError("Job code '{0}' not found".format(old_job_code))
    #         log.error("Job code '{0}' not found".format(old_job_code))
    #         return
    #     if self.jobs_dict[old_job_code].job_type != JobType.APPOINTMENT:
    #         log.error(
    #             "ERROR: ONLY appointment job code can be changed, but  {}  is {} ".format(
    #                 old_job_code, self.jobs_dict[old_job_code].job_type
    #             )
    #         )
    #     old_job = self.jobs_dict[old_job_code]
    #     old_job.job_code = new_job_code
    #     del self.jobs_dict[old_job_code]
    #     self.jobs_dict[new_job_code] = old_job

    #     # location in self.jobs remains untouched.
    #     # TODO, send to kafka.
    #     log.warning(
    #         f"mutate_update_job_code:APPT:{old_job_code}:NEW_APPT:{new_job_code}: appointment code to updated to new one by {self.env_inst_code}. No more recommendations to any of them."
    #     )

    # def mutate_delete_appointment(self, job_code):
    #     # I assume it is Unplanned for now, 2020-04-24 07:22:53.
    #     # No replay
    #     if job_code not in self.jobs_dict.keys():
    #         log.error("mutate_delete_appointment: appt does not exist: ", job_code)
    #         return
    #     self.jobs_dict[job_code].is_active = False
    #     job_index = self.jobs_dict[job_code].job_index
    #     curr_appt = self.jobs_dict[job_code]

    #     release_success_flag, info = self.slot_server.release_job_time_slots(job=curr_appt)
    #     if not release_success_flag:
    #         log.warning(
    #             f"Error whiling tring to release existing appoitnment slot, {curr_appt.job_code}"
    #         )

    #     # Restore job status after removing covering appointment.
    #     for included_job_code in curr_appt.included_job_codes:
    #         self.jobs_dict[included_job_code].is_active = True
    #         if self.jobs_dict[included_job_code].planning_status != JobPlanningStatus.UNPLANNED:
    #             self.mutate_replay_job(job=self.jobs_dict[included_job_code])

    #     self.jobs_dict[job_code] = None
    #     del self.jobs_dict[job_code]

    #     try:
    #         if self.jobs[job_index].job_code != job_code:
    #             log.error(f"mutate_delete_appointment: job code mismatch {job_code}")
    #         else:
    #             del self.jobs[job_index]
    #     except:
    #         log.error(
    #             f"mutate_delete_appointment:exception: job code mismatch job_code={job_code}, job_index = {job_index}, "
    #         )
    #     # Remove appt from redis recommendation frontend
    #     self.redis_conn.delete(
    #         "{}{}".format(kandbox_config.APPOINTMENT_ON_REDIS_KEY_PREFIX, job_code)
    #     )
    #     # Remove recommendations from redis
    #     for rec_code in self.redis_conn.scan_iter(
    #         f"{self.get_recommendation_job_key(job_code=job_code, action_day=-1)}*"
    #     ):
    #         self.redis_conn.delete(rec_code)

    #     log.info(f"APPT:{job_code} is purged out of env {self.env_inst_code}")

    # def mutate_create_worker_absence(self, new_job: Absence, auto_replay=True):

    #     if new_job.job_code in self.jobs_dict.keys():
    #         print("add_job: error, job already existed: ", new_job.job_code)
    #         return
    #         # raise ValueError("duplicate job code '{0}' found".format(new_job.job_code))
    #         # new_job.job_index = job_index

    #     self.jobs.append(new_job)
    #     job_index = len(self.jobs) - 1
    #     new_job.job_index = job_index
    #     self.jobs_dict[new_job.job_code] = new_job
    #     if auto_replay:
    #         self.mutate_replay_worker_absence(job=new_job)
    #     log.debug(
    #         f"ABSENCE:{new_job.job_code}: the absence is created/added into env.",
    #     )

    # def mutate_replay_worker_absence(self, job: Absence):
    #     if (job.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes()) or (
    #         job.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()
    #     ):
    #         log.warning(
    #             f"Start time of absence ({job.job_code}={job.scheduled_start_minutes}) is out of planning window, skippped replaying"
    #         )
    #         return False
    #     action_dict = self.gen_action_dict_from_worker_absence(job)
    #     self.mutate_update_job_by_action_dict(a_dict=action_dict, post_changes_flag=False)
    #     return True

    def mutate_create_job(self, new_job, auto_replay=True):
        # I assume it is Unplanned for now, 2020-04-24 07:22:53.
        # No replay
        if new_job.job_code in self.jobs_dict.keys():
            log.error("add_job: error, job already existed: ", new_job.job_code)
            return
            # raise ValueError("duplicate job code '{0}' found".format(new_job.job_code))
            # new_job.job_index = job_index
        else:
            self.jobs.append(new_job)
            new_job.job_index = len(self.jobs) - 1
            self.jobs_dict[new_job.job_code] = new_job

        # Then apply this appointment action
        if auto_replay:
            if new_job.planning_status != JobPlanningStatus.UNPLANNED:
                self.mutate_replay_job(job=new_job)

        log.info(f"mutate_create_job: successfully added job, code = {new_job.job_code}")

    def mutate_update_job_metadata(self, new_job):
        # I assume it is Unplanned for now, 2020-04-24 07:22:53.
        # No replay
        if new_job.job_code not in self.jobs_dict.keys():
            log.error("add_job: error, job already existed: ", new_job.job_code)
            return
        curr_job = self.jobs_dict[new_job.job_code]

        # Keep the scheduling information intact as before
        new_job.scheduled_worker_codes = curr_job.scheduled_worker_codes
        new_job.scheduled_start_minutes = curr_job.scheduled_start_minutes
        new_job.scheduled_duration_minutes = curr_job.scheduled_duration_minutes

        curr_job_index = curr_job.job_index
        if self.jobs[curr_job_index].job_code != new_job.job_code:
            log.warning(f"mismatched job_index while adding job {new_job.job_code}")
            # return
        self.jobs[curr_job_index] = new_job
        self.jobs_dict[new_job.job_code] = new_job

        log.info(
            f"Successfully updated job metadata, no schedulling action done. code = {new_job.job_code}"
        )
        # Then I skip appling scheduling action

    def mutate_replay_job(self, job): # : Appointment
        if (job.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes()) or (
            job.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()
        ):
            log.info(
                f"Start time of Job ({job.job_code}) is  {job.scheduled_start_minutes}), out of planning window ({self.get_env_planning_horizon_start_minutes()}->{self.get_env_planning_horizon_end_minutes()}), skipped replaying"
            )
            return False
        if job.planning_status == JobPlanningStatus.UNPLANNED:
            log.info(f"U-Status Job ({job.job_code}) is skipped from replaying.")
            return True
        action_dict = self.gen_action_dict_from_job(job, is_forced_action=True)
        self.mutate_update_job_by_action_dict(a_dict=action_dict, post_changes_flag=False)
        return True

    # def mutate_complete_db_job(self, job, prev_travel, curr_minute):
    #     # Mark a job as completed and optionally remove it.

    #     # Keep the scheduling information intact as before

    #     job.planning_status = JobPlanningStatus.FINISHED
    #     self.db_session.add(job)
    #     # event_service.log_job_event(
    #     #     db_session=self.db_session,
    #     #     source='rl_env',
    #     #     # .scheduled_start_datetime
    #     #     description=f"finished",
    #     #     job_code=job.code,
    #     #     details=None
    #     # )
    #     self.db_session.commit()
    #     if self.config.get("collect_statistics", 0) == 1:
    #         self.kpi_stat.push_finished_job_travel(
    #             worker_code=job.scheduled_primary_worker_code,
    #             travel_minutes=prev_travel,
    #             curr_minute=curr_minute,
    #             job=job,
    #             env = self,
    #         )

    #     log.info(f"Successfully mutate_complete_db_job. code = { job.code} at minutes {curr_minute}")

    def process_rule_check_info(self, rule_check_info):

        # This items IS available in depot/warehouse.
        # Then I will add a virtual replenish job and move on.
        # The replenish job is only added to primary worker as all_slots[0]
        for a_rule_result in rule_check_info.messages:
            # print(a_rule_result)
            if (a_rule_result.score_type == "Requested Items") and (a_rule_result.score == 0):
                total_accum_items = a_rule_result.metrics_detail["total_accum_items"]
                total_requested_items = a_rule_result.metrics_detail["total_requested_items"]
                replenish_job = self.mutate_create_replenish_job(
                    slot=a_rule_result.metrics_detail["slot"],
                    total_accum_items=total_accum_items,
                    total_requested_items=total_requested_items,
                )
                if replenish_job is None:
                    return ActionScoringResultType.ERROR
            elif a_rule_result.score == -1:
                return ActionScoringResultType.ERROR
        return ActionScoringResultType.OK

    def mutate_finish_job_in_slot(
            self, worker_code, job_code, start_minutes,
            longitude, latitude):
        
        # 2024-02-12 18:50:45, I will wait till id:u32 to do this version !!!
        ord_code, job_seq = encode_job_code2rustenv(job_code)
        commands = ["s.finish", self.get_env_slot_set_key(), 
            worker_code, str(int(start_minutes)*60), 
            ord_code, str(job_seq)]
        try:
            res = self.redis_conn.execute_command(*commands)
            log.info(f"Successfully finished job {job_code}  for worker_code {worker_code} by command {commands}, res = {res}")
            return True
        except redis.exceptions.ResponseError as e:
            log.error(f"s.finish for job {job_code} failed. Error = {str(e)}.  Command = {commands}")
        return False

        # OLD VERSION
        ####################################################################
        # slot_list = self.get_working_slot_list(
        #     worker_code=worker_code,
        #     start_minutes=start_minutes - 1,
        #     end_minutes=start_minutes + 1,
        #     active_only=False,
        # )
        # for slot in slot_list:
        #     for ji,job in enumerate(slot.assigned_jobs):
        #         if job.code == job_code:
        #             del slot.assigned_jobs[ji]
        #             slot.start_longitude = longitude
        #             slot.start_latitude = latitude
        #             self.add_single_working_time_slot(
        #                 slot=slot, )
        #             log.info(f"job {job_code} is deleted from worker {worker_code}, slot {slot.slot_code}")
        #             return
        # else:
        #     log.warning(f"failed to find slot for worker_code {worker_code}, start_minutes {start_minutes}")
    
        
    def mutate_update_job_by_action(
        self, action: EnvAction, db_session
    ) -> SingleJobCommitInternalOutput: 
        
        job_commit_output = SingleJobCommitInternalOutput(
            status_code=ActionScoringResultType.ERROR,
            messages=[],
            nbr_changed_jobs=0,
            new_job_code="",
        )
        if action.scheduled_slots is None or len(action.scheduled_slots) < 1:
            job_commit_output.messages.append("action.scheduled_slots is empty, nothing to do")
            return job_commit_output

        db_session.commit() # to avoid left over trx
        for target_slot in action.scheduled_slots:# [0]
            deleted_job_code_list = []
            new_planning_status = {}
            new_assigned_jobs = []
            bulk_update_list = []

            for job_i, job in enumerate(action.jobs):
                # if job.planning_status in (JobPlanningStatus.FINISHED, JobPlanningStatus.UNPLANNED):
                if action.action_type == ActionType.UNPLAN:
                    new_planning_status[job.code] = JobPlanningStatus.UNPLANNED
                    deleted_job_code_list.append(job.code)
                elif action.action_type == ActionType.FINISHED:
                    new_planning_status[job.code] = JobPlanningStatus.FINISHED
                    deleted_job_code_list.append(job.code)
                elif action.is_appointment:
                    new_planning_status[job.code] = JobPlanningStatus.PLANNED
                else:
                    new_planning_status[job.code] = JobPlanningStatus.IN_PLANNING

            slot_code = target_slot.slot_code

            original_requested_jobs = target_slot.assigned_jobs
            job_code_set = set()
            for job_i, job in enumerate(original_requested_jobs):
                if job.code in job_code_set:
                    log.error(f"duplicated_job_code_detected_when_saving: {job.code} at slot {target_slot.slot_code}, with jobs {[j.code for j in original_requested_jobs]}")
                    continue

                if job.code not in deleted_job_code_list:
                    # original_requested_jobs, 时间不改，按照随便一个时间。
                    new_assigned_jobs.append(job)
                    job_code_set.add(job.code)

            # Retrive from 
            existing_slot = self.get_working_slot_list(slot_key=slot_code)[0]
            if existing_slot.job_change_count > target_slot.job_change_count:
                raise SlotModifedException

            target_slot.assigned_jobs = new_assigned_jobs
            target_slot.job_change_count += 1

            self.add_single_working_time_slot(slot = target_slot, update_ops=["jobs"])

            log_msg = ""
            # TODO, change to mapping, batch update. 2023-01-01 11:48:00
            for job_i, job in enumerate(target_slot.assigned_jobs):
                curr_job = job_service.get_by_code(db_session=db_session, code=job.code)
                if not curr_job:
                    log.error(f"when update to db, job {job.code} is no longer in db")
                    continue
                # if curr_job.planning_status in {JobPlanningStatus.PLANNED}:
                #     if (curr_job.job_type == JobType.JOB) and (not action.is_forced_action):
                #         job_commit_output.messages.append(
                #             "Failed to change job planning because planning_status == PLANNED and not is_forced_action"
                #         )
                #         return job_commit_output
                # # else:
                # #     job.planning_status = 
                
                curr_job.scheduled_start_datetime = self.env_decode_from_minutes_to_datetime(job.scheduled_start_minutes)
                # curr_job.scheduled_duration_minutes = curr_job.requested_duration_minutes
                curr_job.planning_status = new_planning_status.get(job.code,JobPlanningStatus.IN_PLANNING)
                curr_job.scheduled_primary_worker_code = target_slot.worker_code
                if self.config.get("sync_job_area_code_when_replan","1") == "1":
                    curr_area_code1 = curr_job.flex_form_data.get( "area_code", DEFAULT_AREA_CODE)
                    if curr_area_code1!=target_slot.area_code:
                        curr_job.flex_form_data["area_code"]=target_slot.area_code
                        flag_modified(curr_job, "flex_form_data")
                db_session.add(curr_job)
                db_session.commit()
                log.info(
                    f"JOB:{curr_job.code}:SLOT:{target_slot.slot_code}: job is changed to new time in DB: {curr_job.scheduled_start_datetime}"
                )
                start_dt = self.env_decode_from_minutes_to_datetime(job.scheduled_start_minutes)

                # bulk_update_list.append({
                #         "code":job.code,
                #         "planning_status":"I",
                #         "scheduled_primary_worker_code":target_slot.worker_code,
                #         "scheduled_start_datetime":start_dt,
                #     })
                log_msg = log_msg + f"{job.code}:{str(start_dt)};"

            # WHen one missing, this gives error: sqlalchemy.orm.exc.StaleDataError: UPDATE statement on table 'job' expected to update 7 row(s); 6 were matched.
            # db_session.bulk_update_mappings(
            #     Job,
            #     bulk_update_list,
            # )
            # db_session.commit()
            event_service.log_job_event(
                db_session=db_session,
                source='rl_env',
                description=f"cascading changes to worker: {target_slot.worker_code}",
                flex_form_data = { 
                    "msg":log_msg,
                },
                job_code=action.jobs[0].code,
                details=None
            )

            job_commit_output.nbr_changed_jobs += len(target_slot.assigned_jobs)


        job_commit_output.status_code = ActionScoringResultType.OK
        

        log.info(
            f"SLOT:{target_slot.slot_code}: slot is commited successfully. "
        )

        return job_commit_output

    def mutate_commit_recommendation(
        self, recommendation: RecommendedAction, post_changes_flag: bool = False
    ) -> RecommendationCommitInternalOutput:
        output_result = RecommendationCommitInternalOutput(
            status_code=ActionScoringResultType.OK,
            jobs_output_list=[],
            new_job_code=None,
        )

        # Step 1: Unplan some affected visits according to the recommended action.
        for unplanned_job_code in recommendation.unplanned_job_codes:
            log.warning(
                f"JOB:{unplanned_job_code} is unplanned because of commit appt={recommendation.job_code}"
            )

            unplan_action = self.gen_action_dict_from_job(
                job=self.jobs_dict[unplanned_job_code], is_forced_action=True
            )
            unplan_action.action_type = ActionType.UNPLAN

            internal_result_info = self.mutate_update_job_by_action_dict(
                a_dict=unplan_action, post_changes_flag=True
            )

            if internal_result_info.status_code != ActionScoringResultType.OK:
                log.error(
                    # {internal_result_info}
                    f"APPOINTMENT:{recommendation.job_code}: Failed to unplan job={unplanned_job_code} as a cascading change. "
                )
                return RecommendationCommitInternalOutput(
                    status_code=ActionScoringResultType.ERROR,
                    jobs_output_list=output_result.jobs_output_list,
                    new_job_code=None,
                )
            else:
                log.info(
                    # {internal_result_info}
                    f"APPOINTMENT:{recommendation.job_code}: Successfully unplanned job={unplanned_job_code} as a cascading change. "
                )
                # return internal_result_info
                # simply pass?
            output_result.jobs_output_list.append(internal_result_info)

        # Step 2: Commit other affected jobs along with the action.
        changed_job_codes_set = set()
        for ts_index in range(len(recommendation.job_plan_in_scoped_slots)):
            slot_code = recommendation.scoped_slot_code_list[ts_index]
            for j_index, planned_slot in enumerate(
                recommendation.job_plan_in_scoped_slots[ts_index]
            ):
                changed_job_temp = self.jobs_dict[planned_slot[1]]
                if changed_job_temp.job_type == JobType.APPOINTMENT:
                    if changed_job_temp.job_code != recommendation.job_code:
                        log.error(
                            f"Other appointment ({changed_job_temp.job_code}) should not be changed by appointment ({recommendation.job_code})"
                        )
                    continue

                if planned_slot[3]:  # Changed = True
                    a_job = self.jobs_dict[changed_job_temp.job_code]
                    if a_job.planning_status == JobPlanningStatus.UNPLANNED:
                        log.warning("job should not be unplanned.")
                        a_job.planning_status = JobPlanningStatus.IN_PLANNING

                    a_job.scheduled_worker_codes = recommendation.scheduled_worker_codes
                    a_job.scheduled_start_minutes = planned_slot[0]
                    a_job.scheduled_duration_minutes = self.jobs_dict[
                        changed_job_temp.job_code
                    ].scheduled_duration_minutes

                    a_job.is_changed = True

                    changed_job_codes_set.add(changed_job_temp.job_code)

                # worker_code = res["all_worker_codes"][0]
                # self.workers_dict[worker_code].curr_slot.assigned_job_codes = res.all_assigned_job_codes
                sorted_assigned_job_codes = [
                    s[1] for s in recommendation.job_plan_in_scoped_slots[ts_index]
                ]
                set_result, info = self.slot_server.set_assigned_job_codes(
                    slot_code=slot_code, job_codes=sorted_assigned_job_codes
                )
                if not set_result:
                    log.error(
                        # {internal_result_info}
                        f"APPOINTMENT:{recommendation.job_code}: Failed to commit change for job={changed_job_temp.job_code} as a cascading change. error: {str(internal_result_info)} "
                    )
                else:
                    log.info(
                        # {internal_result_info}
                        f"APPOINTMENT:{recommendation.job_code}: Finished commit change for job={changed_job_temp.job_code} as a cascading change. start = {planned_slot[0]}"
                    )

            output_result.jobs_output_list.append(info)

        self.jobs_dict[recommendation.job_code].is_changed = True

        # self.commit_changed_jobs(changed_job_codes_set=changed_job_codes_set)

        return output_result

    def commit_changed_job2db(self, db_session, job:JobInSlot, worker_code):

        curr_job = job_service.get_by_code(db_session=db_session, code=job.code)
        new_status = JobPlanningStatus.IN_PLANNING
        if curr_job.planning_status in {JobPlanningStatus.PLANNED}:
            if curr_job.scheduled_primary_worker_code != worker_code:
                log.warning(
                        f"Failed to change job planning for {job.code} because planning_status == PLANNED and curr_job.scheduled_primary_worker_code {curr_job.scheduled_primary_worker_code} != worker_code {worker_code} and not is_forced_action"
                    )
                return  
            new_status = JobPlanningStatus.PLANNED
        
        curr_job.planning_status = new_status
        curr_job.scheduled_start_datetime = self.env_decode_from_minutes_to_datetime(job.scheduled_start_minutes)
        curr_job.scheduled_primary_worker_code = worker_code
        db_session.add(curr_job)
        db_session.commit()


        event_service.log_job_event(
            db_session=db_session,
            source='rl_env',
            description=f"planned to worker: { worker_code}, time: {curr_job.scheduled_start_datetime}",
            flex_form_data = {
                "schduled_worker_code": worker_code,
                "scheduled_start_datetime":curr_job.scheduled_start_datetime,
            },
            job_code=curr_job.code,
            details=None
        )
        log.info(
            f"JOB:{curr_job.code}: job is changed to new time: {curr_job.scheduled_start_datetime}"
        )


    def _calc_travel_minutes_difference(
        self, shared_time_slots_optimized, arranged_slots, current_job_code
    ):

        new_travel_minutes_difference = 0
        max_minutes = self.travel_max_minutes * len(shared_time_slots_optimized) + 1

        for a_slot, new_job_code_list in zip(shared_time_slots_optimized, arranged_slots):
            # new_job_code_list = [s[1] for s in arranged_slot]
            (
                prev_travel,
                next_travel,
                inside_travel,
            ) = self.get_travel_time_jobs_in_slot(a_slot, new_job_code_list)
            new_travel_minutes = prev_travel + next_travel + sum(inside_travel)

            new_job_code_list.remove(current_job_code)
            (
                prev_travel,
                next_travel,
                inside_travel,
            ) = self.get_travel_time_jobs_in_slot(a_slot, new_job_code_list)
            original_travel_minutes = prev_travel + next_travel + sum(inside_travel)

            new_travel_minutes_difference += new_travel_minutes - original_travel_minutes
        # print(new_travel_minutes_difference, max_minutes)
        return (max_minutes - new_travel_minutes_difference) / max_minutes

    def pprint_all_slots(self):

        for k in sorted(self.slot_server.time_slot_dict.keys()):
            job_list = self.slot_server.time_slot_dict[k].assigned_job_codes
            (
                prev_travel,
                next_travel,
                inside_travel,
            ) = self.get_travel_time_jobs_in_slot(self.slot_server.time_slot_dict[k], job_list)
            print(
                k,
                self.slot_server.time_slot_dict[k].start_location[0:2],
                (
                    prev_travel,
                    next_travel,
                    inside_travel,
                ),
            )
            print(
                self.slot_server.time_slot_dict[k].start_minutes,
                [(self.jobs_dict[s].scheduled_start_minutes, s) for s in job_list],
            )

    def get_travel_time_jobs_in_slot(self, slot, all_jobs):
        prev_time = 0
        next_time = 0
        inside_time = []
        if len(all_jobs) < 1:
            return 0, 0, []
        if slot.start_location[2] == LocationType.JOB:
            prev_time = self.travel_router.get_travel_minutes_2locations(
                [
                    self.jobs_dict[all_jobs[0]].location.geo_longitude,
                    self.jobs_dict[all_jobs[0]].location.geo_latitude,
                ],
                [slot.start_location[0], slot.start_location[1]],
            )
        if slot.end_location[2] == LocationType.JOB:
            next_time = self.travel_router.get_travel_minutes_2locations(
                [
                    self.jobs_dict[all_jobs[-1]].location.geo_longitude,
                    self.jobs_dict[all_jobs[-1]].location.geo_latitude,
                ],
                [slot.start_location[0], slot.start_location[1]],
            )
        for job_i in range(len(all_jobs) - 1):
            inside_time.append(
                self.travel_router.get_travel_minutes_2locations(
                    [
                        self.jobs_dict[all_jobs[job_i]].location.geo_longitude,
                        self.jobs_dict[all_jobs[job_i]].location.geo_latitude,
                    ],
                    [
                        self.jobs_dict[all_jobs[job_i + 1]].location.geo_longitude,
                        self.jobs_dict[all_jobs[job_i + 1]].location.geo_latitude,
                    ],
                )
            )

        return prev_time, next_time, inside_time

    def _get_travel_time_2_job_indices(self, job_index_1, job_index_2):
        job_1 = self.jobs[job_index_1]
        job_2 = self.jobs[job_index_2]
        return self._get_travel_time_2jobs(job_1, job_2)

    def _get_travel_time_2jobs(self, job_1, job_2):
        return self.travel_router.get_travel_minutes_2locations(
            [
                job_1.location.geo_longitude,
                job_1.location.geo_latitude,
            ],
            [
                job_2.location.geo_longitude,
                job_2.location.geo_latitude,
            ],
        )

    def get_travel_minutes_loc_list(self, loc_list):
        travel_minutes = []
        for loc_i in range(len(loc_list) - 1):
            _t = self.haversine_travel_router.get_travel_minutes_2locations(
                loc_list[loc_i], loc_list[loc_i+1] 
            )
            travel_minutes.append(_t)
        return travel_minutes

    def solve_tsp_slot_assigned_jobs(self, assigned_jobs):
        if len( assigned_jobs) < 3:
            return assigned_jobs 
        assigned_job_locs =  [
            (j.geo_longitude, j.geo_latitude) for j in assigned_jobs 
        ] 

        new_seq, start_distance = self.travel_router.solve_tsp(loc_list = assigned_job_locs )

        # Then generate jobs by this seq
        _assigned_new = assigned_jobs[0:1]
        current_start = assigned_jobs[0].scheduled_start_minutes
        for j_idx, ji in enumerate(new_seq):
            if j_idx < 1:
                continue
            job = assigned_jobs[ji]
            current_start += start_distance[j_idx] + job.scheduled_duration_minutes
            job.prev_travel = start_distance[j_idx]
            job.scheduled_start_minutes=current_start + start_distance[j_idx]
            _assigned_new.append(job)
        return _assigned_new
    
    def solve_greedy_pickdrop_locations(
            self, 
            loc_list,
            next_loc_list,
            curr_loc_mask,
            ):
        solution_idx = [0]
        # solution = [loc_list[0]]
        # visited_idx = set([0])
        curr_loc_i = 0
        for _ in range(len(loc_list) - 1):
            start_idx = 1
            while start_idx < len(curr_loc_mask) and (curr_loc_mask[start_idx] != 0): # start_idx in visited_idx or 
                start_idx += 1
            if start_idx >= len(curr_loc_mask):
                # No more nodes.
                break

            min_dist = self.haversine_travel_router.get_travel_minutes_2locations(
                    loc_list[curr_loc_i], loc_list[start_idx] 
                )
            min_idx = start_idx 

            for loc_i in range(start_idx + 1, len(loc_list)):
                if curr_loc_mask[loc_i] != 0:
                    continue
                _t = self.haversine_travel_router.get_travel_minutes_2locations(
                    loc_list[curr_loc_i], loc_list[loc_i] 
                )
                if _t < min_dist:
                    min_dist = _t
                    min_idx = loc_i
            if next_loc_list[min_idx] != -1:
                if curr_loc_mask[next_loc_list[min_idx]] == 1:
                    curr_loc_mask[next_loc_list[min_idx]] = 0
            curr_loc_mask[min_idx] = -1

            solution_idx.append(min_idx)
            # solution.append(loc_list[min_idx])
            curr_loc_i = min_idx
        return solution_idx # , solution
    

    def unplan_job_list(self,
        target_job_list, db_session, commit_ex_slot = False, worker_code = None, solve_tsp_over_others = False
    ):
        if len(target_job_list) < 1:
            return [], None
        unplan_job_code_list = [j.code for j in target_job_list]
        worker_code_list = [j.scheduled_primary_worker_code for j in target_job_list]
        if len(set(worker_code_list)) != 1:
            log.error("jobs_not_in_same_worker, rejected to unplan")
            return [], None

        for j in target_job_list: 
            j.planning_status = JobPlanningStatus.UNPLANNED
            db_session.add(j)
            db_session.commit()
            
        target_slots = self.get_working_slot_list(worker_code=worker_code_list[0], active_only= True)


        if len(target_slots) < 1:
            return [],None
        elif len(target_slots) > 1:
            log.warning("trying to unplan from multiple workers! skipped.")
        slot  = target_slots[0]
        _new_assigned_jobs = []
        for ji in range(len(slot.assigned_jobs)):
            if slot.assigned_jobs[ji].code not in unplan_job_code_list:
                _new_assigned_jobs.append(slot.assigned_jobs[ji])
                # slot.assigned_jobs[ji].planning_status = JobPlanningStatus.UNPLANNED
        horizon = max(
            slot.start_minutes,
            self.get_env_planning_horizon_start_minutes())
        if solve_tsp_over_others:
            solved_jobs = self.solve_jobs_tsp(
                assigned_jobs = _new_assigned_jobs,
                start_loc = [slot.start_longitude, slot.start_latitude],
                start_minutes = horizon)
        else:
            solved_jobs = _new_assigned_jobs
        slot.assigned_jobs = solved_jobs
        if commit_ex_slot:
            self.add_single_working_time_slot(slot=slot, update_ops=["jobs"])
        if len(target_job_list) != 2:
            return target_job_list, slot

        _pick_job = None
        _drop_job = None
        unplanned_from = []
        for j in target_job_list:
            # j.planning_status = JobPlanningStatus.UNPLANNED
            unplanned_from.append((j.code,j.scheduled_primary_worker_code))
            jt = j.code.split("-")[-1] 
            if jt == 'p':
                _pick_job = j
            elif jt == 'd':
                _drop_job = j
            # db_session.add(j)
        # db_session.commit()
        _todo_job_list = [_pick_job, _drop_job]
        log.info(f"Job is unplanned successfully from {unplanned_from}")    
        return _todo_job_list, slot

    def set_searching_worker_candidates(self, final_job): # : BaseJob
        if final_job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
            log.debug("final_job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET?")
        # if type(final_job.requested_primary_worker_code) == type(["a"]):
        #     log.debug("WHY?")

        # because rule checkers are mutating job, I copy one here.
        curr_job = copy.deepcopy(final_job)

        # orig_scheduled_worker_codes = curr_job.scheduled_worker_codes
        shared_worker_count = set()
        if curr_job.planning_status != JobPlanningStatus.UNPLANNED:
            shared_worker_count.add(len(curr_job.scheduled_worker_codes))

        # scheduled_duration_minutes = job.requested_duration_minutes
        min_number_of_workers = max_number_of_workers = 1
        try:
            min_number_of_workers = int(curr_job.flex_form_data["min_number_of_workers"])
            max_number_of_workers = int(curr_job.flex_form_data["max_number_of_workers"])
        except:
            log.warning(
                f"job {final_job.job_code} has no min_number_of_workers or max_number_of_workers and we assumed as 1"
            )
            pass

        for nbr_worker in range(
            min_number_of_workers,
            max_number_of_workers + 1,
        ):
            shared_worker_count.add(nbr_worker)

        all_qualified_worker_codes = set()

        # evaluate_DateTimeTolerance = KandboxRuleToleranceRule()
        for worker_code in list(self.workers_dict.keys()):
            is_valid = True
            for a_rule in self.rule_set_worker_check:
                curr_job.scheduled_worker_codes = [worker_code]
                check_result = a_rule.evalute_normal_single_worker_n_job(self, job=curr_job)
                if check_result.score == -1:
                    is_valid = False
                    break

            if is_valid:
                all_qualified_worker_codes.add(worker_code)
            # KandboxRulePluginWithinWorkingHour()
            # KandboxRulePluginSufficientTravelTime
            # KandboxRulePluginLunchBreak

        # TODO,  permenant pair & secondary only techs. @xingtong

        candidate_dict = {}

        # differen tiers of scoring
        SCORE_Primary = 1000_000
        SCORE_Permenant_Pair = 10_000  # It has priority if tech is permanently paired.
        SCORE_History = 9_000
        SCORE_Solo = 1_000
        SCORE_Share = {2: 100, 3: 80, 4: 60, 5: 30}
        historical_serving_worker_distribution = (
            curr_job.location.historical_serving_worker_distribution
        )
        if historical_serving_worker_distribution is None:
            historical_serving_worker_distribution = {final_job.requested_primary_worker_code: 1}

        for k, v in historical_serving_worker_distribution.items():
            one_candidate_tuple = tuple(k.split(";"))
            new_score = v

            is_valid = True
            for w_code in one_candidate_tuple:

                if w_code not in all_qualified_worker_codes:
                    # Though this worker served in history, he is no longer qualified for this job
                    is_valid = False
                    break
                if w_code == curr_job.requested_primary_worker_code:
                    new_score += SCORE_Primary
                else:
                    new_score = v + SCORE_History

            if not is_valid:
                continue

            if self.workers_dict[one_candidate_tuple[0]].flex_form_data["is_assistant"]:
                continue

            # Here I exclude those historical combinations no longer valid anymore
            if len(one_candidate_tuple) < min_number_of_workers:
                continue
            if len(one_candidate_tuple) > max_number_of_workers:
                continue

            # If 4 technicians served in the history, I also search for 4 tech combination
            shared_worker_count.add(len(one_candidate_tuple))
            candidate_dict[one_candidate_tuple] = new_score

        # In case in the future, multiple requested worker?
        curr_job.requested_primary_worker_code = copy.deepcopy(
            final_job.requested_primary_worker_code
        )

        if min_number_of_workers <= 1:
            for w_code in all_qualified_worker_codes:
                if (not self.workers_dict[w_code].flex_form_data["is_assistant"]) and (
                    (w_code,) not in candidate_dict.keys()
                ):
                    candidate_dict[(w_code,)] = SCORE_Solo

            # It may overrite historical setting. But primary will highest priority
            try:
                if (curr_job.requested_primary_worker_code,) in candidate_dict:
                    candidate_dict[(curr_job.requested_primary_worker_code,)] = SCORE_Primary
            except:
                log.debug("set_searching_worker_candidates_WHY? ")

        primary_worker_codes = (curr_job.requested_primary_worker_code,)
        # if primary_worker_codes not in candidate_dict.keys():
        # if min_number_of_workers <= 1:
        #     log.debug(f"requested worker not added! {primary_worker_codes}")
        #     candidate_dict[primary_worker_codes] = SCORE_Primary

        if self.workers_dict[curr_job.requested_primary_worker_code].belongs_to_pair is not None:
            primary_worker_codes = self.workers_dict[
                curr_job.requested_primary_worker_code
            ].belongs_to_pair
            if primary_worker_codes not in candidate_dict.keys():
                log.debug(f"requested worker pair not added yet! {primary_worker_codes}")
                candidate_dict[primary_worker_codes] = SCORE_Primary

        qualified_secondary_worker_codes = sorted(
            list(all_qualified_worker_codes - set(primary_worker_codes))
        )

        shared_worker_count_to_check = shared_worker_count - {1}

        for share_count in shared_worker_count_to_check:
            # Primary must be default when shared.
            secondary_share_count = share_count - len(primary_worker_codes)
            if secondary_share_count < 1:
                continue

            for combined_worker in list(
                combinations(qualified_secondary_worker_codes, secondary_share_count)
            ):
                new_combined = primary_worker_codes + combined_worker
                if new_combined in self.permanent_pairs:
                    candidate_dict[new_combined] = SCORE_Permenant_Pair
                else:
                    share_count_score_index = share_count if share_count <= 5 else 5
                    candidate_dict[new_combined] = SCORE_Share[share_count_score_index]

                # if share_count > 2:
                #     log.info(f"{final_job.job_code}--> {new_combined}, share_count {share_count} > 2, be careful ...")
                #     # continue

        # Finally I sort all candidates by their scores
        # I take top 80 only for now.
        # TODO, setup a proper limit on 10 here..., It was 80, 2021-07-15 09:57:51
        final_job_workers_ranked = [
            k
            for k, v in sorted(
                candidate_dict.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ]
        # final_job_workers_ranked = random.sample(final_job_workers_ranked, 20) if len(
        #     final_job_workers_ranked) > 20 else final_job_workers_ranked
        if len(candidate_dict) > 20:
            # --> {candidate_dict}
            log.debug(
                f"{final_job.job_code}, candidates_length = {len(candidate_dict)},  be careful ..."
            )

        final_job.searching_worker_candidates = final_job_workers_ranked
        # [(curr_job.requested_primary_worker_code,)]
        # curr_job.scheduled_worker_codes = orig_scheduled_worker_codes

        return final_job_workers_ranked

    def _get_sorted_worker_code_list(self, current_job_code):
        # TODO
        if current_job_code != self.current_job_code:
            log.warning(f"{current_job_code} ! = self.current_job_code = {self.current_job_code}")
        w_set = set()
        if len(self.jobs) >= 1:
            for w_list in self.jobs_dict[current_job_code].searching_worker_candidates:
                for w_code in w_list:
                    w_set.add(w_code)
        return w_set

        # return list(self.workers_dict.keys())[0 : self.config["nbr_observed_slots"]]

    def _check_action_on_rule_set(
        self, a_dict: ActionDict, unplanned_job_codes: List = []
    ) -> SingleJobDropCheckOutput:

        if (a_dict.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes()) or (
            a_dict.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()
        ):
            return SingleJobDropCheckOutput(
                status_code=ActionScoringResultType.ERROR,
                score=0,
                travel_time=15,
                messages=[
                    ActionEvaluationScore(
                        score=-1,
                        score_type="Planning Window",
                        message=f"scheduled_start_minutes {a_dict.scheduled_start_minutes} out of horizon ({self.get_env_planning_horizon_start_minutes()} - {self.get_env_planning_horizon_end_minutes()})",
                        metrics_detail={},
                    )
                ],
            )

        result_info = SingleJobDropCheckOutput(
            status_code=ActionScoringResultType.OK,
            score=0,
            travel_time=15,
            messages=[],
        )
        if len(unplanned_job_codes) > 0:
            self.unplanned_job_codes = unplanned_job_codes

        for rule in self.rule_set:
            rule_checked = rule.evalute_action_normal(env=self, action_dict=a_dict)

            rule_checked.score_type = rule.title
            result_info.messages.append(rule_checked)  # rule_checked_dict

            if (rule_checked.score < 1) & (result_info.status_code == ActionScoringResultType.OK):
                # Reduce from OK to Warning
                result_info.status_code = ActionScoringResultType.WARNING
                # Else it is already -1. keep it -1

            if rule_checked.score == -1:
                # Reduce overall result to ERROR, and stays at ERROR
                result_info.status_code = ActionScoringResultType.ERROR

        self.unplanned_job_codes = []
        return result_info

    def create_virtual_order(self, db_session,  order_in): # 
        """
            根据order_in 生成 order 对象 和 job 对象 , 只是没有db 操作
        """
        new_order = Order(**order_in.dict(exclude={
            "job_list", "team","scheduled_primary_worker","target_worker", "overwrite_max_orders_limit"}))
        team_obj = team_service.get_by_code(db_session=db_session, code=order_in.team.code)
        org_id = self.org_id
        # org_code = self.org_code
        new_order.team = team_obj
        log.info(f"create_virtual_order  {new_order} ")
        job_list = []
        for job in order_in.job_list:
            check_geo_flag = check_geo_range(
                geo_longitude = job.geo_longitude,
                geo_latitude = job.geo_latitude,
                team = team_obj
            )
            if not check_geo_flag:
                log.warning(
                    f"Job(code={job.code}) geo_longitude: {job.geo_longitude} or result_geo_latitude: {job.geo_latitude} outside the maximum or minimum range")
                raise HTTPException(
                    status_code=400, detail=f"Job(code={job.code}) geo_longitude-{job.geo_longitude} or result_geo_latitude-{job.geo_latitude} outside the maximum or minimum range")

            job_dict = {
                "code": job.code,
                "job_type": job.job_type,
                "org_id": org_id,
                # "org_code": org_code,
                "name": job.name,
                "planning_status": job.planning_status,
                "description": job.description,
                "team": order_in.team.dict(),
                "location": job.location.dict() if job.location else None,
                "geo_longitude": job.geo_longitude,
                "geo_latitude": job.geo_latitude,
                "flex_form_data": job.flex_form_data,
                "requested_primary_worker": None,
                "requested_start_datetime": job.requested_start_datetime,
                "requested_duration_minutes": job.requested_duration_minutes,
                "scheduled_primary_worker": 
                    {"code": job.scheduled_primary_worker.code}
                    if job.scheduled_primary_worker
                    else None,
                "scheduled_start_datetime": job.scheduled_start_datetime,
                "scheduled_duration_minutes": job.scheduled_duration_minutes,
                "auto_planning": job.auto_planning,
                "requested_skills": job.requested_skills,
                "requested_items": job.requested_items,
                "life_cycle_status": None,

                "order_code": new_order.code,
                "tolerance_start_minutes": job.tolerance_start_minutes,
                "tolerance_end_minutes": job.tolerance_end_minutes, 
            }
            
            # from dispatch.job.models import Job
            job_obj = job_service.create(db_session=db_session, **job_dict,create_virtual_order_predict=True)

            
            log.info(f"create_virtual_order = {job_dict} , result = {job_obj}")
            if job_obj is None:
                log.error(f"Failed to create job {job.code} for order {order_in.code}")
            else:
                job_list.append(job_obj)
                
        order_action = self.gen_action_from_order(
            new_order, 
            job_list = job_list, 
            worker_blacklist = [],
            worker_whitelist = [],
            overwrite_max_orders_limit = False,
        )
        
        return order_action

    def gen_action_from_order(
            self, order: Order, job_list = [], worker_blacklist = [],
            worker_whitelist = [],
            overwrite_max_orders_limit: bool = False,
        ) -> EnvAction:
        if order is None:
            raise ValueError("error gen_action_from_order, ")

        ord_dict = row2dict(order)
        # try:
        todo_job_action = EnvAction(
            order=OrderRead.parse_obj(ord_dict),
            jobs = job_list, # [ self.env_encode_single_job_db(j) for j in job_list],
            action_type = ActionType.TODO,
            worker_blacklist = worker_blacklist,
            worker_whitelist = worker_whitelist,
            overwrite_max_orders_limit = overwrite_max_orders_limit,
        )
        return todo_job_action

    def gen_action_4_existing_job(
            self, db_session, job_code,
        ) -> EnvAction:

        db_job = job_service.get_by_code(db_session=db_session, code=job_code)
        if db_job is None:
            raise ValueError("error gen_action_4_existing_job, job not found")
        if db_job.order is None:
            todo_job_action = EnvAction(
                order=None,
                jobs = [db_job], # [ self.env_encode_single_job_db(j) for j in job_list],
                action_type = ActionType.TODO,
            )
        else:

            todo_job_action = EnvAction(
                order= db_job.order,
                # TO make sure that -p is before -d
                jobs = sorted(db_job.order.job_order_rel, key = lambda x: x.code, reverse=True), #  
                action_type = ActionType.TODO,
            )

        return todo_job_action
                     
        # except Exception as e:
        #     log.error(str(e))

    def gen_action_dict_from_job(self, job: Job, is_forced_action: bool = False) -> ActionDict:
        if job is None:
            raise ValueError("error gen_action_dict_from_worker_absence")

        the_action_type = ActionType.FLOATING
        if job.planning_status in (JobPlanningStatus.FINISHED, JobPlanningStatus.PLANNED):
            the_action_type = ActionType.JOB_FIXED
        elif job.planning_status == JobPlanningStatus.IN_PLANNING:
            if job.job_type == JobType.JOB:
                if "AppointmentRequired" in job.flex_form_data.keys():
                    if job.flex_form_data["AppointmentRequired"] == 1:
                        the_action_type = ActionType.JOB_FIXED
                if job.is_appointment_confirmed:
                    the_action_type = ActionType.JOB_FIXED
                # Fix time in the day is treated same as FS, since I am anyway only moving within day.
                if job.job_schedule_type in (
                    JobScheduleType.FIXED_SCHEDULE,
                    JobScheduleType.FIXED_TIME,
                ):
                    the_action_type = ActionType.JOB_FIXED

        elif job.planning_status == JobPlanningStatus.UNPLANNED:
            the_action_type = ActionType.UNPLAN
        else:
            log.error(f"Unknown job planning_status={job.planning_status} in job ({job.job_code})")

        a_dict = ActionDict(
            is_forced_action=is_forced_action,
            job_code=job.job_code,
            action_type=the_action_type,
            # JobType = ABSENCE. JobType is skipped since it can be acquired from self.jobs_dict[job_code]
            scheduled_worker_codes=job.scheduled_worker_codes,
            scheduled_start_minutes=job.scheduled_start_minutes,
            scheduled_duration_minutes=job.scheduled_duration_minutes,
        )
        return a_dict

    # def gen_action_dict_from_worker_absence(self, absence: Absence) -> ActionDict:

    #     if absence is None:
    #         raise ValueError("error gen_action_dict_from_worker_absence")

    #     a_dict = ActionDict(
    #         is_forced_action=True,
    #         job_code=absence.job_code,
    #         action_type=ActionType.JOB_FIXED,
    #         scheduled_worker_codes=absence.scheduled_worker_codes,
    #         scheduled_start_minutes=absence.scheduled_start_minutes,
    #         scheduled_duration_minutes=absence.scheduled_duration_minutes,
    #     )
    #     return a_dict

    # def gen_action_dict_from_appointment(self, job):

    #     if job is None:
    #         raise ValueError("error gen_action_dict_from_appoint ")

    #     return self.gen_action_dict_from_job(job=job, is_forced_action=True)

    def intersect_geo_time_slots(
        self, time_slots, job, duration_minutes=None, max_number_of_matching=99
    ):
        """Find intersect_time_slots. If duration_minutes first job_gps = geo_longlat
        2020-09-22 10:18:58: I created this only because interval tree has no such a query like length_greater_than , https://github.com/chaimleib/intervaltree

        Parameters
        ----------
        time_slots : list(float)
            Input array of worker+day array. The rest of values in action_dict are discarded and re-calculated.

        duration_minutes : int
            If not None and > 0, it returns maximum one time period which is longer than first_minimum_length_match

        Returns
        -------
        time_slot_list: list
            A list of time period. ~The start time already excluded the initial travel time.

        """

        # i and j pointers for arr1
        # and arr2 respectively
        MININUM_TIME_POINT = -1

        list_lengths = [len(x) for x in time_slots]
        nbr_of_all_time_slots = sum(list_lengths)
        time_slot_indices = [0 for _ in range(len(time_slots))]
        result_list = []

        # n = len(arr1)
        # m = len(arr2)

        # Loop through all intervals until one of the interval lists is exhausted
        #
        while sum(time_slot_indices) < nbr_of_all_time_slots:
            # current_time_slots = []
            # I will first find FREE for each list.
            for idx, tp in enumerate(time_slots):
                while time_slot_indices[idx] < list_lengths[idx]:
                    if time_slots[idx][time_slot_indices[idx]].slot_type == TimeSlotType.FLOATING:
                        break
                    else:
                        time_slot_indices[idx] += 1
                # This is the end of this worker's slots
                if time_slot_indices[idx] >= list_lengths[idx]:
                    return result_list

            current_time_slots = [
                time_slots[idx][time_slot_indices[idx]] for idx in range(len(time_slots))
            ]

            # Left bound for intersecting segment
            left_points = []
            right_points = []
            for x in current_time_slots:
                (
                    prev_travel_minutes,
                    next_travel_minutes,
                    inside_travel_minutes,
                ) = self.get_travel_time_jobs_in_slot(
                    x,
                    [job.job_code],
                )
                # Above, it considers only job as candidate, and does not consider other existing inplanning jobs.
                if x.end_minutes - x.start_minutes > prev_travel_minutes + next_travel_minutes:
                    left_points.append(x.start_minutes)  # + prev_travel_minutes
                    right_points.append(x.end_minutes)  # - next_travel_minutes
                else:
                    left_points.append(1)  # + prev_travel_minutes
                    right_points.append(-1)  # - next_travel_minutes

            left_point_max = max(left_points)
            # Right bound for intersecting segment
            right_point_min = min(right_points)

            # If the segment is valid
            if right_point_min - left_point_max >= duration_minutes:
                # [self.slot_server.get_time_slot_key(s) for s in current_time_slots],
                result_list.append([left_point_max, right_point_min, current_time_slots])
                if len(result_list) >= max_number_of_matching:
                    return result_list
            # If i-th interval's right bound is
            # smaller increment i else increment j
            found_index_to_step = False
            for _ in range(len(list_lengths)):
                right_min_index = np.argmin([x.end_minutes for x in current_time_slots])
                if time_slot_indices[right_min_index] < list_lengths[right_min_index] - 1:
                    time_slot_indices[right_min_index] += 1
                    right_points[right_min_index] = MININUM_TIME_POINT
                    found_index_to_step = True
                    break
            if not found_index_to_step:
                break
        return result_list

    def get_worker_route_by_id(self, driverId, to_addr_dict):

        # {"driverId":959129,"to":{"lat":25.704966857563054,"lon":114.68631084629511}}

        payload = {"driverId": driverId, "from": {}, "to": to_addr_dict}
        call_back_url = f"{UU_API_URL}/driver/route/{UU_API_TOKEN}"
        param = str(json.dumps(payload))
        res = requests.post(
            url=call_back_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
                "content-type": "application/json",
            },
            data=param,
        )
        res.content.decode("utf-8")
        if res.status_code != 200:
            raise Exception(f"{res.status_code}-{res.reason}")

        return res

    # section for Redis keys
    #
    #################################
    def get_team_env_key(self) -> str:
        return  "{}_{}".format(
            self.org_id, self.team_id)

    def get_env_slot_set_key(self) -> str:
        return "{{{}}}:e:ws".format(self.team_env_key)
    def get_env_slot_code(self, worker_code, start_minutes) -> str:
        return f"{worker_code}:{int(start_minutes)*60}"


    def get_env_kmedoid_key(self) -> str:
        return "{{{}}}:e:kmedoid".format(self.team_env_key)

    def get_env_config_key(self) -> str:
        return "{{{}}}:e:cfg".format(self.team_env_key)

    def get_env_job_counter_key(self) -> str:
        return "{{{}}}:e:j_cnt".format(self.team_env_key)

    def get_env_planning_day_key(self) -> str:
        return "{{{}}}:e:plan_days".format(self.team_env_key)

    def get_env_job_rule_set_key(self) -> str:
        return "{{{}}}:e:rules_job".format(self.team_env_key)

    def get_env_travel_router_config_key(self) -> str:
        return "{{{}}}:e:travel_router".format(self.team_env_key)

    def get_env_real_time_agent_config_key(self) -> str:
        return "{{{}}}:e:real_time_agent".format(self.team_env_key)

    def get_env_batch_optimizer_config_key(self) -> str:
        return "{{{}}}:e:batch_optimizer".format(self.team_env_key)

    def get_env_lock_key(self) -> str:
        return "{{{}}}:lck".format(self.team_env_key)

    def get_env_worker_lock_key(self, worker_code: str) -> str:
        return "{{{}}}:lck:wkr:{}".format(self.team_env_key, worker_code)

    def get_env_slot_lock_key(self, slot_code: str) -> str:
        return "{{{}}}:lck:slot:{}".format(self.team_env_key, slot_code)

    # def get_env_slot_accum_items_key(self, slot_code: str) -> str:
    #     return "{{{}}}:e:loaded:{}".format(self.team_env_key, slot_code)
    # def get_env_slot_free_items_key(self, slot_code: str) -> str:
    #     return "{{{}}}:e:free:{}".format(self.team_env_key, slot_code)


    def get_recommened_locked_slots_by_job_code_key(self, job_code: str) -> str:
        return "{{{}}}:lck:job:{}".format(self.team_env_key, job_code)
    def get_env_job_failed_list_key(self, job_code: str) -> str:
        return "{{{}}}:e:failed_slots:{}".format(self.team_env_key, job_code)

    def get_env_job_info_key(self, job_code: str) -> str:
        return "{{{}}}:e:job_info:{}".format(self.team_env_key, job_code)

    def save_job_failed_slot(self, job_code: str, worker_code: str,) -> str:
        self.redis_conn.sadd(self.get_env_job_failed_list_key(job_code), worker_code)
        self.redis_conn.expire(self.get_env_job_failed_list_key(job_code), 1800)
        # return "{{{}}}:e:failed_slots:{}".format(self.team_env_key, job_code)

    def get_job_failed_slot(self, job_code: str,) -> list:
        slot_list = self.redis_conn.smembers(self.get_env_job_failed_list_key(job_code))
        return [s.decode("utf-8") for s in slot_list]


    # def get_key_commited_slot_lock(team_env_key, slot_code: str) -> str:
    #     return "{}/env_lock/after_commit_slot/{}".format(team_env_key, slot_code)

    def get_recommened_locked_slot_key(self, slot_code: str) -> str:
        return "{{{}}}:e:lck:slt:{}".format(self.team_env_key, slot_code)


    # This is a key to map job_code to its sorted set of all recommendations (RecommendedAction)
    # def get_recommendation_job_key(self, job_code: str, action_day: int) -> str:
    #     if action_day < 0:
    #         return "{}:rec:{}".format(self.team_env_key, job_code)
    #     else:
    #         return "{}:rec:{}:{}".format(self.team_env_key, job_code, action_day)
    # def get_redis_key_job_queue_name_realtime(self,) -> str:
    #     return "{{{}}}:{}:task".format(self.team_env_key, REDIS_JOB_QUEUE_REALTIME)
    def get_redis_key_result_name_realtime(self,job_code) -> str:
        return "{}:result:{{{}}}:{}".format(
            REDIS_JOB_QUEUE_REALTIME, self.team_env_key, job_code)
    def get_redis_key_result_notify_realtime(self,job_code) -> str:
        return "{}:notify:{{{}}}:{}".format(
            REDIS_JOB_QUEUE_REALTIME, self.team_env_key, job_code)

    def get_redis_key_result_name_optimizer(self,job_code) -> str:
        return "{}:result:{{{}}}:{}".format(
            REDIS_JOB_QUEUE_OPTIMIZER, self.team_env_key, job_code)


    def get_redis_key_area_code(self,) -> str:
        return "{{{}}}:e:area".format(self.team_env_key)
    def get_or_set_area_code2id(self, area_code) -> int:
        try:
            new_id = int(area_code)
            return new_id
        except ValueError as ve:
            # return self.get_or_set_area_code2id(area_code)
            res = self.redis_conn.hget(self.get_redis_key_area_code(), area_code)
            if res is None:
                next_area_id = self.redis_conn.hincrby(self.get_env_config_key(), "area_id_seq",)
                self.redis_conn.hset(self.get_redis_key_area_code(), mapping={area_code: next_area_id})
                return next_area_id
            else:
                return int(res)

    def get_area_id2code(self, area_id) -> str:
        area_id = str(area_id)
        if area_id in self.area_id2code_dict:
            return self.area_id2code_dict[area_id]
        else:
            res = self.redis_conn.hgetall(self.get_redis_key_area_code())
            self.area_id2code_dict = {v.decode():k.decode() for k,v in res.items()}
            if area_id in self.area_id2code_dict:
                return self.area_id2code_dict[area_id]

        return "default" 



    # This is a key to map a slot to all recommendations (RecommendedAction) which are using this slot
    # def get_slot_2_recommendation_job_key(self, slot_code: str) -> str:
    #     return "{}:rec_slot:{}".format(self.team_env_key, slot_code)

    # This is a key to store latest offset on kafka ENV_WINDOW, which is already replayed.
    # This is different from database team.latest_env_kafka_offset since that's indicating latest offset in PG/Mysql DB.


    # def get_env_window_replay_till_offset_key(self) -> str:
    #     return "{{{}}}:e:offset_replay".format(self.team_env_key)

    # def get_env_out_kafka_offset_key(self) -> str:
    #     return "{{{}}}:e:offset_out".format(self.team_env_key)

    # def get_env_window_replay_till_offset(self) -> int:
    #     return int(self.redis_conn.get(self.get_env_window_replay_till_offset_key()))

    # def set_env_window_replay_till_offset(self, offset: int):
    #     return self.redis_conn.set(self.get_env_window_replay_till_offset_key(), offset)

    # def get_env_inst_counter_redis_key(self) -> int:
    #     return "1_env_counter/{}".format(self.team_env_key)

    # def get_env_config_redis_key(self) -> int:
    #     return env_redis_key.get_env_config_key(self.team_env_key)


    # def get_env_worker_lock_redis_key(self, worker_code: str) -> str:
    #     return env_redis_key.(self.team_env_key, worker_code)

    # def get_recommened_locked_slots_by_job_code_redis_key(self, job_code: str) -> str:
    #     return env_redis_key.(self.team_env_key, job_code)

    # def get_recommened_locked_slot_redis_key(self, slot_code: str) -> str:
    #     return env_redis_key.(self.team_env_key, slot_code)




    def get_time_slot_key(team_env_key, worker_code, start_minutes, end_minutes, slot_type=None) -> str:
        start_minutes_str = str(int(start_minutes)).zfill(5)
        end_minutes_str = str(int(end_minutes)).zfill(5)
        return f"{{{team_env_key}}}:s:{worker_code}:{start_minutes_str }_{ end_minutes_str}" # _{slot_type}

    def encode_working_slot_2_str(self, slot: WorkingTimeSlot):
        info_str = self.encode_working_slot_info(
            slot_type=slot.slot_type,
            available_free_minutes=slot.available_free_minutes,
            job_change_count = slot.job_change_count,
            area_code= slot.area_code,
            start_loc=[slot.start_longitude,slot.start_latitude,],
            end_loc=[slot.end_longitude,slot.end_latitude,],
            kmedoid=[],
        )
        jobs_str = self.encode_working_slot_assigned_jobs(jobs=slot.assigned_jobs)
        s_str = f"{slot.slot_code}::{slot.start_minutes}::{slot.end_minutes}::{info_str}::{jobs_str}"
        return s_str

    def encode_working_slot_info(
            self, slot:WorkingTimeSlot
        ) -> str:
        info_str = f"enable_radius{SEPERATOR_TOP_1}{slot.enable_radius}{SEPERATOR_TOP_0}meter_radius{SEPERATOR_TOP_1}{slot.meter_radius}"
        rust_accum_items = copy.deepcopy(slot.accum_items)
        rust_accum_items.update(
            {
                "_weight_":int(slot.capacity_weight),
                "_volume_":int(slot.capacity_volume),
                "_nbr_order_": int(slot.max_nbr_order), 
            }
        )
        if len(slot.skills) > 0:
            info_str = info_str + "{}skills{}{}".format(
                SEPERATOR_TOP_0, SEPERATOR_TOP_1, SEPERATOR_FLEX_0.join(slot.skills)
            )

        if len(slot.accum_items) > 0:
            info_str = info_str + "{}accum_items{}{}".format(
                SEPERATOR_TOP_0, SEPERATOR_TOP_1,
                str(SEPERATOR_FLEX_0).join([f"{k}{SEPERATOR_FLEX_1}{v}" for (k,v) in rust_accum_items.items()])
            )
        kmedoid = self._calc_kmedoids(slot)
        if len(kmedoid) > 0:
            kmedoid_str = str(SEPERATOR_TOP_1).join([str(k) for k in kmedoid])
            info_str = info_str + f"{SEPERATOR_TOP_0}kmedoids{SEPERATOR_TOP_1}{kmedoid_str}"

        return info_str


    def encode_working_slot_detail(
            self, slot:WorkingTimeSlot
        ) -> str:
        end_minutes = slot.end_minutes 
        slot_type=0 if slot.slot_type == "F" else 1 
        area_id=self.get_or_set_area_code2id(slot.area_code) 

        detail_str = str(SEPERATOR_TOP_0).join([
            str(int(end_minutes) * 60),
            str(slot_type),
            str(area_id),
            str(round(slot.start_longitude,LONG_LAT_PRECISION)),
            str(round(slot.start_latitude,LONG_LAT_PRECISION)),
            str(round(slot.end_longitude,LONG_LAT_PRECISION)),
            str(round(slot.end_latitude,LONG_LAT_PRECISION)),
        ])

        return detail_str 



    def encode_working_slot_assigned_jobs(self, jobs=[]) -> str:
        job_str_list = []
        for job in  jobs: 
            if job.planning_status == "P":
                p_status = "1"
            else:
                p_status = "0"
            ord_code, job_seq = encode_job_code2rustenv(job.code)
            flex_form_info_str = encode_job_flex_form2rustenv(job.flex_form_data)
            job_str = str(SEPERATOR_TOP_1).join([
                ord_code, 
                str(job_seq),
                str(round(job.geo_longitude,LONG_LAT_PRECISION)),
                str(round(job.geo_latitude,LONG_LAT_PRECISION)),
                p_status, # 4 - planning_status
                str(int(job.scheduled_start_minutes)*60),
                str(int(job.scheduled_duration_minutes)*60),
                str(int(job.prev_travel)*60), 
                str(int(job.tolerance_end_minutes)*60),
                flex_form_info_str, # jobinslot.info
            ])
            job_str_list.append(job_str)
        return str(SEPERATOR_TOP_0).join(job_str_list)

    def decode_working_slot_assigned_jobs(self, jobs_bstring = b'') -> list:
        # jobs_bstring input example 'sgs$6-0|0|103.85013|1.317449|0|244140|0|240|315840|^sgs$5-0|0|103.84913|1.316449|0|244620|0|60|317520|'
        job_str_splitted = try_bytes_to_str(jobs_bstring).split(SEPERATOR_TOP_0)
        job_list = []
        for job_str in  job_str_splitted: 
            if len(job_str) < 3:
                continue
            job_attr = job_str.split(SEPERATOR_TOP_1)
            if len(job_attr[9]) > 0:
                ff_str_list = job_attr[9].split(SEPERATOR_TOP_2)
            else:
                ff_str_list = []
            flex = {}
            for ri in ff_str_list:
                ri_parts = ri.split(SEPERATOR_TOP_3)
                if len(ri_parts) != 2:
                    continue
                flex[ri_parts[0]] = ri_parts[1]
            if job_attr[1] == "1":
                job_code = f"{job_attr[0]}-p"
            elif job_attr[1] == "2":
                job_code = f"{job_attr[0]}-d"
            else:
                job_code = job_attr[0]
            if job_attr[4] == '1':
                p_status = 'P'
            else:
                p_status = 'I'

            job = JobInSlot(
                scheduled_start_minutes = float(job_attr[5]) / 60,
                code=job_code,
                geo_longitude = float(job_attr[2]),
                geo_latitude = float(job_attr[3]),
                prev_travel = float(job_attr[7]) / 60,
                scheduled_duration_minutes = float(job_attr[6]) / 60,
                tolerance_end_minutes = float(job_attr[8]) / 60,
                flex_form_data = flex,
                planning_status = p_status,
            )
            job_list.append(job)
        return job_list

    def decode_str_2_working_slot(self, slot_str: str) -> WorkingTimeSlot:
        s_s = try_bytes_to_str(slot_str)
        slot_code, start_minutes, end_minutes, info_str, jobs_str = s_s.split("::")
        _info = info_str.split("|")
        slot_summary = _info[0].split("_")
        start_loc_long = float(_info[1].split("_")[0])
        start_loc_lat = float(_info[1].split("_")[1])

        _jobs = self.decode_working_slot_assigned_jobs(jobs_str)
        _s = WorkingTimeSlot(
            slot_code = slot_code,
            slot_type = slot_summary[0],
            available_free_minutes = float(slot_summary[1]),
            job_change_count = int(slot_summary[2]),
            area_code = slot_summary[3],
            worker_code = slot_code.split("_")[0],
            start_minutes = start_minutes,
            end_minutes = end_minutes,
            start_longitude = start_loc_long,
            start_latitude = start_loc_lat,
            end_longitude = float(_info[2].split("_")[0]),
            end_latitude = float(_info[2].split("_")[1]),
            assigned_jobs = _jobs,
        )

        return _s



    # including decode_working_slot_info
    def delete_working_slot_not_in_list(self, workers_dict):
        # system_minutes = self.get_env_planning_horizon_start_minutes()
        system_minutes = self.get_env_planning_horizon_start_minutes()
        env_slot_set_key = self.get_env_slot_set_key()
        commands = ["s.get", env_slot_set_key]
        res = self.redis_conn.execute_command(*commands)
        wts = []
        for slot in res:
            purge_flag = False

            worker_code = slot[0].decode("utf-8")
            if worker_code not in workers_dict:
                purge_flag = True

            if purge_flag:
                self.delete_single_working_time_slot(slot[0].decode("utf-8"), int(slot[1].decode("utf-8")))
                

    def delete_working_slot_4_worker(self, 
            worker_code, purge_stale_slots = False
            ):
        # system_minutes = self.get_env_planning_horizon_start_minutes()
        system_minutes = self.get_env_planning_horizon_start_minutes()
        env_slot_set_key = self.get_env_slot_set_key()
        commands = ["s.get", env_slot_set_key]
        res = self.redis_conn.execute_command(*commands)
        wts = []
        for slot in res:
            slot_worker_code = slot[1].decode("utf-8")
            if slot_worker_code != worker_code:
                continue

            self.delete_single_working_time_slot(slot[0].decode("utf-8"), slot[1].decode("utf-8"))
                

    def parse_slot_result(self,res:list):
        wts = []
        dist = []
        for slot in res:
            start_seconds = int(slot[1])
            start_minutes = start_seconds / 60
            detail_vec = slot[2].split(SEPERATOR_FLEX_0)
            end_minutes = float(detail_vec[0]) / 60

            area_code = self.get_area_id2code(area_id=detail_vec[2])

            _jobs = self.decode_working_slot_assigned_jobs(slot[3])

            _s = WorkingTimeSlot(
                    slot_code = str(SEPERATOR_FLEX_1).join([slot[0], str(start_seconds)]),
                    slot_type = "F" if detail_vec[1] == "0" else "J",
                    available_free_minutes = 0,
                    job_change_count = 0,
                    area_code = area_code, 
                    worker_code = slot[0],
                    start_minutes = start_minutes,
                    end_minutes = end_minutes,
                    start_longitude = float(detail_vec[3]),
                    start_latitude = float(detail_vec[4]),
                    end_longitude = float(detail_vec[5]),
                    end_latitude = float(detail_vec[6]),
                    assigned_jobs = _jobs,
                    # Decoded and filled later on
                    # accum_items = _accum_items,
                    # skills = _skills,    
                )
            # Now I decode working_slot_info for example: 
            # enable_radius|0^meter_radius|0^accum_items|_nbr_order_:9999;_weight_:999999;_volume_:999999;
            # _skills = []
            # _accum_items = {}
            if len(slot[4]) > 0:
                info_vec = slot[4].split(SEPERATOR_TOP_0)
                for info_str in info_vec:
                    info_pair = info_str.split(SEPERATOR_TOP_1)
                    if info_pair[0] == "skills":
                        _s.skills = info_pair[1].split(SEPERATOR_FLEX_0)
                    elif info_pair[0] == "accum_items":
                        # for _accum_item_str in info_pair[1].split(SEPERATOR_FLEX_0):
                        #     if len(_accum_item_str) > 2:
                        #         _accum_item_pair = _accum_item_str.split(SEPERATOR_FLEX_1)
                        #         _accum_items[_accum_item_pair[0]] = _accum_item_pair[1]
                        _s.accum_items = parse_item_from_str(info_pair[1], SEPERATOR_FLEX_0, SEPERATOR_FLEX_1)
                        _s.capacity_volume =  _s.accum_items.get("_volume_", 9999)
                        _s.capacity_weight =  _s.accum_items.get("_weight_", 9999)
                        _s.max_nbr_order =  _s.accum_items.get("_nbr_order_", 9999)

                    elif info_pair[0] == "enable_radius":             
                        _s.enable_radius = int(info_pair[1])
                    elif info_pair[0] == "meter_radius":             
                        _s.meter_radius = int(info_pair[1])


            if len(slot) == 6:
                dist.append(float(slot[5]))
            # if self.always_load_slot_pos or (start_minutes < system_minutes and end_minutes > system_minutes) :
            #     _s = self.get_slot_start_location(_s)

            wts.append(_s)
        return wts, dist
    
    def get_working_slot_list(self, 
            worker_code = None, slot_key = None,
            start_minutes = None, end_minutes = None,
            active_only = True
            ) -> List[WorkingTimeSlot]:
        # system_minutes = self.get_env_planning_horizon_start_minutes()
        env_slot_set_key = self.get_env_slot_set_key()
        if slot_key:
            commands = ["s.get", env_slot_set_key, slot_key]
        else:
            if worker_code:
                if start_minutes is None or end_minutes is None:
                    commands = ["s.wget", env_slot_set_key, worker_code]
                else:
                    commands = ["s.wget", env_slot_set_key, worker_code, start_minutes, end_minutes]
            else:
                commands = ["s.get", env_slot_set_key]
        try:
            res = self.redis_conn.execute_command(*commands)
        except redis.exceptions.ResponseError as e:
            if str(e)[-10:] == 'not exist!' and slot_key:
                log.error(f"I_should_purge_kmedoids for {slot_key} because the slot does not exist. Error = {str(e)}")
                # self.delete_single_working_time_slot(slot_key=slot_key)
                # self.clear_medoid_keys_for_slot(slot_key=slot_key)
                return []
            else:
                raise e
        res_encoded = [[s.decode("utf8") for s in ss] for ss in res]
        system_minutes = self.get_env_planning_horizon_start_minutes()
        wts = []
        rr, dist = self.parse_slot_result(res_encoded)
        for slot in rr:
            if active_only:
                if slot.end_minutes < system_minutes or slot.start_minutes > system_minutes:
                    continue
            wts.append(slot)
        return wts

    def delete_single_working_time_slot(
        self, worker, start_seconds,delete_kmedoid=True #worker_code, start_minutes
    ) -> bool: 
        commands = ["s.del", 
            self.get_env_slot_set_key(), worker, str(start_seconds)
        ]
        try:
            res = self.redis_conn.execute_command(*commands)
        except Exception as e:
            print(f"error in slot delete commond:  {commands=}")

        log.info(
                f"delete_single_working_time_slot: ({self.get_env_slot_set_key()}) -> ({(worker, start_seconds)}) is deleted succesfully!"
            )
        return True

    def get_config_max_nbr_jobs_allowed(self):
        return min(
                int(self.config["nbr_jobs_per_slot"]),
                int(self.config["max_job_in_worker_size"])
            )
    def clear_stale_kmedoid_keys( self,  ):
        env_kmedoid_key = self.get_env_kmedoid_key()
        all_medoid_keys = self.redis_conn.geosearch(
            env_kmedoid_key, 
            longitude = 55, 
            latitude = 21, 
            unit = "m",
            radius = 1000_000, 
            sort="asc",
            count = 10_000,
            # withdist = True
        )
        # log.info(f"clear_stale_kmedoid_keys:geosearch: all_medoid_keys = {all_medoid_keys}")
        # log.info(f"clear_stale_kmedoid_keys:geosearch: len all_medoid_keys = {len(all_medoid_keys)}, first 10 {all_medoid_keys[0:10]}")

        invalid_slot_set = set()
        visited_slot_dict = dict()
        # visited_slot_log_list = []
        # system_minutes = self.get_env_planning_horizon_start_minutes()

        valid_keys = []
        dangling_keys = []

        for kmedoid_key in all_medoid_keys:
            
            # try:
            slot_code = kmedoid_key.decode().split(":")[0]
            if slot_code in visited_slot_dict.keys():
                valid_keys.append(kmedoid_key)
                continue
            try:
                valid_slots = self.get_working_slot_list(
                    slot_key=slot_code, active_only=True
                )
                if len(valid_slots) > 0:
                    visited_slot_dict[slot_code] = valid_slots[0]
                    valid_keys.append(kmedoid_key)
                else:
                    invalid_slot_set.add(slot_code)
                    dangling_keys.append(kmedoid_key)
            except redis.exceptions.ResponseError as e:
                print(f"redis.exceptions.ResponseError, likely slot {slot_code} is no longer in redis?")
                invalid_slot_set.add(slot_code)
                dangling_keys.append(kmedoid_key)
                continue
        log.info(f"clear_stale_kmedoid_keys is done. len all_medoid_keys = {len(all_medoid_keys)}, first 10 {all_medoid_keys[0:10]}. valid_slots = {list(visited_slot_dict.keys())}; valid_keys = {valid_keys}; dangling_keys = {dangling_keys}")


    def fix_missing_kmedoid_start_pos(self,):

        system_minutes = self.get_env_planning_horizon_start_minutes()
        # print(
        #     self.env_decode_from_minutes_to_hhmm_str(system_minutes),
        #     "fix_missing_kmedoid_start_pos: Started scanning ... ",
        # ) 
        working_slot_list = []
        working_slot_list=self.get_working_slot_list(worker_code=None, active_only=True)
        # worker_seq = 0
        # worker_dict = {}
        # planned_jobs_list = []

        env_kmedoid_key = self.get_env_kmedoid_key()
        fix_commands = []
        untouched = []
        for slot in working_slot_list:
            try:
                commands = ["geopos", env_kmedoid_key, f"{slot.slot_code}-0"]
                res = self.redis_conn.execute_command(*commands)
                if res[0] is None:
                    self.redis_conn.geoadd(
                        name = env_kmedoid_key, 
                        values = (slot.start_longitude, slot.start_latitude, f"{slot.slot_code}-0")
                    )
                    fix_commands.append(f"GEOADD  {env_kmedoid_key}  55.4188194 25.1658382 {slot.slot_code}-0")
                else:
                    # log.info(f"slot {slot.slot_code} has start pos: {res}")
                    untouched.append(slot.slot_code)
                # slot.start_longitude = res[0][0]
                # slot.start_latitude = res[0][1]
            except Exception as e:
                log.info(f"error in fix_missing_kmedoid_start_pos on slot {slot.slot_code}, e: {str(e)}, command: GEOADD  {env_kmedoid_key}  55.4188194 25.1658382 {slot.slot_code}-0")
            
            # log.info(f"slot {slot.slot_code} has start pos: {res}")
        # for c in fix_commands:
        log.info(f"Done fixing missing position on slots. fixed = {fix_commands}, untouched = {untouched}")


    def _calc_kmedoids(self, slot) -> list:
        # All tests are performed in 
        # src/dispatch/contrib/k_medoids/k_mediods.py
        # We should not re-generate slot_key, if a slot is already formed.
        # slot_key = slot.slot_code # slot_key =  f"{slot.worker_code}_{slot.start_minutes}"
        
        # kmedoid = [  (slot.start_longitude, slot.start_latitude)] +  # slot start location and plus all jobs
        # kmedoid = [(j.geo_longitude, j.geo_latitude,) for j in slot.assigned_jobs][0:int(self.config["nbr_k_medoids"])-1]
        jobs = slot.assigned_jobs
        nbr_k_medoids = int(self.config["nbr_k_medoids"])
        if len(jobs) <= nbr_k_medoids:
            return []


        X = [(j.geo_longitude, j.geo_latitude,)
             for j in jobs
            ] # list(set( ))
        if len(X) <= nbr_k_medoids * 3:
            max_iter = 8
        else:
            max_iter = 32
        
        kmedoids = KMedoids(
            n_clusters=nbr_k_medoids,
            method = 'pam',
            init = 'k-medoids++',
            # random_state=0,
            max_iter=max_iter
        ).fit(X)
        idx_s = sorted(kmedoids.medoid_indices_.tolist())
        log.info(f"_calc_kmedoids: slot {slot.slot_code}: centers {idx_s}: center jobs {[jobs[j].code for j in idx_s]}, all jobs: {[j.code for j in jobs]}")
        # return kmedoids.cluster_centers_.tolist()
        # return kmedoids.cluster_centers_.tolist()
        return idx_s
                            
    def solve_jobs_tsp(
        self, assigned_jobs: List[JobInSlot], start_loc = None, start_minutes = None
    ) -> List[JobInSlot]:
        if len(assigned_jobs) < 1:
            return []
        if start_loc is None:
            start_loc = [assigned_jobs[0].geo_longitude, assigned_jobs[0].geo_latitude]
            start_minutes = assigned_jobs[0].scheduled_start_minutes

        new_job_locs = [start_loc] + [
            [jc.geo_longitude,jc.geo_latitude]
            for jc in assigned_jobs
        ]            
        new_seq, start_distance = self.travel_router.solve_tsp(loc_list = new_job_locs )
        if new_seq is None:
            return assigned_jobs
        new_assigned_jobs = []
        current_start= start_minutes
        for j_idx, ji in enumerate(new_seq):
            if j_idx < 1:
                continue
            curr_job = assigned_jobs[ji-1]
            current_start += start_distance[j_idx]
            curr_job.scheduled_start_minutes = current_start
            curr_job.tolerance_end_minutes = current_start + 120
            curr_job.prev_travel = start_distance[j_idx]
            new_assigned_jobs.append(curr_job)
        return new_assigned_jobs

    def add_single_working_time_slot(
        self, slot: WorkingTimeSlot, update_ops: str = ["all"]
    ) -> bool:
        # If the slot exists, it will be updated.
        #   ["all","detail","jobs","start_location"/"start","info", "accum_items"/ "accum" ]
        # worker_code, start_minutes: int, end_minutes: int, start_location, end_location, slot_type = "F", assigned_jobs=[]
        if slot is None:
            log.error("add_single_working_time_slot: slot is None"  )
            return False

        if slot.end_minutes - slot.start_minutes < 1:
            log.error(
                f"add_single_working_time_slot failed: end_minutes - start_minutes < 1 ({(slot.start_minutes, slot.end_minutes, )})"
            )
            return False
        
        slot.assigned_jobs = sorted(slot.assigned_jobs, key=lambda j:j.scheduled_start_minutes)
        env_key = self.get_env_slot_set_key()

        detail_str = self.encode_working_slot_detail(slot)
        info_str = self.encode_working_slot_info(slot)

        slot_jobs_str = self.encode_working_slot_assigned_jobs( 
            jobs=slot.assigned_jobs, 
        )
        commands = [
            "s.add",
            env_key, 
            slot.worker_code, str(int(slot.start_minutes)*60),  
            SEPERATOR_TOP_0.join(update_ops), # "all",
            detail_str, slot_jobs_str, info_str, 
        ]
        # try:
        res = self.redis_conn.execute_command(*commands)
        # except redis.exceptions.ResponseError as e:
        #     print(str(e))

        # 2024-02-15 15:07:10 Now they are inside the slot.
        # if len(slot.accum_items) > 0:
        #     _loaded = self.redis_conn.hset(
        #         self.get_env_slot_accum_items_key(slot.slot_code),
        #         mapping=slot.accum_items)
        # if calc_free_items:
        #     slot.free_items = copy.deepcopy(slot.accum_items)
        #     for j in slot.assigned_jobs:
        #         for k,v in j.requested_items.items():
        #             if k in slot.free_items:
        #                 slot.free_items[k] -= float(v)
        #             else:
        #                 log.error(f"This job {j.code} items are not satisfied.")

        # if len(slot.free_items) > 0:
        #     _loaded = self.redis_conn.hset(
        #         self.get_env_slot_free_items_key(slot.slot_code),
        #         mapping=slot.free_items)

        return True


    def sync_rust_env_config(
        self,new_rust_config = None, is_reset=False,
    ) -> bool:
        # 
        if new_rust_config is not None:
            save_from_config = new_rust_config
        else:
            save_from_config = copy.deepcopy(self.config)
            
        saving_rust_config = {}
        for rk in default_rust_env_config_data.keys():
            if rk in save_from_config:
                saving_rust_config[rk] = str(save_from_config[rk])

        if not is_reset:
            for k in ("data_start_seconds", "fixed_horizon_flag", ):
                if k in saving_rust_config:
                    log.warning(f"{k} can not be updated to rustenv")
                    saving_rust_config.pop(k)

        config_str = json.dumps(saving_rust_config)     
        commands = ["s.config", self.get_env_slot_set_key(), config_str]

        res = self.redis_conn.execute_command(*commands)
        log.info(
                f"sync_rust_env_config: ({self.get_env_slot_set_key()}) is synchronized succesfully with config: {config_str}!"
            )
        return True

    def sync_env_config(
        self, flex_form_data, is_reset = False
        ) -> bool:
        if not is_reset:
            for k in ("data_start_day", "data_start_seconds", "fixed_horizon_flag", "update_seq"):
                if k in flex_form_data:
                    # log.warning(f"{k} can not be updated to redis_env if not is_reset")
                    flex_form_data.pop(k)

        self.config.update(flex_form_data)
        self._parse_env_config()

        curr_config = copy.deepcopy(self.config)
        if not is_reset:
            for k in ("data_start_day", "data_start_seconds", "fixed_horizon_flag", "update_seq"):
                if k in curr_config:
                    # log.warning(f"{k} can not be updated to redis_env if not is_reset")
                    curr_config.pop(k)

        self.redis_conn.hset(self.get_env_config_key(), mapping=curr_config)
        _new_seq = self.redis_conn.hincrby(self.get_env_config_key(), "update_seq", amount = 1)
        # Do not increase the current env seq, then next time it will be purged and reloaded. 
        # 2024-02-17 15:09:12, it is possible that someone update env config but does not go though init process, like plugins.
        # self.config["update_seq"] = curr_seq

        self.sync_rust_env_config(new_rust_config = curr_config, is_reset = is_reset)
        # if "horizon_start_datetime" in flex_form_data:
        # This should be handled inside env loading process env.reload_horizon_start_minutes, which is triggered by curr_seq++
        log.info(f"_sync_env_config_: Env=({self.get_env_config_key()}) is boosted by config update, and now update_seq = {_new_seq}.")


    def sync_env_config_incr(
        self, new_config 
        ) -> bool: 
        for k in ("data_start_day", "data_start_seconds", "fixed_horizon_flag", "update_seq"):
            if k in new_config:
                # log.warning(f"{k} can not be updated to redis_env if not is_reset")
                new_config.pop(k)

        self.redis_conn.hset(self.get_env_config_key(), mapping=new_config)
        self.config.update(new_config)
        self.config["new_seq"] = self.redis_conn.hincrby(self.get_env_config_key(), "update_seq", amount = 1)
        log.info(f"_sync_env_config_incr_: Env=({self.get_env_config_key()}) is boosted by config update, new_config = {new_config}.")

    def update_slot_start_location(
        self, worker_code,
        longitude, latitude,
        ) -> bool:
        env_slot_set_key = self.get_env_slot_set_key()
        commands = [
            "s.uploc", env_slot_set_key, worker_code, 
            str(round(longitude, 6)),
            str(round(latitude, 6)),
        ]
        res = self.redis_conn.execute_command(*commands)

        log.info(
                f"update_slot_start_location: ({env_slot_set_key}) -> ({worker_code}) is updated with location {longitude} {latitude}."
            )
        return True

    # def get_time_slot_worker_key_scanner(team_env_key, worker_code,) -> str: 
    #     return f"{{{team_env_key}}}:s:{worker_code}:*"


    # def get_time_slot_jobs_key(slot_key,) -> str:
    #     key_list = slot_key.split(":s:")
    #     return f"{key_list[0]}:sj:{key_list[1]}"


    # def get_time_slot_job_key(self, job_code, longitude, latitude, duration, prev_travel) -> str:
    #     return "{}_{}_{}_{}_{}".format(
    #         job_code, 
    #         round(longitude, LONG_LAT_PRECISION), 
    #         round(latitude, LONG_LAT_PRECISION), 
    #         round(duration, 2),
    #         round(prev_travel, 2),
    #     )
    # def decode_time_slot_job_key(self, slot_key) -> str:
    #     key_splitted = slot_key.split("_")
    #     return {
    #         "job_code":key_splitted[0], 
    #         "longitude":float(key_splitted[1]), 
    #         "latitude":float(key_splitted[2]), 
    #         "duration":float(key_splitted[3]), 
    #         "prev_travel":float(key_splitted[4]), 
    #     }

    def convert_job2jobrequest(self,job,) -> Dict:
        return {
            "code": job.code,
            "longitude": job.geo_longitude,
            "latitude": job.geo_latitude,
            "flex_form": {
                "area_id":str(self.get_or_set_area_code2id(job.flex_form_data.get("area_code",DEFAULT_AREA_CODE))),
            },

        }
    def recall(self, todo_action:EnvAction,):
        job_list = [self.convert_job2jobrequest(j) for j in todo_action.jobs]
        recall_action = {
            "worker_blacklist":todo_action.worker_blacklist, 
            "worker_whitelist":todo_action.worker_whitelist, 
            "overwrite_limit": todo_action.overwrite_max_orders_limit,
            "job_list": job_list,
        }

        # log.info(f"config: {self.config}")
        # 开始记录第一步查询到的信息
        reason_info = {
            "recall_action": recall_action,
        }

        try:
            commands = ["s.recall", self.get_env_slot_set_key(), json.dumps(recall_action)]
            log.debug(f"s.recall.commands={commands}")
            res = self.redis_conn.execute_command(*commands)
            res_json = json.loads(res.decode("utf8"))
            reason_info["slot_trace"] = res_json["slot_trace"]
            nearby_slots, dist_list = self.parse_slot_result(res_json["slots"])
            log.info(f"recall:order:{json.dumps(recall_action)}:")

            all_slots = [[s.slot_code, s.start_longitude, s.start_latitude, len(s.assigned_jobs)] for s in nearby_slots]
            if len(nearby_slots) > 1:
                _hit_result = "no_direct_but_multiple_match"
            elif len(nearby_slots) == 1:
                _hit_result = "no_direct_but_only_one_match"
            else:
                _hit_result = "no_nearby_slot_match"
            reason_info["recall_result"] = {
                "result_type":_hit_result,"len": len(nearby_slots),
                "slots":all_slots,"dist_list": dist_list,
                }
            log.info(f"get_nearby_slots::{_hit_result}: len = {len(nearby_slots)}, slots = {all_slots}, dist_list = {dist_list}, order = {todo_action.order} ")
            return nearby_slots, dist_list , reason_info 

        except redis.exceptions.ResponseError as e:
            log.error(f"recall:order:redis_error:{str(e)}:{json.dumps(recall_action)}")
            reason_info["error"] = str(e)

            return [ ], [ ], reason_info



