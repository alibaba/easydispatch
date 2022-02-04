from typing import List, Optional

from sqlalchemy import Table, Column, Integer, Float, String, ForeignKey, PrimaryKeyConstraint, JSON, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy_utils import TSVectorType

from dispatch.database import Base
from dispatch.models import (
    DispatchBase,
    TermNested,
    TermReadNested,
)
from dispatch.team.models import TeamCreate, TeamRead
from dispatch.auth.models import DispatchUser, UserRead

from sqlalchemy.sql.schema import UniqueConstraint


class Location(Base):
    id = Column(BigInteger, primary_key=True)

    location_code = Column(String, nullable=False)
    geo_longitude = Column(Float, nullable=False)
    geo_latitude = Column(Float, nullable=False)
    geo_address_text = Column(String)
    geo_json = Column(JSON)

    # LocationJobHistoryFeatures

    # job_historical_worker_service_dict
    job_history_feature_data = Column(JSON, default={})
    job_count = Column(Integer, default=0)
    # list_requested_worker_code = models.CharField(null=True, blank=True, max_length=4000)
    avg_actual_start_minutes = Column(Float, default=0)
    avg_actual_duration_minutes = Column(Float, default=0)
    avg_days_delay = Column(Float, default=0)
    stddev_days_delay = Column(Float, default=0)

    dispatch_user_id = Column(Integer, ForeignKey("dispatch_core.dispatch_user.id"))
    dispatch_user = relationship("DispatchUser", backref="location_auth")
    team_id = Column(Integer, ForeignKey("team.id"), nullable=True)
    team = relationship("Team", backref="location2team")
    org_id = Column(Integer, nullable=True, default=-1)

    search_vector = Column(
        TSVectorType(
            "location_code",
            "geo_address_text",
            weights={"location_code": "A", "geo_address_text": "B"},
        )
    )

    __table_args__ = (UniqueConstraint('location_code', 'org_id', name='uix_org_location_code'),)

# Pydantic models...


class LocationBase(DispatchBase):
    """ A location is where a worker or a job is positioned on a map. The longitude and latitude are mandatory and textual addresses are optional.
    \n A location is treated as first class citizen in parallel to job because we see that there are repeated jobs for same customer and location. The historical assignment patterns can be learned on location level.
    """
    id: int = None
    location_code: str = None
    geo_longitude: float = None
    geo_latitude: float = None
    # description: Optional[str] = None
    geo_address_text: str = None
    geo_json: dict = None
    dispatch_user: Optional[UserRead]
    team: Optional[TeamCreate] = None


class LocationCreate(LocationBase):
    
    org_id: int = None


class LocationUpdate(LocationBase):
    pass


class LocationRead(LocationBase):
    id: int
    team: Optional[TeamRead]


class LocationPagination(DispatchBase):
    total: int
    items: List[LocationRead] = []
