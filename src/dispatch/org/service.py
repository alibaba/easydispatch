from dispatch.database import engine
import logging
from sqlalchemy import text

from typing import List, Optional
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from dispatch.auth.models import DispatchUser, DispatchUserOrganization, UserRoles
from dispatch.common.utils.encryption import encrypt, decrypt
# from dispatch.config import ANNUAL_COST_EMPLOYEE, BUSINESS_HOURS_YEAR
import copy
from fastapi import Depends, HTTPException
from dispatch.database import get_db
from dispatch.database_util.manage import init_schema

from .models import Organization, OrganizationBase, OrganizationStatusUpdate
from .enums import OrganizationType
from dispatch.database_util.org_config import DEFAULT_ORG_SETTING

log = logging.getLogger(__name__)


def get(*, db_session, org_id: int = None, org_code: str = None) -> Optional[Organization]:
    """Returns an job based on the given id."""
    if org_id or org_id == 0:
        return db_session.query(Organization).filter(Organization.id == org_id).one_or_none()
    elif org_code:
        return db_session.query(Organization).filter(Organization.code == org_code).one_or_none()

def get_list(*, db_session, org_id: int = None, org_code: str = None) -> List[Optional[Organization]]:
    """Returns an job based on the given id."""
    if org_id or org_id == 0:
        return db_session.query(Organization).filter(Organization.id == org_id).all()
    elif org_code:
        return db_session.query(Organization).filter(Organization.code == org_code).all()


def get_all(*, db_session) -> List[Optional[Organization]]:
    """Returns all jobs."""

    return db_session.query(Organization)


def create(
    *,
    db_session,
    code: str, 
    org_type: str = OrganizationType.DEFAULT,
    org_setting: str =DEFAULT_ORG_SETTING,
    team_flex_form_schema: dict = None,
    worker_flex_form_schema: dict = None,
    job_flex_form_schema: dict = None,
    order_flex_form_schema: dict = None,

    callback_url=None,
    callback_is_active = False,
    max_nbr_jobs=0,
    max_nbr_teams=0,
    max_nbr_workers=0,
    zulip_is_active=False,
    zulip_site="",
    zulip_user_name="",
    zulip_password="",
    msg_template={},
    work_calendar={},
    planner_code = "single_planner",
    default_team_flex_form_data={},
    default_worker_flex_form_data={},
    default_job_flex_form_data={},
    default_order_flex_form_data={},
) -> Organization:

    # We create the job
    flag = True
    try:
        decrypt(zulip_password)
    except Exception as e:
        flag = False
    zulip_password = bytes(zulip_password,
                           "utf-8") if flag else bytes(encrypt(zulip_password), "utf-8")

    org = Organization(
        # id=id,
        code=code,
        org_type=org_type,
        org_setting=org_setting,
        team_flex_form_schema=team_flex_form_schema,
        worker_flex_form_schema=worker_flex_form_schema,
        job_flex_form_schema=job_flex_form_schema,
        msg_template=msg_template,
        work_calendar=work_calendar,
        callback_url=callback_url,
        callback_is_active=callback_is_active,
        max_nbr_jobs=max_nbr_jobs,
        max_nbr_teams=max_nbr_teams,
        max_nbr_workers=max_nbr_workers,
        zulip_password=zulip_password,
        zulip_is_active=zulip_is_active,
        zulip_user_name=zulip_user_name,
        zulip_site=zulip_site,
        order_flex_form_schema=order_flex_form_schema,
    )
    db_session.add(org)
    db_session.commit()

    organization = init_schema(engine=engine, organization=org, planner_code=planner_code)
    org_db = get(db_session=db_session, org_code = code)

    return org_db

org_columns_forbidden_update = {
    "code", "org_type", 
    "max_nbr_jobs", "max_nbr_workers", "max_nbr_teams", 
    "team_flex_form_schema",
    "org_setting",} # "zulip_password"
from sqlalchemy.orm.attributes import flag_modified
   
def update(*, db_session, org: Organization, org_in: OrganizationBase, current_role = UserRoles.OWNER) -> Organization:
    flag = True
    try:
        decrypt(org_in.zulip_password)
    except Exception as e:
        flag = False
    zulip_password = bytes(org_in.zulip_password,
                           "utf-8") if flag else bytes(encrypt(org_in.zulip_password), "utf-8")

    if current_role == UserRoles.SYSTEM:
        skip_columns = {}
    else:
        skip_columns = org_columns_forbidden_update
    update_data = org_in.dict(exclude=skip_columns)

    for field in update_data.keys():
        setattr(org, field, update_data[field])
    org.zulip_password = zulip_password

    org_setting = copy.deepcopy(org.org_setting)
    org_setting["default_worker_flex_form_data"] = org_in.default_worker_flex_form_data
    org_setting["default_job_flex_form_data"] = org_in.default_job_flex_form_data
    org_setting["default_order_flex_form_data"] = org_in.default_order_flex_form_data
    if current_role == UserRoles.SYSTEM:
        org_setting["default_team_flex_form_data"] = org_in.default_team_flex_form_data
    setattr(org, "org_setting", org_setting)
    flag_modified(org, "org_setting")

    db_session.add(org)
    db_session.commit()
    return org


def update_status(*, db_session, org: Organization, org_in: OrganizationStatusUpdate) -> Organization:
    update_data = org_in.dict(exclude=org_columns_forbidden_update)
    for field in update_data.keys():
        setattr(org, field, update_data[field])
    db_session.add(org)
    # db_session.commit()
    return org


def delete(*, db_session, org_id: int):

    ret = db_session.query(Organization).filter(Organization.id == org_id).delete()
    db_session.commit()
    return ret


def add_user(
    *,
    db_session,
    dispatch_user_id: int,
    organization_id: int,
    role: UserRoles = UserRoles.WORKER,
    team_id: int,
    worker_code: str,
):
    """Adds a user to an organization."""
    db_session.add(
        DispatchUserOrganization(
            dispatch_user_id=dispatch_user_id, 
            organization_id=organization_id, 
            role=role, team_id=team_id,
            worker_code=worker_code
        )
    )
    db_session.commit()


def verify_status(*,db_session:Session,org_id:int) ->Optional[Organization]:
    org = db_session.query(Organization).filter(Organization.id==org_id).first()
    if org:
        if org.organization_status == "3":
            raise HTTPException(status_code=400, detail="Organization is invalid")
        
def exist_schema(schema_name):
    with engine.connect() as connection:
        # 执行SQL查询检查schema是否存在
        result = connection.execute(text(f"SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname = '{schema_name}')"))
        # 获取查询结果
        return  result.scalar()
      