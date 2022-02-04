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
from dispatch.models import TimeStampMixin, DispatchBase
from dispatch.depot.models import DepotCreate, DepotRead
from dispatch.item.models import ItemCreate, ItemRead
# Association tables for many to many relationships


#  material part product  asset  item
class ItemInventory(TimeStampMixin, Base):
    id = Column(BigInteger, primary_key=True)
    org_id = Column(Integer, nullable=False, default=0)

    item_id = Column(Integer, ForeignKey("item.id"))
    item = relationship("Item", backref="item_depot_inventory_item")
    depot_id = Column(Integer, ForeignKey("depot.id"))
    depot = relationship("Depot", backref="item_depot_inventory_depot")

    # Kandbox
    max_qty = Column(Float, nullable=False, default=1000)
    # The quantity reserved by planning engine and allocated to workers in different day-slots.
    allocated_qty = Column(Float, nullable=False, default=0)
    # Currently avaialbe quantity.
    curr_qty = Column(Float, nullable=False, default=0)

    # Real stock level should be : allocated_qty + curr_qty

    __table_args__ = (UniqueConstraint('item_id', "depot_id", 'org_id',
                      name='uix_org_id_inventory_item_depot'),)


class ItemInventoryBase(DispatchBase):
    """ A worker may have different names in different business problem, like technicians, service engieers, delivery couriers, postman etc. One worker can work on different jobs at different time. Each worker can work on only one job at each time."""

    org_id: int
    item: ItemRead
    depot: DepotRead

    max_qty: float = 0
    curr_qty: float = 0
    allocated_qty: float = 0


class ItemInventoryCreate(ItemInventoryBase):
    pass


class ItemInventoryUpdate(ItemInventoryBase):
    pass


class ItemInventoryRead(ItemInventoryBase):
    id: int


class ItemInventoryPagination(DispatchBase):
    total: int
    items: List[ItemInventoryRead] = []


class ItemInventorySelect(DispatchBase):
    text: str
    all: int
    input_value: int
