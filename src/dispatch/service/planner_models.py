from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import Field
from sqlalchemy.ext.hybrid import hybrid_property

from sqlalchemy import Boolean, Column, ForeignKey, Integer, PrimaryKeyConstraint, String, Table
from sqlalchemy.orm import backref, relationship
from sqlalchemy_utils import TSVectorType

from dispatch.database import Base

from dispatch.models import DispatchBase, TermReadNested, TimeStampMixin


# from dispatch.service_plugin.models import ServicePlugin, KandboxPlannerPluginType


from dispatch.plugins.kandbox_planner.env.env_models import JobType, ActionEvaluationScore
from dispatch.plugins.kandbox_planner.env.env_enums import (
    ActionScoringResultType,
    JobPlanningStatus,
)


class GenericJobPredictActionInput(DispatchBase):
    team_id: int
    job_code: str


class GenericJobAction(DispatchBase):
    scheduled_worker_codes: List[str]
    scheduled_start_datetime: datetime
    scheduled_duration_minutes: int
    planning_status: str = "I"
    score: float
    score_detail: List[Any]


class GenericJobCommitActionInput(DispatchBase):
    scheduled_worker_codes: List[str]
    scheduled_start_datetime: datetime
    scheduled_duration_minutes: int
    planning_status: str = "I"
    job_code: str
    team_id: str


class GenericJobCommitOutput(DispatchBase):
    errorNumber: int
    errorDescription: Optional[str]


class GenericJobPredictActionOutput(DispatchBase):
    errorNumber: int
    errorDescription: Optional[str]
    recommendations: List[GenericJobAction]


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
    scheduled_primary_worker_id: str
    scheduled_secondary_worker_ids: list
    planning_status: Optional[str] = JobPlanningStatus.IN_PLANNING
    # timeArrival: float  # in javascript timestamp
    start_day: str
    end_day: str

    #  start_day: Optional[str] = None, now included in timeArrival


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
    "WRONG_DATE_INPUT": (
        40003,
        "The selected date  is out of planning window, or in bad format.",
    ),
    "NO_SLOT": (40004, "No slot found"),
}