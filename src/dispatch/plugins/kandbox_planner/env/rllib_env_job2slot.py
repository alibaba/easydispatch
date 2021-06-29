"""
This is used for rllib training purpose.
"""
from dispatch.location.models import Location
from dispatch.plugins.kandbox_planner.planner_engine.naive_manual_planner_shared_jobs_in_slots import (
    NaivePlannerJobsInSlots,
)
from dispatch.plugins.kandbox_planner.util.kandbox_date_util import extract_minutes_from_datetime
from dispatch.plugins.bases.kandbox_planner import (
    KandboxEnvPlugin,
    KandboxPlannerPluginType,
    KandboxEnvProxyPlugin,
)


from dispatch.plugins.kandbox_planner.rule.lunch_break import KandboxRulePluginLunchBreak
from dispatch.plugins.kandbox_planner.rule.travel_time import KandboxRulePluginSufficientTravelTime
from dispatch.plugins.kandbox_planner.rule.working_hour import KandboxRulePluginWithinWorkingHour
from dispatch.plugins.kandbox_planner.rule.requested_skills import KandboxRulePluginRequestedSkills
from dispatch.plugins.kandbox_planner.travel_time_plugin import HaversineTravelTime

# from dispatch.plugins.kandbox_planner.routing.travel_time_routingpy_redis import RoutingPyRedisTravelTime

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
    TESTING_MODE,
)
from dispatch import config
from dispatch.service.planner_models import SingleJobDropCheckOutput
from dispatch.plugins.kandbox_planner.env.env_enums import (
    EnvRunModeType,
    JobPlanningStatus,
)
from dispatch.plugins.kandbox_planner.env.env_enums import *
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
    JobLocationBase
)
import dataclasses
import dispatch.config as kandbox_config
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util

# from dispatch.plugins.kandbox_planner.env.recommendation_server import RecommendationServer
from dispatch.plugins.kandbox_planner.data_adapter.kafka_adapter import KafkaAdapter
from dispatch.plugins.kandbox_planner.data_adapter.fake_kafka_adapter import FakeKafkaAdapter
from dispatch.plugins.kandbox_planner.data_adapter.kplanner_db_adapter import KPlannerDBAdapter
from dispatch.plugins.kandbox_planner.env.cache_only_slot_server import CacheOnlySlotServer
from dispatch.plugins.kandbox_planner.env.working_time_slot import (
    WorkingTimeSlotServer,
    MissingSlotException,
)
from dispatch.config import PLANNER_SERVER_ROLE, MAX_MINUTES_PER_TECH
import socket
import logging
from redis.exceptions import LockError
import redis
import pandas as pd
import pprint
import math
import random
import numpy as np
import sys
from itertools import combinations
from typing import List
import copy
import time
from datetime import datetime, timedelta
import json


from gym import spaces
from ray.rllib.utils.spaces.repeated import Repeated


# This version works on top of json input and produce json out
# Observation: each worker has multiple working_time=days, then divided by slots, each slot with start and end time,


# import holidays


hostname = socket.gethostname()

log = logging.getLogger("rllib_env_job2slot")
# log.setLevel(logging.ERROR)
# log.setLevel(logging.WARN)
# log.setLevel(logging.DEBUG)

RULE_PLUGIN_DICT = {
    "kandbox_rule_within_working_hour": KandboxRulePluginWithinWorkingHour,
    "kandbox_rule_sufficient_travel_time": KandboxRulePluginSufficientTravelTime,
    "kandbox_rule_requested_skills": KandboxRulePluginRequestedSkills,
    "kandbox_rule_lunch_break": KandboxRulePluginLunchBreak,
    #
}


def min_max_normalize(x, input_min, input_max):
    y = (x - input_min) / (input_max - input_min)
    return y


class KPlannerJob2SlotEnv(KandboxEnvPlugin):
    """

    Action should be compatible with GYM, then it should be either categorical or numerical. ActionDict can be converted..
    New design of actions are:
    [
    vector of worker1_prob, worker2_prob (for N workers),
    start_day_i, job_start_minutes, shared_worker_count (shared = 1..M)
    ]

    # Benefit of using start_minutes is that I can use start minutes to find insert job i
    # but it is bigger value space for algorithm to decide.
    """

    title = "Kandbox Environment Job2Slot"
    slug = "kprl_env_job2slot"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "Env for GYM for RL."
    version = "0.1.0"

    metadata = {"render.modes": ["human"]}
    NBR_FEATURE_PER_SLOT = 24
    NBR_FEATURE_PER_UNPLANNED_JOB = 12
    NBR_FEATURE_OVERVIEW = 8

    def __del__(self):
        try:
            del self.kp_data_adapter
        except:
            log.warn("rl_env: Error when releasing kp_data_adapter.")

    def __init__(self, config=None):
        #
        # each worker and job is a dataclass object, internally transformed
        #
        env_config = config
        kp_data_adapter = None
        reset_cache = False
        self.workers_dict = {}  # Dictionary of all workers, indexed by worker_code
        self.workers = []  # List of Workers, pointing to same object in self.workers_dict
        self.jobs_dict = {}  # Dictionary of of all jobs, indexed by job_code
        self.jobs = []  # List of Jobs

        self.locations_dict = {}  # Dictionary of JobLocation, indexed by location_code
        self.changed_job_codes_set = set()

        self.trial_count = 0  # used only for GYM game online training process
        self.trial_step_count = 0
        self.run_mode = EnvRunModeType.PREDICT

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

        self.config = {
            # "data_start_day": "20200501",
            # "nbr_of_days_planning_window": 2,
            "planner_code": "rl_job2slot",
            "allow_overtime": False,
            "nbr_of_observed_workers": NBR_OF_OBSERVED_WORKERS,
            "minutes_per_day": MINUTES_PER_DAY,
            "max_nbr_of_jobs_per_day_worker": MAX_NBR_OF_JOBS_PER_DAY_WORKER,
            "travel_speed_km_hour": 25,
            # in minutes, 100 - travel / 1000 as the score
            "scoring_factor_standard_travel_minutes": SCORING_FACTOR_STANDARD_TRAVEL_MINUTES,
            "flex_form_data": {
                "holiday_days": "20210325",
                "weekly_rest_day": "0",
                "travel_speed_km_hour": 40,
                "travel_min_minutes": 10,
                "planning_working_days": 1,
            },
        }

        if env_config is None:
            log.error("error, no env_config is provided!")
            raise ValueError("No env_config is provided!")

        if "rules" not in env_config.keys():
            rule_set = []
            for rule_slug_config in env_config["rules_slug_config_list"]:
                rule_plugin = RULE_PLUGIN_DICT[rule_slug_config[0]](config=rule_slug_config[1])
                rule_set.append(rule_plugin)
            self.rule_set = rule_set
        else:
            self.rule_set = env_config["rules"]
            env_config.pop("rules", None)

        for x in env_config.keys():
            self.config[x] = env_config[x]
        # TODO, 2021-06-14 07:47:06
        self.config["nbr_of_days_planning_window"] = int(self.config["nbr_of_days_planning_window"])

        self.MAX_OBSERVED_SLOTS = (
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        self.PLANNING_WINDOW_LENGTH = (
            self.config["minutes_per_day"] * self.config["nbr_of_days_planning_window"]
        )
        evaluate_RequestedSkills = KandboxRulePluginRequestedSkills()
        self.rule_set_worker_check = [evaluate_RequestedSkills]  # , evaluate_RetainTech

        self.data_start_datetime = datetime.strptime(
            DATA_START_DAY, kandbox_config.KANDBOX_DATE_FORMAT
        )

        if TESTING_MODE == "yes":
            # if "env_start_day" in self.config.keys():
            # Report exception if there is no env_start_day
            if self.config["env_start_day"] == "_":
                self.horizon_start_minutes = None
            else:
                start_date = datetime.strptime(
                    self.config["env_start_day"], kandbox_config.KANDBOX_DATE_FORMAT
                )
                self.horizon_start_minutes = self.env_encode_from_datetime_to_minutes(start_date)
        else:
            self.horizon_start_minutes = None

        if kp_data_adapter is None:
            log.info("env is creating db_adapter by itslef, not injected.")
            kp_data_adapter = KPlannerDBAdapter(team_id=self.config["team_id"])
        else:
            log.error("INTERNAL:kp_data_adapter is not None for env.__init__")

        self.kp_data_adapter = kp_data_adapter
        if REDIS_PASSWORD == "":
            self.redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=None)
        else:
            self.redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)

        # This team_env_key uniquely identify this Env by starting date and team key. Multiple instances on different servers share same key.
        self.team_env_key = "env_{}_{}".format(self.config["org_code"], self.config["team_id"])

        # env_inst_seq is numeric and unique inside the team_env_key, uniquely identify one instance on a shared Env
        self.env_inst_seq = self.redis_conn.incr(self.get_env_inst_counter_redis_key())

        # env_inst_code is a code for an env Instance, which **globally**, uniquely identify one instance on a shared Env
        self.env_inst_code = "{}_{}_{}".format(self.team_env_key, self.env_inst_seq, hostname)

        self.parse_team_flex_form_config()
        SharingEfficiencyLogic = "1_1.0;2_1.6;3_2.1"

        self.efficiency_dict = {}
        for day_eff in SharingEfficiencyLogic.split(";"):
            self.efficiency_dict[int(day_eff.split("_")[0])] = float(day_eff.split("_")[1])

        if PLANNER_SERVER_ROLE == "trainer":
            self.kafka_server = KafkaAdapter(
                env=None, role=KafkaRoleType.FAKE, team_env_key=self.team_env_key
            )
            self.slot_server = CacheOnlySlotServer(env=self, redis_conn=self.redis_conn)
            self.kafka_input_window_offset = 0
        else:
            self.kafka_server = KafkaAdapter(env=self, role=KafkaRoleType.ENV_ADAPTER)
            self.slot_server = WorkingTimeSlotServer(env=self, redis_conn=self.redis_conn)
            self.kafka_input_window_offset = (
                self.kp_data_adapter.get_team_env_window_latest_offset()
            )
            self.config["flex_form_data"].update(self.kp_data_adapter.get_team_flex_form_data())

        # self.recommendation_server = RecommendationServer(env=self, redis_conn=self.redis_conn)

        if "data_end_day" in self.config.keys():
            log.error("data_end_day is not supported from config!")

        self.kp_data_adapter.reload_data_from_db()
        # I don't know why, self.kp_data_adapter loses this workers_dict_by_id after next call.
        # 2021-05-06 21:34:01
        self.workers_dict_by_id = copy.deepcopy(self.kp_data_adapter.workers_dict_by_id)

        # self._reset_data()

        self.replay_env()
        log.info("replay_env is done, for training purpose")

        # To be compatible with GYM Environment
        self._set_spaces()
        log.info("__init__ done, reloaded data from db, env is ready, please call reset to start")

        # Temp fix
        self.naive_opti_slot = NaivePlannerJobsInSlots(env=self)
        self.env_bootup_datetime = datetime.now()

    def reset(self, shuffle_jobs=False):
        # print("env reset")
        self._reset_data()
        # self._reset_gym_appt_data()
        self.slot_server.reset()

        self.trial_count += 1
        self.trial_step_count = 0
        self.inplanning_job_count = sum(
            [1 if j.planning_status != JobPlanningStatus.UNPLANNED else 0 for j in self.jobs]
        )

        self.current_job_i = 0
        self.total_assigned_job_duration = 0

        self.nbr_inplanning = 0
        self.expected_travel_time_so_far = 0
        self.total_travel_time = 0
        self.total_travel_worker_job_count = 0

        self.current_observed_worker_list = self._get_sorted_worker_code_list(self.current_job_i)

        self.current_appt_i = 0
        self._move_to_next_unplanned_job()

        return self._get_observation()

    def _reset_gym_appt_data(self):

        self.appts = list(self.kp_data_adapter.appointment_db_dict.keys())
        self.appt_scores = {}

        # Used for get_reward, only for gym training
        self.job_travel_time_sample_list_static = [
            (
                self._get_travel_time_2_job_indices(ji, (ji + 1) % len(self.jobs))
                + self._get_travel_time_2_job_indices(ji, (ji + 2) % len(self.jobs))
                + self._get_travel_time_2_job_indices(ji, (ji + 3) % len(self.jobs))
            )
            / 3
            for ji in range(0, len(self.jobs))
        ]

        self.total_travel_time_static = sum(
            [self._get_travel_time_2_job_indices(ji, ji + 1) for ji in range(0, len(self.jobs) - 1)]
        )

    def normalize(self, x, data_type: str):
        if data_type == "duration":
            return min_max_normalize(x, 0, 300)
        elif data_type == "start_minutes":
            return min_max_normalize(x, 0, 1440 * self.config["nbr_of_days_planning_window"])
        elif data_type == "day_minutes_1440":
            return min_max_normalize(x, 0, 1440 * 1)
        elif data_type == "longitude":
            return min_max_normalize(
                x, self.config["geo_longitude_min"], self.config["geo_longitude_max"]
            )
        elif data_type == "latitude":
            return min_max_normalize(
                x, self.config["geo_latitude_min"], self.config["geo_latitude_max"]
            )
        elif data_type == "max_nbr_shared_workers":
            return min_max_normalize(x, 0, 4)
        elif data_type == "max_job_in_slot":
            return min_max_normalize(x, 0, 10)
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
                            f"WORKER:{paired_code}:PAIR_TO:{x.belongs_to_pair}: the paired worker is not found."
                        )
                        is_valid_pair = False
                if not is_valid_pair:
                    continue

                self.permanent_pairs.add(x.belongs_to_pair)
                for paired_code in x.belongs_to_pair:
                    self.workers_dict[paired_code].belongs_to_pair = x.belongs_to_pair

        # This function also alters self.locations_dict
        self.jobs = self.load_transformed_jobs()
        if len(self.jobs) < 1:
            log.warn("No Jobs on initialized Env.")

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
        return "{}/env/counter".format(self.team_env_key)

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
        return int((datetime.now() - self.data_start_datetime).total_seconds() / 60)

    def get_env_planning_horizon_end_minutes(self) -> int:
        #  worker_id, start_minutes, end_minutes, slot_type,  worker_id,start_minutes, end_minutes, slot_type
        return 1440 * (
            int(self.config["nbr_of_days_planning_window"])
            + int(self.get_env_planning_horizon_start_minutes() / 1440)
        )

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
            worker_id=worker_code,
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
        #  worker_id, start_minutes, end_minutes, slot_type,  worker_id,start_minutes, end_minutes, slot_type

        assigned_start_minutes = int(
            (input_datetime - self.data_start_datetime).total_seconds() / 60
        )
        return assigned_start_minutes

    def env_encode_from_datetime_to_day_with_validation(self, input_datetime: datetime) -> int:
        #  worker_id, start_minutes, end_minutes, slot_type,  worker_id,start_minutes, end_minutes, slot_type

        the_minutes = self.env_encode_from_datetime_to_minutes(input_datetime)
        if (the_minutes < self.get_env_planning_horizon_start_minutes()) or (
            the_minutes >= self.get_env_planning_horizon_end_minutes()
        ):  # I removed 10 seconds from end of window.
            raise ValueError("Out of Planning Window")

        return int(the_minutes / self.config["minutes_per_day"])

    def env_decode_from_minutes_to_datetime(self, input_minutes: int) -> datetime:
        #  worker_id, start_minutes, end_minutes, slot_type,  worker_id,start_minutes, end_minutes, slot_type
        assigned_start_datetime = self.data_start_datetime + timedelta(minutes=input_minutes)
        return assigned_start_datetime

    def get_encode_shared_duration_by_planning_efficiency_factor(
        self, requested_duration_minutes: int, nbr_workers: int
    ) -> int:

        factor = self.efficiency_dict[nbr_workers]
        return int(requested_duration_minutes * factor / nbr_workers)

    def parse_team_flex_form_config(self):
        # TODO team.country_code
        # country_code = "CN"  team.country_code
        # self.national_holidays = holidays.UnitedStates()
        # self.national_holidays = holidays.CountryHoliday('US')
        if self.config["flex_form_data"]["holiday_days"] is not None:
            self.national_holidays = self.config["flex_form_data"]["holiday_days"].split(";")
        else:
            self.national_holidays = []

        if self.config["flex_form_data"]["weekly_rest_day"] is not None:
            __split = str(self.config["flex_form_data"]["weekly_rest_day"]).split(";")
        else:
            __split = []

        self.weekly_working_days_flag = [True for _ in range(7)]
        for day_s in __split:
            self.weekly_working_days_flag[int(day_s)] = False

        # 1.	Travel time formula is defined as GPS straight line distance *1.5/ (40 KM/Hour), minimum 10 minutes. Those numbers like 1.5, 40, 10 minutes,
        self.config["travel_speed_km_hour"] = self.config["flex_form_data"]["travel_speed_km_hour"]
        self.config["travel_min_minutes"] = self.config["flex_form_data"]["travel_min_minutes"]
        self.travel_router = HaversineTravelTime(
            travel_speed=self.config["travel_speed_km_hour"],
            min_minutes=self.config["travel_min_minutes"],
        )
        # self.travel_router = RoutingPyRedisTravelTime(
        #     travel_speed=self.config["travel_speed_km_hour"],
        #     min_minutes=self.config["travel_min_minutes"],
        #     redis_conn=self.redis_conn, travel_mode="car"
        # )

    def reload_env_from_redis(self):
        # observation = self.reset(shuffle_jobs=False)
        self.mutate_refresh_planning_window_from_redis()
        self._reset_data()
        if len(self.workers) < 1:
            log.warn(
                "No workers in env, skipped loading slots. Maybe this is the first initialization?"
            )
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
                self.kp_data_adapter.appointment_db_dict[job_code]
            )
            job = self.mutate_create_appointment(appt, auto_replay=False)

        self.slot_server.reload_from_redis_server()

    def mutate_replay_jobs_single_working_day(self, day_seq: int):
        for job_code in self.jobs_dict.keys():
            this_job = self.jobs_dict[job_code]
            if this_job.planning_status == JobPlanningStatus.UNPLANNED:
                continue
            if (this_job.scheduled_start_minutes < day_seq * 1440) or (
                this_job.scheduled_start_minutes > (day_seq + 1) * 1440
            ):
                continue
            if this_job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
                log.debug("mutate_replay_jobs_single_working_day: DEBUGGING_JOB_CODE_SET ")

            action_dict = self.gen_action_dict_from_job(job=this_job, is_forced_action=True)
            info = self.mutate_update_job_by_action_dict(
                a_dict=action_dict, post_changes_flag=False
            )

            if info.status_code != ActionScoringResultType.OK:
                log.error(
                    f"Error in job replay , but it will continue. code= {job_code},  info: {info} "
                )

    def replay_env_to_redis(self):

        # self.slot_server.reset()

        for key in self.redis_conn.scan_iter(f"{self.team_env_key}/s/*"):
            self.redis_conn.delete(key)

        observation = self.reset(shuffle_jobs=False)

        self.mutate_extend_planning_window()

        if len(self.jobs) < 1:
            log.error("No jobs in the env, len(self.jobs) < 1:")
            return
            # raise ValueError("No jobs in the env, len(self.jobs) < 1:")
        # we assume sequence of  I P U
        sorted_jobs = sorted(
            self.jobs, key=lambda job__i_: (job__i_.planning_status, job__i_.job_code)
        )
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
                    f"JOB:{this_job.job_code}:INDEX:{self.current_job_i}: replaying on pause: starting at {this_job.scheduled_start_minutes}."
                )
            if (
                this_job.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes()
            ) or (this_job.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()):
                log.warn(
                    f"JOB:{this_job.job_code}:INDEX:{self.current_job_i}: is out of horizon, starting at {this_job.scheduled_start_minutes} and therefore is skipped."
                )
                self.current_job_i += 1
                continue

            if self.current_job_i >= len(self.jobs):
                break

            if this_job.planning_status not in [
                JobPlanningStatus.IN_PLANNING,
                JobPlanningStatus.PLANNED,
                JobPlanningStatus.COMPLETED,
            ]:

                log.info(
                    f"Replayed until first U-status, self.current_job_i = {self.current_job_i} "
                )
                break
                # return observation, -1, False, None
                # break

            if this_job.scheduled_duration_minutes < 1:
                log.error(
                    f"JOB:{this_job.job_code}:scheduled_duration_minutes = {this_job.scheduled_duration_minutes} < 1 , not allowed, skipped from replay"
                )
                self.current_job_i += 1
                continue

            # action = self.gen_action_from_one_job(self.jobs[self.current_job_i])
            # action_dict = self.decode_action_into_dict(action)

            # This should work for both appt and absence.
            action_dict = self.gen_action_dict_from_job(job=this_job, is_forced_action=True)

            info = self.mutate_update_job_by_action_dict(
                a_dict=action_dict, post_changes_flag=False
            )

            if info.status_code != ActionScoringResultType.OK:
                print(
                    f"Error game replay got error, but it will continue: job_code={this_job.job_code}, current_job_i: {self.current_job_i},  info: {info} "
                )
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

        global_env_config = self.redis_conn.get(self.get_env_config_redis_key())

        if global_env_config is None:
            # This initialize the env dataset in redis for this envionrment.
            # all subsequent env replay_env should read from this .
            log.info("Trying to get lock over the env key to applying messages")
            with self.redis_conn.lock(
                self.get_env_replay_lock_redis_key(), timeout=60 * 10
            ) as lock:
                self.redis_conn.set(self.get_env_config_redis_key(), json.dumps(self.config))
                self.set_env_window_replay_till_offset(0)
                self.replay_env_to_redis()
                # code you want executed only after the lock has been acquired
                # lock.release()
            log.info("Done with redis lock to applying messages")
        else:
            self.reload_env_from_redis()

        # Catch up with recent messages on Kafka. Optional ? TODO

        self.mutate_check_env_window_n_replay()

        self._move_to_next_unplanned_job()
        obs = None  # self._get_observation()

        reward = -1
        done = False
        if obs is None:
            done = True
        info = {"message": f"Replay done"}
        return (obs, reward, done, info)

    # Is this timeout seconds?
    # TODO, replace two with locks by this unified locking

    def mutate_check_env_window_n_replay(self):
        # I need to lock it to protect kafka,  generator not threadsafe.
        # ValueError: generator already executing
        # with lock:
        if PLANNER_SERVER_ROLE == "trainer":
            return

        self.kafka_server.consume_env_messages()

    def env_encode_single_worker(self, obj_worker=None):
        worker = obj_worker.__dict__
        if worker["code"] == "MY|D|3|CT07":
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

        location = obj_worker.location

        home_location = LocationTuple(
            float(location.geo_longitude),
            float(location.geo_latitude),
            "H",
        )
        # working_minutes_array = flex_form_data["StartEndTime"].split(";")

        weekly_start_gps = [home_location for _ in range(7)]
        weekly_end_gps = [home_location for _ in range(7)]
        _weekly_working_slots = [None for _ in range(7)]
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
            # (week_day_i * 1440) +
            today_start_minutes = date_util.int_hhmm_to_minutes(
                int(worker["business_hour"][week_day_code][0]["open"])
                if worker["business_hour"][week_day_code][0]["isOpen"]
                else 0
            )
            today_end_minutes = date_util.int_hhmm_to_minutes(
                int(worker["business_hour"][week_day_code][0]["close"])
                if worker["business_hour"][week_day_code][0]["isOpen"]
                else 0
            )
            _weekly_working_slots[week_day_i] = (
                today_start_minutes,
                today_end_minutes,
            )
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
            overtime_minutes = int(float(self.config["flex_form_data"]["max_overtime_minutes"]))

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
            historical_job_location_distribution=worker["job_history_feature_data"],
            worker_index=0,
            belongs_to_pair=belongs_to_pair,
            is_active=worker["is_active"],
            daily_max_overtime_minutes=overtime_minutes,
            weekly_max_overtime_minutes=60 * 10,
            overtime_limits={},
            used_overtime_minutes={},
        )
        return w_r

    def load_transformed_workers(self):

        # start_date =  self.data_start_datetime

        w = []
        # w_dict = {}
        #
        # index = 0
        for _, worker in self.kp_data_adapter.workers_db_dict.items():
            active_int = 1 if worker.is_active else 0
            if active_int != 1:
                print(
                    "worker {} is not active, maybe it shoud be skipped from loading? ",
                    worker.id,
                )
                # TODO
                # included for now , since maybe job on it?
                continue

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
            abs_location = self.locations_dict[appointment["location_code"]]
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
        if job["planning_status"] in (JobPlanningStatus.PLANNED, JobPlanningStatus.IN_PLANNING):
            try:
                assigned_start_minutes = int(
                    (job["scheduled_start_datetime"] - self.data_start_datetime).total_seconds()
                    / 60
                )
            except ValueError as ve:
                log.error(f"Data error: failed to convert scheduled_start_datetime, job = {job}")
                return None

        requested_start_minutes = int(
            (job["requested_start_datetime"] - self.data_start_datetime).total_seconds() / 60
        )
        min_minutes = requested_start_minutes
        max_minutes = requested_start_minutes
        if "tolerance_start_minutes" in flex_form_data.keys():
            min_minutes = requested_start_minutes + (flex_form_data["tolerance_start_minutes"])
        if "tolerance_end_minutes" in flex_form_data.keys():
            max_minutes = requested_start_minutes + (flex_form_data["tolerance_end_minutes"])

        assigned_start_minutes = 0
        if job["planning_status"] in (JobPlanningStatus.PLANNED, JobPlanningStatus.IN_PLANNING):
            assigned_start_minutes = int(
                (job["scheduled_start_datetime"] - self.data_start_datetime).total_seconds() / 60
            )
        historical_serving_worker_distribution = None
        if "job_history_feature_data" in job.keys():
            if "historical_serving_worker_distribution" in job["job_history_feature_data"].keys():
                historical_serving_worker_distribution = job["job_history_feature_data"][
                    "historical_serving_worker_distribution"
                ]
        if "requested_primary_worker_code" not in job.keys():
            log.debug("No request primary code")
        if historical_serving_worker_distribution is None:
            historical_serving_worker_distribution = {job["requested_primary_worker_code"]: 1}

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

        # prev_available_slots = [
        #     (s.start_minutes, s.end_minutes) for s in job_location.available_slots
        # ]

        net_avail_slots = [
            [
                self.get_env_planning_horizon_start_minutes(),
                self.get_env_planning_horizon_end_minutes(),
            ]
        ]
        # TODO duan, change job_location from tuple to dataclass.
        # job_location.available_slots.clear()

        job_available_slots = self._convert_lists_to_slots(net_avail_slots, job)
        # job_location.available_slots = sorted(list(net_avail_slots), key=lambda x: x[0])
        if "requested_skills" in flex_form_data.keys():
            requested_skills = {
                "skills": set(flex_form_data["requested_skills"]),
            }
        else:
            requested_skills = set()
            log.error(f"job({job['code']}) has no requested_skills")

        the_final_status_type = job["planning_status"]
        is_appointment_confirmed = False

        # if job_schedule_type == JobScheduleType.FIXED_SCHEDULE:
        #     is_appointment_confirmed = True
        primary_workers = []
        if not pd.isnull(job["scheduled_primary_worker_id"]):
            primary_workers.append(
                self.workers_dict_by_id[job["scheduled_primary_worker_id"]]["code"]
            )

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
            scheduled_worker_codes=primary_workers + job["scheduled_secondary_worker_codes"],
            scheduled_start_minutes=assigned_start_minutes,
            scheduled_duration_minutes=job["scheduled_duration_minutes"],
            #
            requested_start_min_minutes=min_minutes,
            requested_start_max_minutes=max_minutes,
            requested_start_minutes=requested_start_minutes,
            requested_time_slots=[[0, 0]],
            requested_primary_worker_code=job["requested_primary_worker_code"],
            requested_duration_minutes=job["requested_duration_minutes"],
            #
            available_slots=job_available_slots,
            flex_form_data=flex_form_data,
            searching_worker_candidates=[],
            included_job_codes=flex_form_data["included_job_codes"],
            new_job_codes=[],
            appointment_status=AppointmentStatus.NOT_APPOINTMENT,
            #
            is_active=job["is_active"],
            is_appointment_confirmed=is_appointment_confirmed,
            is_auto_planning=job["auto_planning"],
        )

        self.set_searching_worker_candidates(final_job)

        # TODO, @xingtong.

        return final_job

    def load_transformed_jobs(self):
        # TODO , need data_window
        # This function also alters self.locations_dict
        #

        w = []

        for k, row_dict in self.kp_data_adapter.jobs_db_dict.items():
            if row_dict["code"] in kandbox_config.DEBUGGING_JOB_CODE_SET:
                log.debug(
                    f"load_transformed_jobs Debug {str(kandbox_config.DEBUGGING_JOB_CODE_SET)} "
                )

            if pd.isnull(row_dict["requested_primary_worker_id"]):
                continue

            job = self.env_encode_single_job(job=row_dict)
            if job is not None:
                w.append(job)
        return w

    def env_encode_single_absence(self, job: dict) -> Absence:

        assigned_start_minutes = int(
            (job["scheduled_start_datetime"] - self.data_start_datetime).total_seconds() / 60
        )
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

    def set_current_job_i(self, job_code):

        self.current_job_i = self.jobs_dict[job_code].job_index

    def decode_single_job_to_solution(self, job: BaseJob):  # _for_training
        all_worker_ids = [
            self.workers_dict[wcode].worker_id for wcode in job.scheduled_worker_codes
        ]
        new_job = {
            "id": self.jobs_dict[job.job_code].job_id,
            "code": job.job_code,
            "planning_status": job.planning_status,
            "scheduled_start_datetime": None,
            "scheduled_duration_minutes": job.scheduled_duration_minutes,  # TODO remove plural
            "scheduled_primary_worker_id": all_worker_ids[0],
            "scheduled_secondary_worker_ids": all_worker_ids[1:],
        }
        if job.planning_status != JobPlanningStatus.UNPLANNED:
            new_job["scheduled_start_datetime"] = self.env_decode_from_minutes_to_datetime(
                job.scheduled_start_minutes
            )
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
                worker_code=w.worker_code, query_start_minutes=query_start_minutes
            )
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
                if (j["scheduled_duration_minutes"] is None) or (
                    np.isnan(j["scheduled_duration_minutes"])
                ):
                    j["scheduled_duration_minutes"] = j["requested_duration_minutes"]
                j["scheduled_duration_minutes"] = 1
                j["scheduled_start_minutes"] = 0
            else:
                if j["scheduled_primary_worker_id"] not in workers_dict.keys():
                    # continue
                    print(
                        "Internal error, j['scheduled_primary_worker_id'] not in workers_dict.keys(): "
                    )
                # if workers_dict[curr_worker]['nbr_conflicts'] < conflict_level:
                #    workers_dict[curr_worker]['nbr_conflicts'] = conflict_level

            scheduled_start_datetime = self.data_start_datetime + timedelta(
                minutes=j["scheduled_start_minutes"]
            )

            scheduled_end_datetime = scheduled_start_datetime + timedelta(
                minutes=j["scheduled_duration_minutes"]
            )
            scheduled_start_datetime_js = int(
                time.mktime(scheduled_start_datetime.timetuple()) * 1000
            )
            if "requested_start_datetime" not in j.keys():
                j["requested_start_datetime"] = self.env_decode_from_minutes_to_datetime(
                    (j["requested_start_min_minutes"] + j["requested_start_max_minutes"]) / 2
                )
                # j["requested_duration_minutes"] =

            j["requested_primary_worker_id"] = j["requested_primary_worker_code"]

            scheduled_end_datetime_js = int(time.mktime(scheduled_end_datetime.timetuple()) * 1000)
            # TODO 2020-10-17 21:59:03
            if pd.isnull(j["scheduled_primary_worker_id"]):
                print("debug: j - scheduled_primary_worker_id is nan, please debug later.")
                continue
            if pd.isnull(j["scheduled_primary_worker_id"]):
                print("debug: j - scheduled_primary_worker_id is nan, please debug later.")
                continue

            if "job_id" not in j.keys():
                print("debug")
                j["requested_primary_worker_id"] = j["scheduled_primary_worker_id"]
                j["changed_flag"] = False
                pass
            plot_job_type = (
                f"{j['job_type']}"
                if j["job_type"] in {JobType.APPOINTMENT, JobType.ABSENCE}
                else f"{j['planning_status']}"  # f"{j['job_schedule_type']}"
            )
            # print(f"{j['job_code']} = {plot_job_type}")

            if j["planning_status"] in (JobPlanningStatus.UNPLANNED):
                j["scheduled_worker_codes"] = [j["requested_primary_worker_code"]]
            new_job = {
                "job_code": j["job_code"],
                "job_type": "{}_1_2_3_4_{}".format(plot_job_type, j["scheduled_share_status"]),
                "requested_primary_worker_id": j["requested_primary_worker_code"],
                "requested_start_datetime": j[
                    "requested_start_datetime"
                ].isoformat(),  # requested_start_datetime_js,
                "requested_duration_minutes": j["requested_duration_minutes"],
                "scheduled_primary_worker_id": self.workers_dict[
                    j["scheduled_worker_codes"][0]
                ].worker_id,
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
                    j["job_code"], j["scheduled_primary_worker_id"]
                )

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
        # /Users/qiyangduan/temp/nlns_env/lib/python3.7/site-packages/pandas/core/frame.py:1490: FutureWarning: Using short name for 'orient' is deprecated. Only the options: ('dict', list, 'series', 'split', 'records', 'index')
        # all_jobs_in_env = all_jobs_in_env_df.to_dict(orient="record")
        all_jobs_in_env = all_jobs_in_env_df.to_dict("record")

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
                    f"unknown worker code, or unknown job codes to the env. slot_code = {slot_code}, error = {str(ke)}"
                )
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

                if (
                    assigned_job.scheduled_start_minutes + assigned_job.scheduled_duration_minutes
                    < query_start_minutes
                ) | (assigned_job.scheduled_start_minutes > query_end_minutes):
                    log.warn(
                        f"Should be error.In slot but Solution skipped job_code={assigned_job.job_code}, minutes = {query_start_minutes} not in {query_start_minutes} -- {query_end_minutes}"
                    )
                    continue

                if len(assigned_job.scheduled_worker_codes) < 1:
                    log.warn(
                        "Internal BUG, why a job from assigned_jobs has no assigned_workers, but?"
                    )
                    continue

                prev_travel_minutes = self.travel_router.get_travel_minutes_2locations(
                    current_start_loc,
                    assigned_job.location,
                )
                # Only single worker jobs are collected in this loop.

                assigned_job_dict = dataclasses.asdict(assigned_job)  # .copy().as_dict()
                assigned_job_dict[
                    "requested_start_datetime"
                ] = self.env_decode_from_minutes_to_datetime(
                    assigned_job.requested_start_min_minutes
                )
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
                if (
                    new_job.scheduled_start_minutes + new_job.scheduled_duration_minutes
                    < query_start_minutes
                ) | (new_job.scheduled_start_minutes > query_end_minutes):
                    # log.debug(
                    #     f"solution skipped job_code={assigned_job.job_code}, minutes = {query_start_minutes} not in {query_start_minutes} -- {query_end_minutes}"
                    # )
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
                new_job_dict["scheduled_start_minutes"]
            )
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
                        prev_travel_minutes + assigned_job.requested_duration_minutes)
                    slot_details[slot_code]["travel_n_duration"] .append(
                        (prev_travel_minutes, assigned_job.requested_duration_minutes))

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
            elif new_job.planning_status in (JobPlanningStatus.COMPLETED,):
                continue
            elif new_job.planning_status in (JobPlanningStatus.PLANNED,):
                if (
                    new_job.scheduled_start_minutes + new_job.scheduled_duration_minutes
                    < self.get_env_planning_horizon_start_minutes()
                ) | (new_job.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()):
                    log.warn(
                        f"solution skipped job_code={new_job.job_code}, minutes = {new_job.scheduled_start_minutes} not in planning window"
                    )
                    continue
                else:
                    log.error(f"Why not in slots? PLANNED, job_code = {job_code}")
            else:
                log.error(f"Why not in slots? INPLANNING, job_code = {job_code}")
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

    def mutate_refresh_planning_window_from_redis(self) -> bool:
        existing_working_days = self.get_planning_window_days_from_redis()

        if len(existing_working_days) < 1:
            min_horizon_start_seq = 0
            max_horizon_start_seq = 4
        else:
            min_horizon_start_seq = min(existing_working_days)
            max_horizon_start_seq = max(existing_working_days)

        if TESTING_MODE == "yes":
            self.horizon_start_minutes = min_horizon_start_seq * 1440
        else:
            self.horizon_start_minutes = None

        # min_planning_day_seq = int(self.get_env_planning_horizon_start_minutes() / 1440)
        # max_planning_day_seq = max(existing_working_days)
        self.config["nbr_of_days_planning_window"] = (
            max_horizon_start_seq - min_horizon_start_seq + 1
        )
        log.info(
            f"Refresh planning window done, min_horizon_start_seq= {min_horizon_start_seq}, max_horizon_start_seq = {max_horizon_start_seq}"
        )

    def mutate_extend_planning_window(self) -> bool:
        existing_working_days = self.get_planning_window_days_from_redis()

        # Hold this value and do not call it multiple times in a loop
        today_start_date = self.env_decode_from_minutes_to_datetime(
            self.get_env_planning_horizon_start_minutes()
        )

        horizon_day_seq = self.env_encode_from_datetime_to_day_with_validation(today_start_date)

        # Now find out all current days in planning windows.
        new_working_days = set()
        for day_i in range(100):
            new_start_date = today_start_date + timedelta(days=day_i)
            day_seq = (new_start_date - self.data_start_datetime).days
            new_weekday = self.env_encode_day_seq_to_weekday(day_seq)
            new_start_date_str = datetime.strftime(
                new_start_date, kandbox_config.KANDBOX_DATE_FORMAT
            )

            if new_start_date_str in self.national_holidays:
                # This is a holiday. It overwrites weekly settings from weekly_working_days_flag.
                continue

            if self.weekly_working_days_flag[new_weekday]:
                # This is a working day
                self.daily_working_flag[day_seq] = True
                new_working_days.add(day_seq)
            else:
                self.daily_working_flag[day_seq] = False

            if len(new_working_days) >= self.config["flex_form_data"]["planning_working_days"]:
                break
        # It may reduce several days of holidays

        # 2020-11-17 06:27:47
        # If planning window start with Sunday, new_working_days does not contain it, horizon_day_seq should still point to Sunday
        self.config["nbr_of_days_planning_window"] = max(new_working_days) - horizon_day_seq + 1

        if new_working_days <= existing_working_days:
            log.warn(
                f"There is no change in planning day when it is called at {datetime.now()}). existing_working_days={existing_working_days}. Maybe we have passed a weekend?  "
            )
            return False

        # Update nbr_of_days_planning_window, which may be larger than specified self.config["flex_form_data"]["DaysForPlanning"]
        # nbr_of_days_planning_window may contain

        days_to_add = new_working_days - existing_working_days
        days_to_delete = existing_working_days - new_working_days

        for day_seq in days_to_delete:
            self._mutate_planning_window_delete_day(day_seq)
            log.info(f"A planning day (day_seq = {day_seq}) is purged out of planning window.  ")
        if len(days_to_add) > 0:
            self.kp_data_adapter.reload_data_from_db()
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
        today_start_date_str = datetime.strftime(today_start_date, kandbox_config.KANDBOX_DATE_FORMAT)

        today_weekday = self.env_encode_day_seq_to_weekday(day_seq)
        self.redis_conn.hdel(self.get_env_planning_day_redis_key(), *[day_seq])

        for worker_code in self.workers_dict.keys():
            #working_day_start = day_seq * 1440 if self.workers_dict[worker_code].weekly_working_slots[0] > 0 else  day_seq * 1440 + self.workers_dict[worker_code].weekly_working_slots[0]
            if self.workers_dict[worker_code].weekly_working_slots[today_weekday][1] < 1440:
                working_day_end = (day_seq) * 1440 + \
                    self.workers_dict[worker_code].weekly_working_slots[today_weekday][1]
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
            today_start_date, kandbox_config.KANDBOX_DATE_FORMAT
        )

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

        self.redis_conn.hset(
            self.get_env_planning_day_redis_key(),
            key=day_seq,
            value=f"{today_start_date_str}_{day_seq*1440}->{(day_seq+1)*1440}"
            # mapping={day_seq: f"{today_start_date_str}_{day_seq*1440}->{(day_seq+1)*1440}"},
        )

        for w in self.workers:

            self._mutate_planning_window_add_worker_day(worker_code=w.worker_code, day_seq=day_seq)

        log.info(
            f"The planning window slot (day_seq = {day_seq}, today_start_date_str = {today_start_date_str}) is added succesfully!"
        )
        return True

    def _mutate_planning_window_add_worker_day(self, worker_code: str, day_seq: int) -> bool:
        # I first calculate the working slot in this day
        w = self.workers_dict[worker_code]
        today_weekday = self.env_encode_day_seq_to_weekday(day_seq)
        slot = (
            day_seq * 1440 + w.weekly_working_slots[today_weekday][0],
            day_seq * 1440 + w.weekly_working_slots[today_weekday][1],
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

            for aslot_ in overlap_slots_sorted:
                if aslot_.slot_type == TimeSlotType.FLOATING:
                    log.error(
                        f"WORKER:{worker_code}:DAY:{day_seq}:SLOT:{slot}, Encountered existing floating working time slot ({aslot_.start_minutes}->{aslot_.end_minutes}) while trying to add working slot. Aborted."
                    )
                    return False

                log.warn(
                    f"WORKER:{worker_code}:DAY:{day_seq}:SLOT:{slot}, Encountered existing working time slot ({aslot_.start_minutes}->{aslot_.end_minutes}) while trying to add working slot {slot}"
                )
                new_slot_end = aslot_.start_minutes
                new_end_location = aslot_.start_location

                self.slot_server.add_single_working_time_slot(
                    worker_code=w.worker_code,
                    start_minutes=new_slot_start,
                    end_minutes=new_slot_end,
                    start_location=new_start_location,
                    end_location=new_end_location,
                )

                new_slot_start = aslot_.end_minutes
                new_start_location = aslot_.end_location

            # Add the last time slot if present
            if new_slot_start < slot[1]:
                self.slot_server.add_single_working_time_slot(
                    worker_code=w.worker_code,
                    start_minutes=new_slot_start,
                    end_minutes=slot[1],
                    start_location=new_start_location,
                    end_location=w.weekly_end_gps[today_weekday],
                )
            return False
        else:
            self.slot_server.add_single_working_time_slot(
                worker_code=w.worker_code,
                start_minutes=slot[0],
                end_minutes=slot[1],
                start_location=w.weekly_start_gps[today_weekday],
                end_location=w.weekly_end_gps[today_weekday],
            )
            log.info(
                f"The worker_day slot (start_minutes = {slot[0]}, w.worker_code = {w.worker_code}) is added succesfully!"
            )
        return True

    # ***************************************************************
    # Mutation functions, lock?
    # They are named as C-R-U-D, therefore Create will add the object to the ENV, Update will update existing one.
    # ***************************************************************

    def mutate_worker_add_overtime_minutes(
        self, worker_code: str, day_seq: int, net_overtime_minutes: int, post_changes_flag=False
    ) -> bool:
        added_successful = True
        if day_seq not in self.workers_dict[worker_code].used_overtime_minutes.keys():
            log.warn(
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
                log.warn(
                    f"Overtime={total_overtime} is larger than limit for worker={worker_code}, key={limit_days_key}"
                )
                added_successful = False
        if post_changes_flag:
            self.kafka_server.post_env_message(
                message_type=KafkaMessageType.UPDATE_WORKER_ATTRIBUTES,
                payload=[
                    {
                        worker_code: {
                            "used_overtime_minutes": self.workers_dict[
                                worker_code
                            ].used_overtime_minutes
                        }
                    }
                ],
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
                f"mutate_create_worker: error, worker already existed: {new_worker.worker_code}"
            )
            return False
            # raise ValueError("duplicate worker code '{0}' found".format(new_worker.worker_code))
        self.workers.append(new_worker)
        self.workers_dict[new_worker.worker_code] = new_worker
        self.workers_dict[new_worker.worker_code].worker_index = len(self.workers) - 1
        for day_seq in self.daily_working_flag.keys():
            self._mutate_planning_window_add_worker_day(
                worker_code=new_worker.worker_code, day_seq=day_seq
            )

        log.info(
            f"mutate_create_worker: successfully added worker, code = {new_worker.worker_code}"
        )

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

    def mutate_create_appointment(self, new_job: Appointment, auto_replay=True):
        # I assume it is Unplanned for now, 2020-04-24 07:22:53.
        # No replay
        if new_job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
            log.debug(f"debug appt {kandbox_config.DEBUGGING_JOB_CODE_SET}")
        if new_job.job_code in self.jobs_dict.keys():
            log.warn(
                f"APPT:{new_job.job_code}: mutate_create_appointment, job already existed",
            )
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
                log.warn(
                    f"APPT:{new_job.job_code}:JOB:{stripped_job_code}: U status job () is included in appointment (). It is simply applied without modifying job."
                )  # log.warn
                continue
        # Then apply this appointment action
        # if False:
        # if not kandbox_config.DEBUG_ENABLE_APPOINTMENT_REPLAY:
        #     return
        if auto_replay:
            release_success, info = self.slot_server.release_job_time_slots(
                self.jobs_dict[stripped_job_code]
            )
            if not release_success:
                log.warn(
                    f"Error releasing job (code={stripped_job_code}) inside the appointment ({new_job.job_code}), but I will continue appointment replay ..."
                )
                # return False

            self.mutate_replay_appointment(job=new_job)

        self.redis_conn.hmset(
            "{}{}".format(kandbox_config.APPOINTMENT_ON_REDIS_KEY_PREFIX, new_job.job_code),
            {"rec_round": 0, "planning_status": "PENDING", "team_id": self.config["team_id"]},
        )

    def mutate_replay_appointment(self, job: Appointment):
        if (job.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes()) or (
            job.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()
        ):
            log.warn(
                f"Start time of appointment ({job.job_code}={job.scheduled_start_minutes}) is out of planning window, skippped replaying"
            )
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
            log.error(
                "ERROR: ONLY appointment job code can be changed, but  {}  is {} ".format(
                    old_job_code, self.jobs_dict[old_job_code].job_type
                )
            )
        old_job = self.jobs_dict[old_job_code]
        old_job.job_code = new_job_code
        del self.jobs_dict[old_job_code]
        self.jobs_dict[new_job_code] = old_job

        # location in self.jobs remains untouched.
        # TODO, send to kafka.
        log.warn(
            f"mutate_update_job_code:APPT:{old_job_code}:NEW_APPT:{new_job_code}: appointment code to updated to new one by {self.env_inst_code}. No more recommendations to any of them."
        )

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
                f"Error whiling tring to release existing appoitnment slot, {curr_appt.job_code}"
            )

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
                f"mutate_delete_appointment:exception: job code mismatch job_code={job_code}, job_index = {job_index}, "
            )
        # Remove appt from redis recommendation frontend
        self.redis_conn.delete(
            "{}{}".format(kandbox_config.APPOINTMENT_ON_REDIS_KEY_PREFIX, job_code)
        )
        # Remove recommendations from redis
        for rec_code in self.redis_conn.scan_iter(
            f"{self.get_recommendation_job_key(job_code=job_code, action_day=-1)}*"
        ):
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
        log.debug(
            f"ABSENCE:{new_job.job_code}: the absence is created/added into env.",
        )

    def mutate_replay_worker_absence(self, job: Absence):
        if (job.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes()) or (
            job.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()
        ):
            log.warn(
                f"Start time of absence ({job.job_code}={job.scheduled_start_minutes}) is out of planning window, skippped replaying"
            )
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
            f"Successfully updated job metadata, no schedulling action done. code = {new_job.job_code}"
        )
        # Then I skip appling scheduling action

    def mutate_replay_job(self, job: Appointment):
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

    def mutate_update_job_by_action_dict(
        self, a_dict: ActionDict, post_changes_flag: bool = False
    ) -> SingleJobCommitInternalOutput:
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
        if self.jobs[self.current_job_i].job_code != a_dict.job_code:
            self.current_job_i = self.jobs_dict[a_dict.job_code].job_index
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
                f"action is rejected  because scheduled_duration_minutes < 1, action = {a_dict}"
            )
            job_commit_output.messages.append(
                f"action is rejected  because scheduled_duration_minutes < 1"
            )
            return job_commit_output
        if curr_job.planning_status in {JobPlanningStatus.PLANNED}:
            if (curr_job.job_type == JobType.JOB) and (not a_dict.is_forced_action):
                job_commit_output.messages.append(
                    f"Failed to change job planning because planning_status == PLANNED and not is_forced_action"
                )
                return job_commit_output
        if (curr_job.planning_status == JobPlanningStatus.UNPLANNED) & (
            a_dict.action_type == ActionType.UNPLAN
        ):
            job_commit_output.messages.append(
                f"Job is already unplanned, and can not be unplanned."
            )
            job_commit_output.status_code = ActionScoringResultType.OK
            return job_commit_output

        if curr_job.planning_status in {
            JobPlanningStatus.IN_PLANNING,
            JobPlanningStatus.PLANNED,  # Here planned is only for replay
        }:

            if (
                (a_dict.action_type != ActionType.UNPLAN)
                & (a_dict.scheduled_start_minutes == curr_job.scheduled_start_minutes)
                & (a_dict.scheduled_worker_codes == curr_job.scheduled_worker_codes)
                & (not a_dict.is_forced_action)
            ):
                job_commit_output.messages.append(
                    f"Job is in-planning, the new scheduled_start_minutes, scheduled_worker_codes are same."
                )
                job_commit_output.status_code = ActionScoringResultType.OK
                return job_commit_output

            if not curr_job.is_replayed:
                log.warn(f"job ({curr_job.job_code}) is not replayed for releasing?")

            # Now we first release previous slot
            release_success_flag, info = self.slot_server.release_job_time_slots(job=curr_job)
            if (not release_success_flag) & curr_job.is_replayed & (not a_dict.is_forced_action):
                log.warn(f"Error in release_job_time_slots, {curr_job.job_code}")
                job_commit_output.messages.append(
                    f"Failed to release job slot for {curr_job.job_code}, release_success_flag = false, error = {str(info)}"
                )
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
                log.info(
                    f"JOB:{curr_job.job_code}: job is unplanned temporary by releasing slot for inplan again. release_success_flag = {release_success_flag}"
                )

        # a normal job duration is 200 minutes. The jobs before 200 minute will not impact current planning window
        # TODO
        if (
            a_dict.scheduled_start_minutes < self.get_env_planning_horizon_start_minutes() - 200
        ) or (a_dict.scheduled_start_minutes > self.get_env_planning_horizon_end_minutes()):
            log.warn(
                f"action is rejected  because scheduled_start_minutes is out of planning window, action = {a_dict}"
            )
            job_commit_output.messages.append(
                f"action is rejected  because scheduled_start_minutes is out of planning window"
            )
            return job_commit_output

        if not a_dict.is_forced_action:
            rule_check_info = self._check_action_on_rule_set(a_dict)
            if rule_check_info.status_code != ActionScoringResultType.OK:
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
                self.jobs_dict[
                    _j_code
                ].scheduled_duration_minutes = self.get_encode_shared_duration_by_planning_efficiency_factor(
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
        curr_job.scheduled_worker_codes = a_dict.scheduled_worker_codes
        curr_job.scheduled_start_minutes = a_dict.scheduled_start_minutes
        # could be accross several days.
        curr_job.scheduled_duration_minutes = a_dict.scheduled_duration_minutes

        # Here I decide to publish the change or not
        if self.run_mode != EnvRunModeType.REPLAY:  # and (not a_dict.is_forced_action)

            if curr_job.planning_status == JobPlanningStatus.UNPLANNED:
                # self.expected_travel_time_so_far += self.job_travel_time_sample_list_static[
                #     self.current_job_i
                # ]
                self.nbr_inplanning += 1

            curr_job.is_changed = True
            self.changed_job_codes_set.add(curr_job.job_code)
            nbr_changed_jobs = len(self.changed_job_codes_set)
            # It might change multiple jobs
            if post_changes_flag:
                self.commit_changed_jobs(changed_job_codes_set={curr_job.job_code})
        else:
            if post_changes_flag:
                log.error(f"Not allowed to post_changes_flag for EnvRunModeType.REPLAY")

        job_commit_output.status_code = ActionScoringResultType.OK
        job_commit_output.nbr_changed_jobs = nbr_changed_jobs

        log.debug(
            f"JOB:{curr_job.job_code}:WORKER:{a_dict.scheduled_worker_codes}:START_MINUTES:{a_dict.scheduled_start_minutes}: job is commited successfully. "
        )

        return job_commit_output

    def commit_changed_jobs(self, changed_job_codes_set=set()):

        # for job in jobs:
        changed_jobs = []
        changed_job_codes = []
        self.changed_job_codes_set = changed_job_codes_set

        for job_code in self.changed_job_codes_set:
            job = self.jobs_dict[job_code]
            if job.is_changed:
                a_job = self.decode_single_job_to_solution(job)
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
            message_type=KafkaMessageType.POST_CHANGED_JOBS, payload=jobs + appt_included_jobs
        )

        # return offset in internal kafka window
        return self.kafka_server.post_env_message(
            message_type=KafkaMessageType.REFRESH_JOB, payload=jobs + appt_included_jobs
        )

    # ***************************************************************
    # # Gym functions
    # ***************************************************************

    def step_by_action_dict(self, action_dict):  # -> (obs, ..., SingleJobCommitInternalOutput)
        # action [1, 0, 0 ]. One hot coding, 1 means this worker take the job.
        if self.run_mode == EnvRunModeType.REPLAY:
            action_dict.is_forced_action = True

        result_info_obj = self.mutate_update_job_by_action_dict(a_dict=action_dict)
        result_info = dataclasses.asdict(result_info_obj)

        if result_info["status_code"] == ActionScoringResultType.OK:
            reward = 0.11  # self._get_reward()  # 1
            self.inplanning_job_count += 1
        else:
            reward = -1

        if self.run_mode == EnvRunModeType.REPLAY:
            self.current_job_i += 1
            has_next = self.current_job_i < len(self.jobs)
        else:
            has_next = self._move_to_next_unplanned_job()

        if has_next:
            done = False
        else:
            done = True
            reward = 5

        # print("Adding job {}--{} to Worker {}-{} , result: {}...".format(self.current_job_i - 1, self.jobs[self.current_job_i - 1]['job_code'],action['worker_code'],action['start_minutes'],add_result ))

        if self.run_mode == EnvRunModeType.REPLAY:
            return ([], 1, done, result_info)

            # print(f"Env Error: trail={self.trial_count}, step={self.trial_step_count}")

        # if self.trial_step_count > len(self.jobs) * 0.3:
        #     done = True
        #     reward = -5
        #     if self.trial_count % 1 == 0:
        #         # print("No more unplanned jobs, done. internal error? It should be handled by has_next!") )
        #         log.info(
        #             f"Env done with Failure: travel_time={self.total_travel_time:.2f}, trial={self.trial_count}, trial_step_count={self.trial_step_count}, nbr_inplanning={self.nbr_inplanning} ... "
        #         )
        self.nbr_inplanning = sum(
            [
                1 if self.jobs_dict[j_i].planning_status != "U" else 0
                for j_i in self.jobs_dict.keys()
            ]
        )
        if self.nbr_inplanning >= len(self.jobs):
            overall_score = self.get_planner_score_stats()["overall_score"]
            done = True
            reward = 4 * overall_score

        # if (done == True) & (self.trial_count % 1 == 0):  # trial_count
        #     # print("No more unplanned jobs, done. internal error? It should be handled by has_next!") )
        #     # self.get_planner_score_stats()["overall_score"]
        #     log.info(
        #         f"Env done with Success: self.inplanning_job_count = {self.inplanning_job_count}, trial_step_count = {self.trial_step_count},  reward={reward:.2f}, travel_time={self.total_travel_time:.2f}, nbr_inplanning={self.nbr_inplanning}, travel_worker_job_count = {self.total_travel_worker_job_count}, trial={self.trial_count}"
        #     )

        obs = self._get_observation()
        if ((len(obs["jobs"]) < 1) or (len(obs["slots"]) < 1)) and (not done):
            log.warn("No jobs or slots to observe, done?")
            done = True
        return (obs, reward, done, result_info)

    def step_recommend_appt(self, action_dict):

        curr_job = copy.deepcopy(self.jobs_dict[action_dict.job_code])

        action_day = int(action_dict.scheduled_start_minutes / 1440)
        curr_job.requested_start_min_minutes = action_day * 1440
        curr_job.requested_start_max_minutes = (action_day + 1) * 1440

        action_dict_list = self.recommendation_server.search_action_dict_on_worker_day(
            a_worker_code_list=action_dict.scheduled_worker_codes,
            curr_job=curr_job,
            max_number_of_matching=3,
        )
        if len(action_dict_list) < 1:
            reward = -0.1
        else:
            reward = action_dict_list[0].score + 0.5
            self.appt_scores[action_dict.job_code] = reward

        info = {"message": f"found {len(action_dict_list)} recommendations"}
        done = True
        for p_i in range(len(self.appts)):
            self.current_appt_i += 1
            if self.current_appt_i >= len(self.appts):
                self.current_appt_i = 0
            if self.appts[self.current_appt_i] not in self.appt_scores.keys():
                done = False
                n_job_code = self.appts[self.current_appt_i]
                self.current_job_i = self.jobs_dict[n_job_code].job_index
                if self.jobs[self.current_job_i].job_code != n_job_code:
                    log.error(
                        f"n_job_code = {n_job_code}, self.jobs[self.current_job_i].job_code = {self.jobs[self.current_job_i].job_code}"
                    )
                break
        if done:
            self.current_job_i = 0
        obs = self._get_observation()

        if self.trial_step_count > self.config["max_trial_step_count"]:
            done = True
            reward = -5
            if self.trial_count % 20 == 0:
                print(
                    f"Env done as Failed: travel_time={self.total_travel_time:.2f}, trial={self.trial_count}, step={self.trial_step_count}, nbr_inplanning={self.nbr_inplanning} ... "
                )

        # if len(self.appt_scores) >= len(self.appts):
        #     done = True
        #     reward += 3
        #     if self.trial_count % 20 == 0:
        #         # print("No more unplanned jobs, done. internal error? It should be handled by has_next!") )
        #         log.info(
        #             f"Env done as Success: trial={self.trial_count}, step={self.trial_step_count}, reward={reward:.2f}, travel_time={self.total_travel_time:.2f}, nbr_inplanning={self.nbr_inplanning}, travel_worker_job_count = {self.total_travel_worker_job_count}"
        #         )

    def _calc_travel_minutes_difference(
        self, shared_time_slots_optimized, arranged_slots, current_job_code
    ):

        new_travel_minutes_difference = 0

        for a_slot, arranged_slot in zip(shared_time_slots_optimized, arranged_slots):
            new_job_code_list = [s[1] for s in arranged_slot]
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

        return (100 - new_travel_minutes_difference) / 100

    def step_recommend_and_plan_job(self, action_dict):

        curr_job = copy.deepcopy(self.jobs_dict[action_dict.job_code])

        action_day = int(action_dict.scheduled_start_minutes / 1440)
        curr_job.requested_start_min_minutes = (
            action_day * 1440 + self.get_env_planning_horizon_start_minutes()
        )
        curr_job.requested_start_max_minutes = (
            action_day + 1
        ) * 1440 + self.get_env_planning_horizon_start_minutes()

        action_dict_list = self.recommendation_server.search_action_dict_on_worker_day(
            a_worker_code_list=action_dict.scheduled_worker_codes,
            curr_job=curr_job,
            max_number_of_matching=3,
        )
        if curr_job.job_code in kandbox_config.DEBUGGING_JOB_CODE_SET:
            log.debug(f"step_recommend_and_plan_job curr_job.job_code = {curr_job.job_code}")

        if len(action_dict_list) >= 1:
            selected_action = action_dict_list[0].to_action_dict(self)

            return self.step_by_action_dict(action_dict=selected_action)

        # else:
        reward = -1
        result_info = {"message": f"found  no action in the given worker+day"}
        done = not self._move_to_next_unplanned_job()

        obs = self._get_observation()

        return (obs, reward, done, result_info)

    def step(self, action):
        self.trial_step_count += 1
        if len(self.internal_obs_slot_list) < 1:
            log.error("len(self.internal_obs_slot_list) < 1, not ready... Reset not called yet?")
            return self._get_observation(), -1, False, {}
        # action [1, 0, 0 ]. One hot coding, 1 means this worker take the job.
        new_act = action.copy()
        max_i = np.argmax(new_act[0: len(self.internal_obs_slot_list)])  #
        if max_i >= len(self.internal_obs_slot_list):
            log.error("Wrong")

        temp_slot = copy.deepcopy(self.internal_obs_slot_list[max_i])
        temp_slot.assigned_job_codes.append(self.jobs[self.current_job_i].job_code)
        shared_time_slots_optimized = [temp_slot]
        obs, reward, done, info = self.step_naive_search_and_plan_job(shared_time_slots_optimized)

        if (not done):
            if (self.trial_step_count > self.config["max_trial_step_count"]):
                done = True
                reward = -5
                msg = f"Env done as Failure:  inplanning = {self.inplanning_job_count}, trial_step_count = {self.trial_step_count},  reward={reward:.2f}, travel_time={self.total_travel_time:.2f}, nbr_inplanning={self.nbr_inplanning}, travel_worker_job_count = {self.total_travel_worker_job_count}, trial={self.trial_count},  when steps reaches maximum"
                info = {
                    "message": msg
                }
                log.info(msg)
        else:
            if (self.trial_count % 1 == 0):
                log.info(
                    f"Env done as Success:  inplanning = {self.inplanning_job_count}, trial_step_count = {self.trial_step_count},  reward={reward:.2f}, travel_time={self.total_travel_time:.2f}, nbr_inplanning={self.nbr_inplanning}, travel_worker_job_count = {self.total_travel_worker_job_count}, trial={self.trial_count}, good"
                )

        return obs, reward, done, info

        # try:
        #     action_dict = self.decode_action_into_dict_native(action)
        #     if self.run_mode == EnvRunModeType.REPLAY:
        #         log.error(f"No more replays")
        #         action_dict.is_forced_action = True
        #     else:
        #         action_dict.is_forced_action = False
        # except LookupError:
        #     print("LookupError: failed to parse action")

        #     # add_result = False
        #     info = {"message": f"LookupError: failed to parse action into acction_dict {action}"}

        #     obs = self._get_observation()
        #     if self.trial_step_count > len(self.appts) * 2:
        #         done = True
        #     else:
        #         done = False
        #     reward = -1
        #     return (obs, reward, done, info)

        # obs, reward, done, info = self.step_recommend_and_plan_job(action_dict)

    def pprint_all_slots(self):

        for k in self.slot_server.time_slot_dict.keys():
            job_list = self.slot_server.time_slot_dict[k].assigned_job_codes

    def step_naive_search_and_plan_job(self, shared_time_slots_optimized):

        job_code = self.jobs[self.current_job_i].job_code
        res = self.naive_opti_slot.dispatch_jobs_in_slots(shared_time_slots_optimized)
        if res["status"] == OptimizerSolutionStatus.SUCCESS:
            selected_action = res["changed_action_dict_by_job_code"][job_code]

            obs, reward, done, result_info = self.step_by_action_dict(action_dict=selected_action)
            if reward == 0.11:
                travel_difference_score = self._calc_travel_minutes_difference(
                    shared_time_slots_optimized, res["slots"], job_code
                )
                reward += travel_difference_score
                reward = reward * (self.inplanning_job_count / len(self.jobs))

            return obs, reward, done, result_info

        # else:
        reward = -1.5
        # reward = -6
        result_info = {"message": f"found no action in the specified slots"}
        done = not self._move_to_next_unplanned_job()
        # done = True

        # if (self.trial_count % 1 == 0):
        #     log.info(
        #         f"Env done with Failure: self.inplanning_job_count = {self.inplanning_job_count}, trial_step_count = {self.trial_step_count},  reward={reward:.2f},  nbr_inplanning={self.nbr_inplanning}, trial={self.trial_count}"
        #     )

        obs = self._get_observation()
        return (obs, reward, done, result_info)

    def step_future_for_job_actions_TODO(self, action):
        # action [1, 0, 0 ]. One hot coding, 1 means this worker take the job.
        self.trial_step_count += 1
        try:
            a_dict = self.decode_action_into_dict(action)
            if self.run_mode == EnvRunModeType.REPLAY:
                a_dict.is_forced_action = True
            else:
                a_dict.is_forced_action = False
        except LookupError:
            log.debug("LookupError: failed to parse action")

            # add_result = False
            info = {"message": f"LookupError: failed to parse action into acction_dict {action}"}

            obs = self._get_observation()
            if self.trial_step_count > len(self.jobs) * 2:
                done = True
            else:
                done = False
            reward = -1
            return (obs, reward, done, info)

        obs, reward, done, info = self.step_by_action_dict(action_dict=a_dict)

        return obs, reward, done, info

    def render(self, mode="human"):
        pass

    def close(self):
        pass

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
        return self._get_travel_time_2jobs(job_1, job_2
                                           )

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
            log.error(
                f"job {final_job.job_code} has no min_number_of_workers or max_number_of_workers and we assumed as 1")
            pass

        for nbr_worker in range(
            min_number_of_workers,
            max_number_of_workers + 1,
        ):
            shared_worker_count.add(nbr_worker)

        all_qualified_worker_codes = set()

        # evaluate_DateTimeTolerance = KandboxRuleToleranceRule()
        for worker_id in self.workers_dict.keys():
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

        for k, v in curr_job.location.historical_serving_worker_distribution.items():
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
                candidate_dict[(curr_job.requested_primary_worker_code,)] = SCORE_Primary
            except:
                log.debug("WHY?")

        primary_worker_codes = (curr_job.requested_primary_worker_code,)
        if primary_worker_codes not in candidate_dict.keys():
            if min_number_of_workers <= 1:
                log.debug(f"requested worker not added! {primary_worker_codes}")
                candidate_dict[primary_worker_codes] = SCORE_Primary

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
        final_job_workers_ranked = [
            k
            for k, v in sorted(
                candidate_dict.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ][0:80]
        if len(candidate_dict) > 20:
            log.debug(
                f"{final_job.job_code}, candidates_length = {len(candidate_dict)},  be careful ..."
            )  # --> {candidate_dict}

        final_job.searching_worker_candidates = final_job_workers_ranked
        # [(curr_job.requested_primary_worker_code,)]
        # curr_job.scheduled_worker_codes = orig_scheduled_worker_codes

        return final_job_workers_ranked

    def _get_sorted_worker_code_list(self, job_index):
        # TODO
        w_set = set()
        if len(self.jobs) >= 1:
            for w_list in self.jobs[self.current_job_i].searching_worker_candidates:
                for w_code in w_list:
                    w_set.add(w_code)
        return w_set

        # return list(self.workers_dict.keys())[0 : self.config["nbr_of_observed_workers"]]

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

    def _move_to_next_unplanned_job(self):
        self.current_job_i += 1
        # if self.current_job_i >= len(self.jobs):
        #  return True
        for step_i in range(len(self.jobs)):
            if self.current_job_i >= len(self.jobs):
                self.current_job_i = 0
            if self.jobs[self.current_job_i].planning_status == JobPlanningStatus.UNPLANNED:
                self.current_job_code = self.jobs[self.current_job_i].job_code

                return True
            self.current_job_i += 1

        return False

    def _move_to_next_not_replayed_job(self) -> str:
        """Find next not replay, but inplanning/planned job"""
        self.current_job_i += 1
        # if self.current_job_i >= len(self.jobs):
        #  return True
        for step_i in range(len(self.jobs)):
            if self.current_job_i >= len(self.jobs):
                self.current_job_i = 0
            if (self.jobs[self.current_job_i].planning_status != JobPlanningStatus.UNPLANNED) and (
                not self.jobs[self.current_job_i].is_replayed
            ):
                return self.jobs[self.current_job_i].job_code
            self.current_job_i += 1

        return None

    def _get_reward(self):
        # This only is based on inplanning

        if self.nbr_inplanning == 0:
            return 0

        job_count = 0
        inplanning_job_count = 0
        for j in self.jobs:
            if not j.is_active:
                continue
            job_count += 1
            if j.planning_status != JobPlanningStatus.UNPLANNED:
                inplanning_job_count += 1

        if job_count <= 0:
            return 0
        reward = inplanning_job_count / job_count
        return reward + 0.1

        """ 2020-10-17 14:43:19 Not good.
        travel_reward = (
            (self.expected_travel_time_so_far / self.nbr_inplanning)
            - (self.total_travel_time / self.total_travel_worker_job_count)
        ) / (self.expected_travel_time_so_far / self.nbr_inplanning)

        """
        if travel_reward > 1:  # Very unlikely
            travel_reward = 1
        if travel_reward < -0.5:
            travel_reward = -0.5
        travel_reward = 0

        reward = (nbr_inplanning * 0.2 / len(self.jobs)) + travel_reward

        if self.nbr_inplanning == len(self.jobs):
            reward = reward + 2  # Additional points

    def _get_observation(self):
        # return self._get_observation_numerical()
        return self._get_observation_slot_list_dict()

        # return self._get_observation_slot_list_tuple()

        # return self._get_observation_slot_list_tuple_toy()
        try:
            return self._get_observation_numerical()
        except:
            log.error("Error in _get_observation_numerical , returning empty observation {}")
            return rl_env.action_space.sample()
            # return {}

    def _get_observation_numerical(self):
        # agent_vector is current observation.
        obs_dict = {}

        if (len(self.jobs) < 1) | (len(self.workers) < 1):
            log.error(
                "Error, no workers or no jobs , returning empty observation (obs_dict = empty)"
            )
            # raise LookupError("Error, Env has no workers or no jobs , returning obs_dict = empty")
            return obs_dict

        self.config["NBR_FEATURE_PER_TECH"] = 19
        # NBR_FEATURE_WORKER_ONLY = self.config['NBR_FEATURE_WORKER_ONLY']
        # NBR_FEATURE_CUR_JOB_n_OVERALL  = self.config['NBR_FEATURE_CUR_JOB_n_OVERALL']
        # NBR_WORK_TIME_SLOT_PER_DAY = self.config['NBR_FEATURE_CUR_JOB_n_OVERALL'] # 1

        self.current_observed_worker_list = self._get_sorted_worker_code_list(self.current_job_i)

        curr_work_time_slots = []

        agent_vector = np.zeros(
            self.config["NBR_FEATURE_PER_TECH"]
            * self.config["nbr_of_days_planning_window"]
            * len(self.current_observed_worker_list)
        )

        o_start_longitude = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        o_start_latitude = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        # o_max_available_working_slot_duration = np.zeros(self.config['nbr_of_observed_workers']* self.config['nbr_of_days_planning_window'])

        o_end_longitude = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        o_end_latitude = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        o_average_longitude = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        o_average_latitude = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        #                                         =
        o_nbr_of_jobs_per_worker_day = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        o_total_travel_minutes = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        o_first_job_start_minutes = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        o_total_occupied_duration = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        o_total_unoccupied_duration = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        #                                         =
        o_max_available_working_slot_duration = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        o_max_available_working_slot_start = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        o_max_available_working_slot_end = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        o_max_unoccupied_rest_slot_duration = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )
        o_total_available_working_slot_duration = np.zeros(
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )

        # + NBR_FEATURE_WORKER_ONLY + NBR_FEATURE_CUR_JOB_n_OVERALL ) # .tolist()

        # Firstly the assigned job stats
        for current_job_worker_index in range(len(self.current_observed_worker_list)):
            # setup home (start,end) GPS
            # x,y = get_normalized_location(self.workers_dict[worker_index]['home_gps'])
            worker = self.workers_dict[self.current_observed_worker_list[current_job_worker_index]]
            worker_index = worker.worker_index

            # assigned time slots for each worker in agent_vector
            # curr_total_free_duration = self.workers_dict[worker_index]['total_free_duration']

            for day_i in range(self.config["nbr_of_days_planning_window"]):

                # Features for this worker_day_assignment
                f_start_longlat = self.get_start_gps_for_worker_day(worker, day_i)
                f_end_longlat = self.get_end_gps_for_worker_day(worker, day_i)
                f_average_longlat = self.get_start_gps_for_worker_day(worker, day_i)

                f_nbr_of_jobs = 0
                f_total_travel_minutes = 0
                # I use 0--24 hours for each day. Do not accumulate.
                f_first_job_start_minutes = self.config["minutes_per_day"]
                f_last_job_end_minutes = self.config["minutes_per_day"]  # (day_i + 1) *

                f_total_occupied_duration = 0  # Sum up from assigned_jobs
                f_total_unoccupied_duration = self.config["minutes_per_day"] * 1

                f_max_available_working_slot_duration = 0
                f_max_available_working_slot_start = 0
                f_max_available_working_slot_end = 0

                f_min_available_working_slot_duration = 0  # kandbox_config.KANDBOX_MAXINT
                f_min_available_working_slot_start = 0
                f_min_available_working_slot_end = 0

                f_max_unoccupied_rest_slot_duration = 0
                f_total_available_working_slot_duration = 0  # Sum up from free_slots

                last_job_end = day_i * self.config["minutes_per_day"]

                # for assigned_job_index_info in worker[  "assigned_jobs"  ]:  # TODO, performance, already sorted, not necessary to loop through all.
                # for day_i in range(self.config["nbr_of_days_planning_window"]):
                job_code_list_today = []
                travel_minutes_list_today = []
                overlap_slots = self.slot_server.get_overlapped_slots(
                    worker_id=worker.worker_code,
                    start_minutes=day_i * 1440,
                    end_minutes=(day_i + 1) * 1440,
                )

                job_slot_prev_travel_minutes = 0

                for a_slot in overlap_slots:
                    if a_slot.slot_type == TimeSlotType.JOB_FIXED:
                        assigned_job_code = a_slot.assigned_job_codes[0]
                        job_code_list_today.append(a_slot.assigned_job_codes[0])
                        travel_minutes_list_today.append(job_slot_prev_travel_minutes)

                    # TODO, performance, already sorted, not necessary to loop through all.
                    elif a_slot.slot_type == TimeSlotType.FLOATING:
                        (
                            prev_travel,
                            next_travel,
                            inside_travel,
                        ) = self.get_travel_time_jobs_in_slot(a_slot, a_slot.assigned_job_codes)

                        free_minutes = (
                            a_slot.end_minutes
                            - a_slot.end_minutes
                            - (prev_travel + next_travel + sum(inside_travel))
                        )

                        f_total_available_working_slot_duration += free_minutes
                        if free_minutes > f_max_available_working_slot_duration:
                            f_max_available_working_slot_duration = free_minutes
                            f_max_available_working_slot_start = a_slot.start_minutes
                            f_max_available_working_slot_end = a_slot.end_minutes

                        if f_min_available_working_slot_duration == 0:
                            f_min_available_working_slot_duration = free_minutes
                            f_min_available_working_slot_start = a_slot.start_minutes
                            f_min_available_working_slot_end = a_slot.end_minutes
                        elif free_minutes < f_min_available_working_slot_duration:
                            f_min_available_working_slot_duration = free_minutes
                            f_min_available_working_slot_start = a_slot.start_minutes
                            f_min_available_working_slot_end = a_slot.end_minutes

                        if len(a_slot.assigned_job_codes) > 0:
                            job_code_list_today += list(a_slot.assigned_job_codes)
                            travel_minutes_list_today += [prev_travel] + inside_travel
                        job_slot_prev_travel_minutes = (
                            next_travel  # Here i assume that it is leading to next job/ or home
                        )

                for job_seq, assigned_job_code in enumerate(job_code_list_today):  #
                    try:
                        the_job = self.jobs_dict[assigned_job_code]
                    except KeyError:
                        log.error(f"JOB:{assigned_job_code} is not found in ENV->self.jobs_dict")
                        continue

                    # This job is assigned to this day.
                    if f_first_job_start_minutes < the_job.scheduled_start_minutes:
                        f_first_job_start_minutes = the_job.scheduled_start_minutes
                        f_start_longlat = [
                            the_job.location.geo_longitude,
                            the_job.location.geo_latitude,
                        ]  #
                    if (
                        the_job.scheduled_start_minutes + the_job.scheduled_duration_minutes
                        < f_last_job_end_minutes
                    ):
                        f_last_job_end_minutes = (
                            the_job.scheduled_start_minutes + the_job.scheduled_duration_minutes
                        )
                        f_end_longlat = [
                            the_job.location.geo_longitude,
                            the_job.location.geo_latitude,
                        ]  #

                    f_average_longlat = [
                        ((f_average_longlat[0] * f_nbr_of_jobs) + the_job.location.geo_longitude)
                        / (f_nbr_of_jobs + 1),
                        ((f_average_longlat[1] * f_nbr_of_jobs) + the_job.location.geo_latitude)
                        / (f_nbr_of_jobs + 1),
                    ]

                    f_nbr_of_jobs += 1
                    f_total_travel_minutes += travel_minutes_list_today[job_seq]

                    f_total_occupied_duration += the_job.scheduled_duration_minutes
                    f_total_unoccupied_duration -= (
                        the_job.scheduled_duration_minutes + travel_minutes_list_today[job_seq]
                    )

                    curr_rest_duration_before_job = (
                        the_job.scheduled_start_minutes
                        - travel_minutes_list_today[job_seq]
                        - last_job_end
                    )
                    if curr_rest_duration_before_job > f_max_unoccupied_rest_slot_duration:
                        f_max_unoccupied_rest_slot_duration = curr_rest_duration_before_job

                if f_total_available_working_slot_duration < 0:
                    # log.debug("Error: f_total_available_working_slot_duration < 0")
                    f_total_available_working_slot_duration = 0

                curr_worker_day_i = (
                    current_job_worker_index * self.config["nbr_of_days_planning_window"] + day_i
                )

                o_start_longitude[curr_worker_day_i] = f_start_longlat[
                    0
                ]  # current_job_worker_index, day_i
                o_start_latitude[curr_worker_day_i] = f_start_longlat[1]

                o_end_longitude[curr_worker_day_i] = f_end_longlat[0]
                o_end_latitude[curr_worker_day_i] = f_end_longlat[1]
                o_average_longitude[curr_worker_day_i] = f_average_longlat[0]
                o_average_latitude[curr_worker_day_i] = f_average_longlat[1]
                #
                o_nbr_of_jobs_per_worker_day[curr_worker_day_i] = f_nbr_of_jobs
                o_total_travel_minutes[curr_worker_day_i] = f_total_travel_minutes
                o_first_job_start_minutes[curr_worker_day_i] = f_first_job_start_minutes
                o_total_occupied_duration[curr_worker_day_i] = f_total_occupied_duration
                o_total_unoccupied_duration[curr_worker_day_i] = f_total_unoccupied_duration
                #
                o_max_available_working_slot_duration[
                    curr_worker_day_i
                ] = f_max_available_working_slot_duration
                o_max_available_working_slot_start[
                    curr_worker_day_i
                ] = f_max_available_working_slot_start
                o_max_available_working_slot_end[
                    curr_worker_day_i
                ] = f_max_available_working_slot_end
                o_max_unoccupied_rest_slot_duration[
                    curr_worker_day_i
                ] = f_max_unoccupied_rest_slot_duration
                o_total_available_working_slot_duration[
                    curr_worker_day_i
                ] = f_total_available_working_slot_duration
                # Not useful, deprecated. Use obs_tuple instead 2020-09-18 08:29:37
                agent_vector[
                    current_job_worker_index
                    * self.config["NBR_FEATURE_PER_TECH"]
                    * self.config["nbr_of_days_planning_window"]
                    + day_i
                    * self.config["NBR_FEATURE_PER_TECH"]: current_job_worker_index
                    * self.config["NBR_FEATURE_PER_TECH"]
                    * self.config["nbr_of_days_planning_window"]
                    + (day_i + 1) * self.config["NBR_FEATURE_PER_TECH"]
                ] = [
                    f_start_longlat[0],
                    f_start_longlat[1],
                    f_end_longlat[0],
                    f_end_longlat[1],
                    f_average_longlat[0],
                    f_average_longlat[1],
                    f_nbr_of_jobs,
                    f_total_travel_minutes,
                    f_first_job_start_minutes,
                    f_total_occupied_duration,
                    f_total_unoccupied_duration,
                    f_max_available_working_slot_duration,
                    f_max_available_working_slot_start,
                    f_max_available_working_slot_end,
                    f_min_available_working_slot_duration,
                    f_min_available_working_slot_start,
                    f_min_available_working_slot_end,
                    f_max_unoccupied_rest_slot_duration,
                    f_total_available_working_slot_duration,
                ]

            # worker_feature_begin_offset = NBR_FEATURE_PER_TECH*worker_index + NBR_DAYS*MAX_ASSIGNED_TIME_SLOT_PER_DAY*NBR_WORK_TIME_SLOT_PER_DAY + NBR_DAYS
            # agent_vector[ worker_feature_begin_offset + 2] = curr_total_free_duration
            # agent_vector[worker_feature_begin_offset + 3] = curr_max_free_slot_duration

        """
    # Secondary all worker statistics
    for current_job_worker_index in self.current_observed_worker_list:
      # setup home (start,end) GPS
      # x,y = get_normalized_location(self.workers_dict[worker_index]['home_gps'])
      worker = self.workers_dict[self.current_observed_worker_list[current_job_worker_index]]

      worker_index = worker['worker_index']
      agent_vector[NBR_FEATURE_PER_TECH*worker_index   + 0: \
                   NBR_FEATURE_PER_TECH*worker_index + NBR_WORK_TIME_SLOT_PER_DAY] \
          =  [ 0, 0 , worker['geo_longitude'] , worker['geo_latitude'] ]
      agent_vector[NBR_FEATURE_PER_TECH*(worker_index+1) - 4: \
                   NBR_FEATURE_PER_TECH*(worker_index+1) - 0 ] \
          =  [ 0, 0 , x,y]

    for worker_index in range(len(self.workers_dict)):
      # Historical customer visit GPS Gaussian , Sigma, Gamma, 2 DIMENSIONAL
      # and others 4
      agent_vector[len(self.workers_dict)*NBR_FEATURE_PER_TECH + worker_index] \
        = self.workers_dict[worker_index]['level'] / 5
    """
        # Thirdly  the job statistics

        # Now append the visit information AS THE 2nd half.
        # job_feature_start_index = len(self.workers_dict)*NBR_FEATURE_PER_TECH + NBR_FEATURE_WORKER_ONLY

        if self.current_job_i >= len(self.jobs):
            new_job_i = len(self.jobs) - 1
        else:
            new_job_i = self.current_job_i

        # obs_dict['worker_job_assignment_matrix'] = agent_vector
        obs_dict["assignment.start_longitude"] = o_start_longitude
        obs_dict["assignment.start_latitude"] = o_start_latitude
        obs_dict[
            "assignment.max_available_working_slot_duration"
        ] = o_max_available_working_slot_duration

        # obs_dict['job.features'] = np.zeroes(3)
        # obs_dict['job.mandatory_minutes_minmax_flag'] = np.zeros(1)
        obs_dict[
            "job.mandatory_minutes_minmax_flag"
        ] = 1  # self.jobs[new_job_i][ "mandatory_minutes_minmax_flag"  ]
        obs_dict["job.requested_start_minutes"] = np.zeros(1)
        obs_dict["job.requested_start_minutes"][0] = self.jobs[
            new_job_i
        ].requested_start_min_minutes
        if obs_dict["job.requested_start_minutes"][0] < 0:
            obs_dict["job.requested_start_minutes"][0] = 0
        elif (
            obs_dict["job.requested_start_minutes"][0]
            >= self.config["minutes_per_day"] * self.config["nbr_of_days_planning_window"] * 2
        ):
            obs_dict["job.requested_start_minutes"][0] = (
                self.config["minutes_per_day"] * self.config["nbr_of_days_planning_window"] * 2 - 1
            )

        obs_dict["job.requested_duration_minutes"] = np.zeros(1)
        obs_dict["job.requested_duration_minutes"][0] = self.jobs[
            new_job_i
        ].requested_duration_minutes

        obs_dict["job.geo_longitude"] = np.zeros(1)
        obs_dict["job.geo_longitude"][0] = self.jobs[new_job_i].location.geo_longitude
        obs_dict["job.geo_latitude"] = np.zeros(1)
        obs_dict["job.geo_latitude"][0] = self.jobs[new_job_i].location.geo_latitude

        obs_tuple = (
            o_start_longitude,
            o_start_latitude,
            o_end_longitude,
            o_end_latitude,
            o_average_longitude,
            o_average_latitude,
            #
            o_nbr_of_jobs_per_worker_day,
            o_total_travel_minutes,
            o_first_job_start_minutes,
            o_total_occupied_duration,
            o_total_unoccupied_duration,
            #
            o_max_available_working_slot_duration,
            o_max_available_working_slot_start,
            o_max_available_working_slot_end,
            o_max_unoccupied_rest_slot_duration,
            o_total_available_working_slot_duration,
            #
            1,  # self.jobs[new_job_i]["mandatory_minutes_minmax_flag"],
            obs_dict["job.requested_start_minutes"],
            obs_dict["job.requested_duration_minutes"],
            obs_dict["job.geo_longitude"],
            obs_dict["job.geo_latitude"],
        )

        """
f_start_longlat[0], f_start_longlat[1], f_end_longlat[0], f_end_longlat[1], f_average_longlat[0],
          f_average_longlat[1],  f_nbr_of_jobs, f_total_travel_minutes, f_first_job_start_minutes,
          f_total_occupied_duration, f_total_unoccupied_duration, f_max_available_working_slot_duration, f_max_available_working_slot_start, f_max_available_working_slot_end,
          f_min_available_working_slot_duration, f_min_available_working_slot_start, f_min_available_working_slot_end, f_max_unoccupied_rest_slot_duration, f_total_available_working_slot_duration

    """

        """
    visit_vector = list(range(5))
    # Location of the new job is added to the end of agent_vector.
    visit_vector[0] = self.jobs[self.current_job_i]['requested_duration_minutes']

    visit_vector[1] = self.jobs[self.current_job_i]['mandatory_minutes_minmax_flag']
    # visit_vector[2] = self.jobs[self.current_job_i]['preferred_minutes_minmax_flag']
    visit_vector[3] = self.jobs[self.current_job_i]['requested_start_minutes']
    visit_vector[4] = self.jobs[self.current_job_i]['requested_start_minutes']
    """

        # obs_dict['job.requested_start_max_minutes'] =  self.jobs[self.current_job_i]['requested_start_minutes']

        # agent_vector[job_feature_start_index +3] = self.jobs[self.current_job_i]['expected_job_day'] / 30
        # agent_vector[job_feature_start_index +4] = self.jobs[self.current_job_i]['tolerated_day_min']  /10
        # agent_vector[job_feature_start_index +5] = self.jobs[self.current_job_i]['tolerated_day_max']  /10

        # visit_vector[ 5] = 0 # self.jobs[self.current_job_i]['customer_level']
        # visit_vector[ 6] = 0 # self.jobs[self.current_job_i]['product_level']

        # obs_dict['current_job_vector'] = visit_vector

        # Finished looping through all workers
        return obs_tuple  # OrderedDict(obs_dict)

    # ***************************************************************
    # # Internal functions
    # ***************************************************************

    def _set_spaces(self):
        obs_slot_low = (
            [self.config["geo_longitude_min"]] * 4 + [self.config["geo_latitude_min"]] * 4 + [0] * 9
        )
        obs_slot_high = (
            [self.config["geo_longitude_max"]] * 4
            + [self.config["geo_latitude_max"]] * 4
            + [self.config["max_nbr_of_jobs_per_day_worker"] + 1]
            + [self.config["minutes_per_day"]] * 3
            + [self.config["minutes_per_day"] * self.config["nbr_of_days_planning_window"]] * 3
            + [1]
            + [self.config["nbr_of_observed_workers"]]
        )
        self.obs_slot_space = spaces.Box(
            low=np.array(obs_slot_low),
            high=np.array(obs_slot_high),
            # shape=(len(obs_slot_high),),
            dtype=np.float32,
        )

        # self.obs_slot_space = spaces.Tuple(
        #     (
        #         # start_loc, end_loc, avg_loc
        #         spaces.Box(
        #             low=self.config["geo_longitude_min"],
        #             high=self.config["geo_longitude_max"],
        #             shape=(4,),
        #             dtype=np.float32,
        #         ),
        #         spaces.Box(
        #             low=self.config["geo_latitude_min"],
        #             high=self.config["geo_latitude_max"],
        #             shape=(4,),
        #             dtype=np.float32,
        #         ),
        #         # f_nbr_of_jobs,
        #         spaces.Box(
        #             low=0,
        #             high=self.config["max_nbr_of_jobs_per_day_worker"] + 1,
        #             shape=(1,),
        #             dtype=np.float32,
        #         ),
        #         # f_slot_duration, f_total_travel_minutes,f_total_occupied_duration, #  f_total_unoccupied_duration, f_max_available_working_slot_duration
        #         spaces.Box(
        #             low=0,
        #             high=self.config["minutes_per_day"],
        #             shape=(3,),
        #             dtype=np.float32,
        #         ),
        #         # f_slot_start_minutes, f_first_job_start_minutes, # f_max_available_working_slot_start, f_max_available_working_slot_end,
        #         spaces.Box(
        #             low=0,
        #             high=self.config["minutes_per_day"]
        #             * self.config["nbr_of_days_planning_window"],
        #             shape=(3,),
        #             dtype=np.float32,
        #         ),
        #         # f_max_unoccupied_rest_slot_duration --- Looks like current RL can only do working hour dispatching.
        #         # f_min_available_working_slot_duration,
        #         # f_min_available_working_slot_start,
        #         # f_min_available_working_slot_end,
        #         # spaces.Discrete(2),  # Mandatory start time or not
        #         spaces.Discrete(2),  # valid slot indicator. ==1
        #         spaces.Discrete(self.config["nbr_of_observed_workers"]),  # technician ID
        #     )
        # )
        obs_job_low = (
            [self.config["geo_longitude_min"]]
            + [self.config["geo_latitude_min"]]
            + [0]
            + [0 - (self.PLANNING_WINDOW_LENGTH * 5)] * 3
            + [0] * 4
        )
        obs_job_high = (
            [self.config["geo_longitude_max"]]
            + [self.config["geo_latitude_max"]]
            + [self.config["minutes_per_day"]]
            + [self.PLANNING_WINDOW_LENGTH * 5] * 3
            + [self.config["nbr_of_observed_workers"]] * 2
            + [1] * 2
        )
        self.obs_job_space = spaces.Box(
            low=np.array(obs_job_low),
            high=np.array(obs_job_high),
            # shape=(len(obs_job_high),),
            dtype=np.float32,
        )

        # self.obs_job_space = spaces.Tuple(
        #     (
        #         # start_loc, end_loc, avg_loc
        #         spaces.Box(
        #             low=self.config["geo_longitude_min"],
        #             high=self.config["geo_longitude_max"],
        #             shape=(1,),
        #             dtype=np.float32,
        #         ),
        #         spaces.Box(
        #             low=self.config["geo_latitude_min"],
        #             high=self.config["geo_latitude_max"],
        #             shape=(1,),
        #             dtype=np.float32,
        #         ),
        #         # f_job_duration,
        #         spaces.Box(
        #             low=0,
        #             high=self.config["minutes_per_day"],
        #             shape=(1,),
        #             dtype=np.float32,
        #         ),
        #         # min, max,  f_job_start_minutes
        #         spaces.Box(
        #             low=0 - (self.PLANNING_WINDOW_LENGTH * 5),
        #             high=self.PLANNING_WINDOW_LENGTH * 5,
        #             shape=(3,),
        #             dtype=np.float32,
        #         ),
        #         #  # min  max nbr of share
        #         spaces.Box(
        #             low=0,
        #             high=self.config["nbr_of_observed_workers"],
        #             shape=(2,),
        #             dtype=np.float32,
        #         ),
        #         # f_max_unoccupied_rest_slot_duration --- Looks like current RL can only do working hour dispatching.
        #         # f_min_available_working_slot_duration,
        #         # f_min_available_working_slot_start,
        #         # f_min_available_working_slot_end,
        #         # spaces.Discrete(2),  # Mandatory start time or not
        #         spaces.Discrete(2),  # valid slot indicator. ==1
        #         spaces.Discrete(2),  # fixed time requirements
        #     )
        # )
        self.observation_space = spaces.Dict(
            {
                "slots": Repeated(self.obs_slot_space, max_len=self.MAX_OBSERVED_SLOTS),
                "jobs": Repeated(self.obs_job_space, max_len=self.MAX_OBSERVED_SLOTS),
            }
        )

        # action_low = 0
        # action_high = np.ones(MAX_OBSERVED_SLOTS)
        # action_low[0:self.config['nbr_of_observed_workers']] = 0
        # action_high[0:self.config['nbr_of_observed_workers']] = 1

        self.action_space = spaces.Box(
            low=0, high=1, shape=(self.MAX_OBSERVED_SLOTS,), dtype=np.float32
        )
        # self.action_space = spaces.Discrete(self.MAX_OBSERVED_SLOTS)

    def _get_observation_slot_list_tuple(self):
        if (len(self.jobs) < 1) | (len(self.workers) < 1):
            log.error(
                "Error, no workers or no jobs , returning empty observation (obs_dict = empty)"
            )
            # raise LookupError("Error, Env has no workers or no jobs , returning obs_dict = empty")
            return (0, 0)

        if self.current_job_i >= len(self.jobs):
            self.current_job_i = 0
        # new_job_i = self.current_job_i
        current_capable_worker_set = self._get_sorted_worker_code_list(self.current_job_i)

        sorted_slot_codes = sorted(list(self.slot_server.time_slot_dict.keys()))
        slot_dict = self.slot_server.time_slot_dict

        curr_work_time_slots = []
        max_available_working_slot_duration = 0
        viewed_slots = []

        for slot_code in sorted_slot_codes:
            # for work_time_i in  range(len( self.workers_dict[worker_code]['assigned_jobs'] ) ): # nth assigned job time unit.
            if slot_code in config.DEBUGGING_SLOT_CODE_SET:
                log.debug(f"_get_observation_slot_list debug {slot_code}")

            # if a_slot.slot_type in (TimeSlotType.JOB_FIXED, TimeSlotType.FLOATING):
            try:
                a_slot = self.slot_server.get_slot(self.redis_conn.pipeline(), slot_code)
                if a_slot.worker_id not in current_capable_worker_set:
                    continue
                the_assigned_codes = sorted(
                    a_slot.assigned_job_codes,
                    key=lambda jc: self.jobs_dict[jc].scheduled_start_minutes,
                )
            except KeyError as ke:
                log.error(
                    f"unknown worker code, or unknown job codes to the env. slot_code = {slot_code}, error = {str(ke)}"
                )
                print(ke)
                continue
            except MissingSlotException as mse:
                log.error(
                    f"MissingSlotException - unknow slot_code = {slot_code}, error = {str(mse)}"
                )
                print(mse)
                continue

            (
                prev_travel,
                next_travel,
                inside_travel,
            ) = self.get_travel_time_jobs_in_slot(a_slot, a_slot.assigned_job_codes)
            #  , what if there is no job?  you get 0,[],0
            all_travels = [prev_travel] + inside_travel + [next_travel]

            f_total_travel_minutes = sum(all_travels)
            f_max_travel_minutes_index = sum(all_travels[:-1])

            slot_vector = np.zeros(self.NBR_FEATURE_PER_SLOT)

            slot_vector[0:2] = [
                self.normalize(a_slot.start_location[0], "longitude"),
                self.normalize(a_slot.start_location[1], "latitude"),
            ]
            slot_vector[2] = 0 if a_slot.start_location[2] == "H" else 1

            slot_vector[3:5] = [
                self.normalize(a_slot.end_location[0], "longitude"),
                self.normalize(a_slot.end_location[1], "latitude"),
            ]
            slot_vector[5] = 0 if a_slot.end_location[2] == "H" else 1

            slot_vector[6] = self.normalize(
                len(a_slot.assigned_job_codes), "max_job_in_slot"
            )  # f_nbr_of_jobs = 0
            slot_vector[7] = self.normalize(f_total_travel_minutes, "day_minutes_1440")
            if len(a_slot.assigned_job_codes) < 1:
                slot_vector[8:10] = slot_vector[0:2]
                slot_vector[10:12] = slot_vector[3:5]
                # all_location_0 = [a_slot.start_location[0], a_slot.end_location[0]]
                # all_location_1 = [a_slot.start_location[1], a_slot.end_location[1]]
                #   [
                #     sum(all_location_0) / len(all_location_0),
                #     sum(all_location_1) / len(all_location_1),
                #     sum(all_location_0) / len(all_location_0),
                #     sum(all_location_1) / len(all_location_1),
                # ]
            else:
                slot_vector[8:10] = [
                    self.normalize(
                        self.jobs_dict[a_slot.assigned_job_codes[0]].location[0], "longitude"
                    ),
                    self.normalize(
                        self.jobs_dict[a_slot.assigned_job_codes[0]].location[1], "latitude"
                    ),
                ]
                slot_vector[10:12] = [
                    self.normalize(
                        self.jobs_dict[a_slot.assigned_job_codes[-1]].location[0], "longitude"
                    ),
                    self.normalize(
                        self.jobs_dict[a_slot.assigned_job_codes[-1]].location[1], "latitude"
                    ),
                ]

                # all_location_0 = [
                #     self.jobs_dict[a_slot.assigned_job_codes[j]].location[0]
                #     for j in range(len(a_slot.assigned_job_codes))
                # ]
                # all_location_1 = [
                #     self.jobs_dict[a_slot.assigned_job_codes[j]].location[1]
                #     for j in range(len(a_slot.assigned_job_codes))
                # ]
                # slot_vector[10:12] = [
                #     sum(all_location_0) / len(all_location_0),
                #     sum(all_location_1) / len(all_location_1),
                # ]

            # f_total_occupied_duration  # Sum up from assigned_jobs
            f_total_occupied_duration = sum(
                self.jobs_dict[a_slot.assigned_job_codes[j]].scheduled_duration_minutes
                for j in range(len(a_slot.assigned_job_codes))
            )
            slot_vector[12] = self.normalize(f_total_occupied_duration, "day_minutes_1440")
            if (
                a_slot.end_minutes - a_slot.start_minutes - slot_vector[12]
                > max_available_working_slot_duration
            ):
                max_available_working_slot_duration = (
                    a_slot.end_minutes - a_slot.start_minutes - slot_vector[12]
                )

            slot_vector[13] = self.normalize(a_slot.start_minutes, "start_minutes")
            slot_vector[14] = self.normalize(a_slot.end_minutes, "start_minutes")
            # Start time within a day
            slot_vector[15] = self.normalize(a_slot.start_minutes % 1440, "day_minutes_1440")
            slot_vector[16] = self.normalize(a_slot.end_minutes % 1440, "day_minutes_1440")
            available_free_minutes = (
                a_slot.end_minutes - a_slot.start_minutes - slot_vector[12] - f_total_travel_minutes
            )
            slot_vector[17] = self.normalize(available_free_minutes, "day_minutes_1440")
            slot_vector[18] = self.normalize(a_slot.start_overtime_minutes, "duration")
            slot_vector[19] = self.normalize(a_slot.end_overtime_minutes, "duration")
            # Secondary tech
            slot_vector[20] = 0
            # (  0 if self.workers_dict[a_slot.worker_id].flex_form_data["is_assistant"] else 1 )

            slot_vector[21] = 0  # self.workers_dict[a_slot.worker_id].worker_index
            slot_vector[22] = (
                1 if self.workers_dict[a_slot.worker_id].belongs_to_pair is not None else 0
            )
            slot_vector[23] = 0  # Future

            curr_work_time_slots.append(slot_vector)
            viewed_slots.append(a_slot)

        # Secondary overall statistics about workers, inplanning jobs, including un-planed visits
        unplanned_job_list = []
        current_job_list = []
        target_unplanned_job_i = None

        for job_code, new_job in self.jobs_dict.items():
            if not new_job.is_active:  # events and appt can not be U anyway
                continue
            if new_job.planning_status != JobPlanningStatus.UNPLANNED:
                continue

            unplanned_job_vector = np.zeros(self.NBR_FEATURE_PER_UNPLANNED_JOB)
            unplanned_job_vector[0] = self.normalize(new_job.requested_duration_minutes, "duration")
            unplanned_job_vector[1] = self.normalize(
                new_job.requested_start_min_minutes, "start_minutes"
            )
            unplanned_job_vector[2] = self.normalize(
                new_job.requested_start_max_minutes, "start_minutes"
            )
            # in case FS, FT, requested_start_min_minutes == requested_start_max_minutes. But they might mean other day - FT.
            unplanned_job_vector[3] = self.normalize(
                new_job.requested_start_minutes, "start_minutes"
            )
            unplanned_job_vector[4] = self.normalize(
                new_job.requested_start_min_minutes % 1440, "day_minutes_1440"
            )
            unplanned_job_vector[5] = 0  # 1 if new_job.flex_form_data["ServiceType"] == "FS" else 0
            unplanned_job_vector[6] = 0  # 1 if new_job.flex_form_data["ServiceType"] == "FT" else 0

            unplanned_job_vector[7:9] = [
                self.normalize(new_job.location[0], "longitude"),
                self.normalize(new_job.location[1], "latitude"),
            ]
            # Min shared tech
            unplanned_job_vector[9] = self.normalize(
                new_job.flex_form_data["min_number_of_workers"], "max_nbr_shared_workers"
            )
            unplanned_job_vector[10] = self.normalize(
                new_job.flex_form_data["max_number_of_workers"], "max_nbr_shared_workers"
            )

            unplanned_job_vector[
                11
            ] = 0  # self.workers_dict[  new_job.requested_primary_worker_code ].worker_index

            if new_job.job_code == self.jobs[self.current_job_i].job_code:
                target_unplanned_job_i = len(unplanned_job_list) - 1
                current_job_list.append(unplanned_job_vector)
            else:
                unplanned_job_list.append(unplanned_job_vector)

        if len(unplanned_job_list) + len(current_job_list) < 1:
            log.error("No jobs to observe, done?")
            return None  # (0, 0, 0)
        if len(curr_work_time_slots) < 1:
            log.error("No slots to observe, done?")
            return None  # (0, 0, 0)

        # Thirdly the current job being dispatched
        overview_vector = np.zeros(self.NBR_FEATURE_OVERVIEW)
        overview_vector[0] = 0  # target_unplanned_job_i
        overview_vector[1] = max_available_working_slot_duration
        overview_vector[2] = len(self.workers_dict.keys())
        overview_vector[3] = len(curr_work_time_slots)
        overview_vector[4] = len(self.jobs_dict.keys())
        overview_vector[5] = len(unplanned_job_list)
        overview_vector[6] = self.get_env_planning_horizon_start_minutes()
        overview_vector[7] = int(self.get_env_planning_horizon_start_minutes() / 1440) * 1440
        # Work, Rest days as one-hot
        # Overtime usage?
        #
        obs_tuple = [
            np.stack(curr_work_time_slots, axis=0),
            np.stack(current_job_list + current_job_list, axis=0),  # TODO   + unplanned_job_list
            # np.stack(, axis=0),
            overview_vector,
            viewed_slots,
        ]

        return obs_tuple  # OrderedDict(obs_dict)

    def _get_observation_slot_list_tuple_toy(self):
        curr_work_time_slots = self.curr_work_time_slots
        current_job_list = [self.unplanned_job_list[self.trial_step_count]]
        temp_merged = np.concatenate((
            self.curr_work_time_slots,
            self.unplanned_job_list[self.trial_step_count:] +
            self.unplanned_job_list[:self.trial_step_count]
        ), axis=1)

        obs_tuple = [
            np.stack(curr_work_time_slots, axis=0),
            np.stack(current_job_list + current_job_list, axis=0),
            np.stack(temp_merged, axis=0),
        ]

        return obs_tuple  # OrderedDict(obs_dict)

    def _get_observation_slot_list_dict(self):
        if (len(self.jobs) < 1) | (len(self.workers) < 1):
            log.error(
                "Error, no workers or no jobs , returning empty observation (obs_dict = empty)"
            )
            # raise LookupError("Error, Env has no workers or no jobs , returning obs_dict = empty")
            return (0, 0)

        if self.current_job_i >= len(self.jobs):
            self.current_job_i = 0
        # new_job_i = self.current_job_i
        current_capable_worker_set = self._get_sorted_worker_code_list(self.current_job_i)

        sorted_slot_codes = sorted(list(self.slot_server.time_slot_dict.keys()))
        slot_dict = self.slot_server.time_slot_dict

        curr_work_time_slots = []
        max_available_working_slot_duration = 0
        viewed_slots = []
        obs_dict = {
            "slots": [],
            "jobs": [],
        }

        for slot_code in sorted_slot_codes:
            # for work_time_i in  range(len( self.workers_dict[worker_code]['assigned_jobs'] ) ): # nth assigned job time unit.
            if slot_code in kandbox_config.DEBUGGING_SLOT_CODE_SET:
                log.debug(f"_get_observation_slot_list debug {slot_code}")

            # if a_slot.slot_type in (TimeSlotType.JOB_FIXED, TimeSlotType.FLOATING):
            try:
                a_slot = self.slot_server.get_slot(self.redis_conn.pipeline(), slot_code)
                if a_slot.worker_id not in current_capable_worker_set:
                    continue
                the_assigned_codes = sorted(
                    a_slot.assigned_job_codes,
                    key=lambda jc: self.jobs_dict[jc].scheduled_start_minutes,
                )
            except KeyError as ke:
                log.error(
                    f"unknown worker code, or unknown job codes to the env. slot_code = {slot_code}, error = {str(ke)}"
                )
                print(ke)
                continue
            except MissingSlotException as mse:
                log.error(
                    f"MissingSlotException - unknow slot_code = {slot_code}, error = {str(mse)}"
                )
                print(mse)
                continue

            (
                prev_travel,
                next_travel,
                inside_travel,
            ) = self.get_travel_time_jobs_in_slot(a_slot, a_slot.assigned_job_codes)
            #  , what if there is no job?  you get 0,[],0
            all_travels = [prev_travel] + inside_travel + [next_travel]

            f_total_travel_minutes = sum(all_travels)
            f_max_travel_minutes_index = sum(all_travels[:-1])

            longitude_vector = np.zeros(4)
            longitude_vector[0] = a_slot.start_location[0]
            longitude_vector[1] = a_slot.end_location[0]

            latitude_vector = np.zeros(4)
            latitude_vector[0] = a_slot.start_location[1]
            latitude_vector[1] = a_slot.end_location[1]

            if len(a_slot.assigned_job_codes) < 1:
                longitude_vector[2] = (longitude_vector[0] + longitude_vector[1]) / 2
                latitude_vector[2] = (latitude_vector[0] + latitude_vector[1]) / 2

                longitude_vector[3] = (longitude_vector[0] + longitude_vector[1]) / 2
                latitude_vector[3] = (latitude_vector[0] + latitude_vector[1]) / 2

            else:
                longitude_vector[2] = self.jobs_dict[a_slot.assigned_job_codes[0]].location[0]
                latitude_vector[2] = self.jobs_dict[a_slot.assigned_job_codes[0]].location[1]

                longitude_vector[3] = self.jobs_dict[a_slot.assigned_job_codes[-1]].location[0]
                latitude_vector[3] = self.jobs_dict[a_slot.assigned_job_codes[-1]].location[1]

            f_nbr_of_jobs = np.zeros(1)
            f_nbr_of_jobs[0] = len(a_slot.assigned_job_codes)

            slot_duration_vector = np.zeros(3)
            # f_slot_duration, f_total_travel_minutes,f_total_occupied_duration, # f_total_unoccupied_duration ### , f_max_available_working_slot_duration
            slot_duration_vector[0] = a_slot.end_minutes - a_slot.start_minutes
            slot_duration_vector[1] = f_total_travel_minutes
            slot_duration_vector[2] = f_total_occupied_duration = sum(
                self.jobs_dict[a_slot.assigned_job_codes[j]].scheduled_duration_minutes
                for j in range(len(a_slot.assigned_job_codes))
            )

            start_minutes_vector = np.zeros(3)
            # f_slot_start_minutes, f_first_job_start_minutes,  f_last_job_end_minutes  # f_max_available_working_slot_start, f_max_available_working_slot_end,
            start_minutes_vector[0] = (
                a_slot.start_minutes - self.get_env_planning_horizon_start_minutes()
            )
            start_minutes_vector[1] = start_minutes_vector[0]
            start_minutes_vector[2] = start_minutes_vector[0]

            if len(a_slot.assigned_job_codes) >= 1:
                start_minutes_vector[1] = (
                    self.jobs_dict[a_slot.assigned_job_codes[0]].scheduled_start_minutes
                    - a_slot.start_minutes
                )
                start_minutes_vector[2] = (
                    self.jobs_dict[a_slot.assigned_job_codes[-1]].scheduled_start_minutes
                    + self.jobs_dict[a_slot.assigned_job_codes[-1]].scheduled_duration_minutes
                    - a_slot.start_minutes
                )
                if start_minutes_vector[1] < 0:
                    start_minutes_vector[1] = 0
                if start_minutes_vector[2] < 0:
                    start_minutes_vector[2] = 0

                if start_minutes_vector[1] >= self.PLANNING_WINDOW_LENGTH:
                    start_minutes_vector[1] = self.PLANNING_WINDOW_LENGTH - 1
                if start_minutes_vector[2] >= self.PLANNING_WINDOW_LENGTH:
                    start_minutes_vector[2] = self.PLANNING_WINDOW_LENGTH - 1

            # (  0 if self.workers_dict[a_slot.worker_id].flex_form_data["is_assistant"] else 1 )
            # 1 if self.workers_dict[a_slot.worker_id].belongs_to_pair is not None else 0
            slot_obs = np.concatenate(
                (
                    np.array(longitude_vector),
                    np.array(latitude_vector),
                    np.array(f_nbr_of_jobs),
                    np.array(slot_duration_vector),
                    np.array(start_minutes_vector),
                    #   # valid slot, worker id
                    np.array([1, self.workers_dict[a_slot.worker_id].worker_index]),
                ),
                axis=0,
            )
            # (
            #     np.array(longitude_vector),
            #     np.array(latitude_vector),
            #     np.array(f_nbr_of_jobs),
            #     np.array(slot_duration_vector),
            #     np.array(start_minutes_vector),
            #     1,
            #     self.workers_dict[a_slot.worker_id].worker_index,
            # )

            obs_dict["slots"].append(slot_obs)

            viewed_slots.append(a_slot)
            if len(obs_dict["slots"]) >= self.MAX_OBSERVED_SLOTS:
                break

        # Secondary overall statistics about workers, inplanning jobs, including un-planed visits
        unplanned_job_list = []
        current_job_list = []
        target_unplanned_job_i = None

        for job_code, new_job in self.jobs_dict.items():
            if not new_job.is_active:  # events and appt can not be U anyway
                continue
            if new_job.planning_status != JobPlanningStatus.UNPLANNED:
                continue

            longitude_vector = np.zeros(1)
            longitude_vector[0] = new_job.location[0]

            latitude_vector = np.zeros(1)
            latitude_vector[0] = new_job.location[1]

            duration_vector = np.zeros(1)
            # f_slot_duration
            duration_vector[0] = new_job.requested_duration_minutes

            start_minutes_vector = np.zeros(3)
            start_minutes_vector[0] = (
                new_job.requested_start_min_minutes - self.get_env_planning_horizon_start_minutes()
            )
            start_minutes_vector[1] = (
                new_job.requested_start_max_minutes - self.get_env_planning_horizon_start_minutes()
            )
            start_minutes_vector[2] = (
                new_job.requested_start_minutes - self.get_env_planning_horizon_start_minutes()
            )

            for ii in range(3):
                if start_minutes_vector[ii] >= self.PLANNING_WINDOW_LENGTH * 5:
                    start_minutes_vector[ii] = self.PLANNING_WINDOW_LENGTH * 5 - 1
                if start_minutes_vector[ii] <= -self.PLANNING_WINDOW_LENGTH * 5:
                    start_minutes_vector[ii] = -self.PLANNING_WINDOW_LENGTH * 5 + 1

            share_vector = np.ones(2)
            # Min shared tech
            try:
                share_vector[0] = new_job.flex_form_data["min_number_of_workers"]
                share_vector[1] = new_job.flex_form_data["max_number_of_workers"]
            except:
                log.warn(f"job {new_job.job_code} has no min_number_of_workers")
                pass
            job_obs = np.concatenate(
                (
                    np.array(longitude_vector),
                    np.array(latitude_vector),
                    np.array(duration_vector),
                    np.array(start_minutes_vector),
                    np.array(share_vector),
                    #   # valid job,  NOT FS
                    np.array([1, 0]),
                ),
                axis=0,
            )
            # (
            #     np.array(longitude_vector),
            #     np.array(latitude_vector),
            #     np.array(duration_vector),
            #     np.array(start_minutes_vector),
            #     np.array(share_vector),
            #     1,  # valid job
            #     0,  # NOT FS
            # )

            if new_job.job_code == self.jobs[self.current_job_i].job_code:
                obs_dict["jobs"] = [job_obs] + obs_dict["jobs"]
            else:
                obs_dict["jobs"].append(job_obs)

            if len(obs_dict["jobs"]) >= self.MAX_OBSERVED_SLOTS:
                break

        if len(obs_dict["jobs"]) < 1:
            log.debug("No jobs to observed, done?")
            return obs_dict  # (0, 0, 0)
        if len(obs_dict["slots"]) < 1:
            log.debug("No slots to observed, done?")
            return obs_dict  # (0, 0, 0)

        # Thirdly the current job being dispatched
        # overview_vector = np.zeros(self.NBR_FEATURE_OVERVIEW)
        # overview_vector[0] = 0  # target_unplanned_job_i
        # overview_vector[1] = max_available_working_slot_duration
        # overview_vector[2] = len(self.workers_dict.keys())
        # overview_vector[3] = len(curr_work_time_slots)
        # overview_vector[4] = len(self.jobs_dict.keys())
        # overview_vector[5] = len(unplanned_job_list)
        # overview_vector[6] = self.get_env_planning_horizon_start_minutes()
        # overview_vector[7] = int(self.get_env_planning_horizon_start_minutes() / 1440) * 1440
        # Work, Rest days as one-hot
        # Overtime usage?
        #
        self.internal_obs_slot_list = viewed_slots
        # obs_tuple = [
        #     np.stack(curr_work_time_slots, axis=0),
        #     np.stack(current_job_list + current_job_list, axis=0),
        #     # overview_vector,
        # ]
        # if not self.observation_space.contains(obs_dict):
        #     print("obs is not Good: {}".format(obs_dict))

        # if not self.observation_space.contains(obs_dict):
        #     print("obs is not Good: {}".format(obs_dict))

        return obs_dict  # OrderedDict(obs_dict)

    def encode_dict_into_action(self, a_dict: ActionDict):
        MAX_OBSERVED_SLOTS = (
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )

        n = np.zeros(MAX_OBSERVED_SLOTS + 4)
        start_day_index = int(a_dict.scheduled_start_minutes / self.config["minutes_per_day"])

        for worker_code in a_dict.scheduled_worker_codes:
            worker_index = self.workers_dict[worker_code].worker_index
            n[worker_index * self.config["nbr_of_days_planning_window"] + start_day_index] = 1

        n[-4] = a_dict.scheduled_duration_minutes / 480  # 8 hours Max_job_length
        n[-3] = start_day_index  # * self.env.config['minutes_per_day']  +
        n[-2] = (a_dict.scheduled_start_minutes % self.config["minutes_per_day"]) / 1440
        n[-1] = (len(a_dict.scheduled_worker_codes)) / 1  # / 200 # 60 - shared count

        return n

    def decode_action_into_dict_native(self, action) -> ActionDict:
        """
        convert array of action_space ( worker_day-M*N, 4) into dictionary
        """
        MAX_OBSERVED_SLOTS = (
            self.config["nbr_of_observed_workers"] * self.config["nbr_of_days_planning_window"]
        )

        new_act = action.copy()
        max_i = np.argmax(new_act[0:MAX_OBSERVED_SLOTS])

        # action_day = int(new_act[-3] * self.config["nbr_of_days_planning_window"])
        action_day = max_i % self.config["nbr_of_days_planning_window"]
        if (new_act[-2] < 0) or (new_act[-2] > 1):
            log.warn(f"out of range for start mintues in new_act[-2]")
        job_start_time = action_day * self.config["minutes_per_day"] + (
            new_act[-2] * self.config["minutes_per_day"]
        )  # days * 1440 + minutes

        worker_index = int(max_i / self.config["nbr_of_days_planning_window"])
        scheduled_workers = [self.workers[worker_index].worker_code]
        # TODO
        shared_count = int(new_act[-1])

        c = action[0:MAX_OBSERVED_SLOTS]

        c.shape = [
            self.config["nbr_of_observed_workers"],
            self.config["nbr_of_days_planning_window"],
        ]

        all_worker_flags = c[0: self.config["nbr_of_observed_workers"], action_day]

        for i in range(1, shared_count):
            all_worker_flags[worker_index] = 0
            max_i = np.argmax(all_worker_flags)
            worker_index = max_i  # int(max_i/self.config["nbr_of_days_planning_window"])
            scheduled_workers.append(self.workers[max_i].worker_code)

        # temporary blocking duration chagne 2020-09-17 09:37:44
        a_dict = ActionDict(
            is_forced_action=False,
            job_code=self.jobs[self.current_job_i].job_code,
            action_type=ActionType.FLOATING,
            # JobType = JOB, which can be acquired from self.jobs_dict[job_code]
            scheduled_worker_codes=scheduled_workers,
            scheduled_start_minutes=job_start_time,
            scheduled_duration_minutes=action[-4] * 480,
        )
        return a_dict

    def decode_action_into_dict(self, action) -> ActionDict:
        """
        convert array of action_space ( worker_day-M*N, 4) into dictionary
        """

        if (action[-2] == 0) & (action[-3] == 0) & (action[-4] == 0) & (False):
            a_dict = self.decode_action_into_dict_heuristic_search(action)
        else:
            a_dict = self.decode_action_into_dict_native(action)
        #

        a_dict.job_code = self.jobs[self.current_job_i].job_code
        # TODO, why? 2020-10-26 13:08:39
        a_dict.action_type = ActionType.JOB_FIXED
        return a_dict

    def gen_action_from_one_job(self, one_job):
        return self.gen_action_from_actual_job(one_job)

    def gen_action_from_actual_job(self, one_job):

        a_dict = self.gen_action_dict_from_job(one_job, is_forced_action=True)
        return self.encode_dict_into_action(a_dict)

    def gen_action_dict_from_job(self, job: Job, is_forced_action: bool = False) -> ActionDict:
        if job is None:
            raise ValueError("error gen_action_dict_from_worker_absence")

        the_action_type = ActionType.FLOATING
        if job.planning_status in (JobPlanningStatus.COMPLETED, JobPlanningStatus.PLANNED):
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
                if (
                    time_slot_indices[idx] >= list_lengths[idx]
                ):  # This is the end of this worker's slots
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

    # https://numpydoc.readthedocs.io/en/latest/format.html#docstring-standard
    def decode_action_into_dict_heuristic_search(self, action):
        """Search for free slots in current env and heuristically decide start_datetime and duration.  Sequence of searching is determined by argmax of worker+day array

        Parameters
        ----------
        action : list(float)
            Input array of worker+day array. The rest of values in action_dict are discarded and re-calculated.

        Returns
        -------
        action_dict
            A dictionary containing the correct start end time.
            The assigned workers are specified by primary and secondary_list.
            Duration is filled in by requested_duration with formula Original / (1+(1.7^n))

        """
        curr_job = self.jobs[self.current_job_i]
        new_act = action.copy()
        max_i = np.argmax(new_act[0: len(self.workers)])
        action_worker_index = int(max_i / self.config["nbr_of_days_planning_window"])
        action_day_index = max_i % self.config["nbr_of_days_planning_window"]
        shared_count = int(new_act[-1])
        scheduled_duration = curr_job.requested_duration_minutes / (((shared_count - 1) * 0.5) + 1)
        requested_start_day_n_minutes = (
            action_day_index * self.config["minutes_per_day"] + curr_job["requested_start_minutes"]
        )

        scheduled_primary_worker_id = self.workers[action_worker_index].worker_code
        # TODO
        time_period_lists = [
            self.workers[action_worker_index]["working_time_slots"][action_day_index]
        ]

        scheduled_secondary_worker_ids = []
        for shared_worker_seq in range(0, shared_count):
            new_act[max_i] = 0
            max_i = np.argmax(new_act[0: len(self.workers)])
            sec_worker_index = int(max_i / self.config["nbr_of_days_planning_window"])
            time_period_lists.append(
                self.workers[action_worker_index]["working_time_slots"][action_day_index]
            )
            scheduled_secondary_worker_ids.append(self.workers[sec_worker_index].worker_code)

        found_slot = False
        if curr_job.job_schedule_type == JobScheduleType.FIXED_SCHEDULE:
            search_result = self.intersect_geo_time_slots(
                time_period_lists,
                curr_job,
                duration_minutes=scheduled_duration,
                max_number_of_matching=99,
            )
            for tp in search_result:
                if (tp[0] < requested_start_day_n_minutes) & (
                    requested_start_day_n_minutes + scheduled_duration < tp[1]
                ):
                    found_slot = True
                    assigned_start_day_n_minutes = requested_start_day_n_minutes
                    break
        else:
            search_result = self.intersect_geo_time_slots(
                time_period_lists,
                curr_job,
                duration_minutes=scheduled_duration,
                max_number_of_matching=1,
            )
            if len(search_result) > 0:
                found_slot = True
                assigned_start_day_n_minutes = search_result[0][0]  # No travel time?
        if not found_slot:
            raise LookupError(f"Failed to find slot for current current_job_i={self.current_job_i}")

        """ TODO: loop through other combination of secondary
        for i in range(1, shared_count):
            new_act[max_i] = 0
            max_i = np.argmax(new_act[0 : len(self.workers)])
            scheduled_secondary_worker_ids.append(self.workers[max_i].worker_code)
        """

        # temporary blocking duration chagne 2020-09-17 09:37:44
        a_dict = {
            "scheduled_primary_worker_id": scheduled_primary_worker_id,
            "scheduled_secondary_worker_ids": scheduled_secondary_worker_ids,
            "scheduled_start_day": action_day_index,
            "scheduled_start_minutes": int(assigned_start_day_n_minutes)
            % self.config["minutes_per_day"],
            "assigned_start_day_n_minutes": int(assigned_start_day_n_minutes),
            "scheduled_duration_minutes": scheduled_duration,
        }

        return a_dict


class KPlannerJob2SlotEnvProxy(KandboxEnvProxyPlugin):

    title = "Kandbox Plugin - Environment Proxy"
    slug = "kprl_env_job2slot_proxy"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "Env Proxy for GYM for RL."
    version = "0.1.0"

    env_class = KPlannerJob2SlotEnv
    default_config = {
        # 'replay' for replay Planned jobs, where allows conflicts. EnvRunModeType.PREDICT for training new jobs and predict.
        "run_mode": EnvRunModeType.PREDICT,
        "env_code": "rl_hist_affinity_env_proxy",
        "allow_overtime": False,
        #
        "nbr_of_observed_workers": NBR_OF_OBSERVED_WORKERS,
        "nbr_of_days_planning_window": 2,
        "data_start_day": DATA_START_DAY,
        #
        "minutes_per_day": MINUTES_PER_DAY,
        # 'reversible' : True, # if yes, I can revert one step back.
        "max_nbr_of_jobs_per_day_worker": MAX_NBR_OF_JOBS_PER_DAY_WORKER,
        # 'rule_set':kprl_rule_set,
        "org_code": None,
        "team_id": None,
        "geo_longitude_max": 119,
        "geo_longitude_min": 113,
        "geo_latitude_max": 41,
        "geo_latitude_min": 37,
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "run_mode": {
                "type": "string",
                "code": "Job Type",
                "description": "This affects timing, N=Normal, FS=Fixed Schedule.",
                "enum": ["N", "FS"],
            },
            "nbr_of_observed_workers": {"type": "number", "code": "Number of observed_workers"},
            "nbr_of_days_planning_window": {
                "type": "number",
                "code": "Number of days_planning_window",
            },
            "minutes_per_day": {"type": "number", "code": "minutes_per_day"},
            "max_nbr_of_jobs_per_day_worker": {
                "type": "number",
                "code": "max_nbr_of_jobs_per_day_worker",
            },
        },
    }
