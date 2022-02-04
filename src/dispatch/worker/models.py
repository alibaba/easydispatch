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
    id = Column(BigInteger, primary_key=True)
    code = Column(String, nullable=False,)
    name = Column(String)
    description = Column(String)  # , nullable=False
    is_active = Column(Boolean, default=True)

    team_id = Column(Integer, ForeignKey("team.id"))
    team = relationship("Team", backref="workers")
    org_id = Column(Integer, nullable=True, default=0)

    # Kandbox
    location = relationship("Location", backref="location_worker")
    location_id = Column(BigInteger, ForeignKey("location.id"))

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
    # relationship_owner_id = Column(Integer, ForeignKey("worker.id"))
    # relationship_owner = relationship("Worker", backref="workers")
    events = relationship("Event", backref="worker")

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


class WorkerCreate(WorkerBase):
    team: TeamCreate
    location: Optional[LocationCreate]


class WorkerUpdate(WorkerBase):
    team: TeamCreate
    location: Optional[LocationCreate]


class WorkerRead(WorkerBase):
    id: int
    team: Optional[TeamRead]
    location: Optional[LocationRead]


class WorkerPagination(DispatchBase):
    total: int
    items: List[WorkerRead] = []
