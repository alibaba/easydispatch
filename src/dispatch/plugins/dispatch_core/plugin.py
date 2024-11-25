"""
.. module: dispatch.plugins.dispatch_core.plugin
    :platform: Unix
    :copyright: (c) 2019 by Netflix Inc., see AUTHORS for more
    :license: Apache, see LICENSE for more details.
"""
from datetime import datetime
import base64
import json
import logging
from time import time
import redis

import requests
from fastapi import HTTPException
from typing import List
from fastapi.security.utils import get_authorization_scheme_param

from jose import JWTError, jwt
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.requests import Request
from dispatch import config

from dispatch.config import DISPATCH_UI_URL, REDIS_KEY_TEMPLATE_LOGIN_EXPIRE
from dispatch.worker import service as worker_service
from dispatch.plugins import dispatch_core as dispatch_plugin
from dispatch.plugins.base import plugins
from dispatch.plugins.bases import (
    ParticipantPlugin,
    DocumentResolverPlugin,
    AuthenticationProviderPlugin,
    TicketPlugin,
    ContactPlugin,
)

from dispatch.config import (
    DISPATCH_AUTHENTICATION_PROVIDER_PKCE_JWKS,
    DISPATCH_JWT_SECRET,
    DISPATCH_JWT_ALG,
    redis_pool,
    DISPATCH_JWT_EXP,
)


from .config import DISPATCH_JWT_AUDIENCE, DISPATCH_JWT_EMAIL_OVERRIDE

redis_conn = redis.Redis(connection_pool=redis_pool)

log = logging.getLogger(__name__)


class BasicAuthProviderPlugin(AuthenticationProviderPlugin):
    title = "Dispatch Plugin - Basic Authentication Provider"
    slug = "dispatch-auth-provider-basic"
    description = "Generic basic authentication provider."
    version = dispatch_plugin.__version__

    author = "Netflix"
    author_url = "https://github.com/alibaba/easydispatch.git"

    # def __init__(self, **kwargs):
    # print(f"BasicAuthProviderPlugin __init__ called at {datetime.now()}")

    def get_current_user(self, request: Request, **kwargs):
        authorization: str = request.headers.get("Authorization")
        scheme, param = get_authorization_scheme_param(authorization)
        if not authorization or scheme.lower() != "bearer":
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED, detail="no Authorization bearer found."
            )

        token = authorization.split()[1]

        try:
            data = jwt.decode(token, DISPATCH_JWT_SECRET, algorithms=[DISPATCH_JWT_ALG])
        except JWTError as e:
            # print(DISPATCH_JWT_ALG, str(e), DISPATCH_JWT_SECRET)
            raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=str(e))
        return data["email"]

    def get_current_user_data(self, request: Request, **kwargs):
        authorization: str = request.headers.get("Authorization")
        scheme, param = get_authorization_scheme_param(authorization)
        if not authorization or scheme.lower() != "bearer":
            return

        token = authorization.split()[1]

        try:
            data = jwt.decode(token, DISPATCH_JWT_SECRET, algorithms=[DISPATCH_JWT_ALG])
        except JWTError as e:
            raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=str(e))

        # 3小时无操作则登出
        # 先通过email+org_code 做为key，从redis获取存入的时间戳
        # 如果没有值，则存入当前时间戳
        # 如果有值，则拿redis时间戳和当前时间戳做比较，
        # 如果小于3小时，则更新redis的值，大于等于3小时，则抛出401，同时删除redis的key
        # 
        # TODO 2024-01-11 01:54:03 为什么有这个功能，DISPATCH_JWT_EXP 本身控制就可以了。。。
        # if "/organization_status" not in request.url.path:
        #     exp_rds_key = REDIS_KEY_TEMPLATE_LOGIN_EXPIRE.format(data["org_code"], data["email"], )
        #     now = time()
        #     # exp_time_sceonds = 3 * 60 * 60
        #     exp_time_sceonds = int(DISPATCH_JWT_EXP)
        #     if redis_conn.exists(exp_rds_key):
        #         rds_time = redis_conn.get(exp_rds_key)
        #         if (now - float(rds_time)) < exp_time_sceonds:
        #             redis_conn.set(exp_rds_key, now, None)
        #         else:
        #             redis_conn.delete(exp_rds_key)
        #             raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=f"We could not find user's sessions")
        #     else:
        #         redis_conn.set(exp_rds_key, now, ex=exp_time_sceonds)
        return data


class PKCEAuthProviderPlugin(AuthenticationProviderPlugin):
    title = "Dispatch Plugin - PKCE Authentication Provider"
    slug = "dispatch-auth-provider-pkce"
    description = "Generic PCKE authentication provider."
    version = dispatch_plugin.__version__

    author = "Netflix"
    author_url = "https://github.com/alibaba/easydispatch.git"

    def get_current_user(self, request: Request, **kwargs):
        credentials_exception = HTTPException(
            status_code=HTTP_401_UNAUTHORIZED, detail="Could not validate credentials"
        )

        authorization: str = request.headers.get(
            "Authorization", request.headers.get("authorization")
        )
        scheme, param = get_authorization_scheme_param(authorization)
        if not authorization or scheme.lower() != "bearer":
            raise credentials_exception

        token = authorization.split()[1]

        # Parse out the Key information. Add padding just in case
        key_info = json.loads(base64.b64decode(token.split(".")[0] + "=========").decode("utf-8"))

        # Grab all possible keys to account for key rotation and find the right key
        keys = requests.get(DISPATCH_AUTHENTICATION_PROVIDER_PKCE_JWKS).json()["keys"]
        for potential_key in keys:
            if potential_key["kid"] == key_info["kid"]:
                key = potential_key

        try:
            # If DISPATCH_JWT_AUDIENCE is defined, the we must include audience in the decode
            if DISPATCH_JWT_AUDIENCE:
                data = jwt.decode(token, key, audience=DISPATCH_JWT_AUDIENCE)
            else:
                data = jwt.decode(token, key)
        except JWTError:
            raise credentials_exception

        # Support overriding where email is returned in the id token
        if DISPATCH_JWT_EMAIL_OVERRIDE:
            return data[DISPATCH_JWT_EMAIL_OVERRIDE]
        else:
            return data["email"]


