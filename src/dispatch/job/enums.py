from enum import Enum


class JobPlanningStatus(str, Enum):
    IN_PLANNING = "I"
    UNPLANNED = "U"
    PLANNED = "P"
    COMPLETED = "C"  # maps to visited=V


class JobType(str, Enum):
    job = "job"
    absence_event = "absence_event"
    composite_job = "composite_job"
