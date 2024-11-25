
from collections import Counter
from datetime import datetime
from typing import Any, List, Optional


from fastapi import FastAPI, File, UploadFile
from fastapi_permissions import Allow
from pydantic import BaseModel, validator, Field
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Table,
    select,
    Boolean,
    BigInteger,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from sqlalchemy.sql.schema import UniqueConstraint
from sqlalchemy.sql.sqltypes import ARRAY
from sqlalchemy_utils import TSVectorType

from dispatch.database import Base, SessionLocal
from dispatch.delivery_product.models import DeliveryPrice
from dispatch.order.enums import BusinessStatus, OrderStatus, OrderType
from dispatch.order_event.models import OrderEventRead
from dispatch.worker.models import WorkerCreate, WorkerRead
from dispatch.job.models import JobCreate, JobRead
from dispatch.models import DispatchBase, WorkerReadNested, TimeStampMixin
from dispatch.team.models import  TeamCreate, TeamRead
from dispatch.location.models import LocationRead


class Order(Base, TimeStampMixin):
    """ One order is a group of jobs. 
    The order in different business scenarios:
    -   food delivery. Original inspiration is each delivery order contains at least one pick up
        job and one drop off job.
    -   Shared work in field service. One work order may be splitted into several jobs, 
        and each job should be performed by one individual worker.
    -   Full lifecycle of parcel delivery. Simple parcel delivery can be implemented as a simple job. It 
        does not need order concept. However, if we want track life cycle, including to drop off 
        a parcel to locker/store. Or to pickback from the store/locker.
    """
    # 2022-12-29 09:20:25, removed ID just as job & worker. Using code as PK.
    # id = Column(BigInteger, primary_key=True)
    code = Column(String, nullable=False, primary_key=True)  
    team_id = Column(Integer, ForeignKey("team.id"), nullable=False)
    team = relationship("Team", backref="order_to_team_id")

    external_order_code = Column(String, nullable=True) 
    order_source_code = Column(String, nullable=True)  
    business_code = Column(String, nullable=True)  # code

    flex_form_data = Column(
        JSON, default={}
    )  
    scheduled_primary_worker_code = Column(String, ForeignKey("worker.code"), nullable=True)
    scheduled_primary_worker = relationship(
        "Worker",
        backref="order_scheduled",
        foreign_keys=[scheduled_primary_worker_code],
    )

    location_group_code = Column(String, ForeignKey("location_group.code"), nullable=True)

    external_business_status = Column(String, nullable=True)  # code
    status_code = Column(String, nullable=True)  # code
    business_order_status = Column(String, nullable=True)  # code
    reason_code = Column(String, nullable=True)  # code
    external_order_status = Column(String, nullable=True)  # code
    order_exception_status = Column(String, nullable=True)  # code
    order_type = Column(String, nullable=True, default=OrderType.PickDrop)  # code
    start_time = Column(DateTime)
    auto_planning = Column(Boolean, default=True)
    auto_commit = Column(Boolean, default=True)

    search_vector = Column(
        TSVectorType(
            "code",
            "external_order_code",
            "order_source_code",
            "status_code",
            "external_business_status",
            "reason_code"
        )
    )

    __table_args__ = (UniqueConstraint('code', name='uix_org_order_code'),)
# Pydantic models...


class OrderBase(DispatchBase):
    """A Order is the main object that easydispatch will actively manage. The Order may have different status as Unplanned, Inplanned, Planned.
    \n There maybe different types of Orders, especially the composite Order and the atom Order. Other high level objects like Appointments, Worker's Leave Event are also treated as Orders.
    \n
    """

    code: str = Field(
        title="Order Code", description='Order code is the unique identify for this Order. It must be unique across all teams',)
    external_order_code: Optional[str] = None
    order_source_code: Optional[str] = None
    
    business_code: Optional[str] = None
    flex_form_data: Any = Field(
        default={}, 
        title="Flexible Form Data", 
        description="""You can save all customized Order attributes into a flex_form_data. 
            Those data will be used by dispatching rule plugins to validate the worker-Order assignment.""",
        )
    
    external_business_status: Optional[str] = None    
    status_code: Optional[str] = None

    business_order_status: Optional[str] = None
    reason_code: Optional[str] = None
    external_order_status: Optional[str] = None
    order_exception_status :Optional[str] = None
    order_type: Optional[str] = None
    start_time: Optional[datetime] = None
    scheduled_primary_worker: Optional[WorkerCreate]=None
    location_group_code: Optional[str]=None 
                             
    env: Optional[str] = None
    is_deleted: Optional[int] = None
    auto_planning: bool=False
    auto_commit: bool=False

class OrderCreate(OrderBase):
    team: TeamCreate
    # Those two are used when order_type == pickdrop
    job_list: Optional[List[JobCreate]] = []
    # location_list: Optional[List] = []
    target_worker: str = None
    overwrite_max_orders_limit: bool = False

class OrderUpdate(OrderBase):
    # Order_priority: OrderPriorityBase
    # Order_type: OrderTypeBase
    # id: int
    team: TeamCreate
    # Job should be updatd from job services, not order services. 2022-11-19 04:11:56 
    job_list: Optional[List[JobCreate]] 


class OrderRead(OrderBase): 
    team: Optional[TeamRead]
    job_list: Optional[List[JobCreate]] = [] 
    events: Optional[List[OrderEventRead]] = []
    scheduled_primary_worker: Optional[WorkerRead]
    tpl_region: Optional[str] = ""
    
    

class OrderPagination(DispatchBase):
    total: int
    items: List[OrderRead] = []
    not_find_code:List[str] = []

class OrderSelect(DispatchBase):
    items: List[str] = []

class OrderRelatedBase(DispatchBase):
    order_code: str
    package_type:str=None
    customer_address:str=None
    customer_zipcode:str =None
    customer_name:str=None
    customer_phone_pumber:str=None
    scheduled_start_datetime:datetime=None
    scheduled_primary_worker: Optional[WorkerRead]=None
    package_code :str=None
    length:float=None
    width:float=None
    height:float=None
    volume :float=None
    weight :float=None
    location :Optional[LocationRead]=None
    job_reschedule_times :Optional[LocationRead]=None
    file_code_in :List[str] = []
    delete_file_code_list :List[str] = []
    images_dict:List[Any] = []
    problem_notes :Optional[str] =None
    tpl_region: Optional[str] = ""
    delivery_price: List[DeliveryPrice]=[]


class OrderRelatedUpdate(DispatchBase):
    # order_code: str
    order_code: str=None
    business_order_status:str=None
    reason_code:str=None
    problem_notes:str=None
    file_code_in:List[str] = []
    delete_file_code_list:List[str] = []
    locationId:int=None
    customerAddress:str=None
    length:float=None
    width:float=None
    height:float=None
    volume :float=None
    weight :float=None
    customer_phone_pumber:str=None
    tpl_region: str = ""

class ImagesOss(DispatchBase):
    scenarioCode: str=None
    fileSize:int=None
    fileName:str=None


class UploadOssFile(DispatchBase):
    url:str=None
    accessId:str=None
    callback:str=None
    dir:str=None
    expire:str=None    
    key:str=None
    OSSAccessKeyId:str=None
    policy:str=None
    signature:str=None
    success_action_status:str=None
    images_oss:str=None


class RedliverResponse(DispatchBase):
    status:int=1
    message:str=''
class RedliverRequest(DispatchBase):
    order_code: str=None


class DownloadOrder(DispatchBase):
    q:str = None
    scheduled_primary_worker: Optional[WorkerRead] 
    business_order_status: List[str] = []
    tpl_region: List[str] = []
class BatchSearchOrder(DispatchBase):
    q:str = None
    scheduled_primary_worker: Optional[WorkerRead] 
    business_order_status: List[str] = []
    tpl_region: List[str] = []
    page: int=1
    itemsPerPage:int=10
    sortBy: List[str] = []
    descending: List[bool] = []

class OrderDownloadHistory(Base, TimeStampMixin):
    id = Column(BigInteger, primary_key=True)
    dispatch_user_id = Column(Integer, ForeignKey("dispatch_core.dispatch_user.id"))
    dispatch_user = relationship("DispatchUser", backref="order_download_auth")
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    status = Column(String, nullable=False)  
    file_location = Column(String, nullable=False)
    created_date = Column(DateTime, default=datetime.utcnow)
    expiry_date = Column(DateTime, default=datetime.utcnow)

class DownloadHistoryResponse(DispatchBase):
    start_time: str = None
    end_time: str = None
    status: str = None
    file_location: str = None
    created_date: str = None
    expiry_date: str = None
    disabled: Optional[bool]

class OrderDownloadHistoryCreate(DispatchBase):
    dispatch_user_id: int = None
    start_time: str = None
    end_time: str = None
    status: str = None
    file_location: str = None
    created_date: str = None
    expiry_date: str = None

class DownloadHistoryPagination(DispatchBase):
    total: int
    items: List[DownloadHistoryResponse] = []







default_job_status = {"job_status": "toDo","job_track_status":"notStarted"}