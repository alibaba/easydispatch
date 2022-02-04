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
from dispatch.depot.models import DepotCreate, DepotRead
# Association tables for many to many relationships


#  material part product  asset  item
class Item(TimeStampMixin, Base):
    id = Column(BigInteger, primary_key=True)
    code = Column(String, nullable=False,)
    name = Column(String)
    description = Column(String)  # , nullable=False
    is_active = Column(Boolean, default=True)

    org_id = Column(Integer, nullable=False, default=0)
    # In meter cubical
    volume = Column(Float, nullable=True, default=0.001)
    # In KG
    weight = Column(Float, nullable=True, default=1)

    flex_form_data = Column(JSON, default={})

    search_vector = Column(
        TSVectorType(
            "code",
            "name",
            "description",
        )
    )

    __table_args__ = (UniqueConstraint('code', 'org_id', name='uix_org_id_item_code'),)


class ItemBase(DispatchBase):
    """ A worker may have different names in different business problem, like technicians, service engieers, delivery couriers, postman etc. One worker can work on different jobs at different time. Each worker can work on only one job at each time."""

    code: str
    org_id: int
    name: Optional[str]
    description: Optional[str]

    flex_form_data: dict = {}
    is_active: Optional[bool] = True
    # In meter cubical
    volume: float = 0
    # In KG
    weight: float = 0


class ItemCreate(ItemBase):
    pass


class ItemUpdate(ItemBase):
    pass


class ItemRead(ItemBase):
    id: int


class ItemPagination(DispatchBase):
    total: int
    items: List[ItemRead] = []
