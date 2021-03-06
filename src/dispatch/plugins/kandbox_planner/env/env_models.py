# from dataclasses import dataclass
# import dataclasses
from enum import Enum

from pydantic.dataclasses import dataclass
from pydantic import Field
import pydantic.dataclasses as dataclasses
from dataclasses import InitVar
from dataclasses import astuple as python_dataclasses_astuple

import json
from datetime import date, datetime


from typing import Optional, Any

# Among Object, dataclass, namedtuple. I finally decided to use dataclass to represent most of data structures in Env
#
from datetime import datetime

from collections import namedtuple

from dispatch.plugins.kandbox_planner.env.env_enums import (
    TimeSlotType,
    JobType,
    LocationType,
    JobPlanningStatus,
    JobScheduleType,
    ActionType,
    KafkaMessageType,
    KandboxMessageSourceType,
    AppointmentStatus,
    ActionScoringResultType,
    OptimizerSolutionStatus
)

import typing
from typing import List, Dict, Any
import logging
log = logging.getLogger("rllib_env_job2slot")

# @dataclass # 2020-10-26 04:33:38 Leave as named tuple object
# class LocationTuple (NamedTuple):   # typing.NamedTuple

LocationTuple = namedtuple(
    "LocationTuple",
    ["geo_longitude", "geo_latitude", "location_type", "location_code"],  # H="Home", J=Job, E=Event
    defaults=(
        0,
        0,
        LocationType.JOB,
        None,
    ),
)
# https://stackoverflow.com/questions/52298118/fastest-way-to-keep-data-in-memory-with-redis-in-python


class JobLocationBase(typing.NamedTuple):
    """The Locaiton is implemented as namedtuple for compatibility.
    Consider making it as dataclass in future.

    """

    geo_longitude: float
    geo_latitude: float
    # H="Home", J=Job, E=Event, in future, it could be high building, internal room, etc.
    location_type: LocationType
    location_code: str


class JobLocation(typing.NamedTuple):
    """The Locaiton is implemented as namedtuple for compatibility.
    Consider making it as dataclass in future.

    """

    geo_longitude: float
    geo_latitude: float
    location_type: LocationType  # H="Home", J=Job, E=Event
    location_code: str
    # location_info: LocationTuple  # maintain the position in env.workers. For compatibility, and also in action, it is based on worker's sequence.
    # Key is  tuple (primary, secondary_1, secondary_2))  Caution: all service area code must be alphabetically sorted for secondary!.
    historical_serving_worker_distribution: dict = None

    avg_actual_start_minutes: float = 0
    avg_days_delay: float = 0
    stddev_days_delay: float = 0
    # available_slots: List  # list of [start,end] in linear scale
    # rejected_slots: List

    # requested_worker_served_count: to calcualte default ratio. OR can be calculated out of historical_serving_worker_distribution


@dataclass
class WorkingTimeSlot:
    start_minutes: int
    end_minutes: int
    prev_slot_code: Optional[str]
    next_slot_code: Optional[str]

    slot_type: TimeSlotType
    start_location: LocationTuple
    end_location: LocationTuple

    assigned_job_codes: List[str]
    worker_id: str

    referred_object_code: str = None  # 9
    # This is a positive number and should be used like start_time - start_overtime_minutes
    start_overtime_minutes: int = 0
    # This is a positive number and should be used like end_time + end_overtime_minutes
    end_overtime_minutes: int = 0
    available_free_minutes: int = 0
    total_job_minutes: int = 0
    # If False, this work is over time and when released, it does not recover working slot.
    is_in_working_hour: bool = True
    # The last time when this worker receives on commend, including moving on map, receive new order, etc.
    last_command_tick: int = 0
    # (longigude_index, latitude_index, minute_1, minute_2, minute_3), here minute is absolution minute since data_start_day. Observation is responsible
    # workermap_grid_index: List[float] = None

    # as demo first, to support item stock based dispatching
    # in meter cubic. M^3
    vehicle_type: str = "van"
    max_volume: float = 0.2
    # in kilogram. kg
    max_weight: float = 50
    loaded_items: Dict = Field(default_factory=dict)

    env: InitVar[any] = None

    def __post_init__(self, env):
        if env is not None:
            self.calc_free_time(env)
        else:
            self.total_job_minutes = -1
            self.available_free_minutes = -1

    def calc_free_time(self, env):
        (
            prev_travel_minutes,
            next_travel_minutes,
            inside_travel_minutes,
        ) = env.get_travel_time_jobs_in_slot(self, self.assigned_job_codes)
        self.available_free_minutes = (
            self.end_minutes
            - self.start_minutes
            - prev_travel_minutes
            - next_travel_minutes
            - sum(inside_travel_minutes)
        )

        self.total_job_minutes = sum(
            [env.jobs_dict[j].scheduled_duration_minutes for j in self.assigned_job_codes]
        )


class TimeSlotJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if type(o) in (str, int, float, bool, bytes):
            return super().default(o)
        elif type(o) == WorkingTimeSlot:
            return python_dataclasses_astuple(o)
        else:
            return str(o)


@dataclass
class BaseJob:
    """A class for holding Job Information in the RL environment, not in the database"""
    job_id: int  # id is same as the pk in database.
    job_code: str  # Unique Key in Env.
    job_index: int  # maintain the position in env.jobs. For compatibility only. DO NOT USE IT.
    job_type: JobType
    job_schedule_type: JobScheduleType  # attribute-1.
    location: JobLocation

    planning_status: JobPlanningStatus

    # I really want to chagne it back to CODE. 2020-10-25 06:45:09
    # scheduled_primary_worker_id: int
    # scheduled_secondary_worker_ids: List[int]
    # Done, to code, 2020-10-28 17:32:43

    # historical_primary_worker_count: dict
    # historical_secondary_worker_count: dict
    # historical_serving_worker_distribution: dict
    # 
    requested_skills: dict  
    requested_start_min_minutes: int
    requested_start_max_minutes: int
    # The preferred time might nobe be avg(min,max). Min max are used to calculate the tolerance only. But the preferred time might be anywhre.
    requested_start_minutes: int  # In case of FT, this determines start hour only
    requested_time_slots: List[tuple]
    requested_primary_worker_code: str
    requested_duration_minutes: int
    # it is covered by requested_start_min_minutes & max. removed 2020-11-01 10:43:41. duan.
    # Default to requested_start_min_minutes
    # requested_start_datetime: datetime  # No day, no minutes
    flex_form_data: dict
    # The search candidate list for recommendations. Each element is a tuple [("CT12", "CT24")]
    searching_worker_candidates: List
    # list of [start,end] in linear scale 2021-02-20 10:19:25 . This is to replace location.available_slots
    available_slots: List
    appointment_status: AppointmentStatus  # = AppointmentStatus.UNKNOWN
    #
    included_job_codes: List[str]
    new_job_codes: List[str]  # all alternative job_code to identify same job.
    #
    # First one is primary, and the rest are secondary, All secondary must be sorted.
    scheduled_worker_codes: Optional[List[str]] = None
    # including day information. day*1440 + minutesa_in_day
    scheduled_start_minutes: Optional[int] = 0
    scheduled_duration_minutes: Optional[int] = 0
    #
    requested_items: Dict = Field(default_factory=dict)
    #
    is_changed: bool = False
    is_active: bool = True
    is_replayed: bool = False
    is_appointment_confirmed: bool = True
    is_auto_planning: bool = False
    #
    retry_minutes: int = -2
    priority: int = 1  # attribute-2.


class Job(BaseJob):
    pass


class Appointment(BaseJob):
    pass


@dataclass
class Absence(BaseJob):
    pass


@dataclass
class Worker:
    """The data class for holding worker information in the environment, not in the database"""

    # maintain the position in env.workers. For compatibility, and also in action, it is based on worker's sequence.
    worker_index: int
    worker_id: int  # For now worker_id is the ID in database table.
    worker_code: str  # This is the main primary key in ENV.
    flex_form_data: dict

    # working minutes, starting at 0 everyday, 1 entry per day , index starts from Sunday as 0.
    weekly_working_slots: List[tuple]
    weekly_start_gps: List[LocationTuple]
    weekly_end_gps: List[LocationTuple]
    # working minutes as continuous value. It is possible to have multiple working slot in one day.
    # TODO, this should not belong to a worker. This should be made as an ENV Variable. For now, do not USE IT.
    # It is replaced by slots on redis.
    linear_working_slots: List[tuple]

    # Every day linear_daily_start_gps has one entry
    # 2020-11-03 08:40:43 Converted to functions based on weekly_start_gps -->  env.get_start_gps_for_worker_day
    # linear_daily_start_gps: List[LocationTuple]
    # linear_daily_end_gps: List[LocationTuple]

    # If there are multiple skills, each one should be a key:[list], for example:
    # { "product_code": ["prod_1", "Prod_2"],
    #   "level": ["senior", "junior"],
    # }
    skills: dict
    is_active: bool

    overtime_limits: dict  # key is (day_seq,)
    used_overtime_minutes: dict  # key is day_seq

    historical_job_location_distribution: Any = None
    # The total used and limit of overtime minutes are controlled by
    daily_max_overtime_minutes: int = 0
    weekly_max_overtime_minutes: int = 0

    belongs_to_pair: tuple = None
    curr_slot: WorkingTimeSlot = None


# @dataclass
# class Material:
#     """The material
#     """

#     weight: float
#     volume: float
#     code: str = "Faked"


@dataclass
class ActionDict:
    """The action in dict, instead of pure numerical value as demanded by GYM environement.

    Can be converted to action as numpy array.
    """

    job_code: str
    is_forced_action: bool
    #  JobType.FLOATING, ActionType.JOB_FIXED, or UNPLAN. JOB Type will be from job. Now seperated.
    action_type: ActionType
    scheduled_start_minutes: int  # This is the elapsed minutes since data_start_day
    scheduled_duration_minutes: int
    # scheduled_primary_worker_id: int
    # scheduled_secondary_worker_ids: List[int]

    # First one is primary, and the rest are secondary, All secondary must be sorted.
    scheduled_worker_codes: List[str]


@dataclass
class ActionEvaluationScore:
    score: float
    score_type: str
    message: str
    metrics_detail: dict


@dataclass
class JobsInSlotsDispatchResult:
    status: OptimizerSolutionStatus
    changed_action_dict_by_job_code: dict
    all_assigned_job_codes: list
    # list of list, each internal list is [start mintues, jobcode, sequence/shift,changed_flag]
    planned_job_sequence: list
    result_info: Dict = Field(default_factory=dict)


@dataclass
class RecommendedAction:
    """A class for holding one recommendaton package regarding an appointment"""

    job_code: str
    #
    scoped_slot_code_list: List[str]

    scheduled_start_minutes: int
    scheduled_duration_minutes: int
    # sequence follows  scheduled_primary_worker_id + scheduled_secondary_worker_ids
    # # First one must be primary, and the rest are secondary, All secondary must be sorted.
    scheduled_worker_codes: List[str]
    score: float
    score_detail: List[ActionEvaluationScore]
    # job_plan_in_scoped_slots is list of slots.
    # Inside each slot, One job is tracked as [525, 'MY|D|89173841|1|PESTS|1|17', 0, True]
    job_plan_in_scoped_slots: List  # tuple[int, str, int, bool]
    unplanned_job_codes: List

    def get_action_day(self, env) -> int:
        return int(self.scheduled_start_minutes / env.config["minutes_per_day"])

    def to_recommandation_string(self) -> str:
        rec_tuple = (
            self.scoped_slot_code_list,
            self.scheduled_start_minutes,
            self.scheduled_duration_minutes,
            self.scheduled_worker_codes,
            self.score_detail,
            self.score,
        )
        return json.dumps(rec_tuple)

    def from_recommandation_string(self, rec_string: str, job_code: str):
        raise NotImplemented("ERROR")
        rec_tuple = json.loads(rec_string)
        return RecommendedAction(
            job_code=job_code,
            scoped_slot_code_list=rec_tuple[0],
            scheduled_start_minutes=rec_tuple[1],
            scheduled_duration_minutes=rec_tuple[2],
            # First one is primary, and the rest are secondary, All secondary must be sorted.
            scheduled_worker_codes=[],
            score=0,
            score_detail=[],
        )
        return json.dumps(rec_tuple)

    def to_action_dict(self, env):
        a_dict = ActionDict(
            is_forced_action=False,
            job_code=self.job_code,
            action_type=ActionType.FLOATING,
            scheduled_worker_codes=self.scheduled_worker_codes,
            scheduled_start_minutes=self.scheduled_start_minutes,
            scheduled_duration_minutes=self.scheduled_duration_minutes,
        )
        return a_dict

    def from_action_dict(self, env, a_dict):
        a_rec = RecommendedAction(
            job_code=a_dict.job_code,
            # action_type=ActionType.JOB_FIXED,
            # JobType = JOB, which can be acquired from self.jobs_dict[job_code]
            scheduled_worker_codes=a_dict.scheduled_worker_codes,
            scheduled_start_minutes=a_dict.scheduled_start_minutes,
            scheduled_duration_minutes=a_dict.scheduled_duration_minutes,
            scoped_slot_code_list=None,
            score=-1,
            score_detail=None,
        )
        return a_rec


@dataclass
class SingleJobCommitInternalOutput:
    status_code: ActionScoringResultType
    # score: float, only in scoring
    messages: List[Any]
    # done: bool , # Leave this info to step()

    # detail: str
    nbr_changed_jobs: int
    new_job_code: Optional[str]


@dataclass
class RecommendationCommitInternalOutput:
    status_code: ActionScoringResultType
    jobs_output_list: List[SingleJobCommitInternalOutput]
    new_job_code: Optional[str]


# permenant pair.


###########################################################################
##   Kafka   ###
###########################################################################


@dataclass
class KafkaEnvMessage:
    message_type: KafkaMessageType
    message_source_type: KandboxMessageSourceType
    message_source_code: str

    payload: List[Any]


class KPIStat:
    """ 
    """

    def __init__(self):
        self.cancel_count = 0
        self.pick_overdue_count = 0
        self.drop_overdue_count = 0
        self.instant_reward = 0
        self.low_instant_reward = 0

    def push_instant_reward(self, r):
        self.instant_reward += r
        if self.instant_reward < -10:
            log.debug(f"Warning, self.instant_reward {self.instant_reward} < -5 ...")

    def pop_instant_reward(self):
        temp_r = self.instant_reward
        if self.instant_reward < -10:
            self.low_instant_reward += 1
        self.instant_reward = 0
        return temp_r

    def reset(self):
        self.cancel_count = 0
        self.pick_overdue_count = 0
        self.drop_overdue_count = 0
        self.instant_reward = 0
        self.low_instant_reward = 0


if __name__ == "__main__":

    lc = LocationTuple(1.2, 3, "H")

    a_slot = WorkingTimeSlot(
        slot_type=TimeSlotType.FLOATING,
        start_minutes=1,
        end_minutes=100,
        prev_slot_code=None,
        next_slot_code=None,
        start_location=lc,
        end_location=LocationTuple(1.2, 4, "J"),
        worker_id="duan",
        available_free_minutes=-1,
        assigned_job_codes=[],
    )
    print(a_slot)
    j_slot = json.dumps(a_slot, cls=TimeSlotJSONEncoder)
    print("Dumped:", j_slot)
    j_t = json.loads(j_slot)
    abc = WorkingTimeSlot(*j_t)

    print("abc=", abc)

    rec_a = RecommendedAction(
        job_code="job_1",
        scoped_slot_code_list=["slot-1", "slot-2"],
        scheduled_start_minutes=12,
        scheduled_duration_minutes=22,
        # First one is primary, and the rest are secondary, All secondary must be sorted.
        scheduled_worker_codes=[],
        score=0,
        score_detail=[],
        job_plan_in_scoped_slots=[],
    )
    rec_s = rec_a.to_recommandation_string()
    print(rec_s)
    import dataclasses as dataclasses

    rec_record = dataclasses.astuple(rec_a)

    print("dataclasses.astuple:", rec_record)

    print(json.dumps(rec_record))
    abc = json.dumps(rec_record)
    print("recovered", json.loads(abc))

    print("recovered action", RecommendedAction(*json.loads(abc)))

    loc = JobLocation(
        geo_longitude=lc[0],
        geo_latitude=lc[1],
        location_type=lc[2],
        location_code=lc[3],
        historical_serving_worker_distribution={"duan": 1},
        avg_actual_start_minutes=0,
        avg_days_delay=0,
        stddev_days_delay=0,
        # rejected_slots=[],
    )

    loc_base = JobLocationBase(*loc[0:4])
    print(loc_base)

    a_job = Job(
        job_id=1,
        job_code="job 1",
        job_index=0,
        job_type=JobType.JOB,
        job_schedule_type=JobScheduleType.NORMAL,  # job_seq: 89, job['job_code']
        planning_status=JobPlanningStatus.UNPLANNED,
        scheduled_worker_codes=["duan"],
        scheduled_start_minutes=0,
        scheduled_duration_minutes=0,
        location=loc,
        requested_skills={},
        #
        requested_start_min_minutes=0,
        requested_start_max_minutes=1440 * 3650,
        requested_time_slots=[],
        requested_primary_worker_code="0",
        # requested_start_datetime=datetime.now(),  # No day, no minutes
        requested_duration_minutes=0,
        flex_form_data={},
        available_slots=[],  # list of [start,end] in linear scale
        is_active=True,
        searching_worker_candidates=[""],
        appointment_status=AppointmentStatus.PENDING,
    )
    print(a_job)
    print("--------")

    print(dataclasses.astuple(a_job))

    a_t = dataclasses.astuple(a_job)
    # print(json.dumps(a_t, cls=ComplexDatetimeEncoder))
    print(json.dumps(a_t))

    print(a_t[1] == JobPlanningStatus.UNPLANNED)
    print("U" == JobPlanningStatus.UNPLANNED)
    print("U" == a_t[1])

    recovered_job = json.loads(json.dumps(a_t))  # , cls=ComplexDatetimeEncoder
    print(recovered_job)

    m = KafkaEnvMessage(
        message_type=KafkaMessageType.UPDATE_JOB,
        message_source_type=KandboxMessageSourceType.ENV,
        message_source_code="mac1",
        payload=[{"test": "duan"}],
    )
    print(m)
