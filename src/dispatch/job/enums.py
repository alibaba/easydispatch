from enum import Enum


class JobPlanningStatus(str, Enum):
    """Planning Status for JOB. 
    \n U == Un-planned. When is Job is U status, the scheduled information (scheduled_start/duration/workers) is ignored. 
    \n I == In-planning. When is Job is I status, the scheduled attributes must have valid values. 
    \n P == Planned. When is Job is P status, it is treated as fixed agreement for both worker assignment and datetime. The easydispatch engine will not modify its scheduling information.  
    \n C == Completed. When is Job is C status, it will be removed. In future, it will be moved to historical storage. DO NOT USE THIS STATUS. 
    """
    IN_PLANNING = "I"
    UNPLANNED = "U"
    PLANNED = "P"
    COMPLETED = "C"  # maps to visited=V


class JobType(str, Enum):
    job = "job"
    absence_event = "absence_event"
    composite_job = "composite_job"
