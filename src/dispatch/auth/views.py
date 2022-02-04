import json
from dispatch.config import redis_pool, redis
import logging
from dispatch.database_util.org_config import team_flex_form_schema, worker_flex_form_schema, job_flex_form_schema
import time
from dispatch.job.models import JobRead
from dispatch.plugin.models import PluginCreate
import dispatch.plugins.base
from dispatch.service.models import ServiceCreate
import dispatch.service_plugin
from typing import List
from dispatch.team.models import TeamCreate
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.sql.functions import current_date, user
from dispatch.common.utils.encryption import decrypt, encrypt
from dispatch.database_util.service import common_parameters, search_filter_sort_paginate
from dispatch.database import get_auth_db as get_db
from dispatch.database import init_schema
from dispatch.config import ENABLE_REGISTER
from dispatch.job.service import SHORTUUID
from dispatch.org.models import OrganizationBase, OrganizationBaseRead
from dispatch.org import service as org_service
# from dispatch.service import service as plannerService
# from dispatch.service_plugin import service as pluginService
# from dispatch.service_plugin.models import ServicePluginCreate
# from dispatch.team import service as teamService
from .models import (
    DispatchUser,
    UserLogin,
    UserRegister,
    UserRead,
    UserRoles,
    UserUpdate,
    UserPagination,
    UserLoginResponse,
    UserRegisterResponse,
)
from .service import (
    get,
    get_by_email,
    get_org_user,
    update,
    create,
    get_current_user,
    delete
)


auth_router = APIRouter()
user_router = APIRouter()

log = logging.getLogger(__name__)


@user_router.get("/", response_model=UserPagination)
def get_users(*,
              current_user: DispatchUser = Depends(get_current_user), common: dict = Depends(common_parameters)):
    """
    Get all users.
    """

    common["fields"] = ["org_id"]
    common["values"] = [current_user.org_id]
    common["ops"] = ["=="]
    return search_filter_sort_paginate(model="DispatchUser", **common)


@user_router.get("/{user_id}", response_model=UserRead)
def get_user(*, db_session: Session = Depends(get_db), user_id: int):
    """
    Get a user.
    """
    user = get(db_session=db_session, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="The user with this id does not exist.")
    return user


@user_router.put("/{user_id}", response_model=UserUpdate)
def update_user(*, db_session: Session = Depends(get_db),
                current_user: DispatchUser = Depends(get_current_user),
                user_id: int, user_in: UserUpdate):
    """
    Update a user.
    """
    user = get(db_session=db_session, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="The user with this id does not exist.")
    # print(user.org_code, user.is_org_owner)
    if user_in.old_password and not user.check_password(user_in.old_password):
        raise HTTPException(status_code=400, detail="old password is wrong.")

    if user_in.email == current_user.email:
        if user_in.role != user.role and user.role == UserRoles.WORKER:
            raise HTTPException(status_code=400, detail="No modification role permission.")
    else:
        if current_user.role != UserRoles.OWNER or user_in.old_password:
            raise HTTPException(status_code=400, detail="No modification  permission.")
    user = update(db_session=db_session, user=user, user_in=user_in)
    redis_conn = redis.Redis(connection_pool=redis_pool)
    redis_conn.delete(f"user:{user_in.email}")
    return user


@auth_router.post("/login", response_model=UserLoginResponse)
def login_user(
    req: Request,
    user_in: UserLogin,
    db_session: Session = Depends(get_db),
):
    user = get_by_email(db_session=db_session, email=user_in.email)
    # print(user.org_code, user.is_org_owner)
    if user and user.check_password(user_in.password):
        # NOT for authorization purpose
        # req.state.code = user.code
        # req.state.org_code = user.org_code
        if not user.is_active:
            raise HTTPException(status_code=400, detail=f"User {user_in.email} is not activated...")

        log.info(f"user login success: email = {user.email}")
        return {"token": user.token}

    raise HTTPException(status_code=400, detail="Invalid username or password")


@auth_router.post("/register", response_model=UserRegisterResponse)
def register_user(
    req: Request,
    user_in: UserRegister,
    db_session: Session = Depends(get_db),  #


):
    # TODO
    # if ENABLE_REGISTER != "yes":
    #     raise HTTPException(status_code=401, detail="Registration is disabled.")

    # # check user is null
    try:
        if user_in.email:
            # 正常新增
            user_info = get_by_email(db_session=db_session, email=user_in.email)
            if user_info:
                raise HTTPException(
                    status_code=400, detail=f"User ({user_in.email}) already exists")
        else:
            raise HTTPException(status_code=400, detail="Email can not be empty")

        if user_in.org_code:
            # check org table is null
            # add org, org_user,user
            org_data = org_service.get(db_session=db_session, org_code=user_in.org_code)
            if org_data is None:
                org_id = SHORTUUID.random(length=9)

                # add user
                user_in.role = UserRoles.OWNER
                user_in.is_org_owner = True
                user_in.is_active = True
                user_in.org_id = org_id
                user_in.default_team_id = org_id
                user = create(db_session=db_session, user_in=user_in)

                # create org_user relationship
                org_service.add_user(
                    db_session=db_session, organization_id=org_id, dispatch_user_id=user.id, role=user.role, team_id=org_id
                )

                org_in = OrganizationBase(code=user_in.org_code, id=org_id,
                                        max_nbr_jobs=100, max_nbr_workers=10, max_nbr_teams=2, team_flex_form_schema=team_flex_form_schema,
                                        worker_flex_form_schema=worker_flex_form_schema, job_flex_form_schema=job_flex_form_schema)
                org_in_dict = org_in.dict()
                org_in_dict['id'] = org_id
                org_service.create(db_session=db_session, **org_in_dict)

                return user
            else:
                if not org_data.public_registration:
                    raise HTTPException(status_code=400, detail="This organization already exists")
                else:
                    # create invitation code dynamically by the team
                    user_in.id = SHORTUUID.random(length=9)
                    user_in.org_id = org_data.id
                    if user_in.role == UserRoles.WORKER:
                        # Requires activation.
                        user_in.is_active = False
                    elif user_in.role == UserRoles.CUSTOMER:
                        # Requires activation.
                        user_in.is_active = True

                    user = create(db_session=db_session, user_in=user_in)
                    # user_in.en_code = org_service.add_user( 
                    #     db_session=db_session, 
                    #     organization_id=org_data.id, 
                    #     dispatch_user_id=user_id, 
                    #     role=UserRoles.WORKER, 
                    #     team_id=user_in.default_team_id
                    # )
                    return user



        if user_in.en_code:
            # check org table have data
            # check org_user table have data
            # add user data
            try:

                de_code = decrypt(user_in.en_code)
            except Exception:
                raise HTTPException(
                    status_code=400, detail="Please enter the correct organization Invitation code")

            user_in.id = int(de_code.split("|")[0])
            user_in.org_id = int(de_code.split("|")[1])

            org_data = org_service.get(db_session=db_session, org_id=user_in.org_id)
            if not org_data:
                raise HTTPException(status_code=401, detail="The organization does not exist.")

            org_user = get_org_user(db_session=db_session, user_id=user_in.id,
                                    org_id=user_in.org_id)
            if not org_user:
                raise HTTPException(status_code=401, detail="User role does not exist")

            user_in.org_code = org_data.code
            user_in.org_id = org_data.id
            user_in.default_team_id = org_user.team_id
            user_in.role = org_user.role
            user_in.is_active = True
            user_in.is_org_owner = True if org_user.role == UserRoles.OWNER else False
            user = create(db_session=db_session, user_in=user_in)

            # Remove the record by changing id.
            org_user.organization_id = 0 - org_user.organization_id
            db_session.add(org_user)
            db_session.commit()

            return user

        else:
            raise HTTPException(
                status_code=400, detail="Please enter the correct organization Invitation code")

    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Registration Error: {e.detail}")


@auth_router.get("/me", response_model=UserRead)
def get_me(
    req: Request,
    db_session: Session = Depends(get_db),
):
    current_user = get_current_user(db_session=db_session, request=req)
    return current_user


@auth_router.post("/register_user_org", summary="Create a new org.")
def create_org(
    *,
    db_session: Session = Depends(get_db),
    org_in: OrganizationBase,
):
    """
    register add org  , no login info
    """
    org = org_service.get(db_session=db_session, org_code=org_in.code)
    if org:
        raise HTTPException(status_code=400, detail="add user org error .code exist")

    org_in_dict = org_in.dict()
    org_in_dict['id'] = SHORTUUID.random(length=9)
    org = org_service.create(db_session=db_session, **org_in_dict)
    en_code = encrypt(org.id)
    return en_code


@user_router.delete("/{user_id}", summary="Delete an user.")
def delete_user(*, db_session: Session = Depends(get_db), user_id: str,
                current_user: DispatchUser = Depends(get_current_user)):
    """
    Delete an worker job.
    """
    user = get(db_session=db_session, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="The requested user does not exist.")
    if user.email == current_user.email or current_user.role != UserRoles.OWNER:
        raise HTTPException(status_code=404, detail="No delete permission.")
    delete(db_session=db_session, id=user_id)
    return True
