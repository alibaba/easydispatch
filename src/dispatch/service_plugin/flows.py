import logging

from dispatch.config import INCIDENT_PLUGIN_CONTACT_SLUG
from dispatch.database import SessionLocal
from dispatch.event import service as event_service
from dispatch.service import service as service_service
from dispatch.plugin import service as plugin_service


from dispatch.plugins.base import plugins

from dispatch.plugins.bases.kandbox_planner import KandboxPlannerPluginType

from .service import get_or_create


log = logging.getLogger(__name__)


def add_planning_plugin(
    plugin_id: id,
    service_id: id,
    db_session: SessionLocal,
    planning_plugin_type=KandboxPlannerPluginType.kandbox_env,
):
    """Adds a planning_plugin."""
    # We load the service
    service = service_service.get(db_session=db_session, service_id=service_id)
    # plugin = plugin_service.get(db_session=db_session, plugin_id=plugin_id)

    # We get or create a new service_plugin
    service_plugin = get_or_create(
        db_session=db_session,
        service_id=service.id,
        plugin_id=plugin_id,
        planning_plugin_type=planning_plugin_type,
    )

    service.planning_plugins.append(service_plugin)

    # We add and commit the changes
    db_session.add(service)
    db_session.commit()

    event_service.log(
        db_session=db_session,
        source="Kandbox Planning",
        description=f"{plugin.name} is added to service with type {planning_plugin_type}",
        # service_id=service_id,
    )

    return service_plugin


""" TODO
"""


def remove_planning_plugin(user_email: str, service_id: int, db_session: SessionLocal):
    """Removes a planning_plugin."""
    # We load the service
    service = service_service.get(db_session=db_session, service_id=service_id)

    # We get information about the plugin
    contact_plugin = plugins.get(INCIDENT_PLUGIN_CONTACT_SLUG)
    plugin_info = contact_plugin.get(user_email)
    plugin_fullname = plugin_info["fullname"]

    log.debug(f"Removing {plugin_fullname} from service {service.name}...")

    planning_plugin = get_by_service_id_and_email(
        db_session=db_session, service_id=service_id, code=user_email
    )

    if not planning_plugin:
        log.debug(
            f"Can't remove {plugin_fullname}. They're not an active planning_plugin of service {service.name}."
        )
        return False

    # We mark the planning_plugin as inactive
    planning_plugin.is_active = False

    # We make the planning_plugin renounce to their active roles
    planning_plugin_active_roles = planning_plugin_role_service.get_all_active_roles(
        db_session=db_session, planning_plugin_id=planning_plugin.id
    )
    for planning_plugin_active_role in planning_plugin_active_roles:
        planning_plugin_role_service.renounce_role(
            db_session=db_session, planning_plugin_role=planning_plugin_active_role
        )

    # We add and commit the changes
    db_session.add(planning_plugin)
    db_session.commit()

    event_service.log(
        db_session=db_session,
        source="Dispatch Core App",
        description=f"{planning_plugin.plugin.name} removed from service",
        service_id=service_id,
    )

    return True


def reactivate_planning_plugin(user_email: str, service_id: int, db_session: SessionLocal):
    """Reactivates a planning_plugin."""
    # We load the service
    service = service_service.get(db_session=db_session, service_id=service_id)

    # We get information about the plugin
    contact_plugin = plugins.get(INCIDENT_PLUGIN_CONTACT_SLUG)
    plugin_info = contact_plugin.get(user_email)
    plugin_fullname = plugin_info["fullname"]

    log.debug(f"Reactivating {plugin_fullname} on service {service.name}...")

    planning_plugin = get_by_service_id_and_email(
        db_session=db_session, service_id=service_id, code=user_email
    )

    if not planning_plugin:
        log.debug(
            f"{plugin_fullname} is not an inactive planning_plugin of service {service.name}."
        )
        return False

    # We mark the planning_plugin as active
    planning_plugin.is_active = True

    # We create a role for the planning_plugin
    planning_plugin_role_in = ServicePluginRoleCreate(role=ServicePluginRoleType.planning_plugin)
    planning_plugin_role = planning_plugin_role_service.create(
        db_session=db_session, planning_plugin_role_in=planning_plugin_role_in
    )
    planning_plugin.planning_plugin_role.append(planning_plugin_role)

    # We add and commit the changes
    db_session.add(planning_plugin)
    db_session.commit()

    event_service.log(
        db_session=db_session,
        source="Dispatch Core App",
        description=f"{plugin_fullname} reactivated",
        service_id=service_id,
    )

    return True
