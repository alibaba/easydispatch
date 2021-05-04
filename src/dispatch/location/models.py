from typing import List, Optional

from sqlalchemy import Table, Column, Integer, Float, String, ForeignKey, PrimaryKeyConstraint, JSON
from sqlalchemy.orm import relationship
from sqlalchemy_utils import TSVectorType

from dispatch.database import Base
from dispatch.models import (
    DispatchBase,
    TermNested,
    TermReadNested,
)


class Location(Base):
    id = Column(Integer, primary_key=True)

    location_code = Column(String, unique=True)
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

    search_vector = Column(
        TSVectorType(
            "location_code",
            "geo_address_text",
            weights={"location_code": "A", "geo_address_text": "B"},
        )
    )


# Pydantic models...
class LocationBase(DispatchBase):
    # kandbox planner
    location_code: str
    geo_longitude: float
    geo_latitude: float
    # description: Optional[str] = None
    geo_address_text: str = None
    geo_json: dict = None


class LocationCreate(LocationBase):
    pass


class LocationUpdate(LocationBase):
    pass


class LocationRead(LocationBase):
    id: int


class LocationPagination(DispatchBase):
    total: int
    items: List[LocationRead] = []
