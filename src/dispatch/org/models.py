from datetime import datetime
from typing import Any, List, Optional

from pydantic import Field
from sqlalchemy import (
    JSON,
    Column,
    String,
    BigInteger,
    Integer,
    Boolean,
    LargeBinary,
    Sequence
)

from dispatch.auth.models import UserRoles
from dispatch.database import Base
from dispatch.models import DispatchBase, TimeStampMixin
from dispatch.team.models import TeamCreate
from dispatch.worker.models import WorkerCreate


from dispatch.org.enums import OrganizationType 


class Organization(Base, TimeStampMixin):

    __table_args__ = {"schema": "dispatch_core"}
    id = Column(BigInteger, Sequence(
        'org_id_seq', start=101, increment=1, schema="dispatch_core"
        ), primary_key=True,)
    code = Column(String, nullable=False, unique=True)
    org_type = Column(String, nullable=True, default=OrganizationType.DEFAULT)   

    max_nbr_jobs = Column(Integer, nullable=False, default=0)
    max_nbr_teams = Column(Integer, nullable=False, default=3)
    max_nbr_workers = Column(Integer, nullable=False, default=0)

    org_setting = Column(JSON, default={})

    team_flex_form_schema = Column(
        JSON, default={}
    )

    worker_flex_form_schema = Column(
        JSON, default={}
    )

    job_flex_form_schema = Column(
        JSON, default={}
    )
    
    order_flex_form_schema = Column(
        JSON, default={}
    )
    
    msg_template = Column(
        JSON, default={}
    )
    work_calendar = Column(
        JSON, default={}
    )
    zulip_is_active = Column(Boolean, default=False)
    zulip_site = Column(String, nullable=True, unique=False)
    zulip_user_name = Column(String, nullable=True, unique=False)
    zulip_password = Column(LargeBinary, nullable=True)

    callback_is_active = Column(Boolean, default=False) # callback_url 的开关 
    callback_url = Column(String, nullable=True)

    public_registration = Column(Boolean, default=False)
    organization_status = Column(String, nullable=False, default="1")
    
    

class OrganizationBase(DispatchBase):

    code: str = Field(title="Organization Code",
                      description='Organization code is the unique identify for this Organization',)
    org_type: str
    org_setting: Any = Field(default={}, title="setting in json", description='',)

    callback_url: Optional[str] = None
    
    team_flex_form_schema: Any = Field(default={}, title="Flexible Form Schema", description='', )
    worker_flex_form_schema: Any = Field(default={}, title="Flexible Form Schema", description='', )
    job_flex_form_schema: Any = Field(default={}, title="Flexible Form Schema", description='', )
    order_flex_form_schema: Any = Field(default={}, title="Flexible Form Schema", description='', )

    default_team_flex_form_data: Any = Field(default={}, title="Default Flexible Form Data", description='', )
    default_worker_flex_form_data: Any = Field(default={}, title="Default Flexible Form Data", description='', )
    default_job_flex_form_data: Any = Field(default={}, title="Default Flexible Form Data", description='', )
    default_order_flex_form_data: Any = Field(default={}, title="Default Flexible Form Data", description='', )

    msg_template: Any = Field(default={}, title="Flexible Form Data", description='',)
    work_calendar: Any = Field(default={}, title="Flexible Form Data", description='',)
    max_nbr_jobs: Any = Field(default=0, title="max_nbr_jobs", description='',)
    max_nbr_teams: Any = Field(default=0, title="max_nbr_jobs", description='',)
    max_nbr_workers: Any = Field(default=0, title="max_nbr_workers", description='',)

    zulip_is_active: Optional[bool] = False
    
    callback_is_active: Optional[bool] = False
    zulip_site: Optional[str] = None
    zulip_user_name: Optional[str] = None
    # This password should be the key.
    # zulip_password_is_key
    zulip_password: Optional[str] = None


class OrganizationBaseRead(OrganizationBase):
    id: int = Field(default=0, title="", description='', )
    code: str = Field(title="Organization Code",
                      description='Organization code is the unique identify for this Organization', )
    callback_url: Optional[str] = None


    msg_template: Any = Field(default={}, title="Flexible Form Data", description='', )
    work_calendar: Any = Field(default={}, title="Flexible Form Data", description='', )
    worker_count: int = 0
    team_count: int = 0
    job_count: int = 0

    zulip_is_active: Optional[bool] = False
    zulip_site: Optional[str] = ""
    zulip_user_name: Optional[str] = ""
    # zulip_password: Optional[str] = ""

    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    organization_status: str


class OrganizationPagination(DispatchBase):
    total: int
    items: List[OrganizationBaseRead] = []


class OrganizationRegistCode(DispatchBase):
    role: UserRoles
    team: TeamCreate
    worker:Optional[List[WorkerCreate]] = []
    switch_worker:Optional[bool] = False

class OrganizationStatusUpdate(DispatchBase):
    organization_status: str
