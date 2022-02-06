from dispatch.zulip_server.core import get_zulip_client_by_org_id
import traceback
from dispatch.org import service as orgService
from dispatch.plugins.bases.kandbox_planner import KandboxPlannerPluginType
from dispatch.service_plugin import service as service_plugin_service
from dispatch.logs import service as logService
import json
import logging
import requests
from sqlalchemy import inspect
import sqlalchemy.sql.expression
from sqlalchemy.sql.functions import func
from dispatch.logs.models import LogCreate
from dispatch.plugins.kandbox_planner.data_adapter.kafka_adapter import KafkaAdapter
import math
from tqdm import tqdm
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi.encoders import jsonable_encoder
import shortuuid 
# ANNUAL_COST_EMPLOYEE, BUSINESS_HOURS_YEAR, 
from dispatch.config import ISO_DATE_FORMAT, KANDBOX_DATETIME_FORMAT_ISO, KANDBOX_DATE_FORMAT
from dispatch.database import SessionLocal
from dispatch.event import service as event_service
from dispatch.worker import service as worker_service
from dispatch.worker.models import WorkerCreate
from dispatch.location import service as location_service
from dispatch.location.models import Location, LocationCreate, LocationUpdate
from dispatch.plugin import service as plugin_service
from dispatch.plugins.base import plugins
from dispatch.tag import service as tag_service
from dispatch.tag.models import TagCreate, TagUpdate
from dispatch.team.models import TeamCreate
from dispatch.event.models import Event
from dispatch.plugins.kandbox_planner.location_adapter.location_service_adapter import LocationAdapterService
from dispatch import config

import copy
from fastapi import Depends
from dispatch.database import get_db

from sqlalchemy.orm import Session
from dispatch.team import service as team_service
from .models import Job, JobUpdate, JobPlanningInfoUpdate, JobLifeCycleUpdate

from dispatch.plugins.kandbox_planner.env.env_enums import (
    JobType,
    KafkaMessageType,
    KandboxMessageSourceType,
    KandboxMessageTopicType,
    KafkaRoleType,
    JobLifeCycleStatus_SEQUENCE,
    JobLifeCycleStatus,
    JobPlanningStatus,
)
from dispatch.plugins.kandbox_planner.env.env_models import KafkaEnvMessage
from dispatch.config import INCIDENT_PLUGIN_CONTACT_SLUG, SQLALCHEMY_DATABASE_URI
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import sessionmaker

from dispatch.item_inventory import service as inventory_service  # import  get_by_depot_item_list
from dispatch.depot import service as depot_service
from dispatch.item import service as item_service
from dispatch.item_inventory_event import service as inventory_event_service

try:
    from dispatch.contrib.pldt.test_data import _init_call_back_data, test_ipms_data, test_apms_data
except:
    pass

from dispatch.plugins.kandbox_planner.util.kandbox_util import (
    parse_item_str
)
log = logging.getLogger(__name__)

HOURS_IN_DAY = 24
SECONDS_IN_HOUR = 3600

kafka_server = KafkaAdapter(env=None, role=KafkaRoleType.FAKE, team_env_key="API_Server")

SHORTUUID = shortuuid.ShortUUID(alphabet="0123456789")

# engine = create_engine(str(SQLALCHEMY_DATABASE_URI))
# db_session = sessionmaker(bind=engine)
# session = db_session()

# session = Depends(get_db)


def get(*, db_session, job_id: int) -> Optional[Job]:
    """Returns an job based on the given id."""
    return db_session.query(Job).filter(Job.id == job_id).first()


def get_by_name(*, db_session, job_name: str) -> Optional[Job]:
    """Returns an job based on the given name."""
    return db_session.query(Job).filter(Job.name == job_name).first()


def get_by_code(*, db_session, code: str) -> Optional[Job]:
    """Returns an job based on the given code."""
    return db_session.query(Job).filter(Job.code == code).first()


def get_by_org_id_count(*, db_session, org_id: int) -> Optional[int]:
    """Returns an job based on the given code."""
    return db_session.query(func.count(Job.id)).filter(Job.org_id == org_id).scalar()


def get_all(*, db_session) -> List[Optional[Job]]:
    """Returns all jobs."""
    return db_session.query(Job).all()


def get_by_team(*, team_id: int, db_session) -> List[Optional[Job]]:
    """Returns all jobs."""
    return db_session.query(Job).filter(Job.team_id == team_id).all()


def get_by_team_and_status(*, team_id: int, db_session, planning_status_list: list, start_time=any, end_time=any) -> List[Optional[Job]]:
    """Returns all jobs."""
    return db_session.query(Job).filter(Job.team_id == team_id, Job.scheduled_start_datetime >= start_time, Job.scheduled_start_datetime <= end_time, Job.planning_status.in_(planning_status_list)).all()


def get_all_by_status(*, db_session, planning_status: JobPlanningStatus, skip=0, limit=100) -> List[Optional[Job]]:
    """Returns all jobs based on the given planning_status."""
    return (db_session.query(Job).filter(Job.planning_status == planning_status).offset(skip).limit(limit).all())


def get_all_last_x_hours_by_status(*, db_session, planning_status: JobPlanningStatus, hours: int, skip=0, limit=100) -> List[Optional[Job]]:
    """Returns all jobs of a given planning_status in the last x hours."""
    now = datetime.utcnow()

    return (db_session.query(Job).filter(Job.planning_status == planning_status).filter(Job.created_at >= now - timedelta(hours=hours)).offset(skip).limit(limit).all())


def get_all_by_job_type(*, db_session, job_type: str, skip=0, limit=100) -> List[Optional[Job]]:
    """Returns all jobs with the given job type."""
    return (db_session.query(Job).filter(Job.job_type.name == job_type).offset(skip).limit(limit).all())


def get_all_by_job_date_time(*, db_session, start_time: str, end_time: str) -> List[Optional[Job]]:
    """Returns all jobs with the given job type."""
    return (db_session.query(Job).filter(Job.created_at.between(start_time, end_time)).all())


def _check_location(location, flex_form_data):
    flag = True
    try:
        if flex_form_data.get('geo_longitude_max') and flex_form_data.get('eo_longitude_min') and (location['longitude'] > flex_form_data.get('geo_longitude_max') or location['longitude'] < flex_form_data.get('eo_longitude_min') or location['latitude'] > flex_form_data.get('geo_latitude_max') or location['latitude'] < flex_form_data.get('geo_latitude_min')):
            flag = False
    except:
        pass

    return flag


def create(
    *,
    db_session,
    # job_priority: str = None,
    # job_type: str,
    code: str,
    job_type: str = "visit",
    org_id: str = None,
    org_code: str = None,
    name: str = None,
    planning_status: str,
    tags: List[dict] = [],
    description: str = None,
    team: TeamCreate,
    location: LocationCreate,
    flex_form_data: dict = None,
    requested_primary_worker: WorkerCreate = None,
    requested_start_datetime: datetime = None,
    requested_duration_minutes: float = None,
    scheduled_primary_worker: WorkerCreate = None,
    scheduled_secondary_workers: List[WorkerCreate] = [],
    scheduled_start_datetime: datetime = None,
    scheduled_duration_minutes: float = None,
    auto_planning: bool = True,
    requested_skills: List[str] = [],
    requested_items: List[str] = [],
    life_cycle_status: JobLifeCycleUpdate = None
) -> Job:
    """Creates a new job."""

    tag_objs = []
    for t in tags:
        tag_objs.append(tag_service.get_or_create(db_session=db_session, tag_in=TagCreate(**t)))

    team_obj = team_service.get_by_code(db_session=db_session, code=team["code"])

    location_obj = location_service.get_by_location_code(
        db_session=db_session,
        location_code=location["location_code"])
    if location_obj is None:
        loc_to_create = LocationCreate(**location)
        loc_to_create.org_id = org_id
        if loc_to_create.geo_address_text and not loc_to_create.geo_latitude:
            try:
                nid = SHORTUUID.random(length=9)
                location_config = {
                    "url": config.LOCATION_SERVICE_URL,
                    "token": config.LOCATION_SERVICE_TOKEN,
                    "request_method": config.LOCATION_SERVICE_REQUEST_METHOD,
                }
                payload = {"address_id": nid,
                           "input_address": loc_to_create.geo_address_text
                           }
                # get location service
                location_plug = service_plugin_service.get_by_service_id_and_type(
                    db_session=db_session,
                    service_id=team_obj.service_id,
                    service_plugin_type=KandboxPlannerPluginType.kandbox_location_service,
                ).all()
                if location_plug:
                    location_plugin = plugins.get(location_plug[0].plugin.slug)
                    location_adapter_service = location_plugin(config=location_config)
                    status, _location_ret, msg = location_adapter_service.get_pldt_location(payload)

                    if status:
                        if isinstance(_location_ret['latitude'], float):
                            if _check_location(_location_ret, team_obj.flex_form_data):
                                loc_to_create.geo_latitude = _location_ret['latitude']
                                loc_to_create.geo_longitude = _location_ret['longitude']
                                loc_to_create.id = _location_ret['location_id']
                                loc_to_create.location_code = _location_ret['location_code']
                            else:
                                logService.create(db_session=db_session, log_in=LogCreate(
                                    title='Location Response Data OutSide', category='Location', content=f"location outside,job code:{code},input_address:{payload['input_address']}, msg:{str(_location_ret)}", org_id=int(org_id), team_id=team_obj.id))
                                log.error(
                                    f"Location Response Data OutSide ,{msg} :{payload['input_address']}")
                        else:
                            logService.create(db_session=db_session, log_in=LogCreate(
                                title='Location Response Data NUll', category='Location', content=f"job code:{code},input_address:{payload['input_address']},msg:{str(_location_ret)}", org_id=int(org_id), team_id=team_obj.id))
                            log.error(
                                f"Location Response Data NUll ,{msg} :{payload['input_address']}")
                    else:
                        logService.create(db_session=db_session, log_in=LogCreate(
                            title=msg['type'], category='Location', content=f"job code:{code},input_address:{payload['input_address']},msg:{str(msg['msg'])}", org_id=int(org_id), team_id=team_obj.id))
                        log.error(
                            f"Location Response failed ,{msg} :{payload['input_address']}")
                else:
                    log.error(
                        f"not find location plug,service:{team_obj.service_id},{KandboxPlannerPluginType.kandbox_location_service}")
            except Exception as e:
                print(traceback.format_exc())
                log.error(f"address request error:{loc_to_create.geo_address_text},{ e} ")

        location_obj = location_service.get_or_create_by_code(
            db_session=db_session, location_in=loc_to_create)
        # if location_obj.geo_longitude < 1:
        #     location_obj.geo_longitude = loc_to_create.geo_longitude
        #     location_obj.geo_latitude = loc_to_create.geo_latitude
        db_session.add(location_obj)
    # location_obj = location_service.update(
    #     db_session=db_session, location=location_obj, location_in=LocationUpdate(**location)
    # )

    if requested_primary_worker:
        requested_primary_worker = worker_service.get_by_code(
            db_session=db_session, code=requested_primary_worker["code"])
    if scheduled_primary_worker:
        scheduled_primary_worker = worker_service.get_by_code(
            db_session=db_session, code=scheduled_primary_worker["code"])
    scheduled_secondary_workers_list = []
    if scheduled_secondary_workers is not None:
        for w in scheduled_secondary_workers:
            scheduled_secondary_workers_list.append(
                worker_service.get_by_code(db_session=db_session, code=w['code']))
    # We create the job
    if requested_skills:
        flex_form_data['requested_skills'] = requested_skills
    if requested_items:
        flex_form_data['requested_items'] = requested_items
    job = Job(
        code=code,
        name=name,
        org_id=org_id,
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
        scheduled_secondary_workers=scheduled_secondary_workers_list,
        auto_planning=auto_planning,
        requested_skills=requested_skills,
        requested_items=requested_items,
    )
    db_session.add(job)

    if job.job_type == JobType.REPLENISH:
        depot_code = flex_form_data["depot_code"]
        depot = depot_service.get_by_code(db_session=db_session, code=depot_code)

        for item_str in flex_form_data["requested_items"]:
            item_list = parse_item_str(item_str)
            item = item_service.get_by_code(db_session=db_session, code=item_list[0])
            inv = inventory_service.get_by_item_depot(
                db_session=db_session,
                item_id=item.id,
                depot_id=depot.id,
                org_id=team_obj.org_id
            ).one_or_none()
            inv.curr_qty -= item_list[1]
            inv.allocated_qty += item_list[1]
            if inv.curr_qty < 0:
                log.error(
                    f" Not enough inventory for item: {item_list[0]}, depot: {depot_code}, org.id: {team_obj.org_id}")
                continue
            db_session.add(inv)
            inventory_event_service.log(
                db_session=db_session,
                source="Env_Replenish",
                description=f"Allocated {item_list[1]} {item_list[0]} from depot: {depot_code}",
                item_code=item_list[0],
                depot_code=depot_code,
                item_id=item.id,
                depot_id=depot.id
            )

    db_session.commit()

    print(f"\033[37;46m\t1:add job succeed,{code}\033[0m")
    log.info(f"1:add job succeed,{code}")
    event_service.log(
        db_session=db_session,
        source="Dispatch Core App",
        description=f"Job ({code}) is created, planning_status={planning_status}, requested_start_datetime={requested_start_datetime}",
        job_id=job.id,
    )

    post_job_to_kafka(job=job, message_type=KafkaMessageType.CREATE_JOB,
                      db_session=db_session, org_code=org_code)

    print(f"\033[37;46m\t2:job post kafka in succeed,{code}\033[0m")
    log.info(f"2:job post kafka in succeed,{code}")

    # zulip send message
    if job.planning_status != JobPlanningStatus.UNPLANNED:
        zulip_dict = get_zulip_client_by_org_id(job.org_id)
        if zulip_dict:
            zulip_core = zulip_dict['client']
            zulip_core.update_job_send_message(
                job, [job.scheduled_primary_worker] + job.scheduled_secondary_workers)

    return job


def post_job_to_kafka(job: Job, message_type, db_session, org_code=None):
    job_dict = {c.key: getattr(job, c.key) for c in inspect(job).mapper.column_attrs}

    job_dict["requested_primary_worker_code"] = None
    if job.requested_primary_worker is not None:
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
    if not org_code:
        org_data = orgService.get(db_session=db_session, org_id=job.org_id)
        org_code = org_data.code
    topic_name = f"{KandboxMessageTopicType.ENV_WINDOW}.env_{org_code}_{job.team.id}"

    offset = kafka_server.post_message(topic_name=topic_name, m=kem)
    job.team.latest_env_kafka_offset = offset
    db_session.add(job.team)
    db_session.commit()


def update_planning_info(*, db_session, job_in: JobPlanningInfoUpdate) -> Job:

    existing_job = get_by_code(db_session=db_session, code=job_in.code)

    existing_job.planning_status = job_in.planning_status
    if job_in.scheduled_start_datetime:
        existing_job.scheduled_start_datetime = job_in.scheduled_start_datetime
    if job_in.scheduled_duration_minutes:
        existing_job.scheduled_duration_minutes = job_in.scheduled_duration_minutes
    if job_in.scheduled_primary_worker_code:
        existing_job.scheduled_primary_worker = worker_service.get_by_code(
            db_session=db_session, code=job_in.scheduled_primary_worker_code)

    # if len(job_in.scheduled_secondary_workers) > 0:
    # else:
    #     existing_job.scheduled_secondary_workers = None
    if job_in.scheduled_secondary_worker_codes:
        existing_job.scheduled_secondary_workers = [worker_service.get_by_code(
            db_session=db_session, code=_c) for _c in job_in.scheduled_secondary_worker_codes]

    db_session.add(existing_job)
    db_session.commit()
    new_plan = (
        job_in.planning_status.value,
        job_in.scheduled_primary_worker_code,
        job_in.scheduled_secondary_worker_codes,
        str(job_in.scheduled_start_datetime),
        job_in.scheduled_duration_minutes
    )
    message = f"Job ({job_in.code}) is changed to a different plan: {new_plan}"
    event_service.log(
        db_session=db_session,
        source=job_in.update_source,
        # .scheduled_start_datetime
        description=f"changed planning:  {new_plan}",
        job_id=existing_job.id,
        # details={
        #     "job_code":job_in.code,
        #     "message":message,
        #     "planning_status": job_in.planning_status,
        #     "scheduled_primary_worker_code": job_in.scheduled_primary_worker_code,
        #     "scheduled_start_datetime": str(job_in.scheduled_start_datetime),
        # }
    )
    post_job_to_kafka(job=existing_job, message_type=KafkaMessageType.UPDATE_JOB,
                      db_session=db_session)

    # zulip send message
    zulip_dict = get_zulip_client_by_org_id(existing_job.org_id)
    if zulip_dict:
        zulip_core = zulip_dict['client']
        zulip_core.update_job_send_message(
            existing_job, [existing_job.scheduled_primary_worker] + existing_job.scheduled_secondary_workers)
    return existing_job


def update_life_cycle_info(*, db_session, job_in: JobLifeCycleUpdate) -> Job:

    existing_job = get_by_code(db_session=db_session, code=job_in.code)

    if JobLifeCycleStatus_SEQUENCE[existing_job.life_cycle_status] > JobLifeCycleStatus_SEQUENCE[job_in.life_cycle_status]:
        log.error(
            f"life cycle status {existing_job.life_cycle_status} --> {job_in.life_cycle_status} is not allowed. ")
        return existing_job

    event_txt = f"changed job life cycle status: {existing_job.life_cycle_status} --> {job_in.life_cycle_status}, by: {job_in.update_source}, comment: {job_in.comment} "

    existing_job.life_cycle_status = job_in.life_cycle_status
    existing_job.updated_at = datetime.now()
    existing_job.updated_by = f"life_cycle:{job_in.update_source}"

    db_session.add(existing_job)
    db_session.commit()

    event_service.log(
        db_session=db_session,
        source=job_in.update_source,
        description=event_txt,
        job_id=existing_job.id,
        details={
            "job_code": job_in.code,
            "life_cycle_status": job_in.life_cycle_status,
            "update_source": job_in.update_source,
            "comment": job_in.comment,
        }
    )
    return existing_job

    # zulip send message
    # zulip_dict = get_zulip_client_by_org_id(existing_job.org_id)
    # if zulip_dict:
    #     zulip_core = zulip_dict['client']
    #     zulip_core.update_job_send_message(
    #         existing_job, [existing_job.scheduled_primary_worker] + existing_job.scheduled_secondary_workers)
    # return existing_job


def update(*, db_session, job: Job, job_in: JobUpdate, org_code: str) -> Job:
    tags = []
    for t in job_in.tags:
        tags.append(tag_service.get_or_create(db_session=db_session, tag_in=TagUpdate(**t)))

    scheduled_secondary_workers = []
    if job_in.scheduled_secondary_workers:
        for w in job_in.scheduled_secondary_workers:
            scheduled_secondary_workers.append(
                worker_service.get_by_code(db_session=db_session, code=w.code))
    if job_in.team and job_in.team.code != job.team.code:
        team_obj = team_service.get_by_code(db_session=db_session, code=job_in.team.code)
        job.team = team_obj
    if job_in.location and job_in.location.location_code and job_in.location.location_code != job.location.location_code:
        location_obj = location_service.get_or_create_by_code(
            db_session=db_session, location_in=job_in.location)
        job.location = location_obj
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
            db_session=db_session, code=job_in.scheduled_primary_worker.code)
    if job_in.requested_primary_worker is not None:
        job.requested_primary_worker = worker_service.get_by_code(
            db_session=db_session, code=job_in.requested_primary_worker.code)

    db_session.add(job)
    db_session.commit()
    event_service.log(
        db_session=db_session,
        source="Dispatch Core App",
        description=f"Job ({job_in.code}) is updated {job_in.flex_form_data}",
        job_id=job.id,
    )
    print(f"\033[37;46m\t1: job update succeed {job.code}\033[0m")
    post_job_to_kafka(job=job, message_type=KafkaMessageType.UPDATE_JOB,
                      db_session=db_session, org_code=org_code)

    print(f"\033[37;46m\t2: job psot kafka in succeed {job.code}\033[0m")
    # zulip send message
    if job.planning_status != JobPlanningStatus.UNPLANNED:
        zulip_dict = get_zulip_client_by_org_id(job.org_id)
        if zulip_dict:
            zulip_core = zulip_dict['client']
            zulip_core.update_job_send_message(
                job, [job.scheduled_primary_worker] + job.scheduled_secondary_workers)

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
                participant_role_time_hours * SECONDS_IN_HOUR * get_engagement_multiplier(participant_role.role))

            participant_total_roles_time_seconds += participant_role_time_seconds

        participants_total_response_time_seconds += participant_total_roles_time_seconds

    # we calculate the time spent in job review related activities
    job_review_hours = 0
    if job_review:
        num_participants = len(job.participants)
        job_review_prep = (
            1  # we make the assumption that it takes an hour to prepare the job review
        )
        # we make the assumption that only half of the job participants will attend the 1-hour, job review session
        job_review_meeting = (num_participants * 0.5 * 1)
        job_review_hours = job_review_prep + job_review_meeting

    # we calculate and round up the hourly rate
    hourly_rate = math.ceil(ANNUAL_COST_EMPLOYEE / BUSINESS_HOURS_YEAR)

    # we calculate and round up the job cost
    job_cost = math.ceil(((participants_total_response_time_seconds /
                         SECONDS_IN_HOUR) + job_review_hours) * hourly_rate)

    return job_cost


def uu_init_job_data(*, session: SessionLocal, data_list: list):
    try:
        i = 0
        for update_job in data_list:
            _job_data = get_by_code(db_session=session, code=update_job['code'])
            if _job_data:
                # update
                update_job_new = JobUpdate(**update_job)
                update(db_session=session, job=_job_data, job_in=update_job_new)
            else:
                # add
                create(db_session=session, tags=[], scheduled_secondary_workers=[], **update_job)

            i += 1

        return True if i > 0 else False
    except Exception as e:
        session.rollback()
        return False


def _create_update_job(session, job_dict):
    try:

        _job_data = get_by_code(db_session=session, code=job_dict['code'])
        if _job_data:
            # update
            update_job_new = JobUpdate(**job_dict)
            update(db_session=session, job=_job_data, job_in=update_job_new)
        else:
            # add
            create(db_session=session, tags=[], scheduled_secondary_workers=[], **job_dict)
    except Exception as e:
        session.rollback()
        return False


def multithreading_create_update_job(session: SessionLocal, data_list: list):
    for i in tqdm(data_list):
        _create_update_job(session, i)

    # We can use a with statement to ensure threads are cleaned up promptly
    # try:
    #     with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
    #         print('插入job...')
    #         results = list(tqdm(executor.map(_create_update_job, data_list), total=len(data_list)))
    #     return True
    # except:
    #     return False


def job_callback_token(msg, url):
    """
    call_back
    request post
    """
    param = str(json.dumps(msg))
    res = requests.post(url=url,
                        headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
                            'content-type': "application/json"
                        },
                        data=param)
    res.content.decode('utf-8')
    flag = False
    if res.status_code != 200:
        raise Exception(f"kafka callback:{res.status_code}-{res.reason}")
    else:
        flag = True
    return flag, res.json()



def job_callback(redis_conn, msg, url):
    """
    call_back
    request post
    """
    key = "apms_ipms_token"
    token = ''
    if redis_conn.exists(key) <= 0:
        _msg = {'username': config.CALLBACK_USER_NAME, 'password': config.CALLBACK_PASSWORD}
        call_back_token_url = config.CALLBACK_TOKEN_URL
        state, token_dict = job_callback_token(_msg, call_back_token_url)
        if state:
            redis_conn.set(key, token_dict['token'])
            redis_conn.expire(key, 4 * 60 * 60)
            token = token_dict['token']
        else:
            log.error("get apms_ipms_token error")
    else:
        token = redis_conn.get(key)
        token = token.decode('utf-8')

    param = json.dumps(_init_call_back_data(msg))
    res = requests.post(url=url,
                        headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
                            'content-type': "application/json",
                            'Authorization': 'Bearer ' + token
                        },
                        data=str(param))
    res.content.decode('utf-8')
    flag = False
    data = ''
    if res.status_code != 200:
        if res.status_code == 500:
            data = f"kafka callback:{res.status_code}-{res.text}"
        elif res.status_code == 400:
            data = f"kafka callback:{res.status_code}-{res.text},possible project_id repeat"
    else:
        flag = True
        data = res.json()
    return flag, data
