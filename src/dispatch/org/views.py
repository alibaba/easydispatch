

import json
from sqlalchemy.schema import DropSchema
from dispatch.config import REDIS_KEY_TEMPLATE_USER, redis_pool, redis
from dispatch.database import engine
from sqlalchemy import text
from fastapi import status
import copy
from dispatch.auth import service as authService
from dispatch.job import service as jobService
# from dispatch.plugins.kandbox_planner.data_adapter.kafka_adapter import OrganizationJobSchedueCalllback
from dispatch.team import service as teamService
from dispatch.worker import service as workerService

from dispatch.order import service as orderService 
from typing import List
# import zulip
from sqlalchemy import inspect


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

# from dispatch.zulip_server.core import ZulipCore, all_zulip_client_dict, get_api
from dispatch.auth.models import UserRoles
from dispatch.org.models import OrganizationBase, OrganizationBaseRead, OrganizationPagination, OrganizationRegistCode

from dispatch.org.service import add_user, create, delete, get, get_list, update,exist_schema
import logging
log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=OrganizationBaseRead, summary="Retrieve the current organization.")
def get_orgs(
    db_session: Session = Depends(get_db),
    current_user: DispatchUser = Depends(get_current_user),
):
    """
    Retrieve the current organization. The the Owner can retrieve information about its orgnization.
    """
    if current_user.role not in (UserRoles.OWNER, UserRoles.SYSTEM, UserRoles.PLANNER):
        raise HTTPException(status_code=404)
    data = get(db_session=db_session, org_id=current_user.org_id, org_code=None)
    if data:
        job_all_count = jobService.get_by_org_id_count(
            db_session=db_session, org_id=current_user.org_id)
        team_all_count = teamService.get_by_org_id_count(
            db_session=db_session, org_id=current_user.org_id)
        worker_all_count = workerService.get_by_org_id_count(
            db_session=db_session, org_id=current_user.org_id)
        if not data.org_type:
            data.org_type = "default"
        data = OrganizationBaseRead(**data.__dict__)
        data.worker_count = worker_all_count
        data.team_count = team_all_count
        data.job_count = job_all_count
        data.zulip_password = None
        data.default_team_flex_form_data = data.org_setting.get("default_team_flex_form_data",{})
        data.default_worker_flex_form_data = data.org_setting.get("default_worker_flex_form_data",{})
        data.default_job_flex_form_data = data.org_setting.get("default_job_flex_form_data",{})
        data.default_order_flex_form_data = data.org_setting.get("default_order_flex_form_data",{})

    return data


# @router.get("/id/{org_id}", response_model=OrganizationBaseRead, summary="Retrieve the org.")
# def get_org_by_id(
#     *,
#     db_session: Session = Depends(get_db),
#     org_id: int,
#     current_user: DispatchUser = Depends(get_current_user),
# ):
#     """
#     Deprecated, please use 
#     """
#     if current_user.role != "Owner" or current_user.org_id!=int(org_id):
#         raise HTTPException(status_code=404)

#     org = get(db_session=db_session, org_id=org_id, org_code=None)

#     return org if org else {}


# @router.get("/code/{org_code}", response_model=OrganizationBaseRead, summary="Retrieve a single org.")
# def get_org_by_code(
#     *,
#     db_session: Session = Depends(get_db),
#     org_code: str,
#     current_user: DispatchUser = Depends(get_current_user),
# ):
#     """
#     Retrieve details about a specific job.
#     """
#     org = get(db_session=db_session, org_code=org_code)
#     if org:
#         if current_user.role != "Owner" or current_user.org_id!=org.org_id:
#             raise HTTPException(status_code=404)
#     return org if org else {}


# @router.post("/", response_model=OrganizationBaseRead, summary="Create a new org.")
# def create_org(
#     *,
#     db_session: Session = Depends(get_db),
#     org_in: OrganizationBase,
#     current_user: DispatchUser = Depends(get_current_user),
# ):
#     """
#     Create a new org.
#     """
#     raise HTTPException(status_code=404)
#     if current_user.role == UserRoles.WORKER:
#         raise HTTPException(status_code=400, detail="No permission")

#     org = get(db_session=db_session, org_code=org_in.code)
#     if org:
#         return update(db_session=db_session, org=org, org_in=org_in)
#     org_in_dict = org_in.dict()
#     org_in_dict['id'] = current_user.org_id
#     org_in_dict['max_nbr_jobs'] = 100
#     org_in_dict['max_nbr_workers'] = 10
#     org_in_dict['max_nbr_teams'] = 2
#     org = create(db_session=db_session, **org_in_dict)

#     return org


@ router.put("/{org_id}", response_model=OrganizationBaseRead, summary="Update an existing org.")
def update_org(
    *,
    db_session: Session = Depends(get_db),
    org_id: int,
    org_in: OrganizationBase,
    current_user: DispatchUser = Depends(get_current_user),
    # background_tasks: BackgroundTasks,
):
    """
    Update an worker job.
    """
    if current_user.role not in (UserRoles.SYSTEM, UserRoles.OWNER)  or current_user.org_id!=org_id:
        raise HTTPException(
            status_code=404, detail="Normal user is not allowed to modify settings. Only Owner can modify it.")

    org = get(db_session=db_session, org_id=org_id)
    if not org:
        raise HTTPException(status_code=404, detail="This organization is not found.")

    # old_org_code = copy.copy(org.code)
    # old_org = copy.deepcopy(org)
    # change auth org code ? why should we allow it?
    if org.code != org_in.code:
        raise HTTPException(status_code=400, detail="Organization code does not match.")
        authService.update_by_org_code(db_session=db_session, org_id=org.id, org_code=org_in.code)


    org_by_code_list = get_list(db_session=db_session, org_code=org_in.code)
    if [i for i in org_by_code_list if str(i.id) != str(org_id)]:
        raise HTTPException(
            status_code=404, detail=f"Organization code {org_in.code} does not match")
    # NOTE: Order matters we have to get the previous state for change detection
    org_update = update(db_session=db_session, org=org, org_in=org_in, current_role=current_user.role)
    # try:
    #     # zulip change
    #     if org_update.id in all_zulip_client_dict:
    #         del all_zulip_client_dict[org_update.id]
    #     if org_update.zulip_is_active:
    #         refresh = False if org_update.zulip_user_name == old_org.zulip_user_name and org_update.zulip_password == old_org.zulip_password and org_update.zulip_site == old_org.zulip_site else True
    #         if org_update.zulip_user_name and org_update.zulip_password and org_update.zulip_site:
    #             config = get_api(org_update.zulip_user_name,
    #                             org_update.zulip_password, org_update.zulip_site, refresh=refresh)
    #             client = zulip.Client(email=config.get(
    #                 'email'), api_key=config.get('api_key'), site=org_update.zulip_site)
    #             all_zulip_client_dict[org_update.id] = {
    #                 "org_obj": org_update,
    #                 "client": ZulipCore(org_update, client),
    #             }
    #             all_zulip_client_dict[org_update.id]['client'].init_subcribe_team()
    # except Exception as e:
    #     raise HTTPException(status_code=400, detail=f"zulip init error {e.detail}")

    # try:
    #     # update url_callback in redis
    #     job_callback = OrganizationJobSchedueCalllback()
    #     job_callback.get_update_redis_info(refresh=True)
    #     job_callback.close()
    # except Exception as e:
    #     pass
    return org_update


@ router.delete("/{org_id}", response_model=int, summary="Delete an org.")
def delete_org(*, db_session: Session = Depends(get_db), org_id: int,
               current_user: DispatchUser = Depends(get_current_user),):
    """
    Delete an worker job.
    """
    if current_user.role != UserRoles.OWNER:
        raise HTTPException(status_code=400, detail="Not the owner. Only the owner can delete the orgnaization")
    # res = delete(db_session=db_session, org_id=org_id)
    # delete organization,dispatch_user, dispatch_user_organization,
    # delete schema for organization

    redis_conn = redis.Redis(connection_pool=redis_pool)
    all_user = authService.get_by_org_id(db_session=db_session, org_id=org_id)
    for user in all_user:
        user_redis_key = REDIS_KEY_TEMPLATE_USER.format(user.email) 
        redis_conn.delete(user_redis_key) 
        
    result = delete(db_session=db_session, org_id=org_id)
    authService.delete_by_org_id(db_session=db_session, org_id=org_id)
    
    # 版本更新 不可用了 
    # insp = inspect(db_session.connection())
    schema_name = f"dispatch_organization_{current_user.org_code}"
    if exist_schema(schema_name=schema_name):
        # with db_session.get_bind().begin() as connection:
        #     db_session.connection().execute(DropSchema(schema_name, cascade=True))
        drop_schema = DropSchema(schema_name,cascade=True)

        # 使用连接和执行DDL操作
        with engine.begin() as connection:
            drop_schema.execute(bind=connection)
    db_session.close()
    return result


    # try:
    #     # update url_callback in redis
    #     job_callback = OrganizationJobSchedueCalllback()
    #     job_callback.get_update_redis_info(refresh=True)
    #     job_callback.close()
    # except Exception as e:
    #     pass
    # return res


@ router.post("/add_user_org", summary="Create an invitation code.")
def create_organization(
    *,
    db_session: Session = Depends(get_db),
    current_user: DispatchUser = Depends(get_current_user),
    regist_data: OrganizationRegistCode,
):
    """Generate an orgnization invitation code. Other users can use this code to join this orgniazation."""
    try:
        en_code=''
        log.info(f"create_organization:{regist_data}")
        if current_user.role != UserRoles.OWNER:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="No create permission")
        en_code_list = []
        if regist_data.switch_worker:
            for worker in regist_data.worker:
                select_worker = workerService.get_by_code(db_session=db_session,code = worker.code)
                if not select_worker:
                    continue
                user_id = SHORTUUID.random(length=9)
                add_user(
                    db_session=db_session, organization_id=current_user.org_id, 
                    dispatch_user_id=user_id, role=regist_data.role, 
                    team_id=regist_data.team.id,worker_code=worker.code
                )
                w_en_code = encrypt(f"{user_id}|{current_user.org_id}")
                en_code_list.append({"worker":worker.code,"regist_code":w_en_code})
            en_code = json.dumps(en_code_list)
        else:
            user_id = SHORTUUID.random(length=9)
            add_user(
                db_session=db_session, organization_id=current_user.org_id, 
                dispatch_user_id=user_id, role=regist_data.role, 
                team_id=regist_data.team.id,worker_code=None
            )
            en_code = encrypt(f"{user_id}|{current_user.org_id}")

    except Exception as e :
        log.info(f"create_organization:{str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal error when adding user. {str(e)}")

    result = {
        "register_code": en_code
    }
    log.info(f"create_organization RUNNING SUCCEESS , {result}")
    return result


# def log_out(*, db_session, org_id: int, org_code: str):


# 获取组织状态


@router.get("/organization_status")
def get_orgnaization_status(*, db_session: Session = Depends(get_db), 
                            current_user: DispatchUser = Depends(get_current_user)):
    try:
        data = get(db_session=db_session, org_id=current_user.org_id, org_code=None)

        return {
            "code": 200,
            "msg": "success",
            "data": {
                "organization_status": data.organization_status
            }
        }
    except:
        return {
            "code": 500,
            "msg": "server error"
        }
