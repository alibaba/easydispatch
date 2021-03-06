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

import requests
from fastapi import HTTPException
from typing import List
from fastapi.security.utils import get_authorization_scheme_param

from jose import JWTError, jwt
from starlette.status import HTTP_401_UNAUTHORIZED
from starlette.requests import Request

from dispatch.config import DISPATCH_UI_URL
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
)


from .config import DISPATCH_JWT_AUDIENCE, DISPATCH_JWT_EMAIL_OVERRIDE

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
            raise HTTPException(status_code=HTTP_401_UNAUTHORIZED,
                                detail="no Authorization bearer found.")

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


class DispatchTicketPlugin(TicketPlugin):
    title = "Dispatch Plugin - Ticket Management"
    slug = "dispatch-ticket"
    description = "Uses dispatch itself to create a ticket."
    version = dispatch_plugin.__version__

    author = "Netflix"
    author_url = "https://github.com/alibaba/easydispatch.git"

    def create(
        self,
        job_id: int,
        title: str,
        job_type: str,
        job_priority: str,
        commander: str,
        reporter: str,
        job_type_plugin_metadata: dict = {},
    ):
        """Creates a Dispatch ticket."""
        resource_id = f"dispatch-{job_id}"
        return {
            "resource_id": resource_id,
            "weblink": f"{DISPATCH_UI_URL}/jobs/{resource_id}",
            "resource_type": "dispatch-internal-ticket",
        }

    def update(
        self,
        ticket_id: str,
        title: str,
        description: str,
        job_type: str,
        priority: str,
        status: str,
        commander_email: str,
        reporter_email: str,
        conversation_weblink: str,
        conference_weblink: str,
        document_weblink: str,
        storage_weblink: str,
        cost: float,
        job_type_plugin_metadata: dict = {},
    ):
        """Updates the job."""
        return


class DispatchDocumentResolverPlugin(DocumentResolverPlugin):
    title = "Dispatch Plugin - Document Resolver"
    slug = "dispatch-document-resolver"
    description = "Uses dispatch itself to resolve job documents."
    version = dispatch_plugin.__version__

    author = "Netflix"
    author_url = "https://github.com/alibaba/easydispatch.git"

    def get(self, job_type: str, job_priority: str, job_description: str, db_session=None):
        """Fetches documents from Dispatch."""
        route_in = {
            "text": job_description,
            "context": {
                "job_priorities": [job_priority],
                "job_types": [job_type],
                "terms": [],
            },
        }

        route_in = RouteRequest(**route_in)
        recommendation = route_service.get(db_session=db_session, route_in=route_in)
        return recommendation.documents


class DispatchContactPlugin(ContactPlugin):
    title = "Dispatch Plugin - Contact plugin"
    slug = "dispatch-contact"
    description = "Uses dispatch itself to resolve job participants."
    version = dispatch_plugin.__version__

    author = "Netflix"
    author_url = "https://github.com/alibaba/easydispatch.git"

    def get(self, email, db_session=None):
        return getattr(
            worker_service.get_by_code(db_session=db_session, code=email),
            "__dict__",
            {"email": email, "fullname": email},
        )


class DispatchParticipantResolverPlugin(ParticipantPlugin):
    title = "Dispatch Plugin - Participant Resolver"
    slug = "dispatch-participant-resolver"
    description = "Uses dispatch itself to resolve job participants."
    version = dispatch_plugin.__version__

    author = "Netflix"
    author_url = "https://github.com/alibaba/easydispatch.git"

    def get(self, job_type: str, job_priority: str, job_description: str, db_session=None):
        """Fetches participants from Dispatch."""
        route_in = {
            "text": job_description,
            "context": {
                "job_priorities": [job_priority.__dict__],
                "job_types": [job_type.__dict__],
                "terms": [],
            },
        }

        route_in = RouteRequest(**route_in)
        recommendation = route_service.get(db_session=db_session, route_in=route_in)

        log.debug(f"Recommendation: {recommendation}")
        # we need to resolve our service contacts to workers
        for s in recommendation.service_contacts:
            p = plugins.get(s.type)
            log.debug(f"Resolving service contact. ServiceContact: {s}")
            worker_email = p.get(s.external_id)

            worker = worker_service.get_or_create(db_session=db_session, code=worker_email)
            recommendation.workers.append(worker)

        db_session.commit()
        return list(recommendation.workers), list(recommendation.team_contacts)
