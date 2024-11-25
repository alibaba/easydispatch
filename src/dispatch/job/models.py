from collections import Counter
from datetime import datetime
from typing import Any, List, Optional,Dict

from fastapi_permissions import Allow
from pydantic import BaseModel, Field

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Table, 
    Boolean,
    BigInteger,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from sqlalchemy.sql.schema import UniqueConstraint
from sqlalchemy.sql.sqltypes import ARRAY
from sqlalchemy_utils import TSVectorType

# from dispatch.auth.models import UserRoles
from dispatch.database import Base, SessionLocal
from dispatch.event.models import EventRead
from dispatch.worker.models import WorkerCreate, WorkerRead
from dispatch.location.models import LocationCreate, LocationRead
from dispatch.models import DispatchBase, WorkerReadNested, TimeStampMixin
from dispatch.team.models import Team, TeamCreate, TeamRead

# from .enums import JobPlanningStatus, JobType


from dispatch.plugins.kandbox_planner.env.env_enums import JobLifeCycleStatus, JobScheduleType, JobType, JobPlanningStatus


class Job(Base, TimeStampMixin):
    code = Column(String, primary_key=True)  # code
    job_type = Column(String, nullable=False, default=JobType.JOB)  # JobType
    name = Column(String)
    description = Column(String)  # , nullable=False

    planning_status = Column(
        String, nullable=False, default=JobPlanningStatus.UNPLANNED
    )
    life_cycle_status = Column(
        String, nullable=False, default=JobLifeCycleStatus.CREATED
    )
    auto_planning = Column(Boolean, default=True)

    # Whether or not the job is effective. If not, it is not occupying time slots even if inplanning.
    # It is false for jobs in appointments
    # All finished, cancelled jobs should also have is_active == False
    is_active = Column(Boolean, default=True)  

    team_id = Column(Integer, ForeignKey("team.id"), nullable=False)
    team = relationship("Team", backref="job_to_team_id")

    org_id = Column(Integer, nullable=True, default=0)

    flex_form_data = Column(
        JSON, default={"job_schedule_type": "N"}
    )  # Column(String, default='{"key_1":["skill_1"]}')
    schedule_type = Column(
        String, nullable=True, default=JobScheduleType.NORMAL
    )
    tolerance_start_minutes = Column(Float, default=-1440)
    tolerance_end_minutes = Column(Float, default=1440)


    # job_status = Column(String, default="toDo")
    # job_track_status = Column(String, default="notStarted")
    # Reserved for customer usage. Not visible to planner and workers.
    # cust_flex_form = Column( JSON, default={ } )  

    requested_start_datetime = Column(DateTime)  # null=True, blank=True,
    requested_duration_minutes = Column(Float)
    requested_primary_worker_code = Column(String, ForeignKey("worker.code"))
    requested_primary_worker = relationship(
        "Worker",
        backref="job_requested",
        foreign_keys=[requested_primary_worker_code],
    )
    # requested_secondary_worker are in participant, with   "requested_secondary"

    # This is more oriented to customer site time span, which may request location owner (customer)'s attention.
    # Each participant's time should better be in participant table.

    scheduled_start_datetime = Column(DateTime)
    scheduled_duration_minutes = Column(Float)
    scheduled_primary_worker_code = Column(String, ForeignKey("worker.code"))
    scheduled_primary_worker = relationship(
        "Worker",
        backref="job_scheduled",
        foreign_keys=[scheduled_primary_worker_code],
    )
    # appointment = relationship("Appointment", backref="included_jobs")
    # appointment_id = Column(Integer, ForeignKey("appointment.id"))
    actual_start_datetime = Column(DateTime)
    actual_duration_minutes = Column(Float)
    actual_worker_code = Column(String, ForeignKey("worker.code"))
    actual_worker = relationship(
        "Worker",
        backref="job_actual",
        foreign_keys=[actual_worker_code],
    )

    location = relationship("Location", backref="job_loc")
    location_code = Column(String, ForeignKey("location.code"), nullable=True)
    geo_longitude = Column(Float, nullable=True)
    geo_latitude = Column(Float, nullable=True)

    order = relationship("Order", backref="job_order_rel")
    order_code = Column(String, ForeignKey("order.code"))

    search_vector = Column(
        TSVectorType(
            "code",
            "description",
            "name",
            weights={"code": "A", "name": "B", "description": "C"},
        )
    )

    events = relationship("JobEvent", backref="job")

    requested_skills = Column(ARRAY(String))
    requested_items = Column(ARRAY(String))

# Pydantic models...


class JobBase(DispatchBase):
    """A Job is the main object that easydispatch will actively manage. The job may have different status as Unplanned, Inplanned, Planned.
    \n There maybe different types of jobs, especially the composite job and the atom job. Other high level objects like Appointments, Worker's Leave Event are also treated as jobs.
    \n
    """

    code: str = Field(
        title="Job Code", description='Job code is the unique identify for this job. It must be unique across all teams',)
    job_type: str = Field(
        title="Job Type", 
        description='Type of Job code as in JOB(visit), appt, leave, dropoff, pickup, replenish, ...',
        default=JobType.JOB)
    # business_type: str = Field(
    #     title="Business Type", 
    #     description='Type of Job as dropoff, pickup, replenish, ',
    #     default=JobType.JOB)
    name: Optional[str] = None
    description: Optional[str] = None
    org_id: Optional[str] = None
    planning_status: JobPlanningStatus = JobPlanningStatus.UNPLANNED
    life_cycle_status: JobLifeCycleStatus = JobLifeCycleStatus.CREATED
    auto_planning: Optional[bool] = Field(
        default=False, title="Automatic Planning Flag", description='When a job code have auto_planning == True, the easydispatch engine will try dispatch it when its status is U and make its status to I',)
    flex_form_data: Any = Field(
        default={}, title="Flexible Form Data", 
        description='You can save all customized job attributes into a flex_form_data. Those data will be used by dispatching rule plugins to validate the worker-job assignment. \n Examples of field candidates are: requested_skills, job_schedule_type, ...',)

    requested_start_datetime: Optional[datetime] = None
    requested_duration_minutes: float = 1
    requested_primary_worker_code: Optional[str] = None 

    scheduled_start_datetime: Optional[datetime] = None
    scheduled_duration_minutes: float = None
    scheduled_primary_worker_code: Optional[str] = None 
    # scheduled_secondary_workers: Optional[List[WorkerRead]] = []
    actual_start_datetime: Optional[datetime] = None
    actual_duration_minutes: float = None
    actual_worker_code: Optional[str] = None 

    requested_skills: Optional[List[str]] = []
    requested_items: Optional[List[str]] = []
    # tags: Optional[List[Any]] = []  # any until we figure out circular imports
    geo_longitude: float = None 
    geo_latitude: float = None
    tolerance_start_minutes: float = -1440
    tolerance_end_minutes: float = 1440


class JobCreate(JobBase):
    team: TeamCreate
    location: Optional[LocationCreate] = None

    # refer https://github.com/tiangolo/fastapi/issues/211
    flex_form_data: dict = Field(
        default={}, title="Flexible Form Data", 
        description='You can save all customized job attributes into a flex_form_data. Those data will be used by dispatching rule plugins to validate the worker-job assignment. \n Examples of field candidates are: requested_skills, job_schedule_type, ...',)
    requested_start_datetime: Optional[datetime] = None
    requested_duration_minutes: float = None

    requested_primary_worker: Optional[WorkerCreate]

    scheduled_start_datetime: Optional[datetime] = None
    scheduled_duration_minutes: float = None
    scheduled_primary_worker: Optional[WorkerCreate]  # : WorkerRead
    # scheduled_secondary_workers: Optional[List[WorkerCreate]] = []
    requested_skills: Optional[List[str]] = []
    requested_items: Optional[List[str]] = []
    # target_worker: str = None
    overwrite_max_orders_limit: bool = False
    is_appointment: bool = False


class JobUpdate(JobBase):
    # job_priority: JobPriorityBase+
    # job_type: JobTypeBase
    team: TeamCreate
    location: Optional[LocationCreate] = None

    # refer https://github.com/tiangolo/fastapi/issues/211
    flex_form_data: dict = Field(
        default={}, title="Flexible Form Data", description='You can save all customized job attributes into a flex_form_data. Those data will be used by dispatching rule plugins to validate the worker-job assignment. \n Examples of field candidates are: requested_skills, job_schedule_type, ...',)
    requested_start_datetime: Optional[datetime] = None
    requested_duration_minutes: float = None
    scheduled_start_datetime: Optional[datetime] = None
    scheduled_duration_minutes: float = None

    requested_primary_worker: Optional[WorkerCreate]
    scheduled_primary_worker: Optional[WorkerCreate]  # : WorkerRead
    # scheduled_secondary_workers: Optional[List[WorkerCreate]] = []
    update_source: str = "Unknown"
    requested_skills: Optional[List[str]] = []
    requested_items: Optional[List[str]] = []
    token = ""


class JobLifeCycleUpdate(DispatchBase):
    # This is a subset of JobUpdate
    code: str
    life_cycle_status: JobLifeCycleStatus = JobLifeCycleStatus.CREATED
    update_source: str = "life_cycle"
    job_type: bool = False
    comment: Optional[str] = None
    
    job_source: Optional[str] = None
    order_code: Optional[str] = None
    flex_form_data: Dict[str, Any] ={} 
    


class JobPlanningInfoUpdate(JobBase):
    # This is a subset of JobUpdate
    code: str
    job_type: Optional[str] = JobType.JOB
    planning_status: JobPlanningStatus = JobPlanningStatus.UNPLANNED
    scheduled_start_datetime: Optional[datetime] = None
    scheduled_duration_minutes: float = None

    scheduled_worker_code: Optional[str]  # : WorkerRead
    # scheduled_secondary_worker_codes: Optional[List[str]] = []
    update_source: str = "NA"



class JobRead(JobBase):
    team: TeamRead
    location: Optional[LocationRead]
    # job_track_status:str = ""
    job_track_status:str = None


    requested_primary_worker: Optional[WorkerRead]
    scheduled_primary_worker: Optional[WorkerRead]  # : WorkerRead
    # scheduled_secondary_workers: Optional[List[WorkerRead]] = []

    events: Optional[List[EventRead]] = []

    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    customer_address :str = None
    customer_zipcode :str = None
    external_order_code :str = None

class UnplannedJobRead(DispatchBase):
    code: str = Field(
        title="Job Code", description='Job code is the unique identify for this job. It must be unique across all teams',)
    geo_longitude: float = None 
    geo_latitude: float = None
    geo_longitude_loc: float = None 
    geo_latitude_loc: float = None
    requested_start_datetime: Optional[datetime] = None
    requested_duration_minutes: float = None
    requested_primary_worker_code: Optional[str] = None

    scheduled_start_datetime: Optional[datetime] = None
    scheduled_duration_minutes: float = None
    scheduled_primary_worker_code: Optional[str] = None  # : WorkerRead
    tolerance_end_minutes: float = 0

class UnplannedJobPagination(DispatchBase):
    total: int
    items: List[UnplannedJobRead] = []
    not_find_code:List[str] = []


class JobPagination(DispatchBase):
    total: int
    items: List[JobRead] = []
    not_find_code:List[str] = []


# Is this duplicated with Jobs/ ?
class WorkerJobEnvRead(BaseModel):
    total: int
    jobs: List[JobRead] = []
    workers: List[JobRead] = []


class JobReadResponese(DispatchBase):
    state: Optional[int]
    msg: Optional[str]
    data: Optional[JobRead]


class JobWorkerChange(DispatchBase):
    jobs: List[Optional[JobRead]] =[]
    worker: Optional[WorkerRead] = None



class JobRelated(DispatchBase):
    id: int
    order_code: str
    job_biz_job_type: Optional[str] =None
    job_biz_job_status: Optional[str] =None
    problem_reason_code:Optional[str] =None
    customer_address:Optional[str] =None
    allow_change_time_window_list: List[Any] = []
    job_track_status: Optional[str] = ''


class JobRelatedUpdate(DispatchBase):
    job_biz_job_status: Optional[str] =None
    problem_reason_code:Optional[str] =None
    requested_start_datetime:Optional[datetime] = None
    

class JobUpdateWorkerUpdate(DispatchBase):
    worker_code:Optional[str] =None
    job_code_list:Optional[List[int]] = []

class JobBatchSearch(DispatchBase):
    query_param: Optional[str] = None
    worker_code: Optional[str] = None
    planning_status: Optional[List[str]] = []
    page: int=1
    itemsPerPage:int=10
    sortBy: Optional[List[str]] = []
    descending: Optional[List[bool]] = []

class JobPlanningStatusUpdate(DispatchBase):
    team_id: str
    planning_status: str
    update_planning_status: str
    worker_code_list: Optional[list[str]] = []
    start_datetime: Optional[str] = None
    end_datetime: Optional[str] = None


    