# from dataclasses import dataclass
# import dataclasses
from enum import Enum
import pydantic
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

from dispatch.config import DEFAULT_AREA_CODE
from dispatch.plugins.kandbox_planner.env.env_enums import (
    OrderCreateResultStatusType,
    PlannerType,
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
    ["geo_longitude", "geo_latitude", "location_type", "code"],  # H="Home", J=Job, E=Event
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
    code: str


class JobLocation(typing.NamedTuple):
    """The Locaiton is implemented as namedtuple for compatibility.
    Consider making it as dataclass in future.

    """

    geo_longitude: float
    geo_latitude: float
    location_type: LocationType  # H="Home", J=Job, E=Event
    code: str
    # location_info: LocationTuple  # maintain the position in env.workers. For compatibility, and also in action, it is based on worker's sequence.
    # Key is  tuple (primary, secondary_1, secondary_2))  Caution: all service area code must be alphabetically sorted for secondary!.
    historical_serving_worker_distribution: dict = None
    avg_actual_start_minutes: float = 0
    avg_days_delay: float = 0
    stddev_days_delay: float = 0
    # available_slots: List  # list of [start,end] in linear scale
    # rejected_slots: List

    # requested_worker_served_count: to calcualte default ratio. OR can be calculated out of historical_serving_worker_distribution


# @dataclass
# class BaseJob:
#     """A class for holding Job Information in the RL environment, not in the database"""
#     job_code: str  # Unique Key in Env.
#     job_type: JobType
#     job_schedule_type: JobScheduleType  # attribute-1.
#     location: JobLocation

#     planning_status: JobPlanningStatus


#     # historical_primary_worker_count: dict
#     # historical_secondary_worker_count: dict
#     # historical_serving_worker_distribution: dict
#     # 
#     requested_skills: dict  
#     requested_start_min_minutes: int
#     requested_start_max_minutes: int
#     # The preferred time might nobe be avg(min,max). Min max are used to calculate the tolerance only. But the preferred time might be anywhre.
#     requested_start_minutes: int  # In case of FT, this determines start hour only
#     requested_time_slots: List[tuple]
#     requested_primary_worker_code: str
#     requested_duration_minutes: int
#     # it is covered by requested_start_min_minutes & max. removed 2020-11-01 10:43:41. duan.
#     # Default to requested_start_min_minutes
#     # requested_start_datetime: datetime  # No day, no minutes
#     flex_form_data: dict
#     # The search candidate list for recommendations. Each element is a tuple [("CT12", "CT24")]
#     searching_worker_candidates: List
#     # list of [start,end] in linear scale 2021-02-20 10:19:25 . This is to replace location.available_slots
#     available_slots: List
#     appointment_status: AppointmentStatus  # = AppointmentStatus.UNKNOWN
    
#     # When a job is a "composite" or an "appointment", this list contains the sub-jobs (tasks) it contains
#     included_job_codes: List[str]
#     new_job_codes: List[str]  # all alternative job_code to identify same job.
#     #
#     # First one is primary, and the rest are secondary, All secondary must be sorted.
#     scheduled_worker_codes: Optional[List[str]] = None
#     # including day information. day*1440 + minutesa_in_day
#     scheduled_start_minutes: Optional[float] = 0
#     scheduled_duration_minutes: Optional[float] = 0
#     #
#     #
#     actual_worker_codes: Optional[List[str]] = None
#     actual_start_minutes: Optional[float] = 0
#     actual_duration_minutes: Optional[float] = 0
#     #
#     requested_items: Dict = Field(default_factory=dict)
#     #
#     is_changed: bool = False
#     is_active: bool = True
#     is_replayed: bool = False
#     is_appointment_confirmed: bool = True
#     is_auto_planning: bool = False
#     #
#     # 999 will disable retry. -2 can at least retry once
#     retry_minutes: int = 99999999 # -2
#     priority: int = 1  # attribute-2.


# class Job(BaseJob):
#     pass


# class Appointment(BaseJob):
#     pass




# @dataclass
# class Absence(BaseJob):
#     pass

# (j.geo_longitude, j.geo_latitude, j.code, all_job_index, c_weight, c_volume, 1, c_time_window))
class OptiJobLoc(pydantic.BaseModel):
    geo_longitude: float
    geo_latitude: float
    # node_type == slot, job, order, ORDER is not used.
    # if node_type == order, there should be ending long/lat
    node_type: str 
    code: str
    orig_index: int
    c_weight: int
    c_volume: int
    # c_order_count: int
    c_time_window: List 
    fixed_worker_index: Optional[int] = None
    requested_duration_minutes : int = 1
    skills:Optional[list] = None
    # drop_geo_longitude: Optional[float] = None
    # drop_geo_latitude: Optional[float] = None
    flex_form_data: Dict = pydantic.Field(default_factory=dict)

class OptiContext:
    def __init__(self, env=None, db_session=None, 
        depot_at_head=False, 
        depot_longlat = (0,0),
        max_opti_seconds = 30,
        ): # , area_code = None

        self.job_loc_idx = {}
        self.worker_loc_idx = {}
        self.skill_idx = {}
        self.env = env
        self.db_session=db_session
        self.depot_at_head = depot_at_head
        self.depot_longlat = depot_longlat

        self.location_group2worker_index = {}
        self.worker_code2index = {}
        self.lg2worker_code = {}
        self.max_opti_seconds = max_opti_seconds
        # self.area_code = area_code
        
    def convert_skills(self, skill_str_list):
        new_ids = set()
        for s in skill_str_list:
            if s not in self.skill_idx:
                prev_len = len(self.skill_idx)
                self.skill_idx[s] = prev_len + 1
            new_ids.add(self.skill_idx[s])
        return new_ids

class JobInSlotResult(pydantic.BaseModel):
    code: str
    scheduled_start_datetime: str
    prev_travel: float
    scheduled_duration_minutes: float

class JobInSlot(pydantic.BaseModel):
    scheduled_start_minutes: float
    code: str
    geo_longitude: float
    geo_latitude: float
    prev_travel: float
    scheduled_duration_minutes: float
    tolerance_end_minutes: float
    flex_form_data: Dict = Field(default_factory=dict)
    planning_status: str = "I"
    # planning_status: str =""
    def to_result(self, env):
        a_rec = JobInSlotResult(
            code=self.code,
            scheduled_start_datetime=datetime.strftime(
                env.env_decode_from_minutes_to_datetime(self.scheduled_start_minutes),
                "%Y-%m-%dT%H:%M:%S",
                ),
            prev_travel=self.prev_travel,
            scheduled_duration_minutes=self.scheduled_duration_minutes,
        )
        return a_rec

class GetEnvJobsInput(pydantic.BaseModel):
    team_code: str
    area_codes: str = ""
    worker_codes: str = ""
    reset_start_datetime: bool = False
    active_only: bool = True


class ConfirmJobsResult(pydantic.BaseModel):
    env_jobs: Dict[str, List[JobInSlotResult]]
    status: str = "OK"




###########################################################################
##   Slots   ###
###########################################################################


# @dataclass
class WorkingTimeSlot(pydantic.BaseModel):
    slot_code: str
    slot_type: TimeSlotType
    worker_code: str
    start_minutes: int
    end_minutes: int
    # prev_slot_code: Optional[str]
    # next_slot_code: Optional[str] # Deprecated since rust.indexedmap
    
    # In logged env: When there are jobs finished, the start location is the last completed job location.
    # In realtime env: start location should be realtime tracked location of the worker.
    start_longitude: float
    start_latitude: float
    end_longitude: float
    end_latitude: float

    assigned_jobs: List[JobInSlot]

    # is_active, is indicated by available_free_minutes == 0, or > 0
    available_free_minutes: int = 0

    area_code: str =  DEFAULT_AREA_CODE
    # Count of job (location) changes to this slot. This is to trigger free minutes and k-medoid calculation 
    job_change_count: int = 0
    # This is a positive number and should be used like start_time - start_overtime_minutes
    start_overtime_minutes: int = 0
    # This is a positive number and should be used like end_time + end_overtime_minutes
    end_overtime_minutes: int = 0

    total_job_minutes: int = 0
    # If False, this work is over time and when released, it does not recover working slot.
    is_in_working_hour: bool = True
    # The last minute when this worker receives on commend, including moving on map, receive new order, etc.
    last_command_tick: int = 0
    # (longigude_index, latitude_index, minute_1, minute_2, minute_3), here minute is absolution minute since data_start_day. Observation is responsible
    # workermap_grid_index: List[float] = None

    # as demo first, to support item stock based dispatching
    # in meter cubic. M^3
    vehicle_type: str = "van"
    max_nbr_order: int = 999 # in kilogram. kg
    capacity_volume: float = 0 # in kilogram. kg
    capacity_weight: float = 0
    accum_items: Dict = Field(default_factory=dict)
    free_items: Dict = Field(default_factory=dict)
    skills: List = Field(default_factory=list)
    enable_radius: int = 0
    meter_radius: int = 0

    # planning_status: str=""
    # env: InitVar[any] = None

    # def __post_init__(self, env):
    #     if env is not None:
    #         self.calc_free_time(env)
    #     else:
    #         self.total_job_minutes = -1
    #         self.available_free_minutes = -1

    # def calc_free_time(self, env):
    #     (
    #         prev_travel_minutes,
    #         next_travel_minutes,
    #         inside_travel_minutes,
    #     ) = env.get_travel_time_jobs_in_slot(self, self.assigned_job_codes)
    #     self.available_free_minutes = (
    #         self.end_minutes
    #         - self.start_minutes
    #         - prev_travel_minutes
    #         - next_travel_minutes
    #         - sum(inside_travel_minutes)
    #     )

    #     self.total_job_minutes = sum(
    #         [env.jobs_dict[j].scheduled_duration_minutes for j in self.assigned_job_codes]
    #     )


class TimeSlotJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if type(o) in (str, int, float, bool, bytes):
            return super().default(o)
        elif type(o) == WorkingTimeSlot:
            return python_dataclasses_astuple(o)
        else:
            return str(o)

@dataclass
class Worker:
    """The data class for holding worker information in the environment, not in the database"""

    # maintain the position in env.workers. For compatibility, and also in action, it is based on worker's sequence.
    # worker_index: int
    # worker_id: int  # For now worker_code is the ID in database table.
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
# 
# @dataclass 
class EnvAction(pydantic.BaseModel):
    """ 
    """
    #  JobType.FLOATING, ActionType.JOB_FIXED, or UNPLAN. JOB Type will be from job. Now seperated.
    action_type: ActionType
    order: Any # OrderRead
    jobs: List[Any] # 
    worker_blacklist: List[str] = []
    worker_whitelist: List[str] = []
    # area_code: str = "A" # 2023-05-13 09:26:51 why this?
    overwrite_max_orders_limit: bool = False

    # Removed time because first layer of job2slot decision is only on slot, Subsequent TSP decides time.
    # scheduled_start_minutes: float  # This is the elapsed minutes since data_start_day. For multiple jobs, this is the first one.
    # scheduled_duration_minutes: float

    # V1: scheduled_worker_codes: List, First one is primary, and the rest are secondary, All secondary must be sorted.
    # V2: scheduled_worker_codes: List, First one is primary, and all (including primary) are sorted according to jobs sequence.
    # in v2, this should be used for multiple order sequences in same order.
    # scheduled_worker_codes: List[str] = None
    # V3_NNS(2023-05-13 08:49:26): use slots directly. For pickdrop delivery, it is one slot. For share/splitted jobs in single order, there are multiple slots
    scheduled_slots: List[WorkingTimeSlot] = [] # list of slots, containing JobInSlot
    score: str = None 
    # db_exist_flag: bool = True
    # env_exist_flag: bool = False
    is_appointment: bool = False


@dataclass
class ActionDict:
    """The action in dict, This is used for frontend rule checking.
    EnvAction is after optimization and EnvAction is used to commit into env.

    Can be converted to action as numpy array.
    """
    order: Any
    jobs: List[Any]
    is_forced_action: bool
    #  JobType.FLOATING, ActionType.JOB_FIXED, or UNPLAN. JOB Type will be from job. Now seperated.
    action_type: ActionType
    scheduled_start_minutes: float  # This is the elapsed minutes since data_start_day. For multiple jobs, this is the first one.
    scheduled_duration_minutes: float
    # scheduled_primary_worker_code: str
    # scheduled_secondary_worker_codes: List[int]

    # V1: scheduled_worker_codes: List, First one is primary, and the rest are secondary, All secondary must be sorted.
    # V2: scheduled_worker_codes: List, First one is primary, and all (including primary) are sorted according to jobs sequence.
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
    # sequence follows  scheduled_primary_worker_code + scheduled_secondary_worker_codes
    # # First one must be primary, and the rest are secondary, All secondary must be sorted.
    scheduled_worker_codes: List[str]
    score: float
    score_detail: Dict
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
        raise NotImplemented("from_recommandation_string")
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


# @dataclass
class SingleJobCommitInternalOutput(pydantic.BaseModel):
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


class SingleEnvStepResult(pydantic.BaseModel):
    has_unplanned: bool
    current_datetime: datetime
    current_step: int
    action: Optional[EnvAction]
    result: Optional[SingleJobCommitInternalOutput]

class OrderCreationResult(pydantic.BaseModel):
    status: OrderCreateResultStatusType
    order: Any # OrderRead
    jobs: List[Any] = [] # list of slots, containing JobInSlot
    worker_code:Optional[str] = None
    scheduled_slots: List[JobInSlotResult] = None # list of slots, containing JobInSlot
    changed_slots: Dict  = {} 
    reason_info: dict  = {} 

class OrderCreationResultSchedule(pydantic.BaseModel):
    worker_code:Optional[str] = None
    scheduled_slots: List[JobInSlotResult] = None # list of slots, containing JobInSlot

class ConfirmAssignmentInput(pydantic.BaseModel):
    worker_code: str
    set_job_status_p: bool = False
    new_sequence: List[str] = None



class ReplanCommonInput(pydantic.BaseModel):
    planner_type: PlannerType = PlannerType.PICKDROP
    allow_same_worker: bool = False
    target_worker: str = None
    overwrite_max_orders_limit: bool = False
    commit_new_plan: bool = True
    unplan_existing: bool = True


class ReplanOrderInput(ReplanCommonInput):
    order_code: str

class ReplanJobInput(ReplanCommonInput):
    job_code: str

class WorkerCodeSchedle(pydantic.BaseModel):
    worker_code: str = None


###########################################################################
##   Kafka   ###
###########################################################################


@dataclass
class KafkaEnvMessage:
    message_type: KafkaMessageType
    message_source_type: KandboxMessageSourceType
    message_source_code: str

    payload: List[Any]


class KPIStat(pydantic.BaseModel):
    """ 
    """
    cancel_count:int = 0
    finished_count: int = 0
    pick_overdue_count:int  = 0
    drop_overdue_count:int  = 0
    instant_reward:int  = 0
    low_instant_reward:int  = 0
    worker_total_travel:dict = {}
       # worker: (minute, location, prev_job_code ( if running for a job), next_job_code ( if running for a job))
    worker_trajetory:dict = {}

    # def __init__(self, **kwargs):
    #     super().__init__(**kwargs)
    #     self.cancel_count = 0
    #     self.pick_overdue_count = 0
    #     self.drop_overdue_count = 0
    #     self.instant_reward = 0
    #     self.low_instant_reward = 0

    #     self.worker_total_travel = {}
    #     # worker: (minute, location, prev_job_code ( if running for a job), next_job_code ( if running for a job))
    #     self.worker_trajetory = {}

        # job code: (requested, scheduled, actual)
        # self.job_minutes = {} , Moving to jobs_dict itself.

    def push_finished_job_travel(self, 
        worker_code, travel_minutes, curr_minute, job, env
        ):
        requested_start_minutes = env.env_encode_from_datetime_to_minutes(
                job.requested_start_datetime)
        scheduled_start_minutes = env.env_encode_from_datetime_to_minutes(
                job.scheduled_start_datetime)
        if worker_code in self.worker_total_travel.keys():
            self.worker_total_travel[worker_code] += travel_minutes
            self.worker_trajetory[worker_code].append (
                (curr_minute, job.code, scheduled_start_minutes, job)
            )
        else:
            self.worker_total_travel[worker_code] = travel_minutes
            self.worker_trajetory[worker_code] =[ (
                (curr_minute, job.code, scheduled_start_minutes, job)
            )]
        
        self.finished_count += 1
        if  scheduled_start_minutes > requested_start_minutes + job.tolerance_end_minutes:
            log.info(f"job {job.code} is overdue at {scheduled_start_minutes}, requested before {requested_start_minutes + job.tolerance_end_minutes}")
            if job.code[-2:] == '-p':
                self.pick_overdue_count += 1
            else:
                self.drop_overdue_count += 1



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
        self.finished_count = 0
        self.pick_overdue_count = 0
        self.drop_overdue_count = 0
        self.instant_reward = 0
        self.low_instant_reward = 0


class NoAvailableSlots(Exception):
    "Raised when the env failed to get slots for dispatching"
    pass

class SlotModifedException(Exception):
    "Raised when the slot is changed by others, to avoid conflicts"
    pass


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
        worker_code="duan",
        available_free_minutes=-1,
        assigned_job_codes=[],
        env=None,
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
        code=lc[3],
        historical_serving_worker_distribution={"duan": 1},
        avg_actual_start_minutes=0,
        avg_days_delay=0,
        stddev_days_delay=0,
        # rejected_slots=[],
    )

    loc_base = JobLocationBase(*loc[0:4])
    print(loc_base)
