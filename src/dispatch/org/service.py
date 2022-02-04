from dispatch.database import engine
import logging
from typing import List, Optional
from fastapi.encoders import jsonable_encoder
from dispatch.auth.models import DispatchUser, DispatchUserOrganization, UserRoles
from dispatch.common.utils.encryption import encrypt, decrypt
# from dispatch.config import ANNUAL_COST_EMPLOYEE, BUSINESS_HOURS_YEAR
import copy
from fastapi import Depends
from dispatch.database import get_db
from dispatch.database_util.manage import init_schema

from .models import Organization, OrganizationBase

log = logging.getLogger(__name__)


def get(*, db_session, org_id: int = None, org_code: str = None) -> Optional[Organization]:
    """Returns an job based on the given id."""
    if org_id or org_id == 0:
        return db_session.query(Organization).filter(Organization.id == org_id).first()
    elif org_code:
        return db_session.query(Organization).filter(Organization.code == org_code).first()


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
    id: int,
    team_flex_form_schema: dict = None,
    worker_flex_form_schema: dict = None,
    job_flex_form_schema: dict = None,
    callback_url=None,
    max_nbr_jobs=0,
    max_nbr_teams=0,
    max_nbr_workers=0,
    zulip_is_active=False,
    zulip_site="",
    zulip_user_name="",
    zulip_password="",
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
        id=id,
        code=code,
        team_flex_form_schema=team_flex_form_schema,
        worker_flex_form_schema=worker_flex_form_schema,
        job_flex_form_schema=job_flex_form_schema,
        callback_url=callback_url,
        max_nbr_jobs=max_nbr_jobs,
        max_nbr_teams=max_nbr_teams,
        max_nbr_workers=max_nbr_workers,
        zulip_password=zulip_password,
        zulip_is_active=zulip_is_active,
        zulip_user_name=zulip_user_name,
        zulip_site=zulip_site,
    )
    organization = init_schema(engine=engine, organization=org)

    return organization


def update(*, db_session, org: Organization, org_in: OrganizationBase) -> Organization:
    flag = True
    try:
        decrypt(org_in.zulip_password)
    except Exception as e:
        flag = False
    zulip_password = bytes(org_in.zulip_password,
                           "utf-8") if flag else bytes(encrypt(org_in.zulip_password), "utf-8")
    update_data = org_in.dict(exclude={"max_nbr_jobs", "max_nbr_workers", "max_nbr_teams", "zulip_password"}
                              )

    for field in update_data.keys():
        setattr(org, field, update_data[field])
    org.zulip_password = zulip_password
    db_session.add(org)
    db_session.commit()
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
):
    """Adds a user to an organization."""
    db_session.add(
        DispatchUserOrganization(
            dispatch_user_id=dispatch_user_id, organization_id=organization_id, role=role, team_id=team_id
        )
    )
    db_session.commit()
