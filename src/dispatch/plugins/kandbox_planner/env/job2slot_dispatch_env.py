"""
This is the parent class for env business logics. For rllib training purpose and serving, use sub-classes.

# This is a minimal working env file.
{"weekly_rest_day": "0", "holiday_days": "20210325", "env_start_day": "20210524", 
"respect_initial_travel": false, 
"horizon_start_minutes": 1900, "planning_working_days": 1, "travel_speed_km_hour": 19.8, "travel_min_minutes": 5, 
"scoring_factor_standard_travel_minutes": 90,
"inner_slot_planner": "nearest_neighbour",
"geo_longitude_max": 121.32,
"geo_longitude_min": 120.72,
 "geo_latitude_max": 14.852,
"geo_latitude_min": 14.252
}

14.552, 121.02
"""
import random
import json
from datetime import datetime, timedelta
import time
import copy
from typing import Dict, List
from itertools import combinations
import numpy as np
import pandas as pd
import redis
from redis.exceptions import LockError
import logging
import socket
from dispatch.config import PLANNER_SERVER_ROLE, MAX_MINUTES_PER_TECH
from dispatch.plugins.kandbox_planner.env.working_time_slot import (
    WorkingTimeSlotServer,
    MissingSlotException,
)
# from dispatch.plugins.base import plugins
# TODO, seems odd, 2021-11-29 18:56:57, duan,
# from dispatch.main import  app
# from dispatch.common.utils.cli import install_plugins, install_plugin_events
# install_plugins()


from dispatch.plugins.kandbox_planner.env.cache_only_slot_server import CacheOnlySlotServer
from dispatch.plugins.kandbox_planner.data_adapter.kplanner_db_adapter import KPlannerDBAdapter
from dispatch.plugins.kandbox_planner.data_adapter.kafka_adapter import KafkaAdapter
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util
import dispatch.config as kandbox_config
import dataclasses
from dispatch.plugins.kandbox_planner.env.env_models import (
    WorkingTimeSlot,
    LocationTuple,
    JobLocation,
    Worker,
    Job,
    BaseJob,
    Appointment,
    ActionDict,
    Absence,
    SingleJobCommitInternalOutput,
    ActionEvaluationScore,
    JobLocationBase,
    RecommendedAction,
    RecommendationCommitInternalOutput,
)
from dispatch.plugins.kandbox_planner.env.env_enums import *
from dispatch.plugins.kandbox_planner.env.env_enums import (
    EnvRunModeType,
    JobPlanningStatus,
)
from dispatch.service.planner_models import SingleJobDropCheckOutput
from dispatch.config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_PASSWORD,
    NBR_OF_OBSERVED_WORKERS,
    MINUTES_PER_DAY,
    MAX_NBR_OF_JOBS_PER_DAY_WORKER,
    SCORING_FACTOR_STANDARD_TRAVEL_MINUTES,
    DATA_START_DAY,
    MIN_START_MINUTES_FROM_NOW,
    UU_API_TOKEN,
    UU_API_URL,)
from scipy.stats import multivariate_normal
from dispatch.plugins.kandbox_planner.util.kandbox_util import (
    min_max_normalize,
    min_max_denormalize,
    parse_item_str
)
import requests

from dispatch.plugins.kandbox_planner.util.kandbox_date_util import extract_minutes_from_datetime
from dispatch.plugins.bases.kandbox_planner import (
    KandboxEnvPlugin,
    KandboxEnvProxyPlugin,
    KandboxPlannerPluginType,
)

from dispatch.plugins.kandbox_planner.planner_engine.jobs_in_slots_planner_shared_head_tail import (
    NaivePlannerJobsInSlots, )

from dispatch.plugins.kandbox_planner.planner_engine.optimizer_shared_jobs_in_slots import OptimizerJobsInSlots
from dispatch.plugins.kandbox_planner.planner_engine.jobs_in_slots_nearest_neighbour import NearestNeighbourPlannerJobsInSlots
from dispatch.team.service import get_or_add_redis_team_flex_data
from dispatch.plugins.kandbox_planner.planner_engine.jobs_in_slots_weighted_nearest_neighbour import WeightedNearestNeighbourPlannerJobsInSlots

from dispatch.plugins.kandbox_planner.planner_engine.jobs_in_slots_ortools_routing import OrtoolsRoutingPlannerJobsInSlots
inner_slot_planner_cls_dict = {
    # kandbox_inner_planner_ortools_routing
    "ortools_routing": OrtoolsRoutingPlannerJobsInSlots,
    "nearest_neighbour": NearestNeighbourPlannerJobsInSlots,
    "weighted_nearest_neighbour": WeightedNearestNeighbourPlannerJobsInSlots,
    "head_tail": NaivePlannerJobsInSlots,
    "opti": OptimizerJobsInSlots,
}


#

# from dispatch.plugins.kandbox_planner.env.recommendation_server import RecommendationServer


# from src.dispatch.contrib.uupaotui.processor.core import order_pool

# This version works on top of json input and produce json out
# Observation: each worker has multiple working_time=days, then divided by slots, each slot with start and end time,

# import holidays

hostname = socket.gethostname()

log = logging.getLogger("rllib_env_job2slot")
# log.setLevel(logging.ERROR)
# log.setLevel(logging.WARN)
# log.setLevel(logging.DEBUG)

# RULE_PLUGIN_DICT = {
#     "kandbox_rule_within_working_hour": KandboxRulePluginWithinWorkingHour,
#     "kandbox_rule_sufficient_travel_time": KandboxRulePluginSufficientTravelTime,
#     "kandbox_rule_requested_skills": KandboxRulePluginRequestedSkills,
#     "kandbox_rule_lunch_break": KandboxRulePluginLunchBreak,
#     #
# }


class Job2SlotDispatchEnv(KandboxEnvPlugin):
    """

    Action should be compatible with GYM, then it should be either categorical or numerical. ActionDict can be converted..

    """

    title = "Job2Slot dispatching basic"
    slug = "job2slot_dispatch_env"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "Env for GYM for RL."
    version = "0.1.0"

    def __del__(self):
        try:
            del self.kp_data_adapter
        except:
            log.warn("rl_env: Error when releasing kp_data_adapter.")

    def __init__(self, config=None):
        #
        # each worker and job is a internally saved as dataclass object. They are transformed from a dict in database, or kafka.
        #
        env_config = config
        kp_data_adapter = None
        # reset_cache = False
        # self.items_dict = {
        #     "paper tower": {"volume": 1, "weight": 0.1},
        #     "paper roll": {"volume": 1, "weight": 0.1},
        #     "Ultraprotect Spray": {"volume": 0.2, "weight": 1},
        #     "Foam Soap": {"volume": 0.2, "weight": 1},
        #     "Body and Hair Gel": {"volume": 0.2, "weight": 1},
        #     "Commercial Mat": {"volume": 0.2, "weight": 1},
        # }
        self.run_mode = EnvRunModeType.PREDICT

        self.workers_dict = {}  # Dictionary of all workers, indexed by worker_code
        self.workers = []  # List of Workers, pointing to same object in self.workers_dict
        self.jobs_dict = {}  # Dictionary of of all jobs, indexed by job_code
        self.jobs = []  # List of Jobs

        self.locations_dict = {}  # Dictionary of JobLocation, indexed by location_code
        self.changed_job_codes_set = set()

        self.unplanned_job_code_list = []
        self.job_generation_count = 0
        self.all_locations = []
        self.current_job_code = None

        self.current_job_i = 0
        self.total_assigned_job_duration = 0

        self.nbr_inplanning = 0
        self.expected_travel_time_so_far = 0
        self.total_travel_time = 0
        self.total_travel_worker_job_count = 0

        self.kafka_input_window_offset = 0
        self.kafka_slot_changes_offset = 0

        self.unplanned_job_codes = []

        # self.config["daily_overtime_minutes"] = []
        self.national_holidays = []  # TODO, change it to set() @duan
        self.weekly_working_days_flag = []
        # self.daily_weekday_sequence = []  # Replaced by self.env_encode_day_seq_to_weekday(day_seq)
        # 2020-11-09 04:41:16 Duan, changed from  [] to {}, since this will keep growing and should be purged regularly
        self.daily_working_flag = {}

        self.internal_obs_slot_list = []

        if REDIS_PASSWORD == "":
            self.redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=None)
        else:
            self.redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)

        self.config = {}

        if env_config is None:
            log.error("error, no env_config is provided!")
            raise ValueError("No env_config is provided!")

        # This team_env_key uniquely identify this Env by starting date and team key. Multiple instances on different servers share same key.
        self.team_env_key = "env_{}_{}".format(env_config["org_code"], env_config["team_id"])

        # env_inst_seq is numeric and unique inside the team_env_key, uniquely identify one instance on a shared Env
        self.env_inst_seq = self.redis_conn.incr(self.get_env_inst_counter_redis_key())

        # env_inst_code is a code for an env Instance, which **globally**, uniquely identify one instance on a shared Env
        self.env_inst_code = "{}_{}_{}".format(self.team_env_key, self.env_inst_seq, hostname)

        self.rule_set = []
        if "rules" in env_config.keys():
            self.rule_set = env_config["rules"]
            env_config.pop("rules", None)
        else:
            self.rule_set = []
            log.warn(f"env {self.env_inst_code} has zero rule plugins")
        #     rule_set = []
        #     for rule_slug_config in env_config["rules_slug_config_list"]:
        #         rule_plugin = RULE_PLUGIN_DICT[rule_slug_config[0]](config=rule_slug_config[1])
        #         rule_set.append(rule_plugin)
        #     self.rule_set = rule_set
        # self.rule_set_worker_check = [KandboxRulePluginRequestedSkills()]  # , evaluate_RetainTech
        self.rule_set_worker_check = []
        if "worker_check_rules" in env_config.keys():
            self.rule_set_worker_check = env_config["worker_check_rules"]
            env_config.pop("worker_check_rules", None)

        if "travel_router" in env_config:
            self.travel_router = env_config.get('travel_router')
            env_config.pop("travel_router", None)
        else:
            # raise ValueError("No travel_router is provided!")

            # 1.	Travel time formula is defined as GPS straight line distance *1.5/ (40 KM/Hour), minimum 10 minutes. Those numbers like 1.5, 40, 10 minutes,
            # self.config["travel_speed_km_hour"] = self.config["flex_form_data"]["travel_speed_km_hour"]
            # self.config["travel_min_minutes"] = self.config["flex_form_data"]["travel_min_minutes"]
            self.travel_max_minutes = self.config.get("travel_max_minutes", 180)  # 3 Hours
            from dispatch.plugins.kandbox_planner.travel_time_plugin import HaversineTravelTime
            self.travel_router = HaversineTravelTime(
                travel_speed=self.config.get("travel_speed_km_hour", 20),
                min_minutes=self.config.get("travel_min_minutes", 1),
                max_minutes=self.travel_max_minutes,
                travel_mode="driving",
            ) 
            log.error(f"Router not configured. Initiated default travel router: {self.travel_router.slug} for env: {self.env_inst_code}")

        self.config.update(env_config)
        if "data_end_day" in self.config.keys():
            log.error("data_end_day is not supported from config!")

        # TODO, 2021-06-14 07:47:06
        self.config["nbr_of_days_planning_window"] = int(self.config["nbr_of_days_planning_window"])
        # TODO 2021-08-14 11:32:10

        self.data_start_datetime = datetime.strptime(
            DATA_START_DAY, kandbox_config.KANDBOX_DATE_FORMAT)

        if kp_data_adapter is None:
            log.info("env is creating db_adapter by itslef, not injected.")
            kp_data_adapter = KPlannerDBAdapter(
                org_code=self.config["org_code"],
                team_id=self.config["team_id"])
        else:
            log.error("INTERNAL:kp_data_adapter is not None for env.__init__")



        self.kp_data_adapter = kp_data_adapter

        self._reset_horizon_start_minutes()
        self.parse_team_flex_form_config()

        SharingEfficiencyLogic = "1_1.0;2_1.66;3_2.15"

        self.efficiency_dict = {}
        for day_eff in SharingEfficiencyLogic.split(";"):
            self.efficiency_dict[int(day_eff.split("_")[0])] = float(day_eff.split("_")[1])

        self.reload_data_from_db_adapter(
            self.env_start_datetime,
            end_datetime=self.env_decode_from_minutes_to_datetime(
                self.get_env_planning_horizon_end_minutes())
        )
        self.depots_dict = self.kp_data_adapter.get_depots_dict()
        self.items_dict = self.kp_data_adapter.get_items_dict()

        self.kafka_input_window_offset = 0
        if PLANNER_SERVER_ROLE == "trainer":
            self.kafka_server = KafkaAdapter(
                env=None, role=KafkaRoleType.FAKE, team_env_key=self.team_env_key)

            self.slot_server = CacheOnlySlotServer(env=self, redis_conn=self.redis_conn)
        else:
            self.kafka_input_window_offset = (
                self.kp_data_adapter.get_team_env_window_latest_offset())
            self.config.update(self.kp_data_adapter.get_team_flex_form_data())
            self.config["nbr_of_days_planning_window"] = self.config["planning_working_days"]

            self.kafka_server = KafkaAdapter(env=self, role=KafkaRoleType.ENV_ADAPTER)

            self.slot_server = WorkingTimeSlotServer(env=self, redis_conn=self.redis_conn)

        # self.recommendation_server = RecommendationServer(env=self, redis_conn=self.redis_conn)

        # I don't know why, self.kp_data_adapter loses this workers_dict_by_id after next call.
        # 2021-05-06 21:34:01
        # self.workers_dict_by_id = copy.deepcopy(self.kp_data_adapter.workers_dict_by_id)
        # self.jobs_db_dict = copy.deepcopy(self.kp_data_adapter.jobs_db_dict)

        self._reset_data()

        self.replay_env()
        log.debug("replay_env is done")

        # Temp fix
        # TODO, the opti shuold be plugin as well.
        self.inner_slot_heur = inner_slot_planner_cls_dict[self.config["inner_slot_planner"]](
            env=self)
        self.inner_slot_opti = inner_slot_planner_cls_dict["opti"](env=self)
        self.env_bootup_datetime = datetime.now()

        log.info("__init__ done, reloaded data from db, env is ready to serve")

    @property
    def horizon_start_minutes(self):
        return self._horizon_start_minutes

    @horizon_start_minutes.setter
    def horizon_start_minutes(self, value):
        self._horizon_start_minutes = value
        # print('announcing _horizon_start_minutes change')

    def reload_data_from_db_adapter(self, start_datetime, end_datetime):
        if self.config.get("sample_history", False):
            self.kp_data_adapter.sample_history_data_from_db(
                start_datetime, end_datetime,
                job_generation_max_count=self.config.get("job_generation_max_count", 30),
                nbr_observed_slots=self.config.get("nbr_observed_slots", 7))
        else:
            self.kp_data_adapter.reload_data_from_db(start_datetime, end_datetime)

    def parse_team_flex_form_config(self):
        # TODO team.country_code
        # country_code = "CN"  team.country_code
        # self.national_holidays = holidays.UnitedStates()
        # self.national_holidays = holidays.CountryHoliday('US')
        self.national_holidays = []
        if self.config.get('holiday_days') is not None:
            if len(self.config["holiday_days"]) > 0:
                self.national_holidays = self.config["holiday_days"].split(";")

        __split = []
        if self.config.get('weekly_rest_day') is not None:
            if len(self.config["weekly_rest_day"]) > 0:
                __split = str(self.config["weekly_rest_day"]).split(";")

        self.weekly_working_days_flag = [True for _ in range(7)]
        for day_s in __split:
            self.weekly_working_days_flag[int(day_s)] = False

        new_working_days = self._get_new_working_days()
        self.config["nbr_of_days_planning_window"] = len(new_working_days)

    def dispatch_jobs_in_slots(self, working_time_slots=[]):
        # This func calls default inner slot planner.
        return self.inner_slot_heur.dispatch_jobs_in_slots(working_time_slots)

    def _reset_gym_appt_data(self):

        self.appts = list(self.kp_data_adapter.appointment_db_dict.keys())
        self.appt_scores = {}

        # Used for get_reward, only for gym training
        self.job_travel_time_sample_list_static = [(self._get_travel_time_2_job_indices(ji, (ji + 1) % len(self.jobs)) + self._get_travel_time_2_job_indices(ji, (ji + 2) % len(self.jobs)) +
                                                    self._get_travel_time_2_job_indices(ji, (ji + 3) % len(self.jobs))) / 3 for ji in range(0, len(self.jobs))]

        self.total_travel_time_static = sum(
            [self._get_travel_time_2_job_indices(ji, ji + 1) for ji in range(0, len(self.jobs) - 1)])

    def normalize(self, x, data_type: str):
        # 2021-07-27 11:00:55 Added ceilling on top > 1 --> 1.
        if data_type == "longitude":
            y = min_max_normalize(x, self.config["geo_longitude_min"],
                                  self.config["geo_longitude_max"])
        elif data_type == "latitude":
            y = min_max_normalize(x, self.config["geo_latitude_min"],
                                  self.config["geo_latitude_max"])
        elif data_type == "duration":
            y = min_max_normalize(x, 0, 300)
        elif data_type == "start_minutes":
            y = min_max_normalize(x, 0, 1440 * self.config["nbr_of_days_planning_window"])
        elif data_type == "day_minutes_1440":
            y = min_max_normalize(x, 0, 1440 * 1)
        elif data_type == "5_minutes":
            y = min_max_normalize(x, 0, 5)
        elif data_type == "15_minutes":
            y = min_max_normalize(x, 0, 15)
        elif data_type == "30_minutes":
            y = min_max_normalize(x, 0, 30)
        elif data_type == "180_minutes":
            y = min_max_normalize(x, 0, 180)
        elif data_type == "480_minutes":
            y = min_max_normalize(x, 0, 480)
        elif data_type == "max_nbr_shared_workers":
            y = min_max_normalize(x, 0, 4)
        elif data_type == "n_job_in_slot":
            y = min_max_normalize(x, 0, self.config["MAX_NBR_JOBS_IN_SLOT"])
        elif data_type == "clip":
            y = x
        else:
            # log.error(f"Unknow data_type = {data_type}")
            raise ValueError(f"Unknow data_type = {data_type}")
        if y > 1:
            log.debug(f"Warning: x={x} is bigger than higher bound of type = {data_type} ")
            y = 1
        if y < 0:
            log.debug(f"Warning: x={x} is smaller than lower bound of type = {data_type} ")
            y = 0

        return y

    def denormalize(self, x, data_type: str):
        if data_type == "duration":
            return min_max_denormalize(x, 0, 300)
        elif data_type == "start_minutes":
            return min_max_denormalize(x, 0, 1440 * self.config["nbr_of_days_planning_window"])
        elif data_type == "day_minutes_1440":
            return min_max_denormalize(x, 0, 1440 * 1)
        elif data_type == "longitude":
            return min_max_denormalize(
                x, self.config["geo_longitude_min"], self.config["geo_longitude_max"]
            )
        elif data_type == "latitude":
            return min_max_denormalize(
                x, self.config["geo_latitude_min"], self.config["geo_latitude_max"]
            )
        elif data_type == "max_nbr_shared_workers":
            return min_max_denormalize(x, 0, 4)
        elif data_type == "n_job_in_slot":
            return min_max_denormalize(x, 0, self.config["MAX_NBR_JOBS_IN_SLOT"])
        else:
            # log.error(f"Unknow data_type = {data_type}")
            raise ValueError(f"Unknow data_type = {data_type}")
            return x

    def _reset_data(self):
        """It should be used only inside reset ()
        Location (self.locations_dict) remain unchanged in this process.
        """
        self.workers = self.load_transformed_workers()
        self.workers_dict = {}  # Dictionary of dict
        self.permanent_pairs = set()
        #

        for ji, x in enumerate(self.workers):
            self.workers_dict[x.worker_code] = x
            x.worker_index = ji

        for ji, x in self.workers_dict.items():
            if x.belongs_to_pair is not None:
                is_valid_pair = True
                for paired_code in x.belongs_to_pair:
                    if paired_code not in self.workers_dict.keys():
                        log.error(
                            f"WORKER:{paired_code}:PAIR_TO:{x.belongs_to_pair}: the paired worker is not found.")
                        is_valid_pair = False
                if not is_valid_pair:
                    continue

                self.permanent_pairs.add(x.belongs_to_pair)
                for paired_code in x.belongs_to_pair:
                    self.workers_dict[paired_code].belongs_to_pair = x.belongs_to_pair

        # This function also alters self.locations_dict
        self.jobs = self.load_transformed_jobs()
        if len(self.jobs) < 1:
            log.debug("No Jobs on initialized Env.")

        # This encoding includes appointments for now
        # TODO, sperate appointment out? 2020-11-06 14:28:59
        self.jobs_dict = {}  # Dictionary of dict
        for ji, job in enumerate(self.jobs):
            if job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
                log.debug(f"_reset_data:   {job.job_code}")

            job.requested_duration_minutes = int(job.requested_duration_minutes)
            # This reset status and is for training.
            # job.planning_status = "U"

            self.jobs_dict[job.job_code] = job
            job.job_index = ji

        log.debug("env _reset_data finished")

    # This is a key to map job_code to its sorted set of all recommendations (RecommendedAction)
    def get_recommendation_job_key(self, job_code: str, action_day: int) -> str:
        if action_day < 0:
            return "{}/rec/{}".format(self.team_env_key, job_code)
        else:
            return "{}/rec/{}/{}".format(self.team_env_key, job_code, action_day)

    # This is a key to map a slot to all recommendations (RecommendedAction) which are using this slot
    def get_slot_2_recommendation_job_key(self, slot_code: str) -> str:
        return "{}/slot_rec/{}".format(self.team_env_key, slot_code)

    # This is a key to store latest offset on kafka ENV_WINDOW, which is already replayed.
    # This is different from database team.latest_env_kafka_offset since that's indicating latest offset in PG/Mysql DB.
    def get_env_window_replay_till_offset_key(self) -> str:
        return "{}/env/env_window_replay_till_offset".format(self.team_env_key)

    def get_env_out_kafka_offset_key(self) -> str:
        return "{}/env/env_out_till_offset".format(self.team_env_key)

    def get_env_window_replay_till_offset(self) -> int:
        return int(self.redis_conn.get(self.get_env_window_replay_till_offset_key()))

    def set_env_window_replay_till_offset(self, offset: int):
        return self.redis_conn.set(self.get_env_window_replay_till_offset_key(), offset)

    def get_env_inst_counter_redis_key(self) -> int:
        return "1_env_counter/{}".format(self.team_env_key)

    def get_env_config_redis_key(self) -> int:
        return "{}/env/config".format(self.team_env_key)

    def get_env_planning_day_redis_key(self) -> int:
        return "{}/env/planning_days".format(self.team_env_key)

    def get_env_replay_lock_redis_key(self) -> int:
        return "lock_env/{}".format(self.team_env_key)

    def get_recommened_locked_slots_by_job_code_redis_key(self, job_code: str) -> str:
        return "{}/env_lock/by_job/{}".format(self.team_env_key, job_code)

    def get_redis_key_commited_slot_lock(self, slot_code: str) -> str:
        return "{}/env_lock/after_commit_slot/{}".format(self.team_env_key, slot_code)

    def get_recommened_locked_slot_redis_key(self, slot_code: str) -> str:
        return "{}/env_lock/slot/{}".format(self.team_env_key, slot_code)

    def get_env_planning_horizon_start_minutes(self) -> int:
        #  worker_id, start_minutes, end_minutes, slot_type,  worker_id,start_minutes, end_minutes, slot_type
        if self.horizon_start_minutes is not None:
            return self.horizon_start_minutes

        # Env starts from now on
        # return int((datetime.now() - self.data_start_datetime).total_seconds() / 60)

        # The planning should start from next day start
        flex_form_data = get_or_add_redis_team_flex_data(self.redis_conn, self.config['team_id'])
        begin_skip_minutes = int(flex_form_data.get('begin_skip_minutes', 0))
        return int((datetime.now() - self.data_start_datetime).total_seconds() / 60) + begin_skip_minutes

    def get_env_planning_horizon_end_minutes(self) -> int:
        #  worker_id, start_minutes, end_minutes, slot_type,  worker_id,start_minutes, end_minutes, slot_type
        return 1440 * (int(self.config["nbr_of_days_planning_window"]) + int(self.get_env_planning_horizon_start_minutes() / 1440))

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
                    worker.overtime_limits[limit_days_key] - total_overtime)
        if len(available_overtime_list) < 1:
            return 0
        available_overtime = min(available_overtime_list)
        return available_overtime

    def get_worker_floating_slots(self, worker_code: str, query_start_minutes: int) -> List:
        overlap_slots = self.slot_server.get_overlapped_slots(
            worker_id=worker_code,
            start_minutes=0,
            end_minutes=MAX_MINUTES_PER_TECH,
        )
        floating_slots = []
        for a_slot in overlap_slots:  #
            if self.slot_server.get_time_slot_key(a_slot) in kandbox_config.DEBUGGING_SLOT_CODE_SET:
                log.debug("debug atomic_slot_delete_and_add_back")

            if (a_slot.slot_type == TimeSlotType.FLOATING) or (a_slot.start_overtime_minutes + a_slot.end_overtime_minutes > 0):
                if a_slot.start_minutes - query_start_minutes < 0:
                    continue
                # if worker_code == "MY|D|3|CT29":
                #     print("pause")
                floating_slots.append([
                    a_slot.start_minutes - query_start_minutes,
                    a_slot.end_minutes - query_start_minutes,
                    a_slot.start_overtime_minutes,
                    a_slot.end_overtime_minutes,
                ])
        return floating_slots

    def env_encode_day_seq_to_weekday(self, day_seq: int) -> int:
        today_start_date = self.data_start_datetime + timedelta(days=day_seq)
        return (today_start_date.weekday() + 1) % 7

    def env_encode_from_datetime_to_minutes(self, input_datetime: datetime) -> int:
        #  worker_id, start_minutes, end_minutes, slot_type,  worker_id,start_minutes, end_minutes, slot_type

        assigned_start_minutes = int(
            (input_datetime - self.data_start_datetime).total_seconds() / 60)
        return assigned_start_minutes

    def env_encode_from_datetime_to_day_with_validation(self, input_datetime: datetime) -> int:
        #  worker_id, start_minutes, end_minutes, slot_type,  worker_id,start_minutes, end_minutes, slot_type

        the_minutes = self.env_encode_from_datetime_to_minutes(input_datetime)
        # I removed 10 seconds from end of window.
        if (the_minutes < self.get_env_planning_horizon_start_minutes()) or (the_minutes >= self.get_env_planning_horizon_end_minutes()):
            raise ValueError("Out of Planning Window")

        return int(the_minutes / self.config["minutes_per_day"])

    def env_decode_from_minutes_to_datetime(self, input_minutes: int) -> datetime:
        #  worker_id, start_minutes, end_minutes, slot_type,  worker_id,start_minutes, end_minutes, slot_type
        assigned_start_datetime = self.data_start_datetime + timedelta(minutes=input_minutes)
        return assigned_start_datetime

    def get_encode_shared_duration_by_planning_efficiency_factor(self, requested_duration_minutes: int, nbr_workers: int) -> int:

        factor = self.efficiency_dict[nbr_workers]
        return int(requested_duration_minutes * factor / nbr_workers)

    def reload_env_from_redis(self):
        # observation = self.reset(shuffle_jobs=False)
        self.mutate_refresh_planning_window_from_redis()
        self._reset_data()
        if len(self.workers) < 1:
            log.warn("No workers in env, skipped loading slots. Maybe this is the first initialization?")
            return

        for absence_code in self.kp_data_adapter.absence_db_dict:
            # This one loads all data first. The env will decide to replay it or not depending on cache_server(redis)
            job = self.env_encode_single_absence(self.kp_data_adapter.absence_db_dict[absence_code])
            absence_job = self.mutate_create_worker_absence(job, auto_replay=False)

        for job_code in self.kp_data_adapter.appointment_db_dict:
            # This one loads all data first. The env will decide to replay it or not depending on cache_server(redis)
            if job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
                log.debug(f"reload_env_from_redis: {job_code}")

            appt = self.env_encode_single_appointment(
                self.kp_data_adapter.appointment_db_dict[job_code])
            job = self.mutate_create_appointment(appt, auto_replay=False)

        self.slot_server.reload_from_redis_server()

    def mutate_replay_jobs_single_working_day(self, day_seq: int):
        for job_code in self.jobs_dict.keys():
            this_job = self.jobs_dict[job_code]
            if this_job.planning_status == JobPlanningStatus.UNPLANNED:
                continue
            if (this_job.scheduled_start_minutes < day_seq * 1440) or (this_job.scheduled_start_minutes > (day_seq + 1) * 1440):
                continue
            if this_job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
                log.debug("mutate_replay_jobs_single_working_day: DEBUGGING_JOB_CODE_SET ")

            action_dict = self.gen_action_dict_from_job(job=this_job, is_forced_action=True)
            info = self.mutate_update_job_by_action_dict(
                a_dict=action_dict, post_changes_flag=False)

            if info.status_code != ActionScoringResultType.OK:
                log.error(
                    f"Error in job replay , but it will continue. code= {job_code},  info: {info} ")

    def replay_env_to_redis(self):

        # self.slot_server.reset()

        for key in self.redis_conn.scan_iter(f"{self.team_env_key}/s/*"):
            self.redis_conn.delete(key)

        # observation = self.reset(shuffle_jobs=False)

        self.mutate_extend_planning_window()

        if len(self.jobs) < 1:
            log.error("replay_env_to_redis: No jobs in the env, len(self.jobs) < 1:")
            return
            # raise ValueError("No jobs in the env, len(self.jobs) < 1:")
        # we assume sequence of  I P U
        sorted_jobs = sorted(self.jobs, key=lambda job__i_: (
            job__i_.planning_status, job__i_.job_code))
        self.jobs = sorted_jobs
        for ji, job___ in enumerate(self.jobs):
            self.jobs_dict[job___.job_code].job_index = ji

        self.run_mode = EnvRunModeType.REPLAY
        self.current_job_i = 0
        # previous_observation = self._get_observation()
        for step_job_code in self.jobs_dict.keys():
            this_job = self.jobs_dict[step_job_code]
            if this_job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
                log.debug(
                    f"JOB:{this_job.job_code}:INDEX:{self.current_job_i}: replaying on pause: starting at {this_job.scheduled_start_minutes}.")

            if self.current_job_i >= len(self.jobs):
                break

            if this_job.planning_status not in [
                    JobPlanningStatus.IN_PLANNING,
                    JobPlanningStatus.PLANNED,
                    JobPlanningStatus.FINISHED,
            ]:

                log.info(
                    f"Replayed until first U-status, self.current_job_i = {self.current_job_i} ")
                break
                # return observation, -1, False, None
                # break

            if this_job.scheduled_duration_minutes < 1:
                log.error(
                    f"JOB:{this_job.job_code}:scheduled_duration_minutes = {this_job.scheduled_duration_minutes} < 1 , not allowed, skipped from replay")
                self.current_job_i += 1
                continue

            if (this_job.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes()) or (this_job.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()):
                log.warn(
                    f"replay_env_to_redis, JOB:{this_job.job_code}:INDEX:{self.current_job_i}: is out of horizon, starting at {this_job.scheduled_start_minutes} and therefore is skipped.")
                self.current_job_i += 1
                continue
            # action = self.gen_action_from_one_job(self.jobs[self.current_job_i])
            # action_dict = self.decode_action_into_dict(action)

            # This should work for both appt and absence.
            action_dict = self.gen_action_dict_from_job(job=this_job, is_forced_action=True)

            info = self.mutate_update_job_by_action_dict(
                a_dict=action_dict, post_changes_flag=False)

            if info.status_code != ActionScoringResultType.OK:
                print(
                    f"Error game replay got error, but it will continue: job_code={this_job.job_code}, current_job_i: {self.current_job_i},  info: {info} ")
        # TODO
        self.replay_worker_absence_to_redis()
        self.replay_appointment_to_redis()

        self.run_mode = EnvRunModeType.PREDICT

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

    def replay_env(self):

        msg = f"env = {self.env_inst_code}, Trying to get lock over the env key ({self.get_env_replay_lock_redis_key()}) to applying messages"
        log.debug(msg) 
        flag = True
        with self.redis_conn.lock(self.get_env_replay_lock_redis_key(), timeout=60 * 5, blocking_timeout=60 * 5) as lock:
            flag = False
            if self.config.get("sample_history", False):
                for key in self.redis_conn.scan_iter(f"{self.team_env_key}/env/*"):
                    self.redis_conn.delete(key)
            global_env_config = self.redis_conn.get(self.get_env_config_redis_key())

            if (global_env_config is None):
                # This initialize the env dataset in redis for this envionrment.
                # all subsequent env replay_env should read from this .
                self.redis_conn.set(self.get_env_config_redis_key(), json.dumps(self.config))
                self.set_env_window_replay_till_offset(0)
                self.replay_env_to_redis()
                # code you want executed only after the lock has been acquired
                # lock.release()
            else:
                self.reload_env_from_redis()
        if flag:
            raise LockError("Cannot get a lock ")
        log.debug(f"env = {self.env_inst_code}, Done with redis lock to applying messages")

        # Catch up with recent messages on Kafka. Optional ? TODO

        self.mutate_check_env_window_n_replay()

        if PLANNER_SERVER_ROLE == "trainer":
            self.slot_server = CacheOnlySlotServer(env=self, redis_conn=self.redis_conn)
            self.slot_server.reset()

        # self._move_to_next_unplanned_job()
        # obs = None  # self._get_observation()

        # reward = -1
        # done = False
        # if obs is None:
        #     done = True
        # info = {"message": f"Replay done"}
        # return (obs, reward, done, info)

    # Is this timeout seconds?
    # TODO, replace two with locks by this unified locking
    def mutate_check_env_window_n_replay(self):
        # I need to lock it to protect kafka,  generator not threadsafe.
        # ValueError: generator already executing
        # with lock:
        if PLANNER_SERVER_ROLE == "trainer":
            return

        self.kafka_server.consume_env_messages()

    def env_encode_single_worker(self, worker=None):
        assert type(worker) == dict, "Wrong type, it must be dict"

        if worker["worker_code"] in kandbox_config.DEBUGGING_JOB_CODE_SET:
            log.debug("env_encode_single_worker debug MY|D|3|CT07")

        # worker_week_day = (self.data_start_datetime.weekday() + 1) % 7

        flex_form_data = worker["flex_form_data"].copy()

        # db_session = self.cnx

        # _workers = pd.read_sql(
        #     db_session.query(Location).filter(Location.location_code ==
        #                                       worker['location_id']).statement,
        #     db_session.bind,
        # )
        # worker_info = _workers.set_index("id").to_dict(orient="index")

        # Here it makes planner respect initial travel time
        home_location_type = LocationType.HOME
        if self.config.get("respect_initial_travel", True):
            home_location_type = LocationType.JOB
        home_location = JobLocationBase(
            float(worker["geo_longitude"]),
            float(worker["geo_latitude"]),
            home_location_type,
            worker["location_code"],
        )
        # working_minutes_array = flex_form_data["StartEndTime"].split(";")

        weekly_start_gps = [home_location for _ in range(7)]
        weekly_end_gps = [home_location for _ in range(7)]
        _weekly_working_slots = [[] for _ in range(7)]
        week_day_i = 0
        for week_day_code in [
                "sunday",
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
        ]:
            for day_slot in worker["business_hour"][week_day_code]:
                if day_slot["isOpen"]:
                    today_start_minutes = date_util.int_hhmm_to_minutes(int(day_slot["open"]))
                    today_end_minutes = date_util.int_hhmm_to_minutes(int(day_slot["close"]))
                    _weekly_working_slots[week_day_i].append((
                        today_start_minutes,
                        today_end_minutes,
                    ))

            week_day_i += 1
        skills = {
            "skills": set(flex_form_data["skills"]),
        }
        # loc = LocationTuple(loc_t[0], loc_t[1], LocationType.HOME, f"worker_loc_{worker['id']}",)
        belongs_to_pair = None
        if "assistant_to" in flex_form_data.keys():
            if flex_form_data["assistant_to"]:
                belongs_to_pair = (
                    flex_form_data["assistant_to"],
                    worker["code"],
                )

        if "is_assistant" not in flex_form_data.keys():
            flex_form_data["is_assistant"] = False

        overtime_minutes = 0
        if "max_overtime_minutes" in flex_form_data.keys():
            overtime_minutes = int(float(flex_form_data["max_overtime_minutes"]))

        curr_slot = None

        try:
            _location = LocationTuple(
                geo_longitude=worker['geo_longitude'],
                geo_latitude=worker["geo_latitude"],
                location_type=home_location_type,
                location_code=worker['location_code'],
            )
            curr_slot = WorkingTimeSlot(
                assigned_job_codes=worker['job_code_list'] if 'job_code_list' in worker else [],
                worker_id=worker["code"],
                slot_type=TimeSlotType.FLOATING,
                start_minutes=self.get_env_planning_horizon_start_minutes(),
                end_minutes=1440 + self.get_env_planning_horizon_start_minutes(),
                prev_slot_code=None,
                next_slot_code=None,
                start_location=_location,
                end_location=_location,
            )
        except:
            pass

        flex_form_data["job_history_feature_data"] = worker["job_history_feature_data"]

        try:
            geo_dist = multivariate_normal(
                [worker["job_history_feature_data"]["mean"]["longitude"],
                 worker["job_history_feature_data"]["mean"]["latitude"]
                 ],
                worker["job_history_feature_data"]["cov"]
            )
        except KeyError as ke:
            log.debug(f"worker {worker['code']} is missing feature  {str(ke)}, from 'job_history_feature_data'. Setting as default ")
            geo_dist = multivariate_normal(
                [(self.config["geo_longitude_max"] + self.config["geo_longitude_min"]) / 2,
                 (self.config["geo_latitude_max"] + self.config["geo_latitude_min"]) / 2
                 ],
                [
                    [(self.config["geo_longitude_max"] - self.config["geo_longitude_min"]) / 2, 0],
                    [0, (self.config["geo_latitude_max"] - self.config["geo_latitude_min"]) / 2]
                ]
            )
        except np.linalg.LinAlgError as ne:
            log.warning(f"worker {worker['code']} encoding error, np.linalg.LinAlgError, {str(ne)}")
            print(flex_form_data["job_history_feature_data"])
            geo_dist = multivariate_normal(
                [(self.config["geo_longitude_max"] + self.config["geo_longitude_min"]) / 2,
                 (self.config["geo_latitude_max"] + self.config["geo_latitude_min"]) / 2
                 ],
                [
                    [(self.config["geo_longitude_max"] - self.config["geo_longitude_min"]) / 2, 0],
                    [0, (self.config["geo_latitude_max"] - self.config["geo_latitude_min"]) / 2]
                ]
            )

        w_r = Worker(
            worker_id=worker["id"],
            worker_code=worker["code"],
            flex_form_data=flex_form_data,
            # "level= worker.flex_form_data["level"],
            skills=skills,
            # location=loc,
            #
            # TODO, @duan, only 1 slot per day? 2020-11-17 15:36:00
            # 6 times  for _ in range(len(k_worker['result']))
            weekly_working_slots=_weekly_working_slots,
            weekly_start_gps=weekly_start_gps,
            weekly_end_gps=weekly_end_gps,
            linear_working_slots=[],  # 6 times  for _ in range(len(k_worker['result']))
            # linear_daily_start_gps=daily_start_gps,
            # linear_daily_end_gps=daily_end_gps,
            historical_job_location_distribution=geo_dist,
            worker_index=worker["id"],
            belongs_to_pair=belongs_to_pair,
            is_active=worker["is_active"],
            daily_max_overtime_minutes=overtime_minutes,
            weekly_max_overtime_minutes=60 * 10,
            overtime_limits={},
            used_overtime_minutes={},
            curr_slot=curr_slot,
        )
        return w_r

    def load_transformed_workers(self):

        # start_date =  self.data_start_datetime

        w = []
        # w_dict = {}
        #
        # index = 0
        for wk, worker in self.kp_data_adapter.workers_db_dict.items():
            active_int = 1 if worker["is_active"] else 0
            if active_int != 1:
                print(
                    f"worker { worker['id']} is not active, maybe it shoud be skipped from loading? ")
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
            appointment["scheduled_start_datetime"])

        job_form = appointment["flex_form_data"]

        try:
            abs_location = self.locations_dict[appointment["location_code"]]
        except:
            included_job_code = appointment["included_job_codes"][0]
            if included_job_code not in self.jobs_dict.keys():
                log.error(
                    f"{appointment['appointment_code']}: I failed to find the job by code=  {included_job_code}, and then failed to find the Location. Skipped this appointment")
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
                    f"missing included_job_codes, appointment_code= {appointment['appointment_code']}, job_code={jc} ")
                return None
            if self.jobs_dict[jc].planning_status != JobPlanningStatus.UNPLANNED:
                # Keep last one for now
                scheduled_worker_codes = self.jobs_dict[jc].scheduled_worker_codes
        if len(scheduled_worker_codes) < 1:
            #
            log.debug(
                f"APPT:{appointment['appointment_code']}:Only u status in appt? I will take requested. ")
            scheduled_worker_codes.append(self.jobs_dict[jc].requested_primary_worker_code)

        requested_day_minutes = int(assigned_start_minutes / 1440) * 1440

        appt_job = Job(
            job_code=appointment["appointment_code"],
            job_id=-1,
            job_index=appointment["id"],
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
            start_time = datetime.strptime(slot.split(
                "_")[0], kandbox_config.KANDBOX_DATETIME_FORMAT_GTS_SLOT)
            end_time = datetime.strptime(slot.split(
                "_")[1], kandbox_config.KANDBOX_DATETIME_FORMAT_GTS_SLOT)

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

    def _convert_lists_to_slots(self, input_list: list, job):
        orig_loc = self.locations_dict[job["location_code"]]

        CONSTANT_JOB_LOCATION = JobLocationBase(
            geo_longitude=orig_loc.geo_longitude,
            geo_latitude=orig_loc.geo_latitude,
            location_type=LocationType.HOME,
            location_code=orig_loc.location_code,
            # historical_serving_worker_distribution=None,
            # avg_actual_start_minutes=0,
            # avg_days_delay=0,
            # stddev_days_delay=0,
            # available_slots=tuple(),  # list of [start,end] in linear scale
            # rejected_slots=job["rejected_slots"],
        )
        job_available_slots = []

        for slot in sorted(list(input_list), key=lambda x: x[0]):

            wts = WorkingTimeSlot(
                slot_type=TimeSlotType.FLOATING,
                start_minutes=slot[0],
                end_minutes=slot[1],
                prev_slot_code=None,
                next_slot_code=None,
                start_location=CONSTANT_JOB_LOCATION,
                end_location=CONSTANT_JOB_LOCATION,
                worker_id="_",
                available_free_minutes=0,
                assigned_job_codes=[],
            )

            job_available_slots.append(wts)
        return job_available_slots

    def mutate_create_replenish_job(self,
                                    slot: WorkingTimeSlot,
                                    total_loaded_items: Dict,
                                    total_requested_items: Dict,
                                    ) -> Job:
        """ It follow those steps:
        1. summarize all item requirements from all jobs allocated to this slot
        2. Find which depot has enough stock.
        3. Allocate those items from inventory, i.e. from items in depot from curr_qty to allocated_qty.
        """
        if slot is None:
            log.error("mutate_create_replenish_job: slot is None")
            return None
        for jc in slot.assigned_job_codes:
            if jc.split("-")[-1] == "R":
                log.warn(f"replenishment job ({jc}) already exists ...")
                self.kp_data_adapter.update_replenish_job(
                    job=self.jobs_dict[jc], total_requested_items=total_requested_items)
                return self.jobs_dict[jc]
        depot_key = list(self.depots_dict.keys())[0]
        inventory_dict = self.kp_data_adapter.get_depot_item_inventory_dict(
            depot_id=self.depots_dict[depot_key]["id"],
            requested_items=list(total_requested_items.keys())
        )
        depot_location = self.depots_dict[depot_key]["location"]
        items_to_load = dict(total_requested_items)
        for k in inventory_dict.keys():
            if inventory_dict.get(k, 0) - total_requested_items[k] < 0:
                log.warn(f"mutate_create_replenish_job: not enough inventory for item: {k}")
                return None
            # I will load all jobs requests. Current stock are treated as safe stock...
            # items_to_load -= total_loaded_items

        requested_worker_code = slot.worker_id
        scheduled_worker_codes = [requested_worker_code]
        requested_start_minutes = slot.start_minutes  # self.get_env_planning_horizon_start_minutes()
        min_minutes = requested_start_minutes - 144000
        max_minutes = requested_start_minutes + 1440000
        net_avail_slots = [[
            - 144000, 1440000,
        ]]
        new_job = Job(
            job_code=f"{requested_worker_code}-{requested_start_minutes}-R",
            job_id=-1,
            job_index=len(self.jobs_dict),
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

    def env_encode_single_job(self, job: dict) -> Job:  # from db dict object to dataclass object
        if job is None:
            log.error("env_encode_single_job: job is None")
            return
        if job["code"] in kandbox_config.DEBUGGING_JOB_CODE_SET:
            log.debug(f"debug {kandbox_config.DEBUGGING_JOB_CODE_SET}")

        flex_form_data = job["flex_form_data"]

        if pd.isnull(job["requested_start_datetime"]):
            log.error("requested_start_datetime is null, not allowed")
            return None
        if pd.isnull(job["requested_duration_minutes"]):
            log.error("requested_duration_minutes is null, not allowed")
            return None

        assigned_start_minutes = 0
        scheduled_duration_minutes = 0
        if job["planning_status"] in (JobPlanningStatus.PLANNED, JobPlanningStatus.IN_PLANNING):
            try:
                assigned_start_minutes = int(
                    (job["scheduled_start_datetime"] - self.data_start_datetime).total_seconds() / 60)
                scheduled_duration_minutes = job["scheduled_duration_minutes"]
            except Exception as ve:
                log.error(f"Data error: failed to convert scheduled_start_datetime, job = {job}")
                return None

        requested_start_minutes = int(
            (job["requested_start_datetime"] - self.data_start_datetime).total_seconds() / 60)
        min_minutes = requested_start_minutes
        max_minutes = requested_start_minutes
        if "tolerance_start_minutes" in flex_form_data.keys():
            min_minutes = requested_start_minutes + (flex_form_data["tolerance_start_minutes"])
        if "tolerance_end_minutes" in flex_form_data.keys():
            max_minutes = requested_start_minutes + (flex_form_data["tolerance_end_minutes"])

        historical_serving_worker_distribution = {}
        if "job_history_feature_data" in job.keys():
            if "historical_serving_worker_distribution" in job["job_history_feature_data"].keys():
                historical_serving_worker_distribution = job["job_history_feature_data"]["historical_serving_worker_distribution"]

        if job["location_code"] not in self.locations_dict.keys():
            job_location = JobLocation(
                geo_longitude=job["geo_longitude"],
                geo_latitude=job["geo_latitude"],
                location_type=LocationType.JOB,
                location_code=job["location_code"],
                historical_serving_worker_distribution=historical_serving_worker_distribution,
                avg_actual_start_minutes=0,
                avg_days_delay=0,
                stddev_days_delay=0,
                # rejected_slots=job["rejected_slots"],
            )
            self.locations_dict[job_location.location_code] = job_location
        else:
            job_location = self.locations_dict[job["location_code"]]
        # if job_location.geo_longitude < 0:
        #     log.warn(
        #         f"Job {job['code']} has invalid location :  {job_location.location_code} with geo_longitude = {job_location.geo_longitude}"
        #     )

        requested_primary_worker_code = job.get("requested_primary_worker_code", None)
        if requested_primary_worker_code not in self.workers_dict.keys():
            # "W0"
            # requested_primary_worker_code = self.config["default_requested_primary_worker_code"]
            worker_code_list = list(self.workers_dict.keys())
            # if len(worker_code_list) < 1:

            worker_prob = [self.workers_dict[w].historical_job_location_distribution.pdf(
                job_location[0:2]
            ) for w in worker_code_list]
            max_prob_i = np.argmax(worker_prob)
            log.debug("Job {} has invalid requested worker code {}, and it is replaced by {}.".format(
                job["code"],
                requested_primary_worker_code,
                worker_code_list[max_prob_i]
            ))
            requested_primary_worker_code = worker_code_list[max_prob_i]

        # prev_available_slots = [
        #     (s.start_minutes, s.end_minutes) for s in job_location.available_slots
        # ]

        net_avail_slots = [[
            self.get_env_planning_horizon_start_minutes(),
            self.get_env_planning_horizon_end_minutes(),
        ]]
        # TODO duan, change job_location from tuple to dataclass.
        # job_location.available_slots.clear()

        job_available_slots = self._convert_lists_to_slots(net_avail_slots, job)
        # job_location.available_slots = sorted(list(net_avail_slots), key=lambda x: x[0])
        if "requested_skills" in job.keys():
            # requested_skills = {
            #     "skills": set(job["requested_skills"]),
            # }
            requested_skills =set(job["requested_skills"])
        else:
            requested_skills =set()
            # {
            #     "skills": set()
            # }
            log.warning(f"job({job['code']}) has no requested_skills")

        the_final_status_type = job["planning_status"]
        is_appointment_confirmed = False

        # if job_schedule_type == JobScheduleType.FIXED_SCHEDULE:
        #     is_appointment_confirmed = True

        if "included_job_codes" not in flex_form_data.keys():
            flex_form_data["included_job_codes"] = []

        scheduled_worker_codes = job.get("scheduled_worker_codes", [])
        # print(job["scheduled_primary_worker_id"])
        if not self.kp_data_adapter.workers_dict_by_id:
            self.reload_data_from_db_adapter(
                self.env_start_datetime,
                end_datetime=self.env_decode_from_minutes_to_datetime(
                    self.get_env_planning_horizon_end_minutes())
            )
        if len(scheduled_worker_codes) < 1:
            if not pd.isnull(job["scheduled_primary_worker_id"]):
                scheduled_worker_codes.append(
                    self.kp_data_adapter.workers_dict_by_id[job["scheduled_primary_worker_id"]]["code"])
            scheduled_worker_codes += job.get("scheduled_secondary_worker_codes", [])
        priority = 1
        if "priority" in flex_form_data.keys() and isinstance(flex_form_data["priority"], int):
            priority = flex_form_data["priority"]
        job_requested_items = flex_form_data.get("requested_items", [])
        parsed_requested_items = {}
        for item_str in job_requested_items:
            item_list = parse_item_str(item_str)
            parsed_requested_items[item_list[0]] = item_list[1]
        final_job = Job(
            job_code=job["code"],
            job_id=job["id"],
            job_index=0,
            job_type=job["job_type"],  # JobType.JOB,
            job_schedule_type=JobScheduleType.NORMAL,
            planning_status=the_final_status_type,
            location=job_location,
            requested_skills=requested_skills,  # TODO
            #
            scheduled_worker_codes=scheduled_worker_codes,
            scheduled_start_minutes=assigned_start_minutes,
            scheduled_duration_minutes=scheduled_duration_minutes,
            #
            requested_start_min_minutes=min_minutes,
            requested_start_max_minutes=max_minutes,
            requested_start_minutes=requested_start_minutes,
            requested_time_slots=[[0, 0]],
            requested_primary_worker_code=requested_primary_worker_code,
            requested_duration_minutes=job["requested_duration_minutes"],
            #
            available_slots=job_available_slots,
            flex_form_data=flex_form_data,
            searching_worker_candidates=[],
            included_job_codes=flex_form_data["included_job_codes"],
            new_job_codes=[],
            appointment_status=AppointmentStatus.NOT_APPOINTMENT,
            #
            requested_items=parsed_requested_items,
            #
            is_active=job["is_active"],
            is_appointment_confirmed=is_appointment_confirmed,
            is_auto_planning=job["auto_planning"],
            priority=priority,

        )
        if self.config.get("set_searching_worker_candidates", True):
            self.set_searching_worker_candidates(final_job)
        else:
            final_job.searching_worker_candidates = []

        return final_job

    def load_transformed_jobs(self):
        # TODO , need data_window
        # This function also alters self.locations_dict
        #

        w = []

        for k, row_dict in self.kp_data_adapter.jobs_db_dict.items():
            if row_dict["code"] in kandbox_config.DEBUGGING_JOB_CODE_SET:
                log.debug(
                    f"load_transformed_jobs Debug {str(kandbox_config.DEBUGGING_JOB_CODE_SET)} ")

            # if pd.isnull(row_dict["requested_primary_worker_id"]):
            #     continue

            job = self.env_encode_single_job(job=row_dict)
            if job is not None:
                w.append(job)
        return w

    def env_encode_single_absence(self, job: dict) -> Absence:

        assigned_start_minutes = int(
            (job["scheduled_start_datetime"] - self.data_start_datetime).total_seconds() / 60)
        scheduled_primary_worker_code = job["code"]

        job_code = job["absence_code"]

        abs_location = LocationTuple(
            geo_longitude=job["geo_longitude"],
            geo_latitude=job["geo_latitude"],
            location_type=LocationType.HOME,
            location_code=f"evt_loc_{job_code}",
        )
        # loc = LocationTuple(loc_t[0], loc_t[1], LocationType.HOME, f"worker_loc_{worker['id']}",)
        return Absence(
            job_code=job_code,
            job_id=job["id"],
            job_index=0,
            job_type=JobType.ABSENCE,
            job_schedule_type=JobScheduleType.FIXED_SCHEDULE,  # job_seq: 89, job['job_code']   "FS"
            planning_status=JobPlanningStatus.PLANNED,
            location=abs_location,
            requested_skills={},  # TODO
            #
            scheduled_worker_codes=[scheduled_primary_worker_code],
            scheduled_start_minutes=assigned_start_minutes,
            scheduled_duration_minutes=job["scheduled_duration_minutes"],
            #
            requested_start_min_minutes=0,
            requested_start_max_minutes=0,
            requested_start_minutes=0,
            requested_time_slots=[],
            #
            requested_primary_worker_code=scheduled_primary_worker_code,
            # requested_start_datetime=assigned_start_minutes,  # No day, no minutes
            requested_duration_minutes=job["scheduled_duration_minutes"],  # TODO remove plural?)
            searching_worker_candidates=[],
            included_job_codes=[],
            new_job_codes=[],
            available_slots=[],
            appointment_status=AppointmentStatus.NOT_APPOINTMENT,
            #
            is_active=True,
            is_replayed=False,
            is_auto_planning=False,
            flex_form_data=job["flex_form_data"],
        )

    def env_decode_single_job_to_dict(self, job: BaseJob):  # _for_training
        all_worker_ids = [
            self.workers_dict[wcode].worker_id for wcode in job.scheduled_worker_codes]

        flex_form = copy.deepcopy(job.flex_form_data)
        flex_form["requested_items"] = []
        for k in job.requested_items.keys():
            flex_form["requested_items"].append(f"{k}:{job.requested_items[k]}")
        new_job = {
            "id": self.jobs_dict[job.job_code].job_id,
            "job_type": job.job_type,
            "code": job.job_code,
            "name": job.job_code,
            "org_code": self.config["org_code"],
            "planning_status": job.planning_status,
            "scheduled_start_datetime": None,
            "scheduled_duration_minutes": job.scheduled_duration_minutes,  # TODO remove plural
            "scheduled_primary_worker_id": all_worker_ids[0],
            "scheduled_secondary_worker_ids": all_worker_ids[1:],
            "scheduled_primary_worker": {"code": job.scheduled_worker_codes[0]},  # : WorkerCreate
            #
            "scheduled_secondary_workers": [
                {"code": wc} for wc in job.scheduled_worker_codes[1:]
            ],  # : List[WorkerCreate] =
            #
            "tags": [],
            "location": {"location_code": job.location.location_code},
            "flex_form_data": flex_form,
            # : WorkerCreate
            "requested_primary_worker": {"code": job.requested_primary_worker_code},
            "requested_start_datetime": self.env_decode_from_minutes_to_datetime(job.requested_start_minutes),
            "requested_duration_minutes": job.requested_duration_minutes,
            "auto_planning": job.is_auto_planning,

        }
        if job.planning_status != JobPlanningStatus.UNPLANNED:
            new_job["scheduled_start_datetime"] = self.env_decode_from_minutes_to_datetime(
                job.scheduled_start_minutes)
        return new_job

    def get_solution_dataset(self, query_start_datetime, query_end_datetime):

        workers_dimensions = [
            "index",
            "skills",
            "max_conflict_level",
            "worker_code",
            "geo_longitude",
            "geo_latitude",
            "weekly_working_minutes",
            "selected_flag",
            "worker_code",
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
            "scheduled_primary_worker_id",
            "geo_longitude",
            "geo_latitude",
            "changed_flag",
            "prev_geo_longitude",
            "prev_geo_latitude",
            "prev_location_type",
        ]

        planned_jobs_list = []
        all_jobs_in_env_list = []

        print(
            datetime.now(),
            "worker_job_dataset_json: Started transforming to dataset for web json... ",
        )

        workers_start_end_dict = {}
        workers_dict = {}
        workers_list = []

        # linear_free_slot = [[510, 610], [720, 840], [1440, 1640], [1840, 1940]]

        query_start_minutes = self.env_encode_from_datetime_to_minutes(query_start_datetime)

        for index, w in enumerate(self.workers):

            linear_free_slot = self.get_worker_floating_slots(
                worker_code=w.worker_code, query_start_minutes=query_start_minutes)
            report_string_dict = copy.deepcopy(w.skills)
            report_string_dict["pair"] = w.belongs_to_pair

            worker1 = {
                "index": index,
                "skills": str(report_string_dict),
                # list(w.skills["product_code"]),  # w["skills"],   pprint.pformat(
                "max_conflict_level": 1,
                "worker_code": w.worker_code,
                "geo_longitude": 0,  # w.location[0],
                "geo_latitude": 0,  # w.location[1],
                "weekly_working_minutes": linear_free_slot,  # w.linear_working_slots,
                "selected_flag": 0 if w.belongs_to_pair is None else 1,
                "worker_code": w.worker_code,
            }
            workers_dict[w.worker_code] = worker1
            workers_list.append(worker1)

        new_df = pd.DataFrame(workers_list)

        # TODO , async warm up env
        df_count = new_df.count().max()
        if (pd.isnull(df_count)) or (df_count < 1):
            return {
                "workers_dimensions": workers_dimensions,
                "workers_data": [],
                "jobs_dimensions": jobs_dimensions,
                "planned_jobs_data": [],
                "all_jobs_in_env": [],  # all_jobs_in_env
                "start_time": query_start_datetime.isoformat(),
                "end_time": query_end_datetime.isoformat(),
                # TODO: worker_time [[day_start, day_end], [day_start, day_end]], office_hours{[day_start, day_end, day_start, day_end, ...] }.
            }

            #
        # new_df.columns
        workers_data = new_df[workers_dimensions].values.tolist()
        jobs_json = self.get_solution_json(query_start_datetime, query_end_datetime)

        for index, j in enumerate(jobs_json):
            if j["job_code"] in kandbox_config.DEBUGGING_JOB_CODE_SET:
                print(f"pause for debugging {kandbox_config.DEBUGGING_JOB_CODE_SET }")

            if j["planning_status"] in [JobPlanningStatus.UNPLANNED]:
                j["scheduled_primary_worker_id"] = workers_data[0][3]
                if (j["scheduled_duration_minutes"] is None) or (np.isnan(j["scheduled_duration_minutes"])):
                    j["scheduled_duration_minutes"] = j["requested_duration_minutes"]
                j["scheduled_duration_minutes"] = 1
                j["scheduled_start_minutes"] = 0
            else:
                if j["scheduled_primary_worker_id"] not in workers_dict.keys():
                    # continue
                    print(
                        "Internal error, j['scheduled_primary_worker_id'] not in workers_dict.keys(): ")
                # if workers_dict[curr_worker]['nbr_conflicts'] < conflict_level:
                #    workers_dict[curr_worker]['nbr_conflicts'] = conflict_level

            scheduled_start_datetime = self.data_start_datetime + \
                timedelta(minutes=j["scheduled_start_minutes"])

            scheduled_end_datetime = scheduled_start_datetime + \
                timedelta(minutes=j["scheduled_duration_minutes"])
            scheduled_start_datetime_js = int(time.mktime(
                scheduled_start_datetime.timetuple()) * 1000)
            if "requested_start_datetime" not in j.keys():
                if "requested_start_minutes" in j.keys():
                    j["requested_start_datetime"] = self.env_decode_from_minutes_to_datetime(
                        j["requested_start_minutes"])
                else:
                    j["requested_start_datetime"] = self.env_decode_from_minutes_to_datetime(
                        (j["requested_start_min_minutes"] + j["requested_start_max_minutes"]) / 2)
                # j["requested_duration_minutes"] =

            j["requested_primary_worker_id"] = j["requested_primary_worker_code"]

            scheduled_end_datetime_js = int(time.mktime(scheduled_end_datetime.timetuple()) * 1000)
            # TODO 2020-10-17 21:59:03
            if pd.isnull(j["scheduled_primary_worker_id"]):
                print("debug: j - scheduled_primary_worker_id is nan, please debug later.")
                continue
            if pd.isnull(j["requested_primary_worker_id"]):
                print("debug: j - requested_primary_worker_id is nan, please debug later.")
                continue

            if "job_id" not in j.keys():
                print("debug")
                j["requested_primary_worker_id"] = j["scheduled_primary_worker_id"]
                j["changed_flag"] = False
                pass
            plot_job_type = (
                f"{j['job_type']}" if j["job_type"] in {JobType.APPOINTMENT,
                                                        JobType.ABSENCE} else f"{j['planning_status']}"  # f"{j['job_schedule_type']}"
            )
            # print(f"{j['job_code']} = {plot_job_type}")

            if j["planning_status"] in (JobPlanningStatus.UNPLANNED):
                j["scheduled_worker_codes"] = [j["requested_primary_worker_code"]]
            new_job = {
                "job_code": j["job_code"],
                "job_type": "{}_1_2_3_4_{}".format(plot_job_type, j["scheduled_share_status"]),
                "requested_primary_worker_id": j["requested_primary_worker_code"],
                # requested_start_datetime_js,
                "requested_start_datetime": j["requested_start_datetime"].isoformat(),
                "requested_duration_minutes": j["requested_duration_minutes"],
                "scheduled_primary_worker_id": self.workers_dict[j["scheduled_worker_codes"][0]].worker_id,
                "scheduled_worker_codes": j["scheduled_worker_codes"],
                "scheduled_worker_index": workers_dict[j["scheduled_primary_worker_id"]]["index"],
                # https://stackoverflow.com/questions/455580/json-datetime-between-python-and-javascript
                "scheduled_start_datetime_js": scheduled_start_datetime_js,  # scheduled_start_datetime.isoformat(),
                "scheduled_end_datetime_js": scheduled_end_datetime_js,  # scheduled_end_datetime.isoformat(),
                "scheduled_start_datetime": scheduled_start_datetime.isoformat(),
                "scheduled_end_datetime": scheduled_end_datetime.isoformat(),
                # "scheduled_start_minutes": j["scheduled_start_minutes"],
                "scheduled_duration_minutes": j["scheduled_duration_minutes"],
                "planning_status": j["planning_status"],
                "conflict_level": 0,  # j["conflict_level"],
                "scheduled_travel_minutes_after": 0,  # j["scheduled_travel_minutes_after"],
                "scheduled_travel_minutes_before": j["scheduled_travel_minutes_before"],
                "scheduled_travel_prev_code": j["scheduled_travel_prev_code"],
                "geo_longitude": j["location"].geo_longitude,
                "geo_latitude": j["location"].geo_latitude,
                "changed_flag": j["is_changed"],
                "prev_geo_longitude": 0,
                "prev_geo_latitude": 0,
                "prev_location_type": "J",
            }

            if j["scheduled_share_status"] != "S":  # add only those P, N.
                all_jobs_in_env_list.append(new_job)
            else:
                new_job["job_code"] = "{}_S_{}".format(
                    j["job_code"], j["scheduled_primary_worker_id"])

            if j["planning_status"] not in [JobPlanningStatus.UNPLANNED]:  # 'I', 'P', 'C'
                new_job["prev_geo_longitude"] = j["prev_geo_longitude"]
                new_job["prev_geo_latitude"] = j["prev_geo_latitude"]
                new_job["prev_location_type"] = j["prev_location_type"]
                planned_jobs_list.append(new_job)

        planned_jobs_data = []
        all_jobs_in_env = all_jobs_in_env_list

        # is_NaN = all_jobs_in_env_df.isnull()
        # row_has_NaN = is_NaN.any(axis=1)
        # rows_with_NaN = all_jobs_in_env_df[row_has_NaN]

        if len(planned_jobs_list) > 0:
            new_planned_job_df = pd.DataFrame(planned_jobs_list).fillna(0)
            planned_jobs_data = new_planned_job_df[jobs_dimensions].values.tolist()

        all_jobs_in_env_df = pd.DataFrame(all_jobs_in_env).fillna(0)
        all_jobs_in_env = all_jobs_in_env_df.to_dict(orient="records")

        print(datetime.now(), "worker_job_dataset_json: Finished.")
        # https://echarts.apache.org/en/option.html#series-custom.dimensions
        # echarts might infer type as number.
        # jobs_dimensions[3]= {"name": 'job_code', "type": 'ordinal'}
        return {
            "workers_dimensions": workers_dimensions,
            "workers_data": workers_data,
            "jobs_dimensions": jobs_dimensions,
            "planned_jobs_data": planned_jobs_data,
            "all_jobs_in_env": all_jobs_in_env,  # all_jobs_in_env,
            "start_time": query_start_datetime.isoformat(),
            "end_time": query_end_datetime.isoformat(),
            # TODO: worker_time [[day_start, day_end], [day_start, day_end]], office_hours{[day_start, day_end, day_start, day_end, ...] }.
        }

    def get_solution_json(self, query_start_datetime, query_end_datetime):
        query_start_minutes = self.env_encode_from_datetime_to_minutes(query_start_datetime)
        query_end_minutes = self.env_encode_from_datetime_to_minutes(query_end_datetime)

        job_solution = []
        inplanning_job_index_set = set()
        shared_prev_jobs = {}

        sorted_slot_codes = sorted(list(self.slot_server.time_slot_dict.keys()))
        slot_dict = self.slot_server.time_slot_dict
        # for worker_code in self.workers_dict.keys():
        pre_job_code = "__HOME"
        prev_slot = None
        # In this loop, it first collects Only all (I/P) in/planned jobs, which are available from working time slots
        current_worker_id = "NOT_EXIST"
        for slot_code in sorted_slot_codes:
            # for work_time_i in  range(len( self.workers_dict[worker_code]['assigned_jobs'] ) ): # nth assigned job time unit.
            if slot_code in kandbox_config.DEBUGGING_SLOT_CODE_SET:
                log.debug("debug atomic_slot_delete_and_add_back")

            # for assigned_job in self.workers_dict[worker_code]["assigned_jobs"]:
            # for day_i in range(self.config["nbr_of_days_planning_window"]):
            # a_slot = slot_dict[slot_code]
            # I Loop through all

            # if a_slot.slot_type in (TimeSlotType.JOB_FIXED, TimeSlotType.FLOATING):
            try:
                a_slot = self.slot_server.get_slot(self.redis_conn.pipeline(), slot_code)
                the_assigned_codes = sorted(
                    a_slot.assigned_job_codes,
                    key=lambda jc: self.jobs_dict[jc].scheduled_start_minutes,
                )
            except KeyError as ke:
                log.error(
                    f"unknown worker code, or unknown job codes to the env. slot_code = {slot_code}, error = {str(ke)}")
                print(ke)
                continue

            if a_slot.worker_id != current_worker_id:
                current_start_loc = a_slot.start_location
            elif (a_slot.slot_type == TimeSlotType.FLOATING) or (a_slot.prev_slot_code is None):
                current_start_loc = a_slot.start_location

            current_worker_id = a_slot.worker_id

            for assigned_index, assigned_job_code in enumerate(the_assigned_codes):

                assigned_job = self.jobs_dict[assigned_job_code]

                if assigned_job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
                    print(f"pause for debugging {kandbox_config.DEBUGGING_JOB_CODE_SET }")

                if (assigned_job.scheduled_start_minutes + assigned_job.scheduled_duration_minutes < query_start_minutes) | (assigned_job.scheduled_start_minutes > query_end_minutes):
                    log.warn(
                        f"Should be error.In slot but Solution skipped job_code={assigned_job.job_code}, minutes = {query_start_minutes} not in {query_start_minutes} -- {query_end_minutes}")
                    continue

                if len(assigned_job.scheduled_worker_codes) < 1:
                    log.warn("Internal BUG, why a job from assigned_jobs has no assigned_workers, but?")
                    continue

                prev_travel_minutes = self.travel_router.get_travel_minutes_2locations(
                    current_start_loc,
                    assigned_job.location,
                )
                # Only single worker jobs are collected in this loop.

                assigned_job_dict = dataclasses.asdict(assigned_job)  # .copy().as_dict()
                assigned_job_dict["requested_start_datetime"] = self.env_decode_from_minutes_to_datetime(
                    assigned_job.requested_start_min_minutes)
                if len(assigned_job.scheduled_worker_codes) == 1:
                    # changed flag is moved to step()
                    assigned_job_dict["scheduled_share_status"] = "N"
                elif len(assigned_job.scheduled_worker_codes) > 1:
                    try:
                        if assigned_job.scheduled_worker_codes.index(a_slot.worker_id) == 0:
                            assigned_job_dict["scheduled_share_status"] = "P"
                        else:
                            assigned_job_dict["scheduled_share_status"] = "S"
                    except ValueError as ve:
                        log.error(f"Failed to find worker status, job = {assigned_job_dict}")
                        print(ve)
                        continue
                else:
                    log.error(f"Lost assigned worker ID, job = {assigned_job_dict}")
                    continue

                # assigned_job["requested_start_day"] = assigned_job["requested_start_day"]
                assigned_job_dict["scheduled_primary_worker_id"] = a_slot.worker_id

                assigned_job_dict["scheduled_travel_prev_code"] = pre_job_code
                assigned_job_dict["scheduled_travel_minutes_before"] = prev_travel_minutes

                assigned_job_dict["prev_geo_longitude"] = current_start_loc[0]  # .geo_longitude
                assigned_job_dict["prev_geo_latitude"] = current_start_loc[1]  # .geo_latitude
                assigned_job_dict["prev_location_type"] = current_start_loc[2]  # .geo_latitude

                current_start_loc = assigned_job.location

                if a_slot.next_slot_code is not None:  # End of original daily working hour
                    pre_job_code = assigned_job_code
                else:
                    pre_job_code = "__HOME"

                job_solution.append(assigned_job_dict)
                inplanning_job_index_set.add(assigned_job_code)

                if len(assigned_job_dict["scheduled_worker_codes"]) > 1:
                    for worker_code in assigned_job_dict["scheduled_worker_codes"]:
                        shared_prev_jobs[(worker_code, assigned_job_code)] = pre_job_code

                pre_job_code = assigned_job.job_code

        # In this loop, it collects Only U-planned jobs, which are not available from working time slots

        for job_code, new_job in self.jobs_dict.items():
            if new_job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
                print(f"pause for debugging {kandbox_config.DEBUGGING_JOB_CODE_SET }")
            if job_code in inplanning_job_index_set:
                continue
            if not new_job.is_active:  # events and appt can not be U anyway
                log.warn(f"job={ job_code} is skipped from solution because is_active == False")
                continue

            if new_job.planning_status != JobPlanningStatus.UNPLANNED:
                # Not available in slot, a problem to investigate
                if (new_job.scheduled_start_minutes + new_job.scheduled_duration_minutes < query_start_minutes) | (new_job.scheduled_start_minutes > query_end_minutes):
                    log.warn(
                        f"solution skipped job_code={new_job.job_code}, minutes = {query_start_minutes} not in {query_start_minutes} -- {query_end_minutes}"
                    )
                    continue

                log.error(f"job={job_code} is in planning, but not in inplanning_job_index_set")
                continue

            new_job_dict = dataclasses.asdict(new_job)
            try:  # TODO, not necesasary 2020-10-27 15:55:09

                # new_job_dict["scheduled_start_minutes"] = self.jobs[job_index]["requested_start_minutes"]
                # new_job_dict["scheduled_start_day"] = self.jobs[job_index]["requested_start_day"]
                new_job_dict["scheduled_duration_minutes"] = new_job.requested_duration_minutes
                new_job_dict["scheduled_primary_worker_id"] = new_job.requested_primary_worker_code

            except:
                # TODO, duan, 2020-10-20 16:20:36 , why?
                print("debug duan todo, appointment why?")
                continue

            new_job_dict["scheduled_start_datetime"] = self.env_decode_from_minutes_to_datetime(
                new_job_dict["scheduled_start_minutes"])
            new_job_dict["scheduled_share_status"] = "N"
            new_job_dict["scheduled_travel_prev_code"] = "__HOME"
            new_job_dict["scheduled_travel_minutes_before"] = 0

            job_solution.append(new_job_dict)

        return job_solution

    def get_planner_score_stats(self, include_slot_details=False):

        assigned_job_stats = {}

        inplanning_job_index_set = set()
        shared_prev_jobs = {}
        total_travel_minutes = 0

        sorted_slot_codes = sorted(list(self.slot_server.time_slot_dict.keys()))
        pre_job_code = "__HOME"
        prev_slot = None
        current_worker_id = "NOT_EXIST"
        slot_details = {}
        # In this loop, it first collects Only all (I/P) in/planned jobs, which are available from working time slots
        for slot_code in sorted_slot_codes:
            # for work_time_i in  range(len( self.workers_dict[worker_code]['assigned_jobs'] ) ): # nth assigned job time unit.
            if slot_code in kandbox_config.DEBUGGING_SLOT_CODE_SET:
                log.debug("debug atomic_slot_delete_and_add_back")

            try:
                a_slot = self.slot_server.get_slot(self.redis_conn.pipeline(), slot_code)
                the_assigned_codes = sorted(
                    a_slot.assigned_job_codes,
                    key=lambda jc: self.jobs_dict[jc].scheduled_start_minutes,
                )
            except KeyError as ke:
                log.error(
                    f"unknown worker code during get_planner_score_stats, or unknown job codes to the env. slot_code = {slot_code}, error = {str(ke)}")
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

            if a_slot.worker_id != current_worker_id:
                current_start_loc = a_slot.start_location
            elif (a_slot.slot_type == TimeSlotType.FLOATING) or (a_slot.prev_slot_code is None):
                current_start_loc = a_slot.start_location
            # if a_slot.slot_type in (TimeSlotType.JOB_FIXED, TimeSlotType.FLOATING):
            current_worker_id = a_slot.worker_id
            try:
                the_assigned_codes = sorted(
                    a_slot.assigned_job_codes,
                    key=lambda jc: self.jobs_dict[jc].scheduled_start_minutes,
                )
            except KeyError as ke:
                log.error(f"not all job codes are in env. a_slot = {a_slot}, error = {str(ke)}")
                print(ke)
                continue

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

                inplanning_job_index_set.add(assigned_job.job_code)
                current_start_loc = assigned_job.location

        # In this loop, it collects Only U-planned jobs, which are not available from working time slots
        unplanned_job_count = 0
        for job_code, new_job in self.jobs_dict.items():
            if job_code in inplanning_job_index_set:
                continue
            if new_job.job_type == JobType.ABSENCE:
                continue

            if not new_job.is_active:  # events and appt can not be U anyway
                log.warn(f"job={ job_code} is skipped from solution because is_active == False")
                continue

            if new_job.planning_status == JobPlanningStatus.UNPLANNED:
                unplanned_job_count += 1
            elif new_job.planning_status in (JobPlanningStatus.FINISHED, ):
                continue
            elif new_job.planning_status in (JobPlanningStatus.PLANNED, ):
                if (new_job.scheduled_start_minutes + new_job.scheduled_duration_minutes < self.get_env_planning_horizon_start_minutes()) | (new_job.scheduled_start_minutes >
                                                                                                                                             self.get_env_planning_horizon_end_minutes()):
                    log.warn(
                        f"solution skipped job_code={new_job.job_code}, minutes = {new_job.scheduled_start_minutes} not in planning window")
                    continue
                # else:
                #     log.error(f"Why not in slots? PLANNED, job_code = {job_code}")
            # else:
            #     log.error(f"Why not in slots? INPLANNING, job_code = {job_code}")
        onsite_working_minutes = sum(
            [assigned_job_stats[j]["requested_duration_minutes"] for j in assigned_job_stats])
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
            total_overtime_minutes += sum([self.workers_dict[w].used_overtime_minutes[day_seq]
                                          for day_seq in self.workers_dict[w].used_overtime_minutes.keys()])
        if inplanning_job_count + unplanned_job_count <= 0 or onsite_working_minutes <= 0:
            overall_score = 0
        else:
            overall_score = ((onsite_working_minutes / (total_travel_minutes + onsite_working_minutes)) + (inplanning_job_count / (inplanning_job_count + unplanned_job_count)) -
                             (total_overtime_minutes / onsite_working_minutes))

        planner_score_stats = {
            "overall_score": overall_score,
            "score": "{:.3f}".format(overall_score),
            "total_travel_minutes": int(total_travel_minutes),
            "inplanning_job_count": inplanning_job_count,
            "unplanned_job_count": unplanned_job_count,
            "visible_job_count": len(self.jobs_dict),
            "onsite_working_minutes": onsite_working_minutes,
            "planning_window": f"{planning_start} ~ {planning_end}",
            "total_overtime_minutes": total_overtime_minutes,
            "slot_details": slot_details,
        }
        return planner_score_stats

    def get_planning_window_days_from_redis(self) -> set:
        days_on_redis = self.redis_conn.hgetall(self.get_env_planning_day_redis_key())

        existing_working_days = set([int(di) for di in days_on_redis.keys()])
        return existing_working_days

    # **----------------------------------------------------------------------------
    # ## Extended functions
    # **----------------------------------------------------------------------------

    def _reset_horizon_start_minutes(self):
        self.env_start_datetime = datetime.strptime(
            self.config["env_start_day"], kandbox_config.KANDBOX_DATE_FORMAT
        )
        if PLANNER_SERVER_ROLE == "trainer":
            # Respect the config passed in , not from database.
            flex_form_data = self.config
        else:
            flex_form_data = get_or_add_redis_team_flex_data(
                redis_conn=self.redis_conn, team_id=self.config["team_id"])
        if flex_form_data.get('fixed_env_start_day_flag', False):
            # if "env_start_day" in self.config.keys():
            # Report exception if there is no env_start_day
            if self.config["env_start_day"] == "_":
                self.horizon_start_minutes = None
            else:
                begin_skip_minutes = int(flex_form_data.get('begin_skip_minutes', 0))
                self.horizon_start_minutes = self.env_encode_from_datetime_to_minutes(
                    self.env_start_datetime) + begin_skip_minutes  # + 480
                # self.horizon_start_minutes = self.config["horizon_start_minutes"]
        else:
            self.horizon_start_minutes = None

    def mutate_refresh_planning_window_from_redis(self) -> bool:
        existing_working_days = self.get_planning_window_days_from_redis()
        self.existing_working_days = existing_working_days

        if len(existing_working_days) < 1:
            min_horizon_start_seq = 0
            max_horizon_start_seq = 4
        else:
            min_horizon_start_seq = min(existing_working_days)
            max_horizon_start_seq = max(existing_working_days)

        self._reset_horizon_start_minutes()
        # min_planning_day_seq = int(self.get_env_planning_horizon_start_minutes() / 1440)
        # max_planning_day_seq = max(existing_working_days)
        self.config["nbr_of_days_planning_window"] = (
            max_horizon_start_seq - min_horizon_start_seq + 1)
        log.info(
            f"Refresh planning window done, min_horizon_start_seq= {min_horizon_start_seq}, max_horizon_start_seq = {max_horizon_start_seq}")

    def _get_new_working_days(self) -> set:
        # Hold this value and do not call it multiple times in a loop
        today_start_date = self.env_decode_from_minutes_to_datetime(
            self.get_env_planning_horizon_start_minutes())

        # Now find out all current days in planning windows.
        new_working_days = set()
        for day_i in range(100):
            new_start_date = today_start_date + timedelta(days=day_i)
            day_seq = (new_start_date - self.data_start_datetime).days
            new_weekday = self.env_encode_day_seq_to_weekday(day_seq)
            new_start_date_str = datetime.strftime(
                new_start_date, kandbox_config.KANDBOX_DATE_FORMAT)

            if new_start_date_str in self.national_holidays:
                # This is a holiday. It overwrites weekly settings from weekly_working_days_flag.
                continue

            if self.weekly_working_days_flag[new_weekday]:
                # This is a working day
                self.daily_working_flag[day_seq] = True
                new_working_days.add(day_seq)
            else:
                self.daily_working_flag[day_seq] = False

            if len(new_working_days) >= self.config["planning_working_days"]:
                break
        # It may reduce several days of holidays
        return new_working_days

    def mutate_extend_planning_window(self) -> bool:
        self._reset_horizon_start_minutes()
        existing_working_days = self.get_planning_window_days_from_redis()
        self.existing_working_days = existing_working_days

        today_start_date = self.env_decode_from_minutes_to_datetime(
            self.get_env_planning_horizon_start_minutes())
        horizon_day_seq = self.env_encode_from_datetime_to_day_with_validation(today_start_date)
        new_working_days = self._get_new_working_days()

        # 2020-11-17 06:27:47
        # If planning window start with Sunday, new_working_days does not contain it, horizon_day_seq should still point to Sunday
        self.config["nbr_of_days_planning_window"] = max(new_working_days) - horizon_day_seq + 1

        if new_working_days <= existing_working_days:
            log.warn(
                f"There is no change in planning day when it is called at {datetime.now()}). existing_working_days={existing_working_days}. Maybe we have passed a weekend?  ")
            return False

        # Update nbr_of_days_planning_window, which may be larger than specified self.config["DaysForPlanning"]
        # nbr_of_days_planning_window may contain
        self.existing_working_days = new_working_days
        days_to_add = new_working_days - existing_working_days
        days_to_delete = existing_working_days - new_working_days

        for day_seq in days_to_delete:
            self._mutate_planning_window_delete_day(day_seq)
            log.info(f"A planning day (day_seq = {day_seq}) is purged out of planning window.  ")
        if len(days_to_add) > 0:
            self.reload_data_from_db_adapter(
                start_datetime=self.env_decode_from_minutes_to_datetime(
                    1440 * int(self.get_env_planning_horizon_start_minutes() / 1440)),
                end_datetime=self.env_decode_from_minutes_to_datetime(
                    self.get_env_planning_horizon_end_minutes())
            )
        for day_seq in days_to_add:
            if self._mutate_planning_window_add_day(day_seq):
                # log.info(
                #     f"A planning day (day_seq = {day_seq}) is added into the planning window.  "
                # )
                pass
            else:
                log.error(f"Failed to add a planning day (day_seq = {day_seq})  .  ")
            self.mutate_replay_jobs_single_working_day(day_seq)

        self.kafka_server.post_refresh_planning_window()
        return True

    # fmt:off
    def _mutate_planning_window_delete_day(self, day_seq: int) -> bool:
        """ Right now, I delete all slots before this day. """
        today_start_date = self.data_start_datetime + timedelta(days=day_seq)
        # today_start_date_str = datetime.strftime(today_start_date, kandbox_config.KANDBOX_DATE_FORMAT)

        today_weekday = self.env_encode_day_seq_to_weekday(day_seq)
        self.redis_conn.hdel(self.get_env_planning_day_redis_key(), *[day_seq])

        for worker_code in self.workers_dict.keys(): 
            if len(self.workers_dict[worker_code].weekly_working_slots[today_weekday]) > 0:
                # There is a valid working slot 
                working_day_end = (day_seq) * 1440 + \
                    self.workers_dict[worker_code].weekly_working_slots[today_weekday][-1][1]
            else:
                working_day_end = (day_seq + 1) * 1440

            # Do not extending to the whole day if it less than the whole, because there may be time slots from next day, with < 0 start time.??? allowed?
            # forced actions to outside of working hour.
            # However, this may accidently delete
            self.slot_server.delete_slots_from_worker(
                worker_code=worker_code,
                start_minutes=0,  # day_seq * 1440,
                end_minutes=working_day_end,
            )
            # TODO
            # w.linear_working_slots.remove(slot)

    # fmt:on

    def _mutate_planning_window_add_day(self, day_seq: int) -> bool:
        today_start_date = self.data_start_datetime + timedelta(days=day_seq)
        today_start_date_str = datetime.strftime(
            today_start_date, kandbox_config.KANDBOX_DATE_FORMAT)

        today_weekday = self.env_encode_day_seq_to_weekday(day_seq)
        """
        Of course it must be inside this.

        if day_seq in self.daily_working_flag.keys():
            log.error(
                f"The planning_window slot (day_seq = {day_seq}) is aready added. It is skipped this time."
            )
            return False
        """

        # self.redis_conn.hset(self.get_env_planning_day_redis_key(), mapping={day_seq: 0})

        if today_start_date_str in self.national_holidays:
            # This is a holiday. It overwrites weekly settings.
            log.error(f"The planning_window slot (day_seq = {day_seq}) is in holiday.")
            return False

        if not self.weekly_working_days_flag[today_weekday]:
            log.error(f"The planning_window slot (day_seq = {day_seq}) is in weekly rest day .")
            return False

        self.redis_conn.hset(self.get_env_planning_day_redis_key(),
                             key=day_seq,
                             value=f"{today_start_date_str}_{day_seq*1440}->{(day_seq+1)*1440}"
                             # mapping={day_seq: f"{today_start_date_str}_{day_seq*1440}->{(day_seq+1)*1440}"},
                             )

        for w in self.workers:

            self._mutate_planning_window_add_worker_day(worker_code=w.worker_code, day_seq=day_seq)

        log.info(
            f"The planning window slot (day_seq = {day_seq}, today_start_date_str = {today_start_date_str}) is added succesfully!")
        return True

    def _mutate_planning_window_add_worker_day(
        self, worker_code: str, day_seq: int
    ) -> WorkingTimeSlot:
        # I first calculate the working slot in this day
        min_day_seq = min(self.existing_working_days)

        w = self.workers_dict[worker_code]
        today_weekday = self.env_encode_day_seq_to_weekday(day_seq)
        for week_day_slot_i, week_day_slot in enumerate(w.weekly_working_slots[today_weekday]):
            slot = (
                day_seq * 1440 + week_day_slot[0],
                day_seq * 1440 + week_day_slot[1],
            )
            if slot[1] - slot[0] < 1:
                return False
            # Check where there are existing slots overlapping with this working slot from redis.
            overlap_slots = self.slot_server.get_overlapped_slots(
                worker_id=worker_code,
                start_minutes=slot[0],
                end_minutes=slot[1],  # (day_seq + 1) * 1440,
            )
            w.linear_working_slots.append(slot)

            if len(overlap_slots) > 0:
                overlap_slots_sorted = sorted(overlap_slots, key=lambda x: x.start_minutes)
                new_slot_start = slot[0]
                # new_slot_end = overlap_slots_sorted[0].end_minutes
                new_start_location = w.weekly_start_gps[today_weekday]
                # new_end_location = w.weekly_end_gps[today_weekday]

                for aslot_i, aslot_ in enumerate(overlap_slots_sorted):
                    if aslot_.slot_type == TimeSlotType.FLOATING:
                        log.error(
                            f"WORKER:{worker_code}:DAY:{day_seq}:SLOT:{slot}, Encountered existing floating working time slot ({aslot_.start_minutes}->{aslot_.end_minutes}) while trying to add working slot. Aborted."
                        )
                        return False

                    log.warn(
                        f"WORKER:{worker_code}:DAY:{day_seq}:SLOT:{slot}, Encountered existing working time slot ({aslot_.start_minutes}->{aslot_.end_minutes}) while trying to add working slot {slot}")
                    new_slot_end = aslot_.start_minutes
                    new_end_location = aslot_.start_location

                    curr_slot = self.slot_server.add_single_working_time_slot(
                        w=w,
                        start_minutes=new_slot_start,
                        end_minutes=new_slot_end,
                        start_location=new_start_location,
                        end_location=new_end_location,
                    )
                    if aslot_i == 0:
                        if min_day_seq == day_seq:
                            self.workers_dict[w.worker_code].curr_slot = curr_slot

                    new_slot_start = aslot_.end_minutes
                    new_start_location = aslot_.end_location

                # Add the last time slot if present
                if new_slot_start < slot[1]:
                    self.slot_server.add_single_working_time_slot(
                        w=w,
                        start_minutes=new_slot_start,
                        end_minutes=slot[1],
                        start_location=new_start_location,
                        end_location=w.weekly_end_gps[today_weekday],
                    )
            else:
                curr_slot = self.slot_server.add_single_working_time_slot(
                    w=w,
                    start_minutes=slot[0],
                    end_minutes=slot[1],
                    start_location=w.weekly_start_gps[today_weekday],
                    end_location=w.weekly_end_gps[today_weekday],
                )

            log.debug(
                f"The worker_day slot (start_minutes = {slot[0]}, w.worker_code = {w.worker_code}) is added succesfully!")
        return True

    # ***************************************************************
    # Mutation functions. Here they are not locked ... The lock will happen only when persisting to redis. 
    # They are named as C-R-U-D, therefore Create will add the object to the ENV, Update will update existing one.
    # ***************************************************************

    def mutate_worker_add_overtime_minutes(self, worker_code: str, day_seq: int, net_overtime_minutes: int, post_changes_flag=False) -> bool:
        added_successful = True
        if day_seq not in self.workers_dict[worker_code].used_overtime_minutes.keys():
            log.warn(
                f"rejected, day_seq={day_seq} not in self.workers_dict[{worker_code}].used_overtime_minutes.keys()")
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
                log.warn(
                    f"Overtime={total_overtime} is larger than limit for worker={worker_code}, key={limit_days_key}")
                added_successful = False
        if post_changes_flag:
            self.kafka_server.post_env_message(
                message_type=KafkaMessageType.UPDATE_WORKER_ATTRIBUTES,
                payload=[{
                    worker_code: {
                        "used_overtime_minutes": self.workers_dict[worker_code].used_overtime_minutes
                    }
                }],
            )

        # if worker_code == "MY|D|3|CT02":
        #     log.debug(
        #         f"{worker_code} - {net_overtime_minutes} = {self.workers_dict[worker_code].used_overtime_minutes}"
        #     )

        return added_successful

    def mutate_create_worker(self, new_worker: Worker):
        # For now it does not trigger re-planning affected, 2020-10-25 10:09:19

        if new_worker.worker_code in self.workers_dict.keys():
            log.error(
                f"mutate_create_worker: error, worker already existed: {new_worker.worker_code}")
            return False
            # raise ValueError("duplicate worker code '{0}' found".format(new_worker.worker_code))
        self.workers.append(new_worker)
        self.workers_dict[new_worker.worker_code] = new_worker
        self.workers_dict[new_worker.worker_code].worker_index = len(self.workers) - 1
        for day_seq in self.daily_working_flag.keys():
            self._mutate_planning_window_add_worker_day(
                worker_code=new_worker.worker_code, day_seq=day_seq)

        log.info(
            f"mutate_create_worker: successfully added worker, code = {new_worker.worker_code}")

    def mutate_update_worker(self, new_worker: Worker):
        # I assume it is Unplanned for now, 2020-04-24 07:22:53.
        # No replay
        if new_worker.worker_code not in self.workers_dict.keys():
            log.error("mutate_update_worker: The worker code '{0}' is not found".format(
                new_worker.worker_code))
            return
            # raise ValueError("The worker code '{0}' is not found".format(new_worker.worker_code))
        w_idx = self.workers_dict[new_worker.worker_code].worker_index
        if self.workers[w_idx].worker_code != new_worker.worker_code:
            log.error(
                f"worker_index mismatch during mutate_update_worker {new_worker}. Failed to update")
            # TODO, clean up and reset index.
            return
        self.workers_dict[new_worker.worker_code] = new_worker
        self.workers_dict[new_worker.worker_code].worker_index = w_idx
        self.workers[w_idx] = self.workers_dict[new_worker.worker_code]
        log.info(f"mutate_update_worker: success, worker is updated with new profile: {new_worker}")

    def mutate_create_appointment(self, new_job: Appointment, auto_replay=True):
        # I assume it is Unplanned for now, 2020-04-24 07:22:53.
        # No replay
        if new_job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
            log.debug(f"debug appt {kandbox_config.DEBUGGING_JOB_CODE_SET}")
        if new_job.job_code in self.jobs_dict.keys():
            log.warn(f"APPT:{new_job.job_code}: mutate_create_appointment, job already existed", )
            # raise ValueError("duplicate job code '{0}' found".format(new_job.job_code))
            return
            # new_job.job_index = job_index

        self.jobs.append(new_job)
        job_index = len(self.jobs) - 1
        new_job.job_index = job_index
        self.jobs_dict[new_job.job_code] = new_job

        if new_job.included_job_codes is None:
            new_job.included_job_codes = []

        # First return occupied slots from included jobs
        for existing_job_code in new_job.flex_form_data["included_scheduled_visit_ids"].split(";"):
            # remove the job from time slots
            # step current appointment.
            stripped_job_code = existing_job_code.strip()
            try:
                v = self.jobs_dict[stripped_job_code]

            except KeyError:
                print(
                    f"_get_appointment_form_dict: at least one visit is not found job_code={stripped_job_code.strip()}, ",
                    new_job.flex_form_data["all_verified"],
                )
                # new_job.flex_form_data["all_verified"] = False
                return False
            if stripped_job_code not in new_job.included_job_codes:
                new_job.included_job_codes.append(stripped_job_code)

            self.jobs_dict[stripped_job_code].is_active = False
            if self.jobs_dict[stripped_job_code].planning_status == JobPlanningStatus.UNPLANNED:
                # log.warn
                log.warn(
                    f"APPT:{new_job.job_code}:JOB:{stripped_job_code}: U status job () is included in appointment (). It is simply applied without modifying job.")
                continue
        # Then apply this appointment action
        # if False:
        # if not kandbox_config.DEBUG_ENABLE_APPOINTMENT_REPLAY:
        #     return
        if auto_replay:
            release_success, info = self.slot_server.release_job_time_slots(
                self.jobs_dict[stripped_job_code])
            if not release_success:
                log.warn(
                    f"Error releasing job (code={stripped_job_code}) inside the appointment ({new_job.job_code}), but I will continue appointment replay ...")
                # return False

            self.mutate_replay_appointment(job=new_job)

        self.redis_conn.hmset(
            "{}{}".format(kandbox_config.APPOINTMENT_ON_REDIS_KEY_PREFIX, new_job.job_code),
            {
                "rec_round": 0,
                "planning_status": "PENDING",
                "team_id": self.config["team_id"]
            },
        )

    def mutate_replay_appointment(self, job: Appointment):
        if (job.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes()) or (job.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()):
            log.warn(
                f"Start time of appointment ({job.job_code}={job.scheduled_start_minutes}) is out of planning window, skippped replaying")
            return False
        action_dict = self.gen_action_dict_from_appointment(job)
        self.mutate_update_job_by_action_dict(a_dict=action_dict, post_changes_flag=False)

        return True
        # TODO, Third, trigger the heuristic search for recommendations

    # There is no update_appointment. This should be done by API->commit
    # def mutate_update_appointment(self, new_job):
    # Deprecated 2020-12-16 20:57:17
    # Reason: I keep original appt code for multiple times re-scheduling
    def mutate_update_job_code__TODEL(self, old_job_code: str, new_job_code: str):
        # I assume it is Unplanned for now, 2020-04-24 07:22:53.
        # No replay
        if old_job_code not in self.jobs_dict.keys():
            # raise ValueError("Job code '{0}' not found".format(old_job_code))
            log.error("Job code '{0}' not found".format(old_job_code))
            return
        if self.jobs_dict[old_job_code].job_type != JobType.APPOINTMENT:
            log.error("ERROR: ONLY appointment job code can be changed, but  {}  is {} ".format(
                old_job_code, self.jobs_dict[old_job_code].job_type))
        old_job = self.jobs_dict[old_job_code]
        old_job.job_code = new_job_code
        del self.jobs_dict[old_job_code]
        self.jobs_dict[new_job_code] = old_job

        # location in self.jobs remains untouched.
        # TODO, send to kafka.
        log.warn(
            f"mutate_update_job_code:APPT:{old_job_code}:NEW_APPT:{new_job_code}: appointment code to updated to new one by {self.env_inst_code}. No more recommendations to any of them.")

    def mutate_delete_appointment(self, job_code):
        # I assume it is Unplanned for now, 2020-04-24 07:22:53.
        # No replay
        if job_code not in self.jobs_dict.keys():
            log.error("mutate_delete_appointment: appt does not exist: ", job_code)
            return
        self.jobs_dict[job_code].is_active = False
        job_index = self.jobs_dict[job_code].job_index
        curr_appt = self.jobs_dict[job_code]

        release_success_flag, info = self.slot_server.release_job_time_slots(job=curr_appt)
        if not release_success_flag:
            log.warn(
                f"Error whiling tring to release existing appoitnment slot, {curr_appt.job_code}")

        # Restore job status after removing covering appointment.
        for included_job_code in curr_appt.included_job_codes:
            self.jobs_dict[included_job_code].is_active = True
            if self.jobs_dict[included_job_code].planning_status != JobPlanningStatus.UNPLANNED:
                self.mutate_replay_job(job=self.jobs_dict[included_job_code])

        self.jobs_dict[job_code] = None
        del self.jobs_dict[job_code]

        try:
            if self.jobs[job_index].job_code != job_code:
                log.error(f"mutate_delete_appointment: job code mismatch {job_code}")
            else:
                del self.jobs[job_index]
        except:
            log.error(
                f"mutate_delete_appointment:exception: job code mismatch job_code={job_code}, job_index = {job_index}, ")
        # Remove appt from redis recommendation frontend
        self.redis_conn.delete("{}{}".format(
            kandbox_config.APPOINTMENT_ON_REDIS_KEY_PREFIX, job_code))
        # Remove recommendations from redis
        for rec_code in self.redis_conn.scan_iter(f"{self.get_recommendation_job_key(job_code=job_code, action_day=-1)}*"):
            self.redis_conn.delete(rec_code)

        log.info(f"APPT:{job_code} is purged out of env {self.env_inst_code}")

    def mutate_create_worker_absence(self, new_job: Absence, auto_replay=True):

        if new_job.job_code in self.jobs_dict.keys():
            print("add_job: error, job already existed: ", new_job.job_code)
            return
            # raise ValueError("duplicate job code '{0}' found".format(new_job.job_code))
            # new_job.job_index = job_index

        self.jobs.append(new_job)
        job_index = len(self.jobs) - 1
        new_job.job_index = job_index
        self.jobs_dict[new_job.job_code] = new_job
        if auto_replay:
            self.mutate_replay_worker_absence(job=new_job)
        log.debug(f"ABSENCE:{new_job.job_code}: the absence is created/added into env.", )

    def mutate_replay_worker_absence(self, job: Absence):
        if (job.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes()) or (job.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()):
            log.warn(
                f"Start time of absence ({job.job_code}={job.scheduled_start_minutes}) is out of planning window, skippped replaying")
            return False
        action_dict = self.gen_action_dict_from_worker_absence(job)
        self.mutate_update_job_by_action_dict(a_dict=action_dict, post_changes_flag=False)
        return True

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
            log.warn(f"mismatched job_index while adding job {new_job.job_code}")
            # return
        self.jobs[curr_job_index] = new_job
        self.jobs_dict[new_job.job_code] = new_job

        log.info(
            f"Successfully updated job metadata, no schedulling action done. code = {new_job.job_code}")
        # Then I skip appling scheduling action

    def mutate_replay_job(self, job: Appointment):
        if (job.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes()) or (job.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()):
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

    def mutate_complete_job(self, job_code):
        # Mark a job as completed and optionally remove it.

        if job_code not in self.jobs_dict.keys():
            log.error("mutate_complete_job: error, job not exist: ", job_code)
            return
        curr_job = self.jobs_dict[job_code]

        # Keep the scheduling information intact as before

        release_success_flag, info = self.slot_server.release_job_time_slots(job=curr_job)
        if not release_success_flag:
            log.warning(
                f"Error in release_job_time_slots, {curr_job.job_code}, error = {str(info)}"
            )
            return False

        curr_job.planning_status = JobPlanningStatus.FINISHED
        self.jobs_dict[job_code] = curr_job

        log.debug(f"Successfully mutate_complete_job. code = { job_code}")

    def process_rule_check_info(self, rule_check_info):

        # This items IS available in depot/warehouse.
        # Then I will add a virtual replenish job and move on.
        # The replenish job is only added to primary worker as all_slots[0]
        for a_rule_result in rule_check_info.messages:
            # print(a_rule_result)
            if (a_rule_result.score_type == "Requested Items") and (a_rule_result.score == 0):
                total_loaded_items = a_rule_result.metrics_detail["total_loaded_items"]
                total_requested_items = a_rule_result.metrics_detail["total_requested_items"]
                replenish_job = self.mutate_create_replenish_job(
                    slot=a_rule_result.metrics_detail["slot"],
                    total_loaded_items=total_loaded_items,
                    total_requested_items=total_requested_items
                )
                if replenish_job is None:
                    return ActionScoringResultType.ERROR
            elif a_rule_result.score == -1:
                return ActionScoringResultType.ERROR
        return ActionScoringResultType.OK

    def mutate_update_job_by_action_dict(self, a_dict: ActionDict, post_changes_flag: bool = False) -> SingleJobCommitInternalOutput:
        if a_dict.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
            print(f"pause for {a_dict.job_code}")
        if post_changes_flag:
            if PLANNER_SERVER_ROLE == "recommendation":
                log.warn(f"recommender should not post changes, setting to false")
                # post_changes_flag = False
        # TODO If there is not enough capacities without considering travel and time slot, reject it
        if a_dict.job_code not in self.jobs_dict.keys():
            log.error("add_job: error, job already existed: ", a_dict.job_code)
            return
        # duplicated check with above.
        # if len(self.jobs_dict) < 1:
        #     log.error("No jobs to mutate")
        #     return
        if self.current_job_i >= len(self.jobs):
            self.current_job_i = 0
        # if self.jobs[self.current_job_i].job_code != a_dict.job_code:
        #     self.current_job_i = self.jobs_dict[a_dict.job_code].job_index
        # log.warn(
        #     f"job_code = { a_dict.job_code} missmatching.  self.jobs[self.current_job_i].job_code != a_dict.job_code"
        # )

        curr_job = self.jobs_dict[a_dict.job_code]

        # TODO, verify that this is not duplicated action by itself. 2020-10-30 17:25:51
        job_commit_output = SingleJobCommitInternalOutput(
            status_code=ActionScoringResultType.ERROR,
            messages=[],
            nbr_changed_jobs=0,
            new_job_code="",
        )
        if a_dict.scheduled_duration_minutes < 1:
            log.warn(
                f"action is rejected  because scheduled_duration_minutes < 1, action = {a_dict}")
            job_commit_output.messages.append(
                f"action is rejected  because scheduled_duration_minutes < 1")
            return job_commit_output
        if curr_job.planning_status in {JobPlanningStatus.PLANNED}:
            if (curr_job.job_type == JobType.JOB) and (not a_dict.is_forced_action):
                job_commit_output.messages.append(
                    f"Failed to change job planning because planning_status == PLANNED and not is_forced_action")
                return job_commit_output
        if (curr_job.planning_status == JobPlanningStatus.UNPLANNED) & (a_dict.action_type == ActionType.UNPLAN):
            job_commit_output.messages.append(
                f"Job is already unplanned, and can not be unplanned.")
            job_commit_output.status_code = ActionScoringResultType.OK
            return job_commit_output

        if curr_job.planning_status in {
                JobPlanningStatus.IN_PLANNING,
                JobPlanningStatus.PLANNED,  # Here planned is only for replay
        }:

            if ((a_dict.action_type != ActionType.UNPLAN)
                    & (a_dict.scheduled_start_minutes == curr_job.scheduled_start_minutes)
                    & (a_dict.scheduled_worker_codes == curr_job.scheduled_worker_codes)
                    & (not a_dict.is_forced_action)):
                job_commit_output.messages.append(
                    f"Job is in-planning, the new scheduled_start_minutes, scheduled_worker_codes are same.")
                job_commit_output.status_code = ActionScoringResultType.OK
                return job_commit_output

            if not curr_job.is_replayed:
                log.warn(f"job ({curr_job.job_code}) is not replayed for releasing?")

            # Now we first release previous slot
            release_success_flag, info = self.slot_server.release_job_time_slots(job=curr_job)
            if (not release_success_flag) & curr_job.is_replayed & (not a_dict.is_forced_action):
                log.warn(f"Error in release_job_time_slots, {curr_job.job_code}")
                job_commit_output.messages.append(
                    f"Failed to release job slot for {curr_job.job_code}, release_success_flag = false, error = {str(info)}")
                return job_commit_output

            if a_dict.action_type == ActionType.UNPLAN:
                curr_job.planning_status = JobPlanningStatus.UNPLANNED
                if self.run_mode != EnvRunModeType.REPLAY:
                    job_commit_output.nbr_changed_jobs += 1
                    curr_job.is_changed = True
                    self.changed_job_codes_set.add(curr_job.job_code)
                    if post_changes_flag:
                        self.commit_changed_jobs(changed_job_codes_set={curr_job.job_code})

                job_commit_output.status_code = ActionScoringResultType.OK
                log.info(f"JOB:{curr_job.job_code}: job is unplanned successfully. ")

                return job_commit_output
            else:
                log.debug(
                    f"JOB:{curr_job.job_code}: job is unplanned temporary by releasing slot for inplan again. release_success_flag = {release_success_flag}")

        # a normal job duration is 200 minutes. The jobs before 200 minute will not impact current planning window
        # TODO
        if (a_dict.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes() - 200) or (a_dict.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()):
            log.warn(
                f"action is rejected  because scheduled_start_minutes is out of planning window{(self.get_env_planning_horizon_start_minutes(), self.get_env_planning_horizon_end_minutes())}, action = {a_dict}")
            job_commit_output.messages.append(
                f"action is rejected  because scheduled_start_minutes is out of planning window")
            return job_commit_output

        if not a_dict.is_forced_action:
            rule_check_info = self._check_action_on_rule_set(a_dict)
            if rule_check_info.status_code != ActionScoringResultType.OK:
                new_status_code = self.process_rule_check_info(rule_check_info)
                if new_status_code != ActionScoringResultType.OK:
                    job_commit_output.messages.append(rule_check_info)
                    return job_commit_output  # False, rule_check_info  # {'message':'ok'}

        success_flag, info = self.slot_server.cut_off_time_slots(action_dict=a_dict)
        if not success_flag:
            job_commit_output.messages.append(info)
            if a_dict.is_forced_action:
                job_commit_output.status_code = ActionScoringResultType.WARNING
                log.error(f"failed to cut_off_time_slots for replaying job = {a_dict.job_code} ")
                # TODO, send to kafka for inspection
            else:
                job_commit_output.status_code = ActionScoringResultType.ERROR
                # self._move_to_next_unplanned_job()
                return job_commit_output
        else:
            curr_job.is_replayed = True

        if self.jobs_dict[a_dict.job_code].job_type == JobType.ABSENCE:
            # Do not need to update current job
            return job_commit_output
        #
        # Now update the job schedule status.
        #

        nbr_changed_jobs = 0

        if curr_job.job_type == JobType.APPOINTMENT:
            # Align up all jobs included inside the current apointment
            curr_start_minutes = curr_job.scheduled_start_minutes
            for _j_code in curr_job.included_job_codes:
                # APPT_Required==1 will make IN_PLANNING same as PLANNED
                self.jobs_dict[_j_code].planning_status = JobPlanningStatus.IN_PLANNING
                self.jobs_dict[_j_code].scheduled_start_minutes = curr_start_minutes
                self.jobs_dict[_j_code].scheduled_worker_codes = a_dict.scheduled_worker_codes
                self.jobs_dict[_j_code].scheduled_duration_minutes = self.get_encode_shared_duration_by_planning_efficiency_factor(
                    requested_duration_minutes=self.jobs_dict[_j_code].requested_duration_minutes,
                    nbr_workers=len(a_dict.scheduled_worker_codes),
                )
                self.jobs_dict[_j_code].is_active = False
                self.jobs_dict[_j_code].is_appointment_confirmed = True
                self.jobs_dict[_j_code].is_changed = True
                # It might be set in next curr_job.is_changed = True

                curr_start_minutes += self.jobs_dict[_j_code].scheduled_duration_minutes

                # Do not post individual jobs belonging to appt, as it will be posted by appt
        #
        # Now update the job with other 3 information: Tech, start, duration.
        #
        if curr_job.planning_status == JobPlanningStatus.UNPLANNED:
            curr_job.planning_status = JobPlanningStatus.IN_PLANNING
            self.nbr_inplanning += 1
            # self.expected_travel_time_so_far += self.job_travel_time_sample_list_static[
            #     self.current_job_i
            # ]        curr_job.scheduled_worker_codes = a_dict.scheduled_worker_codes
        curr_job.scheduled_worker_codes = a_dict.scheduled_worker_codes
        curr_job.scheduled_start_minutes = a_dict.scheduled_start_minutes
        # could be accross several days.
        curr_job.scheduled_duration_minutes = a_dict.scheduled_duration_minutes

        # Here I decide to publish the change or not
        if self.run_mode != EnvRunModeType.REPLAY:  # and (not a_dict.is_forced_action)

            # if curr_job.planning_status == JobPlanningStatus.UNPLANNED:

            self.changed_job_codes_set.add(curr_job.job_code)
            nbr_changed_jobs = len(self.changed_job_codes_set)
            # It might change multiple jobs
            if post_changes_flag:
                curr_job.is_changed = True
                self.commit_changed_jobs(changed_job_codes_set={curr_job.job_code})
        else:
            if post_changes_flag:
                log.error(f"Not allowed to post_changes_flag for EnvRunModeType.REPLAY")

        job_commit_output.status_code = ActionScoringResultType.OK
        job_commit_output.nbr_changed_jobs = nbr_changed_jobs

        log.debug(
            f"JOB:{curr_job.job_code}:WORKER:{a_dict.scheduled_worker_codes}:START_MINUTES:{a_dict.scheduled_start_minutes}: job is commited successfully. ")

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
            log.warn(
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
                sorted_assigned_job_codes = [s[1]
                                             for s in recommendation.job_plan_in_scoped_slots[ts_index]]
                set_result, info = self.slot_server.set_assigned_job_codes(
                    slot_code=slot_code, job_codes=sorted_assigned_job_codes)
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

        self.commit_changed_jobs(changed_job_codes_set=changed_job_codes_set)

        return output_result

    def commit_changed_jobs(self, changed_job_codes_set=set()):

        # for job in jobs:
        changed_jobs = []
        changed_job_codes = []
        self.changed_job_codes_set = changed_job_codes_set

        for job_code in self.changed_job_codes_set:
            job = self.jobs_dict[job_code]
            if job.is_changed:
                a_job = self.env_decode_single_job_to_dict(job)
                changed_jobs.append(a_job)
                # changed_job_codes.append(job.job_code)
            else:
                log.error("ERROR: tracked but job.is_changed == False")

        self.kp_data_adapter.save_changed_jobs(changed_jobs=changed_jobs)

        new_offset = self.post_changed_jobs(changed_job_codes_set=changed_job_codes_set)
        self.kp_data_adapter.set_team_env_window_latest_offset(offset=new_offset)

        # Reset all tracked changes.
        for job_code in self.changed_job_codes_set:
            self.jobs_dict[job_code].is_changed = False
        self.changed_job_codes_set = set()

    def post_changed_jobs(self, changed_job_codes_set):
        """This is used by ENV to post changed job to external"""

        jobs = []
        for j in changed_job_codes_set:
            job = self.jobs_dict[j]
            if job.scheduled_duration_minutes > job.requested_duration_minutes:
                log.error(
                    f"job.scheduled_duration_minutes>job.requested_duration_minutes, Error detected, post_changed_jobs skipped job_code = {job.job_code}, {job.scheduled_duration_minutes} > {job.requested_duration_minutes}"
                )
                continue
            new_job = copy.copy(job)
            new_job.location = JobLocationBase(*new_job.location[0:4])
            jobs.append(new_job)

        appt_included_jobs = []

        for job in jobs:
            if job.job_type == JobType.APPOINTMENT:
                # Loop through included jobs and re-arrange start time for them
                curr_start_minutes = job.scheduled_start_minutes
                for included_job_code in job.included_job_codes:
                    job_1 = copy.copy(self.jobs_dict[included_job_code])
                    job_1.location = JobLocationBase(*job_1.location[0:4])
                    job_1.scheduled_start_minutes = curr_start_minutes
                    curr_start_minutes += job_1.scheduled_duration_minutes

                    appt_included_jobs.append(job_1)

        self.kafka_server.post_env_out_message(
            message_type=KafkaMessageType.POST_CHANGED_JOBS, payload=jobs + appt_included_jobs)

        # return offset in internal kafka window
        return self.kafka_server.post_env_message(message_type=KafkaMessageType.REFRESH_JOB, payload=jobs + appt_included_jobs)

    def _calc_travel_minutes_difference(self, shared_time_slots_optimized, arranged_slots, current_job_code):

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
                ))

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

    def set_searching_worker_candidates(self, final_job: BaseJob):
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
        for worker_id in list(self.workers_dict.keys()):
            is_valid = True
            for a_rule in self.rule_set_worker_check:
                curr_job.scheduled_worker_codes = [worker_id]
                check_result = a_rule.evalute_normal_single_worker_n_job(self, job=curr_job)
                if check_result.score == -1:
                    is_valid = False
                    break

            if is_valid:
                all_qualified_worker_codes.add(worker_id)
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
        historical_serving_worker_distribution = curr_job.location.historical_serving_worker_distribution
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
            final_job.requested_primary_worker_code)

        if min_number_of_workers <= 1:
            for w_code in all_qualified_worker_codes:
                if (not self.workers_dict[w_code].flex_form_data["is_assistant"]) and ((w_code, ) not in candidate_dict.keys()):
                    candidate_dict[(w_code, )] = SCORE_Solo

            # It may overrite historical setting. But primary will highest priority
            try:
                candidate_dict[(curr_job.requested_primary_worker_code, )] = SCORE_Primary
            except:
                log.debug("WHY?")

        primary_worker_codes = (curr_job.requested_primary_worker_code, )
        if primary_worker_codes not in candidate_dict.keys():
            if min_number_of_workers <= 1:
                log.debug(f"requested worker not added! {primary_worker_codes}")
                candidate_dict[primary_worker_codes] = SCORE_Primary

        if self.workers_dict[curr_job.requested_primary_worker_code].belongs_to_pair is not None:
            primary_worker_codes = self.workers_dict[curr_job.requested_primary_worker_code].belongs_to_pair
            if primary_worker_codes not in candidate_dict.keys():
                log.debug(f"requested worker pair not added yet! {primary_worker_codes}")
                candidate_dict[primary_worker_codes] = SCORE_Primary

        qualified_secondary_worker_codes = sorted(
            list(all_qualified_worker_codes - set(primary_worker_codes)))

        shared_worker_count_to_check = shared_worker_count - {1}

        for share_count in shared_worker_count_to_check:
            # Primary must be default when shared.
            secondary_share_count = share_count - len(primary_worker_codes)
            if secondary_share_count < 1:
                continue

            for combined_worker in list(combinations(qualified_secondary_worker_codes, secondary_share_count)):
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
        final_job_workers_ranked = [k for k, v in sorted(
            candidate_dict.items(),
            key=lambda item: item[1],
            reverse=True,
        )]
        final_job_workers_ranked = random.sample(final_job_workers_ranked, 20) if len(
            final_job_workers_ranked) > 20 else final_job_workers_ranked
        if len(candidate_dict) > 20:
            # --> {candidate_dict}
            log.debug(f"{final_job.job_code}, candidates_length = {len(candidate_dict)},  be careful ...")

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

    def _check_action_on_rule_set(self, a_dict: ActionDict, unplanned_job_codes: List = []) -> SingleJobDropCheckOutput:

        if (a_dict.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes()) or (a_dict.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()):
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

    def gen_action_dict_from_worker_absence(self, absence: Absence) -> ActionDict:

        if absence is None:
            raise ValueError("error gen_action_dict_from_worker_absence")

        a_dict = ActionDict(
            is_forced_action=True,
            job_code=absence.job_code,
            action_type=ActionType.JOB_FIXED,
            scheduled_worker_codes=absence.scheduled_worker_codes,
            scheduled_start_minutes=absence.scheduled_start_minutes,
            scheduled_duration_minutes=absence.scheduled_duration_minutes,
        )
        return a_dict

    def gen_action_dict_from_appointment(self, job):

        if job is None:
            raise ValueError("error gen_action_dict_from_appoint ")

        return self.gen_action_dict_from_job(job=job, is_forced_action=True)

    def intersect_geo_time_slots(self, time_slots, job, duration_minutes=None, max_number_of_matching=99):
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
                if (time_slot_indices[idx] >= list_lengths[idx]):
                    return result_list

            current_time_slots = [time_slots[idx][time_slot_indices[idx]]
                                  for idx in range(len(time_slots))]

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
        res = requests.post(url=call_back_url,
                            headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
                                'content-type': "application/json"
                            },
                            data=param)
        res.content.decode('utf-8')
        if res.status_code != 200:
            raise Exception(f"{res.status_code}-{res.reason}")

        return res


class Job2SlotDispatchEnvProxy(KandboxEnvProxyPlugin):

    title = "job2slot dispatch basic - Environment Proxy"
    slug = "job2slot_dispatch_env_proxy"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "Env Proxy for GYM for RL."
    version = "0.1.0"

    env_class = Job2SlotDispatchEnv
    default_config = {
        # 'replay' for replay Planned jobs, where allows conflicts. EnvRunModeType.PREDICT for training new jobs and predict.
        "run_mode": EnvRunModeType.PREDICT,
        "env_code": "rl_hist_affinity_env_proxy",
        "allow_overtime": False,
        #
        "nbr_observed_slots": NBR_OF_OBSERVED_WORKERS,
        "nbr_of_days_planning_window": 2,
        "data_start_day": DATA_START_DAY,
        #
        "minutes_per_day": MINUTES_PER_DAY,
        # 'reversible' : True, # if yes, I can revert one step back.
        "MAX_NBR_JOBS_IN_SLOT": MAX_NBR_OF_JOBS_PER_DAY_WORKER,
        # 'rule_set':kprl_rule_set,
        "org_code": None,
        "team_id": None,
        "travel_max_minutes": 200,
        "geo_longitude_max": 119,
        "geo_longitude_min": 113,
        "geo_latitude_max": 41,
        "geo_latitude_min": 37,
        "inner_slot_planner": "head_tail",
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "inner_slot_planner": {
                "type": "string",
                "default": "head_tail",
                "title": "name of innner planner for jobs in slots (string)",
                "enum": ["head_tail", "nearest_neighbour"],
            },
            "run_mode": {
                "type": "string",
                "code": "Run Mode",
                "description": "This affects timing, N=Normal, FS=Fixed Schedule.",
                "enum": ["predict", "replay"],
            },
            "nbr_observed_slots": {
                "type": "number",
                "code": "Number of observed_workers"
            },
            "nbr_of_days_planning_window": {
                "type": "number",
                "code": "Number of days_planning_window",
            },
            "minutes_per_day": {
                "type": "number",
                "code": "minutes_per_day"
            },
            "MAX_NBR_JOBS_IN_SLOT": {
                "type": "number",
                "code": "MAX_NBR_JOBS_IN_SLOT",
            },

        },
    }
