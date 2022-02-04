from datetime import datetime
from uuid import UUID

from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy_utils import TSVectorType, JSONType

from dispatch.database import Base
from dispatch.models import DispatchBase, TimeStampMixin


# SQLAlchemy Model
class ItemInventoryEvent(Base, TimeStampMixin):
    # columns
    id = Column(Integer, primary_key=True)
    uuid = Column(SQLAlchemyUUID(as_uuid=True), unique=True, nullable=False)
    event_type = Column(String, nullable=False, default="Job")
    source = Column(String, nullable=False)
    description = Column(String, nullable=False)
    details = Column(JSONType, nullable=True)
    created_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)

    # relationships
    item_id = Column(Integer, nullable=False)
    item_code = Column(String, nullable=True)
    depot_id = Column(Integer, nullable=False)
    depot_code = Column(String, nullable=True)

    job_id = Column(Integer, nullable=True)
    job_code = Column(String, nullable=True)
    account_id = Column(Integer, nullable=True)
    account_code = Column(String, nullable=True)

    # full text search capabilities
    search_vector = Column(
        TSVectorType("source", "description", "item_code", weights={
                     "source": "A", "description": "B", "item_code": "C"})
    )


# Pydantic Models
class ItemInventoryEventBase(DispatchBase):
    uuid: UUID
    source: str
    description: str
    created_at: datetime
    ended_at: Optional[datetime]
    details: Optional[dict]
    #
    item_id: int
    depot_id: int
    #
    item_code: Optional[str]
    depot_code: Optional[str]

    job_id: Optional[int]
    job_code: Optional[str]
    account_id: Optional[int]
    account_code: Optional[str]


class ItemInventoryEventCreate(ItemInventoryEventBase):
    pass


class ItemInventoryEventUpdate(ItemInventoryEventBase):
    pass


class ItemInventoryEventRead(ItemInventoryEventBase):
    id: int
    pass


class ItemInventoryEventNested(ItemInventoryEventBase):
    id: int
