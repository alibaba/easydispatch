from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint, String, Table, JSON
from sqlalchemy.orm import relationship
from sqlalchemy_utils import TSVectorType
from dispatch.database import Base
from dispatch.models import TimeStampMixin, DispatchBase
from dispatch.service.models import ServiceCreate
from pydantic import validator, Field


class Team(Base, TimeStampMixin):
    id = Column(Integer, primary_key=True)
    code = Column(String, nullable=False)
    org_id = Column(Integer, nullable=False, default=0)
    name = Column(String)
    description = Column(String)
    # Two teams may share same service, leveraging same trained model and parameters
    service_id = Column(Integer, ForeignKey("service.id"))
    planner_service = relationship("Service")
    flex_form_data = Column(
        JSON,
        default={"travel_speed_km_hour": 40, "travel_min_minutes": 10, "planning_working_days": 2},
    )

    latest_env_kafka_offset = Column(Integer, default=0)
    latest_env_db_sink_offset = Column(Integer, default=0)
    # I'm not sure this needs to be set explictly rather than via a query
    jobs = relationship("Job", backref="teams")

    search_vector = Column(
        TSVectorType(
            "code",
            "name",
            "description",
            weights={
                "code": "A",
                "description": "B",
                "name": "C",
            },
        )
    )

    __table_args__ = (UniqueConstraint('code', 'org_id', name='uix_org_team_1'),)

    # code = Column(String, nullable=False)
    # 2020-08-09 13:18:47 , I have decided service->team. Each service belong to a team and in service, you can get_rl_planner_service_for_team_id (team.id). This is LRU cached instance. Maximum one RL service per team.
    """
    rl_planning_service_id = Column(Integer, ForeignKey("service.id"))
    rl_planning_service = relationship("Service")

    batch_planning_service_id = Column(Integer, ForeignKey("service.id"))
    batch_planning_service = relationship("Service")
    """


class TeamBase(DispatchBase):
    """ A team is the scope of one dispatching planner instance. The jobs in each team will be assigned to workers in the same team."""

    id: Optional[str] = None
    code: str = Field(
        default=None, title="Code", description="The unique team code.",)
    name: Optional[str]
    org_id: Optional[str] = None
    description: Optional[str]
    planner_service: Optional[ServiceCreate]
    flex_form_data: Optional[dict] = {}


class TeamCreate(TeamBase):
    pass


class TeamUpdate(TeamBase):
    latest_env_kafka_offset: Optional[int] = 0
    latest_env_db_sink_offset: Optional[int] = 0
    pass


class TeamRead(TeamBase):
    id: int
    planner_service: Optional[ServiceCreate]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class TeamPagination(DispatchBase):
    total: int
    items: List[TeamRead] = []
