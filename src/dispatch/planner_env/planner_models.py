from datetime import datetime
from typing import List, Optional, Any, Dict
import pydantic
from sqlalchemy.ext.hybrid import hybrid_property

from sqlalchemy import Boolean, Column, ForeignKey, Integer, PrimaryKeyConstraint, String, Table
from sqlalchemy.orm import backref, relationship
from sqlalchemy_utils import TSVectorType

from dispatch.database import Base

from dispatch.models import DispatchBase, TermReadNested, TimeStampMixin


# from dispatch.service_plugin.models import ServicePlugin, KandboxPlannerPluginType


from dispatch.plugins.kandbox_planner.env.env_models import (
    JobType, ActionEvaluationScore, SingleEnvStepResult, JobInSlotResult)
from dispatch.plugins.kandbox_planner.env.env_enums import (
    ActionScoringResultType,
    JobPlanningStatus,
)



class RunBatchInput(DispatchBase):
    team_code: str
    area_codes: str = ""
    horizon_start_datetime: str = None
    batch_end_datetime: str = None # This is the cut off datetime for the next batch

class ResetPlanningWindowInput(DispatchBase):
    team_code: str

class TeamEnvInput(DispatchBase):
    team_id: int
    start_datetime: Optional[datetime]

class WorkerStatusUpdateInput(DispatchBase):
    """Action_type is begin_shift, end_shift, update_location, accum_items
    """
    worker_code: str
    action_type: str
    shift_start_datetime: datetime = None
    shift_duration_minutes: int = 480
    start_longitude: float = None
    start_latitude: float = None
    end_longitude: float = None
    end_latitude: float = None
    accum_items: Dict = {}

class GenericRequestResult(DispatchBase):
    errorNumber: int
    errorDescription: Optional[str]
    data: Dict = {}

class RunOptimizerOverUnplannedInput(DispatchBase):
    team_code: str
    target_job_list: List[str]


class GenericJobPredictActionInput(DispatchBase):
    team_id: Optional[int]
    team_code: Optional[str]
    job_code: str


class GenericJobAction(DispatchBase):
    order_code: str = None
    job_code: str
    scheduled_worker_codes: List[str]
    scheduled_start_datetime: datetime
    scheduled_duration_minutes: int
    planning_status: str = "I"
    score: float
    score_detail: Dict
    cost: float = 0
    scheduled_slots: List[List[JobInSlotResult]]


class GenericJobCommitActionInput(DispatchBase):
    scheduled_worker_codes: List[str]
    scheduled_start_datetime: Optional[datetime]
    scheduled_duration_minutes: int
    planning_status: str = "I"
    job_code: str
    team_id: str
    fixed_flag: bool = False


class GenericJobCommitOutput(DispatchBase):
    errorNumber: int
    errorDescription: Optional[str]



class GenericJobPredictActionOutput(DispatchBase):
    errorNumber: int
    recommendations: List[GenericJobAction]
    errorDescription: Optional[str]
    errorDetails: Optional[Dict]


class LockedSlot(DispatchBase):
    worker_code: str
    start_datetime: datetime
    end_datetime: datetime
    appt_code: str


class LockedSlotOutput(DispatchBase):
    errorNumber: int
    errorDescription: Optional[str]
    lockedSlots: List[LockedSlot]


class SingleJobDropCheckInput(DispatchBase):
    team_id: int
    job_code: str
    scheduled_duration_minutes: int
    scheduled_start_datetime: datetime
    scheduled_primary_worker_code: str
    start_day: str
    end_day: str
    planning_status: Optional[str] = JobPlanningStatus.IN_PLANNING
    # timeArrival: float  # in javascript timestamp
    scheduled_secondary_worker_codes: Optional[list] = []

    #  start_day: Optional[str] = None, now included in timeArrival
 

class SingleJobDropCheckInputNew(DispatchBase):
    job_code: str
    scheduled_start_datetime: datetime
    planning_status: Optional[str] = JobPlanningStatus.IN_PLANNING
    start_day: str
    end_day: str


class SingleJobDropCheckOutput(DispatchBase):
    status_code: ActionScoringResultType
    score: float
    travel_time: float
    messages: List[Any]  # Here Any is ActionEvaluationScore, but avoiding validation error


PLANNER_ERROR_MESSAGES = {
    "SUCCESS": (0, "Success"),
    "INTERNAL_ERROR": (501, "Internal System Error"),
    "JOB_NOT_EXIST": (40008, "The job id ({}) does not exist."),
    "JOB_NOT_EXIST_IN_ENV": (40002, "The job id ({}) does not exist in planner env."),
    "WRONG_DATE_INPUT": (40003, "The selected date  is out of planning window, or in bad format.",),
    "NO_SLOT": (40004, "No slot found"),
}


class JobTravelMinutes(DispatchBase):
    job_code: str
    team_id: int
    scheduled_start_datetime: str
    scheduled_primary_worker_code: str


class JobTravelMinutesOutput(DispatchBase):
    travel: float




class ResetPlanningWindowResult(pydantic.BaseModel):
    status: str
    config: Optional[Any]
    # {"status": "OK", "config": planner.config}
    env_step_result: Optional[SingleEnvStepResult]


class DevEnvKeyRequest(DispatchBase):
    env_key: str  