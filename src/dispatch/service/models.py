from datetime import datetime
from typing import List, Optional
from sqlalchemy.ext.hybrid import hybrid_property

from sqlalchemy import Boolean, Column, ForeignKey, Integer, PrimaryKeyConstraint, String, Table
from sqlalchemy.orm import backref, relationship
from sqlalchemy_utils import TSVectorType

from dispatch.database import Base
from dispatch.models import DispatchBase, TermReadNested, TimeStampMixin



# SQLAlchemy models...
class Service(TimeStampMixin, Base):
    id = Column(Integer, primary_key=True)
    service_type = Column(String, default="realtime_heuristic_planner")  # RL, batch
    is_active = Column(Boolean, default=True)
    code = Column(String, unique=True)
    name = Column(String)
    description = Column(String)

    search_vector = Column(TSVectorType("code","name","description"))


# Pydantic models...
class ServiceBase(DispatchBase):
    code: str
    name: Optional[str] = None
    service_type: str = "realtime_heuristic_planner"
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ServiceCreate(ServiceBase):
    pass



class ServiceUpdate(ServiceBase):
    pass


class ServiceRead(ServiceBase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ServiceNested(ServiceBase):
    id: int


class ServicePagination(DispatchBase):
    total: int
    items: List[ServiceRead] = []
