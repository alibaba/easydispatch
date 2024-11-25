
from datetime import datetime
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
from dispatch.cloudmarket.worker_event.models import WorkerEvent

from dispatch.config import SQLALCHEMY_DATABASE_URI
from dispatch.database import SessionLocal

from dispatch.location import service as location_service
from dispatch.location.models import Location
from dispatch.plugin import service as plugin_service
from dispatch.plugins.base import plugins
from dispatch.team import service as team_service
from dispatch.auth import service as auth_service

from .models import Worker, WorkerCreate, WorkerUpdate, WorkerCreate
from dispatch.event import service as event_service

log = logging.getLogger(__name__)

def get(*, db_session, code: str) -> Optional[Worker]:
    """Returns an worker given an worker code."""
    return get_by_code(db_session=db_session, code=code)

def get_by_code(*, db_session, code: str) -> Optional[Worker]:
    """Returns an worker given an worker code address."""
    return db_session.query(Worker).filter(Worker.code == code).one_or_none()

def get_by_code_list(*, db_session, code_list: list) -> List[Optional[Worker]]:
    """Returns an worker given an worker code address."""
    return db_session.query(Worker).filter(Worker.code.in_(code_list)).all()


def getworker_name_by_code_list(*, db_session, code_list: list) -> List[Optional[Worker]]:
    """Returns an worker given an worker code address."""
    if code_list:
        return db_session.query(Worker.code , Worker.name,Worker.flex_form_data).filter(Worker.code.in_(code_list)).all()
    else:
        return db_session.query(Worker.code , Worker.name,Worker.flex_form_data).all()



def get_by_auth(*, db_session, email: str) -> Optional[Worker]:
    """Returns an worker given an worker code address."""
    return db_session.query(Worker).join(DispatchUser).filter(
        DispatchUser.email == email
    ).first()
    
    
def get_by_dispatch_user_id(*, db_session, dispatch_user_id: int) -> Optional[Worker]:
    """Returns an worker given an worker code address."""
    return db_session.query(Worker).filter(
        Worker.dispatch_user_id == dispatch_user_id).first() 


    # return db_session.query(Worker,DispatchUser).filter(
    #     Worker.dispatch_user_id == DispatchUser.id).filter(
    #     DispatchUser.email == email
    # ).first() # [0]

def get_by_code_org_id(*, db_session, code: str, org_id: int) -> Optional[Worker]:
    """Returns an worker given an worker code address."""
    return db_session.query(Worker).filter(Worker.code == code, Worker.org_id == org_id).one_or_none()

def get_by_org_id(*, db_session,  org_id: int) -> Optional[Worker]:
    """Returns an worker given an worker code address."""
    return db_session.query(Worker).filter( Worker.org_id == org_id).all()


def get_all(*, db_session) -> List[Optional[Worker]]:
    """Returns all workers."""
    return db_session.query(Worker)


def get_all_active_in_team(*, db_session, team_id: int, worker_code_list = None):
    """Returns all workers."""
    w_query = db_session.query(
        Worker.code,
        Worker.flex_form_data,
        Worker.business_hour,
        Worker.geo_longitude, #.label("worker_longitude"),
        Worker.geo_latitude, #.label("worker_latitude"),
        Worker.shift_start_datetime,
        Worker.is_shift_started,
        Worker.shift_duration_minutes,
        Worker.is_active,
        # ).outerjoin(Location, Worker.location_code==Location.code
        ).filter(Worker.team_id == team_id
        ).filter(Worker.is_active == True
    )
    if worker_code_list:
        w_query=w_query.filter(Worker.code.in_(worker_code_list))
    
    return w_query.all()



def get_by_team(*, team_id: int, db_session) -> List[Optional[Worker]]:
    """Returns all workers."""
    return db_session.query(Worker).filter(Worker.team_id == team_id).all()


def get_by_org_id_count(*, db_session, org_id: int) -> Optional[int]:
    """Returns an job based on the given code."""
    return db_session.query(func.count(Worker.code)).filter(Worker.org_id == org_id).scalar()


def get_count_by_active(*, db_session, is_active: boolean) -> Optional[int]:
    """Returns an job based on the given code."""
    return db_session.query(func.count(Worker.code)).filter(Worker.is_active == is_active).scalar()

def get_or_create(*, db_session, code: str, **kwargs) -> Worker:
    """Gets or creates an worker."""
    log.warning(f"should not call get_or_create on worker {code}")
    worker = get_by_code(db_session=db_session, code=code)

    if not worker:
        contact_plugin = plugin_service.get_active(db_session=db_session, plugin_type="worker")
        worker_info = contact_plugin.instance.get(code, db_session=db_session)
        kwargs["code"] = worker_info.get("code", code)
        kwargs["name"] = worker_info.get("fullname", "Unknown")
        kwargs["weblink"] = worker_info.get("weblink", "Unknown")
        worker_in = WorkerCreate(**kwargs)
        worker = create(db_session=db_session, worker_in=worker_in)

    return worker


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
        if worker_in.geo_longitude is None or worker_in.geo_latitude is None:
            raise HTTPException(status_code=400, detail=f"longitude/latitude must be specified if there is no Location code ")
        location_obj = None
    user_email = None
    u=None
    if worker_in.dispatch_user:
        u = auth_service.get_by_email(db_session=db_session, email=worker_in.dispatch_user.email)
        user_email = u.email

    if worker_in.assigned_locations:
        assigned_locations = [location_service.get_or_create_by_code(
        db_session=db_session, location_in=_c) for _c in worker_in.assigned_locations]
        worker = Worker(**worker_in.dict(exclude={"flex_form_data", "team",   "dispatch_user", "assigned_locations"}),
                    team=team,
                    location=location_obj,
                    dispatch_user=u,
                    flex_form_data=worker_in.flex_form_data, 
                    assigned_locations = assigned_locations
                )
    else:
    
        worker = Worker(**worker_in.dict(exclude={ # , "update_location_flag"
            "location", "flex_form_data", "team", "dispatch_user", "assigned_locations"
            }),
            team=team,
            location=location_obj,
            dispatch_user=u,
            flex_form_data=worker_in.flex_form_data, 
        )
    db_session.add(worker)
    db_session.commit()
    now_time = datetime.now()
    
    
    # shift_start_datetime 温超项目 不用这个字段了
    event_service.log_worker_event(
        db_session=db_session,
        worker_code = worker_in.code,
        source=user_email,
        started_at=now_time,
        ended_at=now_time,  
        description="created",   
        details = json.dumps( worker_in.dict(exclude={"team", "location", "dispatch_user", "assigned_locations","shift_start_datetime"})  )   
    )
    db_session.commit()
    return worker


def update_business_hour(
    db_session,
    worker_code,
    business_hour
) -> Worker:
    
    
    worker = get(db_session=db_session, code=worker_code)
    if not worker:
        raise HTTPException(status_code=404, detail="The worker with this id does not exist.")

    worker.business_hour = business_hour
    db_session.add(worker)
    db_session.commit()
    return worker


def update(
    *,
    db_session,
    worker: Worker,
    worker_in: WorkerUpdate,
) -> Worker:
    flag, msg = _check_business_hour(worker_in.business_hour)
    if flag:
        log.error(f"{worker_in.code} , {msg}")
        raise HTTPException(status_code=400, detail=f"Failed when checking business_hour for {worker_in.code} , {msg}")

    update_data = worker_in.dict(
        exclude={"flex_form_data", "team", "location", "dispatch_user", "assigned_locations"},
    )
    if not worker.team or worker.team.code != worker_in.team.code:
        team = team_service.get_by_code(db_session=db_session, code=worker_in.team.code)
        worker.team = team

    if worker_in.location and (not worker.location or worker_in.location.code != worker.location.code):
        location_obj = location_service.get_or_create_by_code(
            db_session=db_session, location_in=worker_in.location)
        worker.location = location_obj

    if worker_in.assigned_locations:
        worker.assigned_locations = [location_service.get_or_create_by_code(
            db_session=db_session, location_in=_c) for _c in worker_in.assigned_locations]
    else:
        worker.assigned_locations = []
    if worker_in.dispatch_user and (
        (worker.dispatch_user is None)
        or
        (worker.dispatch_user.email != worker_in.dispatch_user.email)
    ):
        u = auth_service.get_by_email(db_session=db_session, email=worker_in.dispatch_user.email)
        worker.dispatch_user = u

    if not worker_in.dispatch_user and worker.dispatch_user :
         worker.dispatch_user = None
    for field, field_value in update_data.items():
        setattr(worker, field, field_value)

    worker.flex_form_data = worker_in.flex_form_data
    db_session.add(worker)
    db_session.commit()
    return worker


def delete(*, db_session, code: str):
    db_session.query(WorkerEvent).filter(WorkerEvent.worker_code == code).delete()
    db_session.query(Worker).filter(Worker.code == code).delete()
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

# ########
# Used for Env


    # def get_env_jobs(self, 
    #     start_datetime, 
    #     end_datetime, 
    #     worker_code= None, 
    #     include_unplanned=False,
    #     include_inplanning=True,
    # ): 
    #     start_datetime = self.env_start_datetime
    #     end_datetime = self.env_start_datetime + timedelta(days=self.config["nbr_of_days_planning_window"])
    #     return self.get_jobs_worker_days( 
    #         start_datetime = start_datetime, 
    #         end_datetime = end_datetime, 
    #         worker_code = worker_code, 
    #         include_unplanned=include_unplanned,
    #         include_inplanning=include_inplanning,
    #         # include_finished = False,
    #     )


# def get_workers(self, worker_code_list=[] ):
#     # TODO, add throttling, local cache for 1 minutes.
#     return 



from dispatch.auth.models import DispatchUser, UserRegister, UserRoles

def create_dipatch_core_user(db_session , worker_in,org_data,team):
    regist_flag = worker_in.flex_form_data.get("regist_default_account", False)
    mobile_phone = worker_in.flex_form_data.get("mobile_phone", None)
    login_password = worker_in.flex_form_data.get("login_password", mobile_phone)
    worker_role = worker_in.flex_form_data.get("worker_role", UserRoles.WORKER)
    if regist_flag and mobile_phone:
        mobile_phone = str(mobile_phone)
        user_data = auth_service.get_by_email(db_session=db_session, email=mobile_phone)
        if user_data:
            auth_service.update_email_password(db_session=db_session, user_id=user_data.id, email=mobile_phone,password=login_password , user_data=user_data)
        else:
            user = UserRegister(
                email=mobile_phone,
                password=login_password,
                role=worker_role,
                org_id=org_data.id,
                org_code=org_data.code,
                en_code=None,
                is_active=True,
                is_org_owner=True,
                is_team_owner=True,
                default_team_id=team.id,
                import_sample_data=False,
            )
        in_user = auth_service.create(db_session=db_session, user_in=user)
        worker_in.dispatch_user = in_user
        
