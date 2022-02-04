
import json
import logging

# import random
from typing import List, Optional
from xmlrpc.client import boolean

from fastapi import HTTPException
from sqlalchemy.sql.functions import func
from tqdm import tqdm
from fastapi.encoders import jsonable_encoder
from dispatch.auth.models import DispatchUser

from dispatch.config import INCIDENT_PLUGIN_CONTACT_SLUG, SQLALCHEMY_DATABASE_URI
from dispatch.database import SessionLocal

from dispatch.location import service as location_service
from dispatch.plugin import service as plugin_service
from dispatch.plugins.base import plugins
from dispatch.team import service as team_service
from dispatch.auth import service as auth_service

from .models import Worker, WorkerCreate, WorkerUpdate, WorkerCreate

log = logging.getLogger(__name__)


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


def get_by_auth(*, db_session, email: str) -> Optional[Worker]:
    """Returns an worker given an worker code address."""
    return db_session.query(Worker).join(DispatchUser).filter(
        DispatchUser.email == email
    ).first()

    # return db_session.query(Worker,DispatchUser).filter(
    #     Worker.dispatch_user_id == DispatchUser.id).filter(
    #     DispatchUser.email == email
    # ).first() # [0]

def get_by_code_org_id(*, db_session, code: str, org_id: int) -> Optional[Worker]:
    """Returns an worker given an worker code address."""
    return db_session.query(Worker).filter(Worker.code == code, Worker.org_id == org_id).one_or_none()

# def get_jobs_by_worker_day(*, db_session, worker_code: str, working_day:str) -> Optional[Worker]:
#     """Returns an worker given an worker code address."""
#     return db_session.query(Worker).filter(Worker.code == code).one_or_none()


def get_all(*, db_session) -> List[Optional[Worker]]:
    """Returns all workers."""
    return db_session.query(Worker)


def get_by_team(*, team_id: int, db_session) -> List[Optional[Worker]]:
    """Returns all workers."""
    return db_session.query(Worker).filter(Worker.team_id == team_id).all()


def get_by_org_id_count(*, db_session, org_id: int) -> Optional[int]:
    """Returns an job based on the given code."""
    return db_session.query(func.count(Worker.id)).filter(Worker.org_id == org_id).scalar()


def get_count_by_active(*, db_session, is_active: boolean) -> Optional[int]:
    """Returns an job based on the given code."""
    return db_session.query(func.count(Worker.id)).filter(Worker.is_active == is_active).scalar()


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
    flag, msg = _check_business_hour(worker_in.business_hour)
    if flag:
        log.error(f"{worker_in.code} , {msg}")
        raise HTTPException(status_code=400, detail=f"{worker_in.code} , {msg}")
    team = team_service.get_by_code(db_session=db_session, code=worker_in.team.code)
    if worker_in.location is not None:
        worker_in.location.org_id = worker_in.org_id
        location_obj = location_service.get_or_create_by_code(

            db_session=db_session, location_in=worker_in.location)
    else:
        location_obj = None

    if worker_in.dispatch_user:
        u = auth_service.get_by_email(db_session=db_session, email=worker_in.dispatch_user.email)
    else:
        u = None

    contact = Worker(**worker_in.dict(exclude={"flex_form_data", "team", "location", "dispatch_user"}),
                     team=team,
                     location=location_obj,
                     dispatch_user=u,
                     flex_form_data=worker_in.flex_form_data)
    db_session.add(contact)
    db_session.commit()
    return contact


def update(
    *,
    db_session,
    worker: Worker,
    worker_in: WorkerUpdate,
) -> Worker:
    flag, msg = _check_business_hour(worker_in.business_hour)
    if flag:
        log.error(f"{worker_in.code} , {msg}")
        raise HTTPException(status_code=400, detail=f"{worker_in.code} , {msg}")

    update_data = worker_in.dict(
        exclude={"flex_form_data", "team", "location", "dispatch_user"},
    )
    if worker.team.code != worker_in.team.code:
        team = team_service.get_by_code(db_session=db_session, code=worker_in.team.code)
        worker.team = team

    if worker_in.location and (not worker.location or worker_in.location.location_code != worker.location.location_code):
        location_obj = location_service.get_or_create_by_code(
            db_session=db_session, location_in=worker_in.location)
        worker.location = location_obj

    if worker_in.dispatch_user and (
        (worker.dispatch_user is None)
        or
        (worker.dispatch_user.email != worker_in.dispatch_user.email)
    ):
        u = auth_service.get_by_email(db_session=db_session, email=worker_in.dispatch_user.email)
        worker.dispatch_user = u

    for field, field_value in update_data.items():
        setattr(worker, field, field_value)

    worker.flex_form_data = worker_in.flex_form_data
    db_session.add(worker)
    db_session.commit()
    return worker


def delete(*, db_session, worker_id: int):
    db_session.query(Worker).filter(Worker.id == worker_id).delete()
    db_session.commit()


def uu_init_worker_data(*, session: SessionLocal, data_list: list, flag=False):
    try:
        i = 0
        if flag:
            print('插入worker...')
            for worker_data in tqdm(data_list):
                _data = get_by_code(db_session=session, code=worker_data.code)
                if _data:
                    # update
                    update_worker_new = WorkerUpdate(**worker_data.__dict__)
                    update(db_session=session, worker=_data, worker_in=update_worker_new)
                else:
                    # add
                    create_worker = WorkerCreate(**worker_data.__dict__)
                    create(db_session=session, worker_in=create_worker)

                i += 1

            return True if i > 0 else False
        else:
            for worker_data in data_list:
                _data = get_by_code(db_session=session, code=worker_data.code)
                if _data:
                    # update
                    update_worker_new = WorkerUpdate(**worker_data.__dict__)
                    update(db_session=session, worker=_data, worker_in=update_worker_new)
                else:
                    # add
                    create_worker = WorkerCreate(**worker_data.__dict__)
                    create(db_session=session, worker_in=create_worker)

                i += 1

            return True if i > 0 else False
    except Exception as e:
        return False


def _check_business_hour(business_hour):
    flag = False
    msg = 'business_hour key error,'
    for week_day_code in [
        "sunday",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
    ]:
        if week_day_code not in business_hour:
            msg += week_day_code
            flag = True
    return flag, msg


def check_zulip_user_id(*, db_session, zulip_user_id: int, team_id: int):
    all_worker = get_by_team(db_session=db_session, team_id=team_id)
    flag = True
    worker_code = ''
    for worker in all_worker:
        user_id = worker.flex_form_data.get('zulip_user_id', None)
        if user_id == zulip_user_id:
            flag = False
            worker_code = worker.code
            break
    return flag, worker_code
