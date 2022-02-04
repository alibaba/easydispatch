
import os
import logging
import time
import shortuuid
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

from sqlalchemy import text
from sqlalchemy.schema import CreateSchema
from sqlalchemy_utils import create_database, database_exists

from dispatch import config, fulltext
from dispatch.common.utils.cli import install_plugins
from dispatch.database import Base, sessionmaker
from dispatch.database_util.enums import DISPATCH_ORGANIZATION_SCHEMA_PREFIX
from dispatch.database_util.org_config import team_flex_form_schema, worker_flex_form_schema, job_flex_form_schema
from dispatch.org.models import Organization
from dispatch.plugin.models import PluginCreate
from dispatch.service.models import ServiceCreate

from dispatch.service import service as plannerService
from dispatch.service_plugin import service as pluginService
from dispatch.service_plugin.models import ServicePluginCreate
from dispatch.team import service as teamService
from dispatch.team.models import TeamCreate
log = logging.getLogger(__file__)

SHORTUUID = shortuuid.ShortUUID(alphabet="0123456789")


def version_schema():
    """Applies alembic versioning to schema."""

    # add it to alembic table
    alembic_path = os.path.join(os.path.dirname(os.path.realpath(
        __file__).replace('database_util/', '')), "alembic.ini")
    script_location = os.path.join(os.path.dirname(os.path.realpath(
        __file__).replace('database_util/', '')), "alembic")
    alembic_cfg = AlembicConfig(alembic_path)
    alembic_cfg.set_main_option("script_location", script_location)
    alembic_command.stamp(alembic_cfg, "head")


def version_schema_new(script_location: str):
    """Applies alembic versioning to schema."""

    # add it to alembic table
    alembic_cfg = AlembicConfig(config.ALEMBIC_INI_PATH)
    alembic_cfg.set_main_option("script_location", script_location)
    alembic_command.stamp(alembic_cfg, "head")


def get_core_tables():
    """Fetches tables that belong to the 'dispatch_core' schema."""
    core_tables = []
    for _, table in Base.metadata.tables.items():
        if table.schema == "dispatch_core":
            core_tables.append(table)
    return core_tables


def get_tenant_tables():
    """Fetches tables that belong to their own tenant tables."""
    tenant_tables = []
    for _, table in Base.metadata.tables.items():
        if not table.schema or table.schema != "dispatch_core":
            tenant_tables.append(table)
    return tenant_tables


def init_database(engine):
    """Initializes the database."""
    if not database_exists(str(config.SQLALCHEMY_DATABASE_URI)):
        create_database(str(config.SQLALCHEMY_DATABASE_URI))

    schema_name = "dispatch_core"
    if not engine.dialect.has_schema(engine, schema_name):
        with engine.connect() as connection:
            connection.execute(CreateSchema(schema_name))

    tables = get_core_tables()

    Base.metadata.create_all(engine, tables=tables)

    version_schema_new(script_location=config.ALEMBIC_CORE_REVISION_PATH)
    setup_fulltext_search(engine, tables)
    # setup an required database functions
    session = sessionmaker(bind=engine)
    db_session = session()

    # default organization
    organization = (
        db_session.query(Organization).filter(Organization.code == "default").one_or_none()
    )
    if not organization:
        org_id = SHORTUUID.random(length=9)
        organization = Organization(code="default", id=org_id,
                                    max_nbr_jobs=100, max_nbr_workers=10, max_nbr_teams=2, team_flex_form_schema=team_flex_form_schema,
                                    worker_flex_form_schema=worker_flex_form_schema, job_flex_form_schema=job_flex_form_schema)
    install_plugins()
    db_session.add(organization)
    db_session.commit()

    init_schema(engine=engine, organization=organization)


def init_schema(*, engine, organization: Organization):
    """Initializes a new schema."""

    schema_name = f"{DISPATCH_ORGANIZATION_SCHEMA_PREFIX}_{organization.code}"
    if not engine.dialect.has_schema(engine, schema_name):
        with engine.connect() as connection:
            connection.execute(CreateSchema(schema_name))

    # set the schema for table creation
    tables = get_tenant_tables()

    schema_engine = engine.execution_options(
        schema_translate_map={
            None: schema_name,
        }
    )

    Base.metadata.create_all(schema_engine, tables=tables)

    # put schema under version control
    version_schema_new(script_location=config.ALEMBIC_TENANT_REVISION_PATH)

    with engine.connect() as connection:
        # we need to map this for full text search as it uses sql literal strings
        # and schema translate map does not apply
        for t in tables:
            t.schema = schema_name
        setup_fulltext_search(connection, tables)

    session = sessionmaker(bind=schema_engine)
    db_session = session()

    organization = db_session.merge(organization)
    db_session.add(organization)
    # create any required default values in schema here
    #
    #
    # create defaultplanner
    service = plannerService.get_by_code(db_session=db_session, code='default_planner')
    if not service:
        try:
            planner = ServiceCreate(code='default_planner',
                                    name="default_planner", is_active=True, org_id=organization.id)
            plannerService.create(db_session=db_session, service_in=planner)
        except Exception as e:
            log.error(e)

        # create defaultTeam
        try:
            env_start_day = time.strftime("%Y%m%d", time.localtime())
            flex_form_data = {"env_start_day": env_start_day, "planning_working_days": 3, "scoring_factor_standard_travel_minutes": 90, "job_address_flag": True, "holiday_days": "",
                              "default_requested_primary_worker_code": "", "respect_initial_travel": False, "worker_job_min_minutes": 1, "horizon_start_minutes": 1925,
                              "travel_speed_km_hour": 19.8, "travel_min_minutes": 5, "job_icon": "fa-user", "worker_icon": "fa-taxi", }
            default_team = TeamCreate(id=organization.id, code='default_team', name='default_team', org_id=organization.id,
                                      description='', planner_service=planner, flex_form_data=flex_form_data)
            teamService.create(db_session=db_session, team_contact_in=default_team)
        except Exception as e:
            log.error(e)

        # add plugin service
        plugin_service_mapping = {
            "kandbox_ortools_cvrptw_1days_optimizer": "kandbox_batch_optimizer",
            "kandbox_heuristic_realtime_agent": "kandbox_agent",
            "kandbox_rule_requested_skills": "kandbox_rule",
            "job2slot_dispatch_env_proxy": "kandbox_env_proxy",
            "kanbox_planner_routing_haversine_proxy": "kandbox_routing_adapter",
        }
        for slug, planning_plugin_type in plugin_service_mapping.items():
            try:
                plugin_batch = PluginCreate(slug=slug, title='', author='',
                                            author_url='', type='', enabled=False, description='', config={}, config_form_spec={})
                service_plugin_in = ServicePluginCreate(
                    org_id=organization.id, plugin=plugin_batch, service=planner, planning_plugin_type=planning_plugin_type)
                pluginService.create(
                    db_session=db_session,
                    service_plugin_in=service_plugin_in,
                )
            except Exception as e:
                log.error(e)

    db_session.commit()
    return organization


def setup_fulltext_search(connection, tables):
    """Syncs any required fulltext table triggers and functions."""
    # parsing functions
    function_path = os.path.join(
        os.path.dirname(os.path.abspath(fulltext.__file__)), "expressions.sql"
    )
    connection.execute(text(open(function_path).read()))

    for table in tables:
        table_triggers = []
        for column in table.columns:
            if column.name.endswith("search_vector"):
                if hasattr(column.type, "columns"):
                    table_triggers.append(
                        {
                            "conn": connection,
                            "table": table,
                            "tsvector_column": "search_vector",
                            "indexed_columns": column.type.columns,
                        }
                    )
                else:
                    log.warning(
                        f"Column search_vector defined but no index columns found. Table: {table.name}"
                    )

        for trigger in table_triggers:
            fulltext.sync_trigger(**trigger)
