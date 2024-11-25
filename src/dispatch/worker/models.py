from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Table,
    BigInteger,
    DateTime,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql.schema import UniqueConstraint
from sqlalchemy.sql.sqltypes import ARRAY
from sqlalchemy_utils import TSVectorType

from dispatch.database import Base
from dispatch.location.models import LocationCreate, LocationRead
from dispatch.models import TimeStampMixin, DispatchBase, TermReadNested
from dispatch.team.models import TeamCreate, TeamRead
from dispatch.auth.models import DispatchUser, UserRead
from pydantic import BaseModel, Field

# Association tables for many to many relationships


DEFAULT_BUSINESS_HOUR = {
    "sunday": [{"open": "", "close": "", "id": "5ca5578b0c5c7", "isOpen": False}],
    "monday": [{"open": "0800", "close": "1700", "id": "5ca5578b0c5d1", "isOpen": True}],
    "tuesday": [{"open": "0800", "close": "1700", "id": "5ca5578b0c5d8", "isOpen": True}],
    "wednesday": [{"open": "0800", "close": "1700", "id": "5ca5578b0c5df", "isOpen": True}],
    "thursday": [{"open": "0800", "close": "1700", "id": "5ca5578b0c5e6", "isOpen": True}],
    "friday": [{"open": "0800", "close": "1700", "id": "5ca5578b0c5ec", "isOpen": True}],
    "saturday": [{"open": "", "close": "", "id": "5ca5578b0c5f8", "isOpen": False}],
}

class Worker(TimeStampMixin, Base):
    # id = Column(BigInteger)
    code = Column(String, primary_key=True,)
    name = Column(String)
    description = Column(String)  # , nullable=False
    is_active = Column(Boolean, default=True)
    
    team_id = Column(Integer, ForeignKey("team.id"))
    team = relationship("Team", backref="workers")
    org_id = Column(Integer, nullable=True, default=0)

    # Worker should not rely on locaiton. It should have it's own lat/long coordinates.
    # If a worker has complicated lat/long coordinates specification, like start from home in morning, office in afternoon. 
    # It should be implemented in flex_form data.

    # 
    location_code = Column(String, ForeignKey("location.code"), nullable=True, )
    location = relationship("Location", backref="location_worker")

    geo_longitude = Column(Float, nullable=True)
    geo_latitude = Column(Float, nullable=True)

    auto_planning = Column(Boolean, default=True)
    is_shift_started = Column(Boolean, default=False)    
    shift_start_datetime = Column(DateTime)  # null=True, blank=True,
    shift_duration_minutes = Column(Float)

    flex_form_data = Column(JSON, default={})
    business_hour = Column(JSON, default=DEFAULT_BUSINESS_HOUR)
    #  material part product  asset  item

    # auth_username = Column(String)  # map to column email in auth.user table

    dispatch_user_id = Column(Integer, ForeignKey("dispatch_core.dispatch_user.id"))
    dispatch_user = relationship("DispatchUser", backref="worker_auth")

    job_history_feature_data = Column(JSON, default={})

    # belongs to Workder+Location_affinity
    # served_location_gmm=models.CharField(max_length=2000, null=True, blank=True) # [1,2,'termite']

    # this is a self referential relationship lets punt on this for now.
    # events = relationship("WorkerEvent", backref="worker")

    # skills should be independent, basic information, outside of flex_form.
    skills = Column(ARRAY(String))
    # Only used for item/material based dispatching. Keep null for others.
    loaded_items = Column(ARRAY(String))

    search_vector = Column(
        TSVectorType(
            "code",
            "name",
            "description",
            search_vector=Column(
                TSVectorType("code", "name", "description",
                             weights={"code": "A", "name": "B", "description": "C"})
            )
        )
    )

    __table_args__ = (UniqueConstraint('code', 'org_id', name='uix_org_id_worker_code'),)


class WorkerBase(DispatchBase):
    """ A worker may have different names in different business problem, like technicians, service engieers, delivery couriers, postman etc. One worker can work on different jobs at different time. Each worker can work on only one job at each time."""

    code: str
    name: Optional[str]
    org_id: Optional[str] = None
    flex_form_data: dict = {}
    business_hour: dict = DEFAULT_BUSINESS_HOUR
    is_active: Optional[bool] = True
    # auth_username: Optional[str]
    dispatch_user: Optional[UserRead]
    description: Optional[str]
    skills: Optional[List[str]] = []
    loaded_items: Optional[List[str]] = []
    assigned_locations: Optional[List[LocationRead]] = []
    location: Optional[LocationCreate] = None
    geo_longitude: Optional[float] = None 
    geo_latitude: Optional[float] = None 
    is_shift_started: Optional[bool] = True
    shift_start_datetime: Optional[datetime] = None
    shift_duration_minutes: float = 480
    auto_planning: Optional[bool] = Field(
        default=False, title="Automatic Planning Flag", description='When a worker has auto_planning == True, the easydispatch engine will try to synchronize its changes to planning engine',)

    


class WorkerCreate(WorkerBase):
    team: TeamCreate


class WorkerUpdate(WorkerBase):
    team: TeamCreate
    update_new_information_only: bool = True



class WorkerUpdateBusinessHour(DispatchBase):
    code: str
    org_id: Optional[str] = None
    business_hour: dict = DEFAULT_BUSINESS_HOUR
    

class WorkerRead(WorkerBase):
    # id: int
    team: Optional[TeamRead]


class WorkerPagination(DispatchBase):
    total: int
    items: List[WorkerRead] = []
