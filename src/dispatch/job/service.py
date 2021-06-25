from sqlalchemy import inspect
from dispatch.plugins.kandbox_planner.data_adapter.kafka_adapter import KafkaAdapter
import math
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from dispatch.config import ANNUAL_COST_EMPLOYEE, BUSINESS_HOURS_YEAR
from dispatch.database import SessionLocal
from dispatch.event import service as event_service
from dispatch.worker import service as worker_service
from dispatch.worker.models import WorkerCreate
from dispatch.location import service as location_service
from dispatch.location.models import LocationCreate, LocationUpdate
from dispatch.plugin import service as plugin_service
from dispatch.plugins.base import plugins
from dispatch.tag import service as tag_service
from dispatch.tag.models import TagCreate, TagUpdate
from dispatch.team.models import TeamCreate
from dispatch.event.models import Event

from dispatch.team import service as team_service
from .enums import JobPlanningStatus
from .models import Job, JobUpdate, JobPlanningInfoUpdate
from dispatch.plugins.kandbox_planner.env.env_enums import (
    KafkaMessageType,
    KandboxMessageSourceType,
    KandboxMessageTopicType,
    KafkaRoleType,
)
from dispatch.plugins.kandbox_planner.env.env_models import KafkaEnvMessage


HOURS_IN_DAY = 24
SECONDS_IN_HOUR = 3600


kafka_server = KafkaAdapter(env=None, role=KafkaRoleType.FAKE, team_env_key="_")


def get(*, db_session, job_id: int) -> Optional[Job]:
    """Returns an job based on the given id."""
    return db_session.query(Job).filter(Job.id == job_id).first()


def get_by_name(*, db_session, job_name: str) -> Optional[Job]:
    """Returns an job based on the given name."""
    return db_session.query(Job).filter(Job.name == job_name).first()


def get_by_code(*, db_session, code: str) -> Optional[Job]:
    """Returns an job based on the given code."""
    return db_session.query(Job).filter(Job.code == code).first()


def get_all(*, db_session) -> List[Optional[Job]]:
    """Returns all jobs."""
    return db_session.query(Job)


def get_all_by_status(
    *, db_session, planning_status: JobPlanningStatus, skip=0, limit=100
) -> List[Optional[Job]]:
    """Returns all jobs based on the given planning_status."""
    return (
        db_session.query(Job)
        .filter(Job.planning_status == planning_status)
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_all_last_x_hours_by_status(
    *, db_session, planning_status: JobPlanningStatus, hours: int, skip=0, limit=100
) -> List[Optional[Job]]:
    """Returns all jobs of a given planning_status in the last x hours."""
    now = datetime.utcnow()

    return (
        db_session.query(Job)
        .filter(Job.planning_status == planning_status)
        .filter(Job.created_at >= now - timedelta(hours=hours))
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_all_by_job_type(*, db_session, job_type: str, skip=0, limit=100) -> List[Optional[Job]]:
    """Returns all jobs with the given job type."""
    return (
        db_session.query(Job).filter(Job.job_type.name == job_type).offset(skip).limit(limit).all()
    )


def create(
    *,
    db_session,
    # job_priority: str = None,
    # job_type: str,
    code: str,
    job_type: str = "visit",
    name: str = None,
    planning_status: str,
    tags: List[dict],
    description: str = None,
    team: TeamCreate,
    location: LocationCreate,
    flex_form_data: dict = None,
    requested_primary_worker: WorkerCreate = None,
    requested_start_datetime: datetime = None,
    requested_duration_minutes: float = None,
    scheduled_primary_worker: WorkerCreate = None,
    scheduled_secondary_workers: List[WorkerCreate],
    scheduled_start_datetime: datetime = None,
    scheduled_duration_minutes: float = None,
    auto_planning: bool = True,
) -> Job:
    """Creates a new job."""

    tag_objs = []
    for t in tags:
        tag_objs.append(tag_service.get_or_create(db_session=db_session, tag_in=TagCreate(**t)))

    team_obj = team_service.get_by_code(db_session=db_session, code=team["code"])
    loc_to_create = LocationCreate(**location)
    location_obj = location_service.get_or_create_by_code(
        db_session=db_session, location_in=loc_to_create
    )
    # if location_obj.geo_longitude < 1:
    #     location_obj.geo_longitude = loc_to_create.geo_longitude
    #     location_obj.geo_latitude = loc_to_create.geo_latitude
    db_session.add(location_obj)
    # location_obj = location_service.update(
    #     db_session=db_session, location=location_obj, location_in=LocationUpdate(**location)
    # )

    if requested_primary_worker:
        requested_primary_worker = worker_service.get_by_code(
            db_session=db_session, code=requested_primary_worker["code"]
        )
    if scheduled_primary_worker:
        scheduled_primary_worker = worker_service.get_by_code(
            db_session=db_session, code=scheduled_primary_worker["code"]
        )
    if scheduled_secondary_workers is None:
        scheduled_secondary_workers = []
    # We create the job
    job = Job(
        code=code,
        name=name,
        job_type=job_type,
        description=description,
        planning_status=planning_status,
        tags=tag_objs,
        flex_form_data=flex_form_data,
        location=location_obj,
        team=team_obj,
        requested_start_datetime=requested_start_datetime,
        requested_duration_minutes=requested_duration_minutes,
        requested_primary_worker=requested_primary_worker,
        scheduled_start_datetime=scheduled_start_datetime,
        scheduled_duration_minutes=scheduled_duration_minutes,
        scheduled_primary_worker=scheduled_primary_worker,
        scheduled_secondary_workers=scheduled_secondary_workers,
        auto_planning=auto_planning,
    )
    db_session.add(job)
    db_session.commit()

    event_service.log(
        db_session=db_session,
        source="Dispatch Core App",
        description=f"Job ({code}) is created, planning_status={planning_status}, scheduled_start_datetime={scheduled_start_datetime}",
        job_id=job.id,
    )

    post_job_to_kafka(job=job, message_type=KafkaMessageType.CREATE_JOB, db_session=db_session)

    return job


def post_job_to_kafka(job: Job, message_type, db_session):
    job_dict = {c.key: getattr(job, c.key) for c in inspect(job).mapper.column_attrs}

    job_dict["requested_primary_worker_code"] = job.requested_primary_worker.code
    job_dict["scheduled_secondary_worker_codes"] = [w.code for w in job.scheduled_secondary_workers]
    job_dict["location_code"] = job.location.location_code
    job_dict["geo_longitude"] = job.location.geo_longitude
    job_dict["geo_latitude"] = job.location.geo_latitude

    if job.scheduled_primary_worker:
        job_dict["scheduled_primary_worker_code"] = job.scheduled_primary_worker.code
    else:
        job_dict["scheduled_primary_worker_code"] = None

    kem = KafkaEnvMessage(
        message_type=message_type,
        message_source_type=KandboxMessageSourceType.ENV,
        message_source_code="USER.Web",
        payload=[job_dict],
    )

    topic_name = f"{KandboxMessageTopicType.ENV_WINDOW}.env_{job.team.org_id}_{job.team.id}"

    offset = kafka_server.post_message(topic_name=topic_name, m=kem)
    job.team.latest_env_kafka_offset = offset
    db_session.add(job.team)
    db_session.commit()


def update_planning_info(*, db_session, job_in: JobPlanningInfoUpdate) -> Job:

    existing_job = get_by_code(db_session=db_session, code=job_in.code)

    existing_job.planning_status = job_in.planning_status
    existing_job.scheduled_start_datetime = job_in.scheduled_start_datetime
    existing_job.scheduled_duration_minutes = job_in.scheduled_duration_minutes
    existing_job.scheduled_primary_worker = worker_service.get_by_code(
        db_session=db_session, code=job_in.scheduled_primary_worker_code
    )

    # if len(job_in.scheduled_secondary_workers) > 0:
    # else:
    #     existing_job.scheduled_secondary_workers = None
    existing_job.scheduled_secondary_workers = [
        worker_service.get_by_code(db_session=db_session, code=_c)
        for _c in job_in.scheduled_secondary_worker_codes
    ]

    db_session.add(existing_job)
    db_session.commit()
    event_service.log(
        db_session=db_session,
        source=job_in.update_source,
        # .scheduled_start_datetime
        description=f"Job ({job_in.code}) is changed to different plan: {job_in}",
        job_id=existing_job.id,
    )
    post_job_to_kafka(job=existing_job, message_type=KafkaMessageType.UPDATE_JOB,
                      db_session=db_session)

    return existing_job


def update(*, db_session, job: Job, job_in: JobUpdate) -> Job:
    tags = []
    for t in job_in.tags:
        tags.append(tag_service.get_or_create(db_session=db_session, tag_in=TagUpdate(**t)))

    scheduled_secondary_workers = []
    for w in job_in.scheduled_secondary_workers:
        scheduled_secondary_workers.append(
            worker_service.get_by_code(db_session=db_session, code=w.code))

    update_data = job_in.dict(
        skip_defaults=True,
        exclude={
            "tags",
            "scheduled_secondary_workers",
            "requested_primary_worker",
            "scheduled_primary_worker",
            "team",
            "location",
        },
    )

    for field in update_data.keys():
        setattr(job, field, update_data[field])

    job.scheduled_secondary_workers = scheduled_secondary_workers
    job.tags = tags
    if job_in.scheduled_primary_worker is not None:
        job.scheduled_primary_worker = worker_service.get_by_code(
            db_session=db_session, code=job_in.scheduled_primary_worker.code
        )
    if job_in.requested_primary_worker is not None:
        job.requested_primary_worker = worker_service.get_by_code(
            db_session=db_session, code=job_in.requested_primary_worker.code
        )

    db_session.add(job)
    db_session.commit()
    event_service.log(
        db_session=db_session,
        source="Dispatch Core App",
        description=f"Job ({job_in.code}) is updated {job_in.flex_form_data}",
        job_id=job.id,
    )
    post_job_to_kafka(job=job, message_type=KafkaMessageType.UPDATE_JOB, db_session=db_session)
    return job


def delete(*, db_session, job_id: int):
    # TODO: When deleting, respect referential integrity here in the code. Or add cascading deletes
    # in models.py.
    db_session.query(Event).filter(Event.job_id == job_id).delete()
    db_session.query(Job).filter(Job.id == job_id).delete()
    db_session.commit()


def calculate_cost(job_id: int, db_session: SessionLocal, job_review=True):
    """Calculates the cost of a given job."""
    job = get(db_session=db_session, job_id=job_id)

    participants_total_response_time_seconds = 0
    for participant in job.participants:

        participant_total_roles_time_seconds = 0
        for participant_role in participant.participant_roles:
            # TODO(mvilanova): skip if we did not see activity from the participant in the job conversation

            participant_role_assumed_at = participant_role.assumed_at

            if participant_role.renounced_at:
                # the participant left the conversation or got assigned another role
                # we use the renounced_at time
                participant_role_renounced_at = participant_role.renounced_at
            elif job.planning_status != JobPlanningStatus.inplanning:
                # the job is stable or closed. we use the stable_at time
                participant_role_renounced_at = job.stable_at
            else:
                # the job is still active. we use the current time
                participant_role_renounced_at = datetime.utcnow()

            # we calculate the time the participant has spent in the job role
            participant_role_time = participant_role_renounced_at - participant_role_assumed_at

            if participant_role_time.total_seconds() < 0:
                # the participant was added after the job was marked as stable
                continue

            # we calculate the number of hours the participant has spent in the job role
            participant_role_time_hours = participant_role_time.total_seconds() / SECONDS_IN_HOUR

            # we make the assumption that participants only spend 8 hours a day working on the job,
            # if the job goes past 24hrs
            # TODO(mvilanova): adjust based on job priority
            if participant_role_time_hours > HOURS_IN_DAY:
                days, hours = divmod(participant_role_time_hours, HOURS_IN_DAY)
                participant_role_time_hours = math.ceil(((days * HOURS_IN_DAY) / 3) + hours)

            # we make the assumption that participants spend more or less time based on their role
            # and we adjust the time spent based on that
            participant_role_time_seconds = int(
                participant_role_time_hours
                * SECONDS_IN_HOUR
                * get_engagement_multiplier(participant_role.role)
            )

            participant_total_roles_time_seconds += participant_role_time_seconds

        participants_total_response_time_seconds += participant_total_roles_time_seconds

    # we calculate the time spent in job review related activities
    job_review_hours = 0
    if job_review:
        num_participants = len(job.participants)
        job_review_prep = (
            1  # we make the assumption that it takes an hour to prepare the job review
        )
        job_review_meeting = (
            num_participants * 0.5 * 1
        )  # we make the assumption that only half of the job participants will attend the 1-hour, job review session
        job_review_hours = job_review_prep + job_review_meeting

    # we calculate and round up the hourly rate
    hourly_rate = math.ceil(ANNUAL_COST_EMPLOYEE / BUSINESS_HOURS_YEAR)

    # we calculate and round up the job cost
    job_cost = math.ceil(
        ((participants_total_response_time_seconds / SECONDS_IN_HOUR) + job_review_hours)
        * hourly_rate
    )

    return job_cost
