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
from sqlalchemy_utils import TSVectorType

from dispatch.database import Base
from dispatch.location.models import LocationCreate, LocationRead
from dispatch.models import TimeStampMixin, DispatchBase
# Association tables for many to many relationships


#  material part product  asset  depot
class Depot(TimeStampMixin, Base):
    id = Column(BigInteger, primary_key=True)
    code = Column(String, nullable=False,)
    name = Column(String)
    description = Column(String)  # , nullable=False
    is_active = Column(Boolean, default=True)

    org_id = Column(Integer, nullable=True, default=0)
    max_volume = Column(Integer, nullable=True, default=0)
    max_weight = Column(Integer, nullable=True, default=0)
    #
    location = relationship("Location", backref="location_depot")
    location_id = Column(BigInteger, ForeignKey("location.id"))

    flex_form_data = Column(JSON, default={})

    search_vector = Column(
        TSVectorType(
            "code",
            "name",
            "description",
            weights={"email": "A", "full_name": "B"},
        )
    )

    __table_args__ = (UniqueConstraint('code', 'org_id', name='uix_org_id_depot_code'),)


class DepotBase(DispatchBase):
    """ A worker may have different names in different business problem, like technicians, service engieers, delivery couriers, postman etc. One worker can work on different jobs at different time. Each worker can work on only one job at each time."""

    code: str
    org_id: int
    name: Optional[str]
    description: Optional[str]

    flex_form_data: dict = {}
    is_active: Optional[bool] = True
    # In meter cubical
    max_volume: float = 0
    # In KG
    max_weight: float = 0
    location: LocationCreate


class DepotCreate(DepotBase):
    pass


class DepotUpdate(DepotBase):
    pass


class DepotRead(DepotBase):
    id: int


class DepotPagination(DispatchBase):
    total: int
    items: List[DepotRead] = []
