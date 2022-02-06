from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, Integer, String, Table, JSON
from sqlalchemy_utils import TSVectorType
from dispatch.database import Base
from dispatch.models import TimeStampMixin, DispatchBase
from pydantic import validator, Field


class Logs(Base, TimeStampMixin):
    id = Column(Integer, primary_key=True)
    title = Column(String)
    category = Column(String, nullable=False)
    content = Column(String)
    org_id = Column(Integer, nullable=False, default=-1)
    team_id = Column(Integer, nullable=False, default=-1)


class LogBase(DispatchBase):

    title: str = Field(
        default=None, title="Code", description="The  log title.",)
    category: Optional[str] = None
    content: Optional[str] = None
    org_id: int
    team_id: int


class LogCreate(LogBase):
    pass


class LogsRead(LogBase):
    id: int
    created_at: datetime
    updated_at: datetime
