from typing import List, Optional

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import HTTPException

from dispatch.plugin import service as plugin_service
from dispatch.service import service as service_service
from dispatch.service_plugin import service as service_plugin_service

# from dispatch.service_plugin.models import ServicePlugin


from dispatch.service.models import Service
from dispatch.plugin.models import Plugin

from dispatch.plugins.bases.kandbox_planner import KandboxPlannerPluginType

from .models import (
    ServicePlugin,
    ServicePluginCreate,
    ServicePluginUpdate,
)


def get(*, db_session, service_plugin_id: int) -> Optional[ServicePlugin]:
    """
    Get a service_plugin by id.
    """
    return db_session.query(ServicePlugin).filter(ServicePlugin.id == service_plugin_id).first()


def get_by_plugin_id(*, db_session, plugin_id: int) -> Optional[ServicePlugin]:
    """
    Get a service_plugin by plugin contact id.
    """
    return db_session.query(ServicePlugin).filter(ServicePlugin.plugin_id == plugin_id).first()


def get_by_service_id_and_type(
    *, db_session, service_id: int, service_plugin_type: str
) -> List[Optional[ServicePlugin]]:
    """
    Get a service_plugin by service id and type name.
    """
    return (
        db_session.query(ServicePlugin)
        .filter(ServicePlugin.service_id == service_id)
        .filter(ServicePlugin.planning_plugin_type == service_plugin_type)
    )


def get_all(*, db_session) -> List[Optional[ServicePlugin]]:
    """
    Get all service_plugins.
    """
    return db_session.query(ServicePlugin)


def get_all_by_service_id(*, db_session, service_id: int) -> List[Optional[ServicePlugin]]:
    """Get all service_plugins by service id."""
    return db_session.query(ServicePlugin).filter(ServicePlugin.service_id == service_id)


def get_or_create(
    *, db_session, service_id: int, plugin_id: int, service_plugin_type: str,
) -> ServicePlugin:
    """Gets an existing service_plugin object or creates a new one."""
    service_plugin = (
        db_session.query(ServicePlugin)
        .filter(ServicePlugin.service_id == service_id)
        .filter(ServicePlugin.plugin_contact_id == plugin_id)
        .one_or_none()
    )

    if not service_plugin:
        # We get information about the plugin
        plugin = plugin_service.get(db_session=db_session, plugin_id=plugin_id)

        service_plugin_in = ServicePluginCreate(
            service_plugin_type=service_plugin_type, plugin=plugin
        )
        service_plugin = create(db_session=db_session, service_plugin_in=service_plugin_in)

    return service_plugin


def create(*, db_session, service_plugin_in: ServicePluginCreate) -> ServicePlugin:
    """
    Create a new service_plugin.
    """
    service = plugin = None
    # service = Service()
    if service_plugin_in.service:
        if service_plugin_in.service.org_id or service_plugin_in.service.org_id == 0:
            service = service_service.get_by_code_and_org_code(
                db_session=db_session, code=service_plugin_in.service.code, org_id=service_plugin_in.service.org_id
            )
        else:
            service = service_service.get_by_code(
                db_session=db_session, code=service_plugin_in.service.code
            )

    plugin = Plugin()
    if service_plugin_in.plugin:
        plugin = plugin_service.get_by_slug(
            db_session=db_session, slug=service_plugin_in.plugin.slug)

    if service is None or plugin is None:
        raise HTTPException(status_code=404, detail="service is None or plugin is None.")
    service_plugin = ServicePlugin(
        **service_plugin_in.dict(exclude={"service", "plugin", "config"}), service_id=service.id, plugin_id=plugin.id, config=plugin.config
    )

    db_session.add(service_plugin)
    db_session.commit()
    return service_plugin


def create_all(*, db_session, service_plugins_in: List[ServicePluginCreate]) -> List[ServicePlugin]:
    """
    Create a list of service_plugins.
    """
    service_plugins = [ServicePlugin(**t.dict()) for t in service_plugins_in]
    db_session.bulk_save_objects(service_plugins)
    db_session.commit()
    return service_plugins


def update(
    *, db_session, service_plugin: ServicePlugin, service_plugin_in: ServicePluginUpdate,
) -> ServicePlugin:
    """
    Updates a service_plugin.
    """

    if service_plugin_in.service:
        service = service_service.get_by_code(
            db_session=db_session, code=service_plugin_in.service.code)
        service_plugin.service = service

    if service_plugin_in.plugin:
        plugin = plugin_service.get_by_slug(
            db_session=db_session, slug=service_plugin_in.plugin.slug)
        service_plugin.plugin = plugin

    service_plugin_data = jsonable_encoder(service_plugin)

    update_data = service_plugin_in.dict(skip_defaults=True, exclude={"service", "plugin"})

    for field in service_plugin_data:
        if field in update_data:
            setattr(service_plugin, field, update_data[field])

    db_session.add(service_plugin)
    db_session.commit()
    return service_plugin


def delete(*, db_session, service_plugin_id: int):
    """
    Deletes a service_plugin.
    """
    service_plugin = (
        db_session.query(ServicePlugin).filter(ServicePlugin.id == service_plugin_id).first()
    )
    db_session.delete(service_plugin)
    db_session.commit()


def switch_agent_plugin_for_service(db_session, service_name="planner", agent_slug=""):
    the_planner_service = service_service.get_by_name(db_session=db_session, name=service_name)
    the_planner_service_agents = service_plugin_service.get_by_service_id_and_type(
        db_session=db_session,
        service_id=the_planner_service.id,
        service_plugin_type=KandboxPlannerPluginType.kandbox_agent,
    )
    for k_agent in the_planner_service_agents:
        service_plugin_service.delete(db_session=db_session, service_plugin_id=k_agent.id)

    """Fetches a given plugin """
    plugin = plugin_service.get_by_slug(db_session=db_session, slug=agent_slug)

    new_service_plugin = ServicePlugin(
        planning_plugin_type=KandboxPlannerPluginType.kandbox_agent,
        service=the_planner_service,
        plugin=plugin,
    )
    db_session.add(new_service_plugin)
    db_session.commit()
    return new_service_plugin
