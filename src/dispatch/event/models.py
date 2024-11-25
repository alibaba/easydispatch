from datetime import datetime
from uuid import UUID

from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy_utils import TSVectorType, JSONType

from dispatch.database import Base
from dispatch.models import DispatchBase, TimeStampMixin


# SQLAlchemy Model


# Pydantic Models
class EventBase(DispatchBase):
    uuid: UUID
    started_at: datetime
    ended_at: datetime
    source: str
    description: str
    details: Optional[dict]
    flex_form_data: Optional[dict]


class EventCreate(EventBase):
    pass


class EventUpdate(EventBase):
    pass


class EventRead(EventBase):
    pass


class EventNested(EventBase):
    id: int
