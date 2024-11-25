from typing import Optional
from sqlalchemy import Column, Integer, Numeric, String, DateTime, JSON,ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from sqlalchemy.dialects.postgresql import UUID as SQLAlchemyUUID
from sqlalchemy_utils import TSVectorType
from uuid import UUID

from typing import Any, List, Optional
from dispatch.database import Base
from dispatch.models import DispatchBase, TimeStampMixin

'''

{
  "message_scenario": "sms",
  "message_type": "delivery_order",
  "message_category": "D01",
  "message_businiss_type": "Order Delivery Time Change",
  "message_template_content": "The Status of order ${businessId} has been changed to ${targetBusinessInfo} by HQ, please contact HQ asap."
}
'''

class MsgTemplate(Base,TimeStampMixin):
    id = Column(Integer,primary_key=True)
    message_code = Column(String, nullable=False)
    message_scenario =Column(String,nullable=False)
    message_type= Column(String, nullable=False)
    message_category= Column(String, nullable=False)
    message_business_type= Column(String, nullable=False)
    message_template_content= Column(String, nullable=False)
    message_trigger_time= Column(DateTime, nullable=True)

    # search_vector = Column(TSVectorType("message_code", "message_scenario","message_businiss_type","message_category","message_type"))



class MsgTemplateBase(DispatchBase):
    
    message_code: str = None
    message_scenario: str= None
    message_type: str= None
    message_category: str= None
    message_business_type: str= None
    message_template_content: str= None    
    message_trigger_time: Optional[datetime] =None   
    created_at: Optional[datetime] =None
    updated_at: Optional[datetime] =None




class MsgTemplateCreate(MsgTemplateBase):
    pass

class MsgTemplateUpdate(MsgTemplateBase):
    id: int

class MsgTemplateRead(MsgTemplateBase):
    id: int

class MsgTemplatePagination(DispatchBase):
    total: int
    items: List[MsgTemplateRead] = []

