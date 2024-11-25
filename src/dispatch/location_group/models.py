from typing import Any, List, Optional
from pydantic import Field

from dispatch.worker.models import WorkerCreate, WorkerRead
from datetime import datetime
from sqlalchemy import (
    Table,
    Column,
    Integer,
    Float,
    String,
    ForeignKey,
    PrimaryKeyConstraint,
    JSON,
    BigInteger,
)
from sqlalchemy.orm import relationship
from sqlalchemy_utils import TSVectorType
from dispatch.database import Base
from dispatch.models import DispatchBase, TimeStampMixin
from dispatch.team.models import TeamCreate, TeamRead

# from dispatch.location.models import Location, LocationRead
from dispatch.auth.models import DispatchUser, UserRead

from sqlalchemy.sql.schema import UniqueConstraint

class LocationGroup(Base,TimeStampMixin):

    code = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    # geo_longitude = Column(Float, nullable=True)
    # geo_latitude = Column(Float, nullable=True)
    flex_form_data = Column(JSON, default={})

    team_id = Column(Integer, ForeignKey("team.id"), nullable=False)
    team = relationship("Team", backref="location_group2team")

    requested_primary_worker_code = Column(String, ForeignKey("worker.code"), nullable=True)
    requested_primary_worker = relationship("Worker", foreign_keys=[requested_primary_worker_code])

    replacement_start_day = Column(String, nullable=True)
    replacement_end_day = Column(String, nullable=True)
    replacement_worker_code = Column(String, ForeignKey("worker.code"), nullable=True)
    replacement_worker = relationship("Worker", foreign_keys=[replacement_worker_code])

    # assinged_locations = relationship(
    #     "Location", 
    #     backref="location_group",
    #     cascade='save-update' 
    # )

    org_id = Column(Integer, nullable=True, default=-1)

    search_vector = Column(
        TSVectorType(
            "code", 
            "name", 
            "requested_primary_worker_code",
            "replacement_worker_code",
            weights={"code": "A", "name": "B", 
                "requested_primary_worker_code":"C",
                "replacement_worker_code":"D",
            },
        )
    )

    # __table_args__ = (UniqueConstraint('code', 'org_id', name='uix_org_location_group_code'),)

# Pydantic models...


class LocationGroupBase(DispatchBase):
    """ A location_group group is used to group locations and can be assigned to a worker. 
    \n A location_group group is somtimes called route, routine in certain business.
    """
    code: str
    name: str = None
    flex_form_data: Any = Field(
        default={},
        title="Flexible Form Data",
        description="You can save all customized attributes into a flex_form_data.",
    )
    team: Optional[TeamCreate] = None

    replacement_start_day: str = None
    replacement_end_day: str = None
    requested_primary_worker: Optional[WorkerRead]
    replacement_worker: Optional[WorkerRead] = None


class LocationGroupCreate(LocationGroupBase):

    org_id: int = None
    # pass


class LocationGroupUpdate(LocationGroupBase):
    pass


class LocationGroupRead(LocationGroupBase):
    team: Optional[TeamRead]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class LocationGroupPagination(DispatchBase):
    total: int
    items: List[LocationGroupRead] = []


class LocationGroupBatchUpdate(DispatchBase):
    location_group_codes: List[str]

    requested_primary_worker: Optional[WorkerRead]
    replacement_start_day: str = None
    replacement_end_day: str = None
    replacement_worker: Optional[WorkerRead] = None


class LocationGroupBatchUpdateResult(DispatchBase):
    created_count: int = 0
    updated_count: int = 0
    failed_count: int = 0

