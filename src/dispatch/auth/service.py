"""
.. module: dispatch.auth.service
    :platform: Unix
    :copyright: (c) 2019 by Netflix Inc., see AUTHORS for more
    :license: Apache, see LICENSE for more details.
"""
import logging
from typing import List, Optional
from fastapi import HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from starlette.requests import Request
from starlette.status import HTTP_401_UNAUTHORIZED
from fastapi_permissions import Authenticated, configure_permissions
import dataclasses
from dispatch.team import service as team_service

from sqlalchemy.orm import Session
from dispatch.database import get_db

from dispatch.plugins.base import plugins
from dispatch.config import (
    DISPATCH_AUTHENTICATION_PROVIDER_SLUG,
    DISPATCH_AUTHENTICATION_DEFAULT_USER,
    redis_pool,
)
import redis
import json
# , UserLoginResponse
from .models import DispatchUser, DispatchUserOrganization, UserRegister, UserRoles, UserUpdate, UserRead

log = logging.getLogger(__name__)

credentials_exception = HTTPException(
    status_code=HTTP_401_UNAUTHORIZED, detail="Could not validate credentials"
)

from dispatch.database import SessionLocal

session_local = SessionLocal()
redis_conn = redis.Redis(connection_pool=redis_pool)

def get(*, db_session, user_id: int) -> Optional[DispatchUser]:
    """Returns an user based on the given user id."""
    return db_session.query(DispatchUser).filter(DispatchUser.id == user_id).one_or_none()


def get_by_email(*, db_session, email: str) -> Optional[DispatchUser]:
    """Returns an user object based on user email."""
    return db_session.query(DispatchUser).filter(DispatchUser.email == email).one_or_none()


def get_by_org_id(*, db_session, org_id: int) -> Optional[DispatchUser]:
    """Returns an user object based on user email."""
    return db_session.query(DispatchUser).filter(DispatchUser.org_id == org_id).all()


def create(*, db_session, user_in: UserRegister) -> DispatchUser:
    """Creates a new dispatch user."""
    # pydantic forces a string password, but we really want bytes
    password = bytes(user_in.password, "utf-8")
    user = DispatchUser(**user_in.dict(exclude={"password", "en_code"}),
                        password=password)
    db_session.add(user)
    db_session.commit()
    return user


def get_or_create(*, db_session, user_in: UserRegister) -> DispatchUser:
    """Gets an existing user or creates a new one."""
    user = get_by_email(db_session=db_session, email=user_in.email)
    if not user:
        return create(db_session=db_session, user_in=user_in)
    return user


def update_by_org_code(*, db_session, org_id: int, org_code: str) -> DispatchUser:
    """Updates a user."""
    user_list = get_by_org_id(db_session=db_session, org_id=org_id)
    for user in user_list:
        user.org_code = org_code
        db_session.add(user)
    db_session.commit()
    return user


def update(*, db_session, user: DispatchUser, user_in: UserUpdate) -> DispatchUser:
    """Updates a user."""
    if user_in.managed_teams:
        new_managed_teams = [
            team_service.get_by_code(db_session=db_session, code=t.code)
            for t in user_in.managed_teams
        ]
    else:
        new_managed_teams = []
    user_data = jsonable_encoder(user)
    update_data = user_in.dict(skip_defaults=True)
    if 'old_password' in update_data:
        update_data.pop('old_password')
    if 'password' in update_data and update_data['password']:
        update_data['password'] = user_in.password_required(update_data['password'])
    else:
        update_data.pop('password')
    for field in user_data:
        if field in update_data:
            setattr(user, field, update_data[field])

    user.managed_teams = new_managed_teams
    db_session.add(user)
    db_session.commit()
    return user


def get_current_user(*, db_session: Session = Depends(get_db), request: Request) -> DispatchUser:
    """Attempts to get the current user depending on the configured authentication provider."""
    # redis_conn = redis.Redis(connection_pool=redis_pool)

    if DISPATCH_AUTHENTICATION_PROVIDER_SLUG:
        auth_plugin = plugins.get(DISPATCH_AUTHENTICATION_PROVIDER_SLUG)
        user_email = auth_plugin.get_current_user(request)
    else:
        log.debug("No authentication provider. Default user will be used")
        user_email = DISPATCH_AUTHENTICATION_DEFAULT_USER
    return get_or_set_user_redis(user_email=user_email)
    # user_json = redis_conn.get(f"user:{user_email}")
    # if user_json:
    #     user_loaded = json.loads(user_json)
    #     user_ = UserRead(**user_loaded)
    #     # user_pass = redis_conn.get(f"user:{user_email}")
    #     return user_
    # else:
    #     # Not in redis, or expired. Load it and set it.
    #     db_user = get_by_email(db_session=db_session, email=user_email)  # _or_create  user_in=UserRegister(
    #     db_user.__dict__['is_active'] = True if db_user.__dict__['is_active'] else False
    #     user_ = UserRead(**db_user.__dict__)
    #     # dict_managed_teams = [
    #     #     {"id": t.id, "code":t.code} for t in db_user.managed_teams
    #     # ]
    #     # user_.managed_teams = dict_managed_teams

    #     redis_conn.set(f"user:{user_email}", json.dumps(user_.dict()), ex=600)
    #     # redis_conn.set(f"user:{user_email}:pass", json.dumps(db_user.password), ex=600)
    #     return user_


def get_user_by_id(user_id) -> DispatchUser:
    """Attempts to get the current user depending on the configured authentication provider."""
    return get_or_set_user_redis(user_id=user_id)

def get_or_set_user_redis(user_email=None, user_id=None, ) -> DispatchUser:
    if user_email is not None:
        user_redis_key = f"user:email:{user_email}"
    elif user_id is not None:
        user_redis_key = f"user:id:{user_email}"
    else:
        raise ValueError("get_or_set_user_redis, no id nor email")

    user_json = redis_conn.get(user_redis_key)
    if user_json:
        user_loaded = json.loads(user_json)
        user_ = UserRead(**user_loaded) 
        return user_
    else:
        # Not in redis, or expired. Load it and set it.
        if user_email is not None:
            db_user = get_by_email(db_session=session_local, email=user_email)  # _or_create  user_in=UserRegister(
        else:
            db_user = get(db_session=session_local, user_id=user_id) 
            
        db_user.__dict__['is_active'] = True if db_user.__dict__['is_active'] else False
        user_ = UserRead(**db_user.__dict__)
        # dict_managed_teams = [
        #     {"id": t.id, "code":t.code} for t in db_user.managed_teams
        # ]
        # user_.managed_teams = dict_managed_teams

        redis_conn.set(user_redis_key, json.dumps(user_.dict()), ex=3600) 
        return user_



def get_active_principals(user: DispatchUser = Depends(get_current_user)) -> List[str]:
    """Fetches the current participants for a given user."""
    principals = [Authenticated]
    principals.extend(getattr(user, "principals", []))
    return principals


Permission = configure_permissions(get_active_principals)


def get_org_user(*, db_session, user_id=None, org_id=None) -> Optional[DispatchUserOrganization]:
    """Returns an user object based on user email."""
    if user_id and org_id:
        return db_session.query(DispatchUserOrganization).filter(DispatchUserOrganization.dispatch_user_id == user_id,
                                                                 DispatchUserOrganization.organization_id == org_id,
                                                                 ).one_or_none()
    elif user_id:
        return db_session.query(DispatchUserOrganization).filter(DispatchUserOrganization.dispatch_user_id == user_id
                                                                 ).one_or_none()
    elif org_id:
        return db_session.query(DispatchUserOrganization).filter(
            DispatchUserOrganization.organization_id == org_id
        ).one_or_none()
    else:
        return None


# def get_org_user_roles(*, db_session, user_id=None, org_id=None) -> List[DispatchUserOrganization]:
#     """Returns list of user roles based on user ID and org_id."""
#     if user_id and org_id:
#         return db_session.query(
#             DispatchUserOrganization
#         ).filter(
#                 DispatchUserOrganization.dispatch_user_id == user_id,
#                 DispatchUserOrganization.organization_id == org_id,
#         ).all()
#     else:
#         log.error(f"get_org_user_roles: wrong input: user_id={user_id}, org_id={org_id}")
#         return []

def delete(*, db_session, id: int):
    # TODO: When deleting, respect referential integrity here in the code. Or add cascading deletes
    # in models.py.
    db_session.query(DispatchUser).filter(DispatchUser.id == id).delete()
    db_session.query(DispatchUserOrganization).filter(
        DispatchUserOrganization.dispatch_user_id == id).delete()
    db_session.commit()


def get_current_role(
    request: Request, current_user: DispatchUser = Depends(get_current_user)
) -> UserRoles:
    """Attempts to get the current user depending on the configured authentication provider."""
    return current_user.role


def delete_by_org_id(*, db_session, org_id: int):

    db_session.query(DispatchUser).filter(DispatchUser.org_id == org_id).delete()
    db_session.query(DispatchUserOrganization).filter(
        DispatchUserOrganization.organization_id.in_([org_id, -org_id])).delete(synchronize_session=False)
    db_session.commit()
