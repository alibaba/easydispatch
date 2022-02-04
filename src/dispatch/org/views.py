

from sqlalchemy.schema import DropSchema
from dispatch.config import redis_pool, redis
from dispatch.database import engine
from sqlalchemy import text
from fastapi import status
import copy
from dispatch.auth import service as authService
from dispatch.job import service as jobService
from dispatch.team import service as teamService
from dispatch.worker import service as workerService
from typing import List
import zulip

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import true
from dispatch import worker
from dispatch.common.utils.encryption import encrypt
from dispatch.job.service import SHORTUUID, get_by_org_id_count
from dispatch.enums import Visibility
from dispatch.auth.models import DispatchUser
from dispatch.auth.service import get_current_user
from dispatch.database import get_db

from dispatch.zulip_server.core import ZulipCore, all_zulip_client_dict, get_api
from dispatch.auth.models import UserRoles
from dispatch.org.models import OrganizationBase, OrganizationBaseRead, OrganizationPagination, OrganizationRegistCode

from dispatch.org.service import add_user, create, delete, get, get_list, update

router = APIRouter()


@router.get("/", response_model=OrganizationBaseRead, summary="Retrieve a list of all jobs.")
def get_orgs(
    db_session: Session = Depends(get_db),
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve a list of all jobs.
    """
    data = get(db_session=db_session, org_id=current_user.org_id, org_code=None)
    if data:
        job_all_count = jobService.get_by_org_id_count(
            db_session=db_session, org_id=current_user.org_id)
        team_all_count = teamService.get_by_org_id_count(
            db_session=db_session, org_id=current_user.org_id)
        worker_all_count = workerService.get_by_org_id_count(
            db_session=db_session, org_id=current_user.org_id)
        data = OrganizationBaseRead(**data.__dict__)
        data.worker_count = worker_all_count
        data.team_count = team_all_count
        data.job_count = job_all_count
    return data


@router.get("/id/{org_id}", response_model=OrganizationBaseRead, summary="Retrieve a single org.")
def get_org_by_id(
    *,
    db_session: Session = Depends(get_db),
    org_id: str,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve details about a specific job.
    """
    org = get(db_session=db_session, org_id=org_id, org_code=None)

    return org if org else {}


@router.get("/code/{org_code}", response_model=OrganizationBaseRead, summary="Retrieve a single org.")
def get_org_by_code(
    *,
    db_session: Session = Depends(get_db),
    org_code: str,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve details about a specific job.
    """
    org = get(db_session=db_session, org_code=org_code)

    return org if org else {}


@router.post("/", response_model=OrganizationBaseRead, summary="Create a new org.")
def create_org(
    *,
    db_session: Session = Depends(get_db),
    org_in: OrganizationBase,
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Create a new org.
    """
    if current_user.role == UserRoles.WORKER:
        raise HTTPException(status_code=400, detail="No create permission")

    org = get(db_session=db_session, org_code=org_in.code)
    if org:
        return update(db_session=db_session, org=org, org_in=org_in)
    org_in_dict = org_in.dict()
    org_in_dict['id'] = current_user.org_id
    org_in_dict['max_nbr_jobs'] = 100
    org_in_dict['max_nbr_workers'] = 10
    org_in_dict['max_nbr_teams'] = 2
    org = create(db_session=db_session, **org_in_dict)

    return org


@ router.put("/{org_id}", response_model=OrganizationBaseRead, summary="Update an existing org.")
def update_org(
    *,
    db_session: Session = Depends(get_db),
    org_id: int,
    org_in: OrganizationBase,
    current_user: DispatchUser = Depends(get_current_user),
    background_tasks: BackgroundTasks,
):
    """
    Update an worker job.
    """
    if current_user.role != UserRoles.OWNER:
        raise HTTPException(
            status_code=404, detail="Normal user is not allowed to modify settings. Only Owner can modify it.")

    org = get(db_session=db_session, org_id=org_id)
    old_org_code = copy.copy(org.code)
    if not org:
        raise HTTPException(status_code=404, detail="This organization is not found.")
    org_by_code_list = get_list(db_session=db_session, org_code=org_in.code)
    if [i for i in org_by_code_list if str(i.id) != str(org_id)]:
        raise HTTPException(
            status_code=404, detail=f"Organization code {org_in.code} does not match")
    # NOTE: Order matters we have to get the previous state for change detection
    org_update = update(db_session=db_session, org=org, org_in=org_in)
    # change auth org code
    if old_org_code != org_in.code:
        authService.update_by_org_code(db_session=db_session, org_id=org.id, org_code=org_in.code)
    try:
        # zulip change
        if org_update.id in all_zulip_client_dict:
            del all_zulip_client_dict[org_update.id]
        if org_update.zulip_is_active:
            refresh = False if org_update.zulip_user_name == org.zulip_user_name and org_update.zulip_password == org.zulip_password and org_update.zulip_site == org.zulip_site else True
            config = get_api(org_update.zulip_user_name,
                             org_update.zulip_password, org_update.zulip_site, refresh=refresh)
            client = zulip.Client(email=config.get(
                'email'), api_key=config.get('api_key'), site=org_update.zulip_site)
            all_zulip_client_dict[org_update.id] = {
                "org_obj": org_update,
                "client": ZulipCore(org_update, client),
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"zulip init error ,{e}")

    return org_update


@ router.delete("/{org_id}", response_model=int, summary="Delete an org.")
def delete_org(*, db_session: Session = Depends(get_db), org_id: int,
               current_user: DispatchUser = Depends(get_current_user),):
    """
    Delete an worker job.
    """
    if current_user.role != UserRoles.OWNER:
        raise HTTPException(status_code=400, detail="No create permission")
    # res = delete(db_session=db_session, org_id=org_id)
    res = log_out(db_session=db_session, org_id=org_id, org_code=current_user.org_code)
    return res


@ router.post("/add_user_org", summary="Create a register code.")
def create_organization(
    *,
    db_session: Session = Depends(get_db),
    current_user: DispatchUser = Depends(get_current_user),
    regist_data: OrganizationRegistCode,
):
    """生成 注册使用的org code"""
    try:

        if current_user.role != UserRoles.OWNER:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="No create permission")
        user_id = SHORTUUID.random(length=9)
        add_user(
            db_session=db_session, organization_id=current_user.org_id, dispatch_user_id=user_id, role=regist_data.role, team_id=regist_data.team.id
        )

    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="add user org error .")

    en_code = encrypt(f"{user_id}|{current_user.org_id}")
    return {
        "register_code": en_code
    }


def log_out(*, db_session, org_id: int, org_code: str):

    # delete organization,dispatch_user, dispatch_user_organization,
    # delete schema for organization

    redis_conn = redis.Redis(connection_pool=redis_pool)
    all_user = authService.get_by_org_id(db_session=db_session, org_id=org_id)
    for user in all_user:
        redis_conn.delete(f"user:{user.email}")
    result = delete(db_session=db_session, org_id=org_id)
    authService.delete_by_org_id(db_session=db_session, org_id=org_id)
    schema_name = f"dispatch_organization_{org_code}"
    if engine.dialect.has_schema(engine, schema_name):
        with engine.connect() as connection:
            connection.execute(DropSchema(schema_name, cascade=True))
    db_session.close()
    return result
