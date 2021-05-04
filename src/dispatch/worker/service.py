import json

# import random
from datetime import datetime, timedelta
from typing import List, Optional

import holidays
import pandas as pd
from fastapi.encoders import jsonable_encoder

from dispatch.config import INCIDENT_PLUGIN_CONTACT_SLUG

from dispatch.location import service as location_service
from dispatch.location.models import Location
from dispatch.plugin import service as plugin_service
from dispatch.plugins.base import plugins
from dispatch.team import service as team_service
from dispatch import  config

from .models import Worker, WorkerCreate, WorkerUpdate


def resolve_user_by_code(code):
    """Resolves a user's details given their code."""
    p = plugins.get(INCIDENT_PLUGIN_CONTACT_SLUG)
    return p.get(code)


def get(*, db_session, worker_id: int) -> Optional[Worker]:
    """Returns an worker given an worker id."""
    return db_session.query(Worker).filter(Worker.id == worker_id).one_or_none()


def get_by_code(*, db_session, code: str) -> Optional[Worker]:
    """Returns an worker given an worker code address."""
    return db_session.query(Worker).filter(Worker.code == code).one_or_none()

# def get_jobs_by_worker_day(*, db_session, worker_code: str, working_day:str) -> Optional[Worker]:
#     """Returns an worker given an worker code address."""
#     return db_session.query(Worker).filter(Worker.code == code).one_or_none()

def get_all(*, db_session) -> List[Optional[Worker]]:
    """Returns all workers."""
    return db_session.query(Worker)


def get_or_create(*, db_session, code: str, **kwargs) -> Worker:
    """Gets or creates an worker."""
    contact = get_by_code(db_session=db_session, code=code)

    if not contact:
        contact_plugin = plugin_service.get_active(db_session=db_session, plugin_type="contact")
        worker_info = contact_plugin.instance.get(code, db_session=db_session)
        kwargs["code"] = worker_info.get("code", code)
        kwargs["name"] = worker_info.get("fullname", "Unknown")
        kwargs["weblink"] = worker_info.get("weblink", "Unknown")
        worker_in = WorkerCreate(**kwargs)
        contact = create(db_session=db_session, worker_in=worker_in)

    return contact


def create(*, db_session, worker_in: WorkerCreate) -> Worker:
    """Creates an worker."""
    team = team_service.get_by_code(db_session=db_session, code=worker_in.team.code)
    if worker_in.location is not None:
        location_obj = location_service.get_or_create_by_code(
            db_session=db_session, location_in=worker_in.location
        )
    else:
        location_obj = None

    contact = Worker(
        **worker_in.dict(exclude={"flex_form_data","team","location"}),
        team=team,
        location=location_obj,
        flex_form_data = worker_in.flex_form_data
    ) 
    db_session.add(contact)
    db_session.commit()
    return contact


def update(
    *,
    db_session,
    worker: Worker,
    worker_in: WorkerUpdate,
) -> Worker:
    worker_data = jsonable_encoder(worker_in)


    update_data = worker_in.dict(
        skip_defaults=True,
        exclude={"flex_form_data","team","location"},
    )

    team = team_service.get_by_code(db_session=db_session, code=worker_in.team.code)

    location_obj = location_service.get_or_create_by_code(
        db_session=db_session, location_in=worker_in.location
    )

    for field in worker_data:
        if field in update_data:
            setattr(worker, field, update_data[field])

    worker.flex_form_data =  worker_in.flex_form_data 

    worker.team = team
    worker.location = location_obj
    db_session.add(worker)
    db_session.commit()
    return worker


def delete(*, db_session, worker_id: int):
    worker = db_session.query(Worker).filter(Worker.id == worker_id).first()
    worker.terms = []
    db_session.delete(worker)
    db_session.commit()
