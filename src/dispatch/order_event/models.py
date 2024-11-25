from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, JSON,ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy_utils import TSVectorType
from uuid import UUID

from dispatch.database import Base
from dispatch.models import DispatchBase, TimeStampMixin


class OrderEvent(Base,TimeStampMixin):
    id = Column(Integer,primary_key=True)
    # 事件的类型，比如创建任务，创建订单，同步订单成功，同步订单失败等。
    event_type = Column(String, nullable=False, default = "status_change")
    uuid = Column(SQLAlchemyUUID(as_uuid=True), unique=True, nullable=False)
    order_code = Column(String, ForeignKey("order.code"), nullable=False)
    order = relationship("Order", backref="order_event_id")
    linked_job_id = Column(String, nullable=True)

    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    source = Column(String)
    description = Column(String)

    flex_data = Column(
        JSON, default={}
    )

    search_vector = Column(
        TSVectorType("source", "description", weights={"source": "A", "description": "B"})
    )



# Pydantic Models
class OrderEventBase(DispatchBase):
    uuid: UUID
    event_type:str
    order_code: str
    linked_job_id:str = None
    started_at: datetime
    ended_at: datetime
    source: str
    description: str = ""
    flex_data: Optional[dict]


class OrderEventCreate(OrderEventBase):
    pass


class OrderEventUpdate(OrderEventBase):
    pass


class OrderEventRead(OrderEventBase):
   pass
