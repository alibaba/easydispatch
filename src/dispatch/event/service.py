import datetime
import logging

from uuid import uuid4

from typing import List, Optional

from fastapi.encoders import jsonable_encoder

from sqlalchemy.dialects.postgresql import UUID

from dispatch.cloudmarket.instance import service as instance_service
from dispatch.cloudmarket.mearsurement import service as mearsurement_service
from ..cloudmarket.sku import service as sku_service

from dispatch.cloudmarket.job_event.models import JobEvent
from dispatch.cloudmarket.worker_event.models import WorkerEvent

from dispatch.cloudmarket.mearsurement.models import Mearsurement


logger = logging.getLogger(__name__)

'''
def get(*, db_session, event_id: int) -> Optional[Event]:
    """
    Get an event by id.
    """
    return db_session.query(Event).filter(Event.id == event_id).one_or_none()


def get_by_uuid(*, db_session, uuid: UUID) -> Optional[Event]:
    """
    Get an event by uuid.
    """
    return db_session.query(Event).filter(Event.uuid == uuid).one_or_none()


def get_by_job_code(*, db_session, job_code: str) -> List[Optional[Event]]:
    """
    Get events by job id.
    """
    return db_session.query(Event).filter(Event.job_code == job_code)


def get_by_job_code_and_source(*, db_session, job_code: str, source: str) -> List[Optional[Event]]:
    """
    Get events by job id and source.
    """
    return db_session.query(Event).filter(Event.job_code == job_code).filter(Event.source == source)


def get_by_job_code_and_worker_code(
    *, db_session, job_code: str, worker_code: str
) -> List[Optional[Event]]:
    """
    Get events by job id and worker id.
    """
    return db_session.query(Event).filter(Event.job_code == job_code).filter(Event.source == worker_code)


def get_all(*, db_session) -> List[Optional[Event]]:
    """
    Get all events.
    """
    return db_session.query(Event)


def create(*, db_session, event_in: EventCreate) -> Event:
    """
    Create a new event.
    """
    event = Event(**event_in.dict())
    db_session.add(event)
    db_session.commit()
    return event


def update(*, db_session, event: Event, event_in: EventUpdate) -> Event:
    """
    Updates an event.
    """
    event_data = jsonable_encoder(event)
    update_data = event_in.dict(skip_defaults=True)

    for field in event_data:
        if field in update_data:
            setattr(event, field, update_data[field])

    db_session.add(event)
    db_session.commit()
    return event


def delete(*, db_session, event_id: str):
    """
    Deletes an event
    """
    event = db_session.query(Event).filter(Event.id == event_id).first()
    db_session.delete(event)
    db_session.commit()
'''


def log_job_event(
    db_session,
    source: str,
    description: str, 
    job_code: str,
    planning_status: str = 'U',
    started_at: datetime = None,
    ended_at: datetime = None,
    details: dict = None,
    flex_form_data: dict = None,
    job = None
) -> JobEvent:
    """
    Logs an event
    """
    # # TODO, temp block
    # return
    uuid = uuid4()

    if not started_at:
        started_at = datetime.datetime.utcnow()

    if not ended_at:
        ended_at = started_at


    logger.info(f"{source}: {description}")


    # 改造 event拆分为 worker_event 和job_event

    job_event = JobEvent()
    job_event.uuid = uuid
    job_event.started_at = started_at
    job_event.ended_at = ended_at
    job_event.source = source
    if job_event.source == "Unknown":
        job_event.source = "Auto Planner"
    job_event.description = description
    job_event.details =  details
    job_event.job_code = job_code
    job_event.planning_status = planning_status
    job_event.flex_form_data = flex_form_data
    job_event.job_execution_time = datetime.datetime.now()
    db_session.add(job_event)
    db_session.commit()

    # 如果该job执行成功，判断是否来自云市场，如果是则再次添加job记录表
    if job and job.planning_status == "I":
        instance = instance_service.get_by_organization_id(db_session=db_session,organization_id=job.org_id)

        if instance:
            #TODO 添加mearsurement表
            sku = sku_service.get_by_sku_id(db_session=db_session,sku_id=instance.sku_id)
            mearsurement = Mearsurement()
            mearsurement.instance_id = instance.instance_id
            mearsurement.fk_organization_id = instance.fk_organization_id
            mearsurement.sku_id = instance.sku_id
            mearsurement.sku_type =sku.sku_payment_type if sku else ''
            mearsurement.job_code = job_code 
            mearsurement.job_name = job.name
            mearsurement.job_type = job.job_type
            mearsurement.planning_status = job.planning_status
            mearsurement.planner_execution_time = datetime.datetime.now()
            mearsurement_service.add(db_session = db_session,mearsurement=mearsurement)


    return job_event


def log_worker_event(
    db_session,
    source: str,
    description: str, 
    worker_code: str = None,
    started_at: datetime = None,
    ended_at: datetime = None,
    details: dict = None,

) -> WorkerEvent:
    """
    Logs an event
    """
    uuid = uuid4()

    if not started_at:
        started_at = datetime.datetime.utcnow()

    if not ended_at:
        ended_at = started_at


    logger.info(f"{source}: {description}")


    worker_event = WorkerEvent(
        worker_code = worker_code,
        uuid = uuid,
        started_at = started_at,
        ended_at = ended_at,
        source = source,
        description = description,
        details = details,
    )
    db_session.add(worker_event)
    db_session.commit()
    return worker_event
