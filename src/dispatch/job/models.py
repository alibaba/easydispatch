from collections import Counter
from datetime import datetime
from typing import Any, List, Optional

from fastapi_permissions import Allow
from pydantic import BaseModel, validator, Field
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
    select,
    Boolean,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from sqlalchemy_utils import TSVectorType

from dispatch.auth.models import UserRoles
from dispatch.config import (
    INCIDENT_RESOURCE_CONVERSATION_COMMANDS_REFERENCE_DOCUMENT,
    INCIDENT_RESOURCE_FAQ_DOCUMENT,
    INCIDENT_RESOURCE_INCIDENT_REVIEW_DOCUMENT,
    INCIDENT_RESOURCE_INVESTIGATION_DOCUMENT,
)
from dispatch.database import Base
from dispatch.event.models import EventRead
from dispatch.worker.models import WorkerCreate, WorkerRead
from dispatch.location.models import LocationCreate, LocationRead
from dispatch.models import DispatchBase, WorkerReadNested, TimeStampMixin
from dispatch.team.models import Team, TeamCreate, TeamRead

from .enums import JobPlanningStatus, JobType


from dispatch.plugins.kandbox_planner.env.env_enums import JobType, JobPlanningStatus


assoc_job_tags = Table(
    "assoc_job_tags",
    Base.metadata,
    Column("job_id", Integer, ForeignKey("job.id")),
    Column("tag_id", Integer, ForeignKey("tag.id")),
    PrimaryKeyConstraint("job_id", "tag_id"),
)

job_scheduled_secondary_workers = Table(
    "job_scheduled_secondary_workers",
    Base.metadata,
    Column("job_id", Integer, ForeignKey("job.id")),
    Column("worker_id", Integer, ForeignKey("worker.id")),
    PrimaryKeyConstraint("job_id", "worker_id"),
)


class Job(Base, TimeStampMixin):
    id = Column(Integer, primary_key=True)
    code = Column(String, nullable=False, unique=True)  # code
    job_type = Column(String, nullable=False, default=JobType.JOB)  # JobType
    name = Column(String)
    description = Column(String)  # , nullable=False

    planning_status = Column(
        String, nullable=False, default=JobPlanningStatus.UNPLANNED
    )
    auto_planning = Column(Boolean, default=True)

    is_active = Column(Boolean, default=True)  # job vs absence

    team_id = Column(Integer, ForeignKey("team.id"), nullable=False)
    team = relationship("Team")

    flex_form_data = Column(
        JSON, default={"job_schedule_type": "N"}
    )  # Column(String, default='{"key_1":["skill_1"]}')

    # requested_worker_code = models.ForeignKey(Worker, null=True, on_delete=models.DO_NOTHING)
    requested_start_datetime = Column(DateTime)  # null=True, blank=True,
    requested_duration_minutes = Column(Float)
    requested_primary_worker_id = Column(Integer, ForeignKey("worker.id"))
    # https://docs.sqlalchemy.org/en/13/orm/join_conditions.html
    # foreign_keys is needed
    requested_primary_worker = relationship(
        "Worker",
        backref="incident_requested",
        foreign_keys=[requested_primary_worker_id],
    )
    # requested_secondary_worker are in participant, with   "requested_secondary"

    # This is more oriented to customer site time span, which may request location owner (customer)'s attention.
    # Each participant's time should better be in participant table.

    scheduled_start_datetime = Column(DateTime)
    scheduled_duration_minutes = Column(Float)
    scheduled_primary_worker_id = Column(Integer, ForeignKey("worker.id"))
    scheduled_primary_worker = relationship(
        "Worker",
        backref="incident_scheduled",
        foreign_keys=[scheduled_primary_worker_id],
    )
    # appointment = relationship("Appointment", backref="included_jobs")
    # appointment_id = Column(Integer, ForeignKey("appointment.id"))

    location = relationship("Location", backref="job_loc")
    location_id = Column(Integer, ForeignKey("location.id"))

    search_vector = Column(
        TSVectorType(
            "code",
            "description",
            "name",
            weights={"code": "A", "name": "B", "description": "C"},
        )
    )

    events = relationship("Event", backref="job")
    tags = relationship("Tag", secondary=assoc_job_tags, backref="job_tag")
    scheduled_secondary_workers = relationship(
        "Worker",
        secondary=job_scheduled_secondary_workers,
        backref="job_scheduled_secondary_workers_rel",
    )


# Pydantic models...
class JobBase(DispatchBase):
    """A Job is the main object that easydispatch will actively manage. The job may have different status as Unplanned, Inplanned, Planned. 
    \n There maybe different types of jobs, especially the composite job and the atom job. Other high level objects like Appointments, Worker's Leave Event are also treated as jobs.
    \n 
    """

    code: str = Field(
        title="Job Code", description='Job code is the unique identify for this job. It must be unique across all teams',)
    job_type: str = Field(
        title="Job Type", description='Type of Job code as in job(visit), composite, appt, leave',)
    name: Optional[str] = None
    description: Optional[str] = None
    planning_status: JobPlanningStatus = JobPlanningStatus.UNPLANNED
    auto_planning: Optional[bool] = Field(
        default=False, title="Automatic Planning Flag", description='When a job code have auto_planning == True, the easydispatch engine will try dispatch it when its status is U and make its status to I',)
    flex_form_data: Any = Field(
        default={}, title="Flexible Form Data", description='You can save all customized job attributes into a flex_form_data. Those data will be used by dispatching rule plugins to validate the worker-job assignment. \n Examples of field candidates are: requested_skills, job_schedule_type, ...',)

    requested_start_datetime: Optional[datetime] = None
    requested_duration_minutes: float = None
    requested_primary_worker: Optional[WorkerRead]

    scheduled_start_datetime: Optional[datetime] = None
    scheduled_duration_minutes: float = None
    scheduled_primary_worker: Optional[WorkerRead]  # : WorkerRead
    scheduled_secondary_workers: Optional[List[WorkerRead]] = []

    tags: Optional[List[Any]] = []  # any until we figure out circular imports


class JobCreate(JobBase):
    team: TeamCreate
    location: LocationCreate

    # refer https://github.com/tiangolo/fastapi/issues/211
    flex_form_data: dict = Field(
        default={}, title="Flexible Form Data", description='You can save all customized job attributes into a flex_form_data. Those data will be used by dispatching rule plugins to validate the worker-job assignment. \n Examples of field candidates are: requested_skills, job_schedule_type, ...',)
    requested_start_datetime: Optional[datetime] = None
    requested_duration_minutes: float = None

    requested_primary_worker: Optional[WorkerCreate]

    scheduled_start_datetime: Optional[datetime] = None
    scheduled_duration_minutes: float = None
    scheduled_primary_worker: Optional[WorkerCreate]  # : WorkerRead
    scheduled_secondary_workers: Optional[List[WorkerCreate]] = []


class JobUpdate(JobBase):
    # job_priority: JobPriorityBase
    # job_type: JobTypeBase
    team: TeamCreate
    location: LocationCreate

    # refer https://github.com/tiangolo/fastapi/issues/211
    flex_form_data: dict = Field(
        default={}, title="Flexible Form Data", description='You can save all customized job attributes into a flex_form_data. Those data will be used by dispatching rule plugins to validate the worker-job assignment. \n Examples of field candidates are: requested_skills, job_schedule_type, ...',)
    requested_start_datetime: Optional[datetime] = None
    requested_duration_minutes: float = None
    scheduled_start_datetime: Optional[datetime] = None
    scheduled_duration_minutes: float = None

    requested_primary_worker: Optional[WorkerCreate]
    scheduled_primary_worker: Optional[WorkerCreate]  # : WorkerRead
    scheduled_secondary_workers: Optional[List[WorkerCreate]] = []
    update_source: str = "Unknown"


class JobPlanningInfoUpdate(JobBase):
    # This is a subset of JobUpdate
    code: str
    planning_status: JobPlanningStatus = JobPlanningStatus.UNPLANNED
    scheduled_start_datetime: Optional[datetime] = None
    scheduled_duration_minutes: float = None

    scheduled_primary_worker_code: Optional[str]  # : WorkerRead
    scheduled_secondary_worker_codes: Optional[List[str]] = []
    update_source: str = "Unknown"


class JobRead(JobBase):
    id: int
    team: TeamRead
    location: LocationRead

    requested_primary_worker: Optional[WorkerRead]
    scheduled_primary_worker: Optional[WorkerRead]  # : WorkerRead
    scheduled_secondary_workers: Optional[List[WorkerRead]] = []

    events: Optional[List[EventRead]] = []

    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class JobPagination(DispatchBase):
    total: int
    items: List[JobRead] = []


# Is this duplicated with Jobs/ ?
class WorkerJobEnvRead(BaseModel):
    total: int
    jobs: List[JobRead] = []
    workers: List[JobRead] = []
