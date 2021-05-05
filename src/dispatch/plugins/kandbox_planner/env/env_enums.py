from enum import Enum


# F=Floating (which is free/movable, with in-planning job_ids), ABS = absence shared visits is here
# J=job (Planned), and J includes A=appointment (Fixed Job) , EX=Exception (conflicted jobs?),  ?
# Maybe in future track "Vacuum Space" to schedule non-working hour jobs? as long as they are not conflicting with other assigned jobs.
class TimeSlotType(str, Enum):
    FLOATING = "F"
    JOB_FIXED = "J"
    ABSENCE = "E"


class TimeSlotOperationType(str, Enum):
    UPDATE = "U"
    DELETE = "D"


class ActionType(str, Enum):
    # F=Floating (which is free/movable, with in-planning job_ids),
    # J=job (Planned), EX=Exception (conflicted jobs?),
    # A=appointment (Fixed Job) ,
    # ABS = absence shared visits is here? Maybe in future track "Vacuum Space" to schedule non-working hour jobs? as long as they are not conflicting with other assigned jobs.
    FLOATING = "F"
    JOB_FIXED = "J"
    UNPLAN = "U"  #


class JobType(str, Enum):
    # INCIDENT = "incident"
    APPOINTMENT = "appt"
    JOB = "visit"
    ABSENCE = "event"


# 'replay' for replay Planned jobs, where allows conflicts. "predict" for training new jobs and predict.
class EnvRunModeType(str, Enum):
    PREDICT = "predict"
    REPLAY = "replay"


class OptimizerSolutionStatus(Enum):
    INFEASIBLE = 1
    SUCCESS = 0
    INPUT_VALIDATION_ERROR = 2


class JobScheduleType(str, Enum):
    FIXED_SCHEDULE = "FS"
    NORMAL = "N"
    FIXED_DATE = "FD"
    FIXED_TIME = "FT"
    NEED_APPOINTMENT = "NA"
    # NIGHT_SCHEDULE = "NN"


class LocationType(str, Enum):
    """ H="Home", J=Job,  """

    HOME = "H"
    JOB = "J"
    ABSENCE = "ABS"


from dispatch.job.enums import JobPlanningStatus

# class JobPlanningStatus(str, Enum):
#     IN_PLANNING = "I"
#     UNPLANNED = "U"
#     PLANNED = "P"
#     COMPLETED = "C"  # maps to visited=V


class AppointmentStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"
    NOT_APPOINTMENT = "NOT_APPOINTMENT"


AppointmentStatus_SEQUENCE = {
    AppointmentStatus.PENDING: 0,
    AppointmentStatus.READY: 3,
    AppointmentStatus.CANCELLED: 3,
    AppointmentStatus.ERROR: 3,
    AppointmentStatus.EXPIRED: 3,
    AppointmentStatus.UNKNOWN: 100,
}


class ActionScoringResultType(str, Enum):
    OK = "OK"
    WARNING = "Warning"
    ERROR = "Error"
    RECOMMENDED_SLOT_DAMAGED = "RECOMMENDED_SLOT_DAMAGED"  # "CODE_40014"


class ActionScoringMetricsCode(str, Enum):
    COMPOSITION_SHARED_JOBS = "composition_shared_jobs"
    WORKING_HOUR = "Within Working Hour"
    ENOUGH_TRAVEL = "Enough Travel"
    LUNCH_BREAK = "Lunch Break"
    REQUESTED_SKILLS = "Requested Skills"


###########################################################################
##   Kafka   ###
###########################################################################


class KafkaRoleType(str, Enum):
    FAKE = "FAKE"  # It does nothing
    PRODUCER_ONLY = "PRODUCER_ONLY"  # Can produce messages, but not consume
    ENV_ADAPTER = "ENV_ADAPTER"
    RECOMMENDER = "RECOMMENDER"  # with all


class KafkaMessageType(str, Enum):
    CREATE_WORKER = "Create_Worker"
    CREATE_JOB = "Create_Job"  #    from GTS loading
    CREATE_APPOINTMENT = "Create_Appointment"
    CREATE_ABSENCE = "Create_Absence"

    UPDATE_WORKER = "Update_Worker"
    UPDATE_WORKER_ATTRIBUTES = "Update_Worker_Attributes"  # REFRESH_WORKER = "Refresh_Worker"  #
    # UPDATE_JOB will update only the attribute and will NOT re-schedule the job.
    UPDATE_JOB = "Update_Job"  # from
    # When planning info is changed, do not use UPDATE_JOB, use RESCHEDULE_JOB.
    RESCHEDULE_JOB = "Reschedule_Job"
    # REFRESH_JOB will be used once the job is applied to timeslot server. Other env instances shall use this message to refresh its local cache.
    REFRESH_JOB = "Refresh_Job"
    UPDATE_APPOINTMENT = "Update_Appointment"
    UPDATE_ABSENCE = "Update_Absence"

    DELETE_WORKER = "Delete_Worker"
    DELETE_JOB = "Delete_Job"  # from GTS loading
    DELETE_APPOINTMENT = "Delete_Appointment"
    DELETE_ABSENCE = "Delete_Absence"

    UPDATE_PLANNING_WINDOW = "Update_Planning_Window"
    REFRESH_PLANNING_WINDOW = "Refresh_Planning_Window"
    REFRESH_RECOMMENDATION = "Refresh_Recommendation"
    REFRESH_RECOMMENDATION_SINGLE_APPOINTMENT = "Refresh_Recommendation_Single_Appointment"

    DELETE_WORKING_TIME_SLOTS = "Delete_Slots"  # Includes deleted and inserted.
    UPDATE_WORKING_TIME_SLOTS = "Update_Slots"  # Includes deleted and inserted.
    POST_CHANGED_JOBS = "Post_Changed_Jobs"  # Includes deleted and inserted.


class KandboxMessageTopicType(str, Enum):
    ENV_WINDOW = "input"
    ENV_WINDOW_OUTPUT = "output"


class KandboxMessageSourceType(str, Enum):
    ENV = "ENV"
    PLANNER_UI = "Planner_UI"
    BATCH_INPUT = "Batch_Input"
    REST_API = "Rest_API"
