from datetime import datetime

from typing import Optional, List

from sqlalchemy.orm import relationship
from sqlalchemy import Column, Boolean, String, Integer, ForeignKey, DateTime, event, JSON
from enum import Enum

from dispatch.database import Base
from dispatch.models import DispatchBase
from dispatch.plugin.models import PluginRead, PluginCreate

# To avoid circular model definition
from dispatch.service.models import ServiceRead, ServiceCreate


from dispatch.plugins.bases.kandbox_planner import KandboxPlannerPluginType


class ServicePlugin(Base):
    # columns
    id = Column(Integer, primary_key=True)

    # Kandbox
    planning_plugin_type = Column(
        String, nullable=False, default=KandboxPlannerPluginType.kandbox_env
    )

    org_id = Column(Integer, nullable=False, default=-1)
    # relationships
    service_id = Column(Integer, ForeignKey("service.id"))
    service = relationship("Service")
    plugin_id = Column(Integer, ForeignKey("dispatch_core.plugin.id"))
    plugin = relationship("Plugin")

    config = Column(JSON)  # Column(String, default='{"key_1":["skill_1"]}')


class ServicePluginBase(DispatchBase):
    planning_plugin_type: str


class ServicePluginCreate(ServicePluginBase):
    org_id: int = -1
    plugin: PluginCreate
    service: ServiceCreate
    config: dict = None
    planning_plugin_type: KandboxPlannerPluginType


class ServicePluginUpdate(ServicePluginCreate):
    pass


class ServicePluginRead(ServicePluginBase):
    id: int
    planning_plugin_type: str
    plugin: PluginRead
    service: ServiceRead
    config: dict = None


class ServicePluginPagination(DispatchBase):
    total: int
    items: List[ServicePluginRead] = []
