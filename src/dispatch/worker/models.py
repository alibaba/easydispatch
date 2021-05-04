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
)
from sqlalchemy.orm import relationship
from sqlalchemy_utils import TSVectorType

from dispatch.database import Base
from dispatch.location.models import LocationCreate, LocationRead
from dispatch.models import TimeStampMixin, DispatchBase, TermReadNested
from dispatch.team.models import TeamCreate, TeamRead

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
    id = Column(Integer, primary_key=True)
    code = Column(String)
    name = Column(String)
    description = Column(String)  # , nullable=False
    is_active = Column(Boolean, default=True)

    team_id = Column(Integer, ForeignKey("team.id"))
    team = relationship("Team", backref="workers")

    # Kandbox
    location = relationship("Location", backref="location_worker")
    location_id = Column(Integer, ForeignKey("location.id"))

    flex_form_data = Column(JSON, default={})
    job_history_feature_data = Column(JSON, default={})
    business_hour  = Column(JSON, default=DEFAULT_BUSINESS_HOUR)


    auth_username = Column(String)  # map to email@auth.user


    # belongs to Workder+Location_affinity
    # served_location_gmm=models.CharField(max_length=2000, null=True, blank=True) # [1,2,'termite']

    # this is a self referential relationship lets punt on this for now.
    # relationship_owner_id = Column(Integer, ForeignKey("worker.id"))
    # relationship_owner = relationship("Worker", backref="workers")
    events = relationship("Event", backref="worker")

    search_vector = Column(
        TSVectorType(
            "code",
            "name",
            "description",
            "auth_username", 
        )
    )


class WorkerBase(DispatchBase):
    code: str
    name: Optional[str]
    flex_form_data: dict = {}
    business_hour: dict = DEFAULT_BUSINESS_HOUR
    is_active: Optional[bool] = True 
    auth_username: Optional[str]

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
