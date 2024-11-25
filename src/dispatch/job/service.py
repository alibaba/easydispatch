from dispatch.auth.models import DispatchUser
from dispatch.database_util.service import apply_model_specific_filters
from dispatch.delivery_info.models import DeliveryInfo
from dispatch.order.models import Order
# from dispatch.zulip_server.core import get_zulip_client_by_org_id
import traceback
from dispatch.org import service as orgService
from dispatch.plugins.kandbox_planner.env.env_enums import KandboxPlannerPluginType
from dispatch.planner_plugin import service as service_plugin_service
from dispatch.logs import service as logService
from fastapi import HTTPException
import logging
from sqlalchemy import inspect
import sqlalchemy.sql.expression
from sqlalchemy.sql.functions import func
from dispatch.logs.models import LogCreate
# from dispatch.plugins.kandbox_planner.data_adapter.kafka_adapter import KafkaAdapter
import math
from tqdm import tqdm
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi.encoders import jsonable_encoder
import shortuuid

# ANNUAL_COST_EMPLOYEE, BUSINESS_HOURS_YEAR,
from dispatch.config import ENV_POST_KAFKA, FIVE_GMAX_RUN_FLAG, KANDBOX_DAY_FORMAT_ISO, KANDBOX_DATETIME_FORMAT_ISO, KANDBOX_DATE_FORMAT,ED_JAVA_URL, ED_JAVA_URL_TIMEOUT

from dispatch.database import SessionLocal
from dispatch.event import service as event_service
from dispatch.worker import service as worker_service
from dispatch.worker.models import WorkerCreate
from dispatch.location import service as location_service
from dispatch.location.models import Location, LocationCreate, LocationUpdate
from dispatch.plugin import service as plugin_service
from dispatch.order import service as order_service
from dispatch.plugins.base import plugins
from dispatch.team.models import TeamCreate
from dispatch.cloudmarket.job_event.models import JobEvent
from dispatch.plugins.kandbox_planner.location_adapter.location_service_adapter import LocationAdapterService
from dispatch import config
# from deepdiff import DeepDiff
from dispatch.job_biz import service as job_biz_service

from sqlalchemy import or_, and_
import copy
from fastapi import Depends
from dispatch.database import get_db

from sqlalchemy.orm import Session
from dispatch.team import service as team_service
from .models import Job, JobPlanningStatusUpdate, JobUpdate, JobPlanningInfoUpdate, JobLifeCycleUpdate, JobRelatedUpdate

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
from dispatch.config import SQLALCHEMY_DATABASE_URI

from sqlalchemy.orm import sessionmaker

from dispatch.item_inventory import service as inventory_service  # import  get_by_depot_item_list
from dispatch.depot import service as depot_service
from dispatch.item import service as item_service
from dispatch.item_inventory_event import service as inventory_event_service
from dispatch.job_biz.models import JobBiz
from sqlalchemy import desc ,asc ,text


try:
    from dispatch.contrib.pldt.test_data import _init_call_back_data, test_ipms_data, test_apms_data
except:
    pass

from dispatch.plugins.kandbox_planner.util.kandbox_util import parse_item_str
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from sqlalchemy_filters import apply_pagination
from sqlalchemy.orm.attributes import flag_modified



log = logging.getLogger(__name__)

session = requests.Session()
retry = Retry(connect=3, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount("http://", adapter)
session.mount("https://", adapter)


HOURS_IN_DAY = 24
SECONDS_IN_HOUR = 3600


SHORTUUID = shortuuid.ShortUUID(alphabet="0123456789")


def get(*, db_session, code: str) -> Optional[Job]:
    """Returns an job based on the given id."""
    return db_session.query(Job).filter(Job.code == code).first()

def get_by_code(*, db_session, code: str) -> Optional[Job]:
    """Returns an job based on the given code."""
    return db_session.query(Job).filter(Job.code == code).one_or_none()

def get_by_name(*, db_session, job_name: str) -> Optional[Job]:
    """Returns an job based on the given name."""
    return db_session.query(Job).filter(Job.name == job_name).first()

def get_by_org_id_count(*, db_session, org_id: int) -> Optional[int]:
    """Returns an job based on the given code."""
    return db_session.query(func.count(Job.code)).filter(Job.org_id == org_id).scalar()


def get_all(*, db_session) -> List[Optional[Job]]:
    """Returns all jobs."""
    return db_session.query(Job).all()


def get_by_team(*, team_id: int, db_session) -> List[Optional[Job]]:
    """Returns all jobs."""
    return db_session.query(Job).filter(Job.team_id == team_id).all()


def get_by_team_and_status(
    *, team_id: int, db_session, planning_status_list: list, start_time=any, end_time=any
) -> List[Optional[Job]]:
    """Returns all jobs."""
    return (
        db_session.query(Job)
        .filter(
            Job.team_id == team_id,
            Job.scheduled_start_datetime >= start_time,
            Job.scheduled_start_datetime <= end_time,
            Job.planning_status.in_(planning_status_list),
        )
        .all()
    )

def get_by_worker_and_status(*, db_session, planning_status_list: list, worker_code:str) -> List[Optional[Job]]:
    """Returns all jobs."""
    return db_session.query(Job).filter(Job.scheduled_primary_worker_code == worker_code,  Job.planning_status.in_(planning_status_list)).all()

def get_job_by_worker(*, db_session, worker_code:str) -> List[Optional[Job]]:
    """Returns all jobs."""
    return db_session.query(Job).filter(Job.scheduled_primary_worker_code == worker_code).all()


def get_by_team_and_req_time(
    *, team_id: int, db_session, start_time=any, end_time=any
) -> List[Optional[Job]]:
    """Returns all jobs."""
    return (
        db_session.query(Job)
        .filter(Job.team_id == team_id)
        .filter(
            or_(
                Job.requested_start_datetime == None,
                and_(
                    Job.requested_start_datetime >= start_time,
                    Job.requested_start_datetime < end_time,
                ),
                and_(
                    Job.scheduled_start_datetime >= start_time,
                    Job.scheduled_start_datetime < end_time,
                ),
            )
        )
        .all()
    )


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


def get_planning_status_data(
    *, db_session, planning_status: JobPlanningStatus
) -> List[Optional[Job]]:
    return (
        db_session.query(Job)
        .filter(Job.planning_status == planning_status)
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


def get_all_by_job_date_time(*, db_session, start_time: str, end_time: str) -> List[Optional[Job]]:
    """Returns all jobs with the given job type."""
    return db_session.query(Job).filter(Job.created_at.between(start_time, end_time)).all()

def get_all_by_order_code(*, db_session, order_code: str) -> List[Optional[Job]]:
    """Fetches all OrderJob for a given type."""
    return db_session.query(Job).filter(Job.order_code == order_code).all()


def create(
    *,
    db_session,
    # job_priority: str = None, 
    code: str,
    job_type: str = "visit",
    org_id: str = None,
    org_code: str = None,
    name: str = None,
    planning_status: str,
    # tags: List[dict] = [],
    description: str = None,
    team: TeamCreate,
    location: LocationCreate,
    flex_form_data: dict = None,
    # absence-test: temporary added to test the absence
    requested_primary_worker_code: WorkerCreate = None,
    scheduled_primary_worker_code: WorkerCreate = None,
    actual_start_datetime: datetime = None,
    actual_duration_minutes: float = None,
    actual_worker_code: WorkerCreate = None,
    # absence-test: end
    requested_primary_worker: WorkerCreate = None,
    requested_start_datetime: datetime = None,
    requested_duration_minutes: float = None,
    scheduled_primary_worker: WorkerCreate = None,
    # scheduled_secondary_workers: List[WorkerCreate] = [],
    scheduled_start_datetime: datetime = None,
    scheduled_duration_minutes: float = None,
    auto_planning: bool = True,
    requested_skills: List[str] = [],
    requested_items: List[str] = [],
    life_cycle_status: JobLifeCycleUpdate = None,
    current_user:DispatchUser = None,
    geo_longitude: float = None,
    geo_latitude: float = None,
    order_code: str = None,
    tolerance_start_minutes: float = 0,
    tolerance_end_minutes: float = 0,
    create_virtual_order_predict: bool = False, 
) -> Job:
    """Creates a new job."""

    team_obj = team_service.get_by_code(db_session=db_session, code=team["code"])

    if location is not None:
        if type(location) == dict:
            loc2create = LocationCreate(**location)
        else:
            loc2create = location
        location_obj = location_service.get(
            db_session=db_session,
            code=loc2create.code)
        if location_obj is None:
            location_obj = location_service.create(db_session=db_session, location_in=loc2create)

    else:
        location_obj = None
        if geo_latitude is None or geo_longitude is None:
            return None
        
    # location_obj = location_service.update(
    #     db_session=db_session, location=location_obj, location_in=LocationUpdate(**location)
    # )

    if requested_primary_worker:
        requested_primary_worker = worker_service.get_by_code(
            db_session=db_session, code=requested_primary_worker["code"]
        )
    if scheduled_primary_worker:
        scheduled_primary_worker = worker_service.get_by_code(
            db_session=db_session, code=scheduled_primary_worker["code"])
    # scheduled_secondary_workers_list = []
    # if scheduled_secondary_workers is not None:
    #     for w in scheduled_secondary_workers:
    #         scheduled_secondary_workers_list.append(
    #             worker_service.get_by_code(db_session=db_session, code=w['code']))
    # We create the job
    if requested_skills:
        flex_form_data["requested_skills"] = requested_skills
    if requested_items:
        flex_form_data["requested_items"] = requested_items
    if scheduled_duration_minutes is None:
        scheduled_duration_minutes = requested_duration_minutes
    job = Job(
        code=code,
        order_code=order_code,
        name=name,
        org_id=org_id,
        job_type=job_type,
        description=description,
        planning_status=planning_status,
        # tags=tag_objs,
        flex_form_data=flex_form_data,
        location=location_obj,
        team=team_obj,
        requested_start_datetime=requested_start_datetime,
        requested_duration_minutes=requested_duration_minutes,
        requested_primary_worker=requested_primary_worker,
        scheduled_start_datetime=scheduled_start_datetime,
        scheduled_duration_minutes=scheduled_duration_minutes,
        scheduled_primary_worker=scheduled_primary_worker,
        # scheduled_secondary_workers=scheduled_secondary_workers_list,
        auto_planning=auto_planning,
        requested_skills=requested_skills,
        requested_items=requested_items,
        geo_longitude=geo_longitude,
        geo_latitude=geo_latitude,
        tolerance_start_minutes = tolerance_start_minutes,
        tolerance_end_minutes = tolerance_end_minutes,
    )
    if create_virtual_order_predict:
        return job 


    db_session.add(job)

    if job.job_type == JobType.REPLENISH:
        depot_code = flex_form_data["depot_code"]
        depot = depot_service.get_by_code(db_session=db_session, code=depot_code)

        for item_str in flex_form_data["requested_items"]:
            item_list = parse_item_str(item_str)
            item = item_service.get_by_code(db_session=db_session, code=item_list[0])
            inv = inventory_service.get_by_item_depot(
                db_session=db_session, item_id=item.id, depot_id=depot.id, org_id=team_obj.org_id
            ).one_or_none()
            inv.curr_qty -= item_list[1]
            inv.allocated_qty += item_list[1]
            if inv.curr_qty < 0:
                log.error(
                    f" Not enough inventory for item: {item_list[0]}, depot: {depot_code}, org.id: {team_obj.org_id}"
                )
                continue
            db_session.add(inv)
            inventory_event_service.log(
                db_session=db_session,
                source="Env_Replenish",
                description=f"Allocated {item_list[1]} {item_list[0]} from depot: {depot_code}",
                item_code=item_list[0],
                depot_code=depot_code,
                item_id=item.id,
                depot_id=depot.id,
            )

    db_session.commit()

    log.info(f"added job successfully, code={code}")
    email = current_user.email if current_user else ''
    event_service.log_job_event(
        db_session=db_session,
        job_code = job.code,
        planning_status=job.planning_status,
        source="Dispatch Core App",
        description=f"{email}, Job ({code}) is created, planning_status={planning_status}, requested_start_datetime={requested_start_datetime}",
        job=job,
    )

    # post_job_to_kafka(job=job, message_type=KafkaMessageType.CREATE_JOB,
    #                   db_session=db_session, org_code=org_code)

    # print(f"\033[37;46m\t2:job post kafka in succeed,{code}\033[0m")
    # log.info(f"2:job post kafka in succeed,{code}")

    # zulip send message
    # if job.planning_status != JobPlanningStatus.UNPLANNED:
    #     zulip_dict = get_zulip_client_by_org_id(job.org_id)
    #     if zulip_dict:
    #         zulip_core = zulip_dict["client"]
    #         zulip_core.update_job_send_message(
    #             job, [job.scheduled_primary_worker]
    #         )

    return job


# def post_job_to_kafka(job: Job, message_type, db_session, org_code=None):
#     job_dict = {c.key: getattr(job, c.key) for c in inspect(job).mapper.column_attrs}

#     job_dict["requested_primary_worker_code"] = None
#     if job.requested_primary_worker is not None:
#         job_dict["requested_primary_worker_code"] = job.requested_primary_worker.code
#     job_dict["scheduled_secondary_worker_codes"] = [w.code for w in job.scheduled_secondary_workers]
#     job_dict["location_code"] = job.location.location_code
#     job_dict["geo_longitude"] = job.location.geo_longitude
#     job_dict["geo_latitude"] = job.location.geo_latitude

#     if job.scheduled_primary_worker:
#         job_dict["scheduled_primary_worker_code"] = job.scheduled_primary_worker.code
#     else:
#         job_dict["scheduled_primary_worker_code"] = None

#     kem = KafkaEnvMessage(
#         message_type=message_type,
#         message_source_type=KandboxMessageSourceType.ENV,
#         message_source_code="USER.Web",
#         payload=[job_dict],
#     )
#     if not org_code:
#         org_data = orgService.get(db_session=db_session, org_id=job.team.org_id)
#         org_code = org_data.code
#     topic_name = f"{KandboxMessageTopicType.ENV_WINDOW}.env_{org_code}_{job.team.id}"

#     offset = kafka_server.post_message(topic_name=topic_name, m=kem)
#     job.team.latest_env_kafka_offset = offset
#     db_session.add(job.team)
#     db_session.commit()






def update_life_cycle_info(*, db_session, job_in: JobLifeCycleUpdate, current_user,job: Job=None,flex_form_data: dict =None  ) -> Job:
    if not job:
        job = get_by_code(db_session=db_session, code=job_in.code)

    if not job:
        raise HTTPException(status_code=404, detail="The requested job does not exist.")

    if (
        JobLifeCycleStatus_SEQUENCE[job.life_cycle_status]
        > JobLifeCycleStatus_SEQUENCE[job_in.life_cycle_status]
    ) or (job.life_cycle_status == job_in.life_cycle_status):
        error_msg = f"life cycle status {job.life_cycle_status} --> {job_in.life_cycle_status} is not allowed. {job_in.dict()}"
        log.info(error_msg)
        return job
        # raise HTTPException(
        #     status_code=400,
        #     detail=error_msg,
        # )
    
    event_txt = f"changed job life cycle status: {job.life_cycle_status} --> {job_in.life_cycle_status}, orig_planning:  {job.planning_status}, by: {job_in.update_source}, comment: {job_in.comment} "
    if job_in.life_cycle_status == JobLifeCycleStatus.FINISHED:
        job.planning_status = JobPlanningStatus.FINISHED
    job.life_cycle_status = job_in.life_cycle_status
    job.updated_at = datetime.now()
    job.updated_by = f"life_cycle {job_in.update_source}"

    if  flex_form_data:
        # TODO  , 这里有个bug , json 不生效
        job.flex_form_data.update(flex_form_data)
        flag_modified(job, "flex_form_data")

    db_session.add(job)
    db_session.commit()
    log.info(f"job {job.code} is updated  with {job_in.dict()}  job_dict {job.__dict__}")

    # TODO 2023-03-16 16:00:36 
    # sqlalchemy.exc.ProgrammingError: (psycopg2.ProgrammingError) can't adapt type 'dict'

    event_service.log_job_event(
        db_session=db_session,
        source=job_in.update_source,
        description=event_txt,
        planning_status=job.planning_status,
        job_code=job.code,
        details=None,
        flex_form_data={
            "job_code": job_in.code,
            "life_cycle_status": job_in.life_cycle_status,
            "planning_status": job.planning_status,
            "update_source": job_in.update_source,
            "comment": job_in.comment,
        },
    )

    return job

    # zulip send message
    # zulip_dict = get_zulip_client_by_org_id(existing_job.org_id)
    # if zulip_dict:
    #     zulip_core = zulip_dict['client']
    #     zulip_core.update_job_send_message(
    #         existing_job, [existing_job.scheduled_primary_worker] + existing_job.scheduled_secondary_workers)
    # return existing_job


def update(
    *, db_session, job: Job, job_in: JobUpdate, org_code: str, current_user: DispatchUser = None
) -> Job:

    # job_json = job.__dict__
    # job_in_json = job_in.dict()
    # diff_value = DeepDiff(job_in_json, job_json, ignore_order=True)
    # diff_values_changed = str(diff_value.get("values_changed", ""))
    # other_diff = ""

    # if job.location.code!=job_in.location.code:
    #     other_diff += f"location old value:{job.location.code} new value:{job_in.location.code} "
    # if job.team.code!=job_in.team.code:
    #     other_diff += f"team old value:{job.team.code} new value:{job_in.team.code}  "
    # if job_in.requested_primary_worker:
    #     if job.requested_primary_worker:
    #         if job.requested_primary_worker.code != job_in.requested_primary_worker.code:
    #             other_diff += f"requested_primary_worker old value:{job.requested_primary_worker.code} new value:{job_in.requested_primary_worker.code}  "
    #     else:
    #         other_diff += f"requested_primary_worker add {job_in.requested_primary_worker.code}  "

    # if job_in.scheduled_primary_worker:
    #     if job.scheduled_primary_worker:
    #         if job.scheduled_primary_worker.code != job_in.scheduled_primary_worker.code:
    #             other_diff += f"scheduled_primary_worker old value:{job.scheduled_primary_worker.code} new value:{job_in.scheduled_primary_worker.code}  "
    #     else:
    #         other_diff += f"scheduled_primary_worker add {job_in.scheduled_primary_worker.code}  "
    
    # in_scheduled_secondary_workers_code = [worker.code for worker in job_in.scheduled_secondary_workers] if job_in.scheduled_secondary_workers else []
    # scheduled_secondary_workers_code = [worker.code for worker in job.scheduled_secondary_workers] if job.scheduled_secondary_workers else []

    # if in_scheduled_secondary_workers_code :
    #     if scheduled_secondary_workers_code :
    #         if  scheduled_secondary_workers_code!=in_scheduled_secondary_workers_code:
    #             other_diff += f"scheduled_secondary_workers_code old value:{scheduled_secondary_workers_code} new value:{in_scheduled_secondary_workers_code}  "
    #     else :
    #         other_diff += f"scheduled_secondary_workers_code add {in_scheduled_secondary_workers_code}  "
    # diff_values_changed += other_diff

    # tags = []
    # for t in job_in.tags:
    #     tags.append(tag_service.get_or_create(db_session=db_session, tag_in=TagUpdate(**t)))

    # scheduled_secondary_workers = []
    # if job_in.scheduled_secondary_workers:
    #     for w in job_in.scheduled_secondary_workers:
    #         scheduled_secondary_workers.append(
    #             worker_service.get_by_code(db_session=db_session, code=w.code))
    if job_in.team and job_in.team.code != job.team.code:
        team_obj = team_service.get_by_code(db_session=db_session, code=job_in.team.code)
        job.team = team_obj
    if job_in.location and job_in.location.code and job_in.location.code != job.location.code:
        location_obj = location_service.get_or_create_by_code(
            db_session=db_session, location_in=job_in.location
        )
        job.location = location_obj
        job.geo_latitude = job.location.geo_latitude
        job.geo_longitude = job.location.geo_longitude
    update_data = job_in.dict(
        skip_defaults=True,
        exclude={
            # "tags",
            # "scheduled_secondary_workers",
            "requested_primary_worker",
            "scheduled_primary_worker",
            "team",
            "location",
            # "requested_start_datetime",
        },
    )

    for field in update_data.keys():
        setattr(job, field, update_data[field])

    flag_modified(job, "flex_form_data")
    # job.scheduled_secondary_workers = scheduled_secondary_workers
    # job.tags = tags
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
    email = current_user.email  if current_user else ''
    event_service.log_job_event(
        db_session=db_session,
        source="api",
        description=f"{email} updated job: ({job_in.code})::  {job_in.json()}",
        job_code=job.code,
        planning_status=job_in.planning_status,
    )
    log.info(f"job update successful {job.code}")
    # post_job_to_kafka(job=job, message_type=KafkaMessageType.UPDATE_JOB,
    #                   db_session=db_session, org_code=org_code)

    # print(f"\033[37;46m\t2: job psot kafka in succeed {job.code}\033[0m")
    # zulip send message
    # if job.planning_status != JobPlanningStatus.UNPLANNED:
    #     zulip_dict = get_zulip_client_by_org_id(job.org_id)
    #     if zulip_dict:
    #         zulip_core = zulip_dict["client"]
    #         zulip_core.update_job_send_message(
    #             job, [job.scheduled_primary_worker] ) # + job.scheduled_secondary_workers

    return job


def delete(*, db_session, code: str):
    # TODO: When deleting, respect referential integrity here in the code. Or add cascading deletes
    # in models.py.
    db_session.query(JobEvent).filter(JobEvent.job_code == code).delete()
    db_session.query(Job).filter(Job.code == code).delete()
    db_session.commit()


def uu_init_job_data(*, session: SessionLocal, data_list: list):
    try:
        i = 0
        for update_job in data_list:
            _job_data = get_by_code(db_session=session, code=update_job["code"])
            if _job_data:
                # update
                update_job_new = JobUpdate(**update_job)
                update(db_session=session, job=_job_data, job_in=update_job_new)
            else:
                # add
                create(
                    db_session=session, 
                    # tags=[], 
                    # scheduled_secondary_workers=[], 
                    **update_job)

            i += 1

        return True if i > 0 else False
    except Exception as e:
        session.rollback()
        return False


def _create_update_job(session, job_dict):
    try:

        _job_data = get_by_code(db_session=session, code=job_dict["code"])
        if _job_data:
            # update
            update_job_new = JobUpdate(**job_dict)
            update(db_session=session, job=_job_data, job_in=update_job_new)
        else:
            # add
            create(
                db_session=session, 
                # tags=[], 
                # scheduled_secondary_workers=[], 
                **job_dict)
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
    
def get_first_by_worker_code(*,db_session,worker_code: str)-> object:
    return db_session.query(Job).filter(sqlalchemy.or_(Job.requested_primary_worker_code == worker_code,
                                                       Job.scheduled_primary_worker_code == worker_code)).first()

def get_worker_id(*, db_session, worker_id: int) -> object:
    return (
        db_session.query(Job)
        .filter(
            sqlalchemy.or_(
                Job.requested_primary_worker_id == worker_id,
                Job.scheduled_primary_worker_id == worker_id,
            )
        )
        .all()
    )


def get_team_id(*, db_session, team_id: int) -> object:
    return db_session.query(Job).filter(Job.team_id == team_id).all()


"""
//job/job_biz/job_reschedule
job 修改时间
"""


def job_reschedule(jobBizId, rescheduleTime, user_id, token):

    url = f"{ED_JAVA_URL}/job/job_biz/job_reschedule"
    headers = {"content-type": "application/json", "User-Token": str(user_id), "token": token}
    params = {"jobBizId": jobBizId, "rescheduleTime": str(rescheduleTime), "platform": "pc"}
    response = session.post(url=url, headers=headers, json=params, timeout=ED_JAVA_URL_TIMEOUT)
    try:
        data = response.json()
        if data["result"] != "success":
            log.error(f"EdJavaError: Failed to get job_reschedule: jobBizId {jobBizId} :{data}")
    except KeyError:
        log.error(f"EdJavaError: Failed to get job_reschedule: jobBizId {jobBizId} :{data}")
    return data


"""
/easydispatch/api/v1/job/job_biz/backtosc_job_success
job - 
"""


def callback_backtosc_job_success(job_biz_id, token, user_id):

    url = f"{ED_JAVA_URL}/job/job_biz/backtosc_job_success"
    headers = {"content-type": "application/json", "User-Token": str(user_id), "token": token}
    params = {"jobBizId": job_biz_id}
    # log.info("debugging deployment....")
    response = session.post(url=url, headers=headers, json=params, timeout=ED_JAVA_URL_TIMEOUT)
    try:
        data = response.json()
        if data["result"] != "success":
            log.error(
                f"EdJavaError: Failed to get callback_backtosc_job_success: orderCode {job_biz_id} :{data}"
            )
    except KeyError:
        log.error(
            f"EdJavaError KeyError: Failed to get callback_backtosc_job_success: orderCode {job_biz_id} :{data}"
        )
    except:
        log.error(
            f"EdJavaError others: Failed to get callback_backtosc_job_success: respnose: {data} "
        )
    return data


"""
/easydispatch/api/v1/job/job_biz/job_batch_change_worker
batch change worker
"""
def  job_batch_change_worker(worker_code,dispatch_user_id,job_code_list,user_id,token):

        url = f"{ED_JAVA_URL}/job/job_biz/job_batch_change_worker"
        headers = {"content-type": "application/json","User-Token":str(user_id),"token":token}
        params = {"dispatchUserId":dispatch_user_id,  "worker":worker_code,"fkJobIdList":job_code_list}
        response = session.post(url=url, headers=headers, json=params, timeout=ED_JAVA_URL_TIMEOUT)
        data = None
        try:
            resp_json = response.json()
            if resp_json["result"] != "success":
                log.error(f"EdJavaError: Failed tojob_batch_change_worker: worker_code {worker_code}   :{resp_json}")
            else:
                log.error(f"EdJavaError: job_batch_change_worker is successful: worker_code  {worker_code} :{resp_json}")
            data =  resp_json
        except KeyError:
            log.error(f"EdJavaError: Failed to job_batch_change_worker: worker_code {worker_code} :{resp_json}")
            return None
        return  data


# //job/job_biz/job_algorithm_success
# 排班成功通知
def  job_algorithm_success(fkJobId ,fkWorkerId,scheduled_primary_worker_code,worker_code,startTime,user_id = 1,token = ""):

        url = f"{ED_JAVA_URL}/job/job_biz/job_algorithm_success"
        headers = {"content-type": "application/json","User-Token":str(user_id),"token":token}
        job_params = {
            "fkJobId": fkJobId, "fkWorkerId": fkWorkerId,
            "scheduledPrimaryWorkerId":scheduled_primary_worker_code,
            "worker":worker_code,"startTime":str(startTime)}
        params = {"paramList": [job_params]}
        response = session.post(url=url, headers=headers, json=params, timeout=ED_JAVA_URL_TIMEOUT)
        data = None
        try:
            resp_json = response.json()
            if resp_json["result"] != "success":
                log.error(f"EdJavaError: Failed to get job_algorithm_success: fkJobId {fkJobId} :{resp_json}")
                return None           
            data =  resp_json["data"]
        except KeyError:
            log.error(f"EdJavaError: Failed to get job_algorithm_success: fkJobId {fkJobId} :{resp_json}")
            return None
        return  data


"""
1.获取job可修改时间

"""


def get_reschedule_times(job_biz_id, user_id, token):

    # url = f"{ED_JAVA_URL}/job/job_biz/get_reschedule_times?jobBizId={job_biz_id}"
    url = f"{ED_JAVA_URL}/job/job_biz/get_reschedule_times?jobBizIdList={job_biz_id}"
    headers = {"content-type": "application/json", "User-Token": str(user_id), "token": token}
    response = session.get(url=url, headers=headers, timeout=ED_JAVA_URL_TIMEOUT)
    data = None
    try:
        resp_json = response.json()
        if resp_json["result"] != "success":
            log.error(
                f"EdJavaError: Failed to get get_reschedule_times: job_biz_id {job_biz_id} :{resp_json}"
            )
            return None
        data = resp_json["data"]["list"]
    except KeyError:
        log.error(
            f"EdJavaError: Failed to get get_reschedule_times: job_biz_id {job_biz_id} :{resp_json}"
        )
        return None
    return data


def set_job_related(
    *,
    db_session,
    job: Job,
    job_biz: JobBiz,
    job_related_in: JobRelatedUpdate,
    user_id: int,
    token: str,
):

    """
    update  detail 

    修改时间
    修改状态

    """
    flag = True
    msg = ""

    # 修改时间
    if job_related_in.requested_start_datetime != job.requested_start_datetime:
        try:
            update_job_time = job_reschedule(
                jobBizId=job_biz.id,
                rescheduleTime=job_related_in.requested_start_datetime,
                token=token,
                user_id=user_id,
            )
            if not update_job_time or update_job_time.get("result") == "fail":
                flag = False
                msg = f"error update_job_time  ,jobBizId {job_biz.id},message:{ update_job_time.get('message')} "
        except Exception as e:
            msg = f"error update_job_time  ,jobBizId {job_biz.id} "
            flag = False
            log.error(f"update_job_time error: {str(e)}")
            log.error(f"{msg}")
            log.error(f"EdJavaError: Failed to  set_job_related ,job_code {job.code}, {e}")

    # 修改状态
    if (
        job_biz.job_type == "backToSc"
        and job_related_in.job_biz_job_status == "delivered"
        and job_biz.job_track_status != "delivered"
    ):
        try:
            update_job_time = callback_backtosc_job_success(
                job_biz_id=job_biz.id, token=token, user_id=user_id
            )
            if not update_job_time or update_job_time.get("result") == "fail":
                flag = False
                msg = (
                    msg
                    + f"error callback_backtosc_job_success  ,jobBizId {job_biz.id}, message:{ update_job_time.get('message')} "
                )
        except Exception as e:
            msg = msg + f"error callback_backtosc_job_success  ,jobBizId {job_biz.id} "
            flag = False
            log.error(f"callback_backtosc_job_success error: {str(e)}")
            log.error(f"{msg}")

        job_biz.job_track_status = job_related_in.job_biz_job_status
        # job_biz.problem_reason_code = job_related_in.problem_reason_code

        db_session.add(job_biz)
        db_session.commit()

    return {
        "msg": "succeed" if flag else msg,
        "flag": flag,
    }


def search_filter_paginate_job(
    db_session, 
    worker_code: str, 
    job_track_status: List[str]= None, 
    external_order_code: List[str]= None,
    page: int = 1,
    items_per_page: int = 5,
    current_user=None,
    role=None,
):

    try:
        param = []
        if worker_code:
            param.append(Job.scheduled_primary_worker_code == worker_code)
        if job_track_status:
            param.append(JobBiz.job_track_status.in_(job_track_status))
        if external_order_code:
            param.append(Order.external_order_code.in_(external_order_code))
        query = db_session.query(
            Job,DeliveryInfo.customer_address, DeliveryInfo.customer_zipcode, 
            JobBiz.job_type,JobBiz.job_track_status, Order.external_order_code
            ).outerjoin(JobBiz, Job.code==JobBiz.job_code
            ).outerjoin(Order, JobBiz.fk_order_code==Order.code
            ).outerjoin(DeliveryInfo, Order.code==DeliveryInfo.fk_order_code
            ).filter(*param)
        query = query.filter((Job.is_deleted == None)|(Job.is_deleted == 0))
        query = apply_model_specific_filters(Job, query, current_user, role)

        if items_per_page == -1:
            items_per_page = None
        query, pagination = apply_pagination(query, page_number=page, page_size=items_per_page)
    except sqlalchemy.exc.ProgrammingError as e:
        log.debug(e)
        return {
            "items": [],
            "itemsPerPage": items_per_page,
            "page": page,
            "total": 0,
        }

    return {
        "items": query.all(),
        "itemsPerPage": pagination.page_size,
        "page": pagination.page_number,
        "total": pagination.total_results,
    }


def set_all_job_finish(*, db_session, team_id: int):
    """Returns all jobs with the given job type."""

    jobs = (
        db_session.query(Job)
        .filter(Job.team_id == team_id)
        .filter(Job.planning_status.in_(["I", "P"]))
        .all()
    )
    for job in jobs:
        job.planning_status = "F"
        db_session.add(job)
        db_session.commit()
        log.info(f"{datetime.now()}, updated job {job.code} status to F")







def get_jobs_query_event_absence(
        self, db_session,
        start_datetime, 
        start_minutes=None,
        end_minutes=None,
        today_start_minutes=None,
        worker_code= None
): 
    events_query = db_session.query(
            Job.scheduled_primary_worker_code,
            Job.job_type,
            Job.scheduled_start_datetime,
            Job.scheduled_duration_minutes
        ).filter(Job.scheduled_primary_worker_code == worker_code,
                    Job.job_type == 'event'
                    ).all()
    """
        Get only event from the job with defined working code and start_datetime
        Read job table, find all related events and return the list;
    """
    events_interval = []
    if not events_query:
        events_interval.append([start_minutes, end_minutes])
        return events_interval
    for event in events_query:
        if event.scheduled_start_datetime.date() != start_datetime.date():
            continue

        start_minutes_event = event.scheduled_start_datetime.hour * 60 + event.scheduled_start_datetime.minute + today_start_minutes
        end_minutes_event = start_minutes_event + event.scheduled_duration_minutes
        s1 = start_minutes
        e1 = end_minutes
        s2 = start_minutes_event
        e2 = end_minutes_event
        # 1-2 worktime and event not overlab
        if e1 < s2 or e2 < s1:
            events_interval.append([s1, e1])
        # 3 worktime completely overlab event: interval = s1 to s2 and e2 to e1
        elif s1 < s2 and e1 > e2:
            events_interval.append([s1, s2])
            events_interval.append([e2, e1])
        # 4 event completely overlab event: no working time 
        elif s1 > s2 and e1 < e2:
            continue
        # 5 worktime and event overlab, worktime starts before event and ends before it: interval = s2 to e1
        elif s1 < s2 and e1 < e2:
            events_interval.append([s2, e1])
        # 6 worktime and event overlab, worktime starts after event and ends after it: interval = e2 to e1
        elif s1 > s2 and e1 > e2:
            events_interval.append([e2, e1])
        # 7 worktime and event overlab, worktime starts after event and ends after it: interval = s1 to s2
        elif s1 > s2 and e1 > e2:
            events_interval.append([s1, s2])
            
    return events_interval


def update_planning_info(
    *, db_session, job_in: JobPlanningInfoUpdate, owner_user_id=None, token=None
) -> Job:

    existing_job = get_by_code(db_session=db_session, code=job_in.code)

    existing_job.planning_status = job_in.planning_status
    if job_in.scheduled_start_datetime:
        existing_job.scheduled_start_datetime = job_in.scheduled_start_datetime
    if job_in.scheduled_duration_minutes:
        existing_job.scheduled_duration_minutes = job_in.scheduled_duration_minutes
    if job_in.scheduled_primary_worker_code:
        existing_job.scheduled_primary_worker = worker_service.get_by_code(
            db_session=db_session, code=job_in.scheduled_primary_worker_code
        )

    # if len(job_in.scheduled_secondary_workers) > 0:
    # else:
    #     existing_job.scheduled_secondary_workers = None
    # if job_in.scheduled_secondary_worker_codes:
    #     existing_job.scheduled_secondary_workers = [worker_service.get_by_code(
    #         db_session=db_session, code=_c) for _c in job_in.scheduled_secondary_worker_codes]

    db_session.add(existing_job)
    db_session.commit()

    # if job_in.planning_status != 'U':
    #     order_code = existing_job.flex_form_data.get('order_code', None)
    #     if order_code is not None:
    #         order = order_service.get(db_session=db_session,id = order_code)
            
    #         if order:
    #             worker = worker_service.get_by_code(db_session=db_session, code = job_in.scheduled_primary_worker_code)
    #             order.scheduled_primary_worker_code = worker.code
    #         else:
    #             log.error(f"order id ({order_code}) is set, but failed to find it for job {job_in.code}")

    # db_session.commit()

    # new_plan = (
    #     job_in.planning_status.value,
    #     job_in.scheduled_primary_worker_code,
    #     job_in.scheduled_secondary_worker_codes,
    #     str(job_in.scheduled_start_datetime),
    #     job_in.scheduled_duration_minutes,
    # )
    # message = f"Job ({job_in.code}) is changed to a different plan: {new_plan}"
    # event_service.log_job_event(
    #     db_session=db_session,
    #     source=job_in.update_source,
    #     # .scheduled_start_datetime
    #     description=f"changed planning:  {new_plan}",
    #     job_code=existing_job.code,
    #     details={
    #         "job_code":job_in.code,
    #         "message":message,
    #         "planning_status": str(job_in.planning_status),
    #         "scheduled_primary_worker_code": job_in.scheduled_primary_worker_code,
    #         "scheduled_start_datetime": str(job_in.scheduled_start_datetime),
    #     }
    # )


    # post_job_to_kafka(job=existing_job, message_type=KafkaMessageType.UPDATE_JOB,
    #                   db_session=db_session)

    # zulip send message
    # zulip_dict = get_zulip_client_by_org_id(existing_job.org_id)
    # if zulip_dict:
    #     zulip_core = zulip_dict['client']
    #     zulip_core.update_job_send_message(
    #         existing_job, [existing_job.scheduled_primary_worker] ) # + existing_job.scheduled_secondary_workers

    # try:
    #     # fkJobId ,fkWorkerId,worker_code,startTime 推送给app端
    #     if existing_job.planning_status=='I' and token:
    #         if existing_job.scheduled_primary_worker.dispatch_user_id:
    #             result_call_back_app_api = job_algorithm_success(
    #                 fkJobId = existing_job.id ,
    #                 fkWorkerId =existing_job.scheduled_primary_worker.dispatch_user_id,
    #                 scheduled_primary_worker_code=existing_job.scheduled_primary_worker.code,
    #                 worker_code = existing_job.scheduled_primary_worker.code,
    #                 startTime = existing_job.scheduled_start_datetime,
    #                 token=token)
    #             if not result_call_back_app_api :
    #                 log.error(f"EdJavaError: Failed to job_algorithm_success: job_code {existing_job.code} :{result_call_back_app_api}")
    #         else:
    #             log.info(f"EdJavaError: dispatch_user_id value not present, and not to callback job_algorithm_success: scheduled_primary_worker {existing_job.scheduled_primary_worker.code} not have dispatch_user_id")
    # except Exception as e:
    #     log.error(f"EdJavaError: Failed to job_algorithm_successn: job_code {existing_job.code} :{e}")
    #     return None
        
    return existing_job




def get_jobs_query_by_worker_days(
    db_session, 
    start_datetime, 
    end_datetime, 
    worker_code= None, 
    team_id = None,
    nbr_minutes_backward_unplanned_jobs = 1440,
    include_unplanned=False,
    include_inplanning=True,
    include_finished=False,
    sort_by: List[str] = None,
    descending: List[bool] = None,
    query_str=None
): 
    if ((not include_unplanned) and (not include_inplanning)) and (not include_finished)  :
        log.error(f"get_jobs_query_by_worker_days: wrong condition: {(team_id, include_unplanned, include_inplanning)}")
        return None
    jobs_query = db_session.query(
            Job.code,
            Job.job_type,
            Job.geo_longitude,
            Job.geo_latitude,
            Job.scheduled_primary_worker_code,
            Job.scheduled_start_datetime,
            Job.scheduled_duration_minutes,
            Job.requested_primary_worker_code,
            Job.requested_start_datetime,
            Job.requested_duration_minutes,
            Job.tolerance_end_minutes,
            Job.planning_status,
            Job.requested_items,
            Job.flex_form_data,
            Location.geo_longitude.label("geo_longitude_loc"),
            Location.geo_latitude.label("geo_latitude_loc"), 
        ).outerjoin(Location, Job.location_code == Location.code
        )
    if team_id:
        jobs_query = jobs_query.filter(Job.team_id == team_id) 
    if include_inplanning:
        inplanning_status_list = ['I','P']
    else:
        inplanning_status_list = []
    if include_finished:
        inplanning_status_list.append('F')
    if include_unplanned:
        if include_inplanning:
            jobs_query = jobs_query.filter(or_(
                    Job.requested_start_datetime == None,  # "is None" does not work. 2022-01-12 14:29:13
                    and_(Job.requested_start_datetime >= start_datetime - timedelta(minutes = nbr_minutes_backward_unplanned_jobs ),
                        Job.planning_status == 'U',
                        Job.requested_start_datetime < end_datetime),
                    and_(Job.scheduled_start_datetime >= start_datetime,
                        Job.planning_status.in_(inplanning_status_list),
                        Job.scheduled_start_datetime < end_datetime),
                )
            )
        else:
            jobs_query = jobs_query.filter(or_(
                    and_(Job.requested_start_datetime == None,  # "is None" does not work. 2022-01-12 14:29:13
                        Job.planning_status == 'U',),
                    and_(Job.requested_start_datetime >= start_datetime - timedelta(minutes = nbr_minutes_backward_unplanned_jobs),
                        Job.planning_status == 'U',
                        Job.requested_start_datetime < end_datetime),
                )
            )
    else:
        jobs_query = jobs_query.filter(and_(Job.scheduled_start_datetime >= start_datetime,
                        Job.planning_status.in_(inplanning_status_list),
                        Job.scheduled_start_datetime < end_datetime),
        )
    if query_str:
        # User.name.like('e%')
        jobs_query =  jobs_query.filter(Job.code.like(f"%{str(query_str).strip()}%"))

    if sort_by:
        sort_by_func = desc if descending and descending[0] else asc 
        query_filed= f'Job.{sort_by[0]}'

        jobs_query = jobs_query.order_by(sort_by_func(text(query_filed)))
    else:
        jobs_query = jobs_query.order_by(text("Job.scheduled_start_datetime"))
        
    if worker_code:
        jobs_query = jobs_query.filter(Job.scheduled_primary_worker_code == worker_code)
    return jobs_query

def get_jobs_worker_days(db_session, 
    start_datetime, 
    end_datetime, 
    worker_code, 
    include_unplanned=False,
    include_inplanning=True,
    team_id = None,
    nbr_minutes_backward_unplanned_jobs = 1440,
    # nbr_days_backward = 1,
    # nbr_days_forward = 1,
    include_finished= False
):
    # if start_datetime is None:
    #     start_datetime = datetime.now() - nbr_days_backward

    # if end_datetime is None:
    #     # end_datetime = self.env_decode_from_minutes_to_datetime(self.get_env_planning_horizon_end_minutes())
    #     end_datetime = datetime.now()


    jobs_query = get_jobs_query_by_worker_days(
        db_session,
        start_datetime, 
        end_datetime, 
        worker_code = worker_code, 
        include_unplanned = include_unplanned,
        include_inplanning = include_inplanning,
        team_id = team_id,
        nbr_minutes_backward_unplanned_jobs = nbr_minutes_backward_unplanned_jobs,
        include_finished=include_finished
    )
    jobs = jobs_query.all()
    return jobs



def get_unplanned_jobs(
        db_session, 
        start_dt,end_dt, team_id,
        page_number = 1, items_per_page = 10,
        sort_by: List[str] = None,
        descending: List[bool] = None,
        query_str=None,
        nbr_minutes_backward_unplanned_jobs = 1440,
        
        ):

    empty_result = {
            "items": [],
            "itemsPerPage": items_per_page,
            "page": page_number,
            "total": 0,
        }
    jobs_query = get_jobs_query_by_worker_days(
        db_session = db_session,
        start_datetime = start_dt, 
        end_datetime = end_dt,
        team_id = team_id,
        worker_code = None,
        include_unplanned = True,
        include_inplanning = False,
        sort_by = sort_by, 
        descending=descending,
        query_str=query_str,
        nbr_minutes_backward_unplanned_jobs = nbr_minutes_backward_unplanned_jobs,
    )       
    if jobs_query is None:
        log.error(f"failed to get jobs_query for team_id {team_id}, empty")
        return empty_result



    try:
        query, pagination = apply_pagination(jobs_query, page_number=page_number, page_size=items_per_page)

    except sqlalchemy.exc.ProgrammingError as e:
        log.error(f"failed to apply_pagination for env, {str(e)}")
        return empty_result

    return {
        "items": query.all(),
        "itemsPerPage": pagination.page_size,
        "page": pagination.page_number,
        "total": pagination.total_results,
    }

# def update_job_planning_status(db_session, update_planning_status: str, planning_status: str, team_id: int, start_day:str, end_day, worker_code_list: list):
def update_job_planning_status(db_session,update_job_data: JobPlanningStatusUpdate):

    """
    set_inplanning_to_planned
    """
    filter_params = []
    if update_job_data.worker_code_list:
        filter_params.append(Job.scheduled_primary_worker_code.in_(update_job_data.worker_code_list))
    if update_job_data.start_datetime:
        filter_params.append(Job.scheduled_start_datetime >= update_job_data.start_datetime)
    if update_job_data.start_datetime:
        filter_params.append(Job.scheduled_start_datetime < update_job_data.end_datetime)
    

    jobs_query = db_session.query(Job
                                  ).filter(Job.team_id == update_job_data.team_id,
                                           Job.planning_status == update_job_data.planning_status, 
                                           *filter_params
                                           )
    for job in jobs_query:
        job.planning_status= update_job_data.update_planning_status
        db_session.add(job)
    db_session.commit()