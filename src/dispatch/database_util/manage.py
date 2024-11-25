from datetime import datetime, timedelta
import os
import logging
import time
import shortuuid
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi.exceptions import HTTPException
from sqlalchemy import create_engine, inspect, text 
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateSchema
from sqlalchemy_utils import create_database, database_exists
# from dispatch.search.fulltext import make_searchable
from dispatch.search import fulltext


from dispatch import config 
from dispatch.common.utils.cli import install_plugins, import_database_models

from dispatch.database import Base, sessionmaker
from dispatch.database_util.enums import DISPATCH_ORGANIZATION_SCHEMA_PREFIX
from dispatch.database_util.org_config import (
    # team_flex_form_schema,
    # worker_flex_form_schema,
    # job_flex_form_schema,
    get_flex_form_schema,
    default_team_flex_form_data,
    default_rust_env_config_data,
)
import copy
from dispatch.org.enums import UserRoles
from dispatch.org.models import Organization
from dispatch.plugin.models import PluginCreate
from dispatch.planner_service.models import ServiceCreate
from dispatch.auth.models import DispatchUser, hash_password

from dispatch.planner_service import service as planner_service
from dispatch.planner_plugin import service as plugin_service
from dispatch.planner_plugin.models import ServicePluginCreate
from dispatch.team import service as team_service
from dispatch.team.models import TeamCreate

log = logging.getLogger(__file__)

SHORTUUID = shortuuid.ShortUUID(alphabet="0123456789")


def version_schema():
    """Applies alembic versioning to schema."""

    # add it to alembic table
    alembic_path = os.path.join(
        os.path.dirname(os.path.realpath(__file__).replace("database_util/", "")), "alembic.ini"
    )
    script_location = os.path.join(
        os.path.dirname(os.path.realpath(__file__).replace("database_util/", "")), "alembic"
    )
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


def get_tenant_tables(table_name = None):
    """Fetches tables that belong to their own tenant tables."""
    tenant_tables = []
    for _, table in Base.metadata.tables.items():
        if not table.schema or table.schema != "dispatch_core":
            if table_name is not None:
                if table.name != table_name:
                    continue
            table.schema = None
            tenant_tables.append(table)
    return tenant_tables


def init_database(engine):
    """Initializes the database."""
    import_database_models()
    if not database_exists(str(config.SQLALCHEMY_DATABASE_URI)):
        create_database(str(config.SQLALCHEMY_DATABASE_URI))

    schema_name = "dispatch_core"
    # insp = inspect(engine)
    # if not insp.has_schema(schema_name):
    if not engine.dialect.has_schema(engine,schema_name):
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema_name))

    tables = get_core_tables()
    Base.metadata.create_all(engine, tables=tables)

    version_schema_new(script_location=config.ALEMBIC_CORE_REVISION_PATH)
    setup_fulltext_search(engine, tables)
    # setup an required database functions
    session = sessionmaker(bind=engine)
    db_session = session()

    install_plugins()
    org_list_to_create = ["root"] #  "pytest"  
    # default organization
    for org_code in org_list_to_create:
        organization = (
            db_session.query(Organization).filter(Organization.code == org_code).one_or_none()
        )
        if not organization:
            # org_id = SHORTUUID.random(length=9)
            organization = Organization(
                code=org_code,
                # id=org_id,
                max_nbr_jobs=100,
                max_nbr_workers=10,
                max_nbr_teams=2,
                team_flex_form_schema= get_flex_form_schema(planner_type="common",schema_type="team",),#team_flex_form_schema,
                worker_flex_form_schema=get_flex_form_schema(planner_type="common",schema_type="worker",),#worker_flex_form_schema,
                job_flex_form_schema=get_flex_form_schema(planner_type="common",schema_type="job",),#job_flex_form_schema,
            )
            db_session.add(organization)
            db_session.commit()

            # new_org = 
            root_user = DispatchUser(
                email = f"{org_code}@easydispatch.uk",
                password = hash_password(config.DISPATCH_JWT_SECRET),
                role = UserRoles.SYSTEM,
                is_org_owner = True,
                default_team_id = 1,
                # org_id
            )
            db_session.add(root_user)
            db_session.commit()

        init_schema(engine=engine, organization=organization)

def init_planner_service(schema_session, org_id):

    # if not service:
    for planner_code in config.PLANNER_TEMPLATE_DICT.keys():
        try:
            planner = ServiceCreate(
                code=planner_code,
                name=planner_code,
                is_active=True,
                # org_id=org_id,
            )
            p_service = planner_service.create(db_session=schema_session, service_in=planner)
        except Exception as e:
            log.error(f"failed to create planner service: {str(e)}")
        # add plugins to this service
        plugin_service_mapping = config.PLANNER_TEMPLATE_DICT[planner_code]
        for slug, planning_plugin_type in plugin_service_mapping.items():
            try:
                plugin_batch = PluginCreate(
                    slug=slug,
                    title="",
                    author="",
                    author_url="",
                    type="",
                    enabled=False,
                    description="",
                    config={},
                    config_form_spec={},
                )
                service_plugin_in = ServicePluginCreate(
                    # org_id=org_id,
                    plugin=plugin_batch,
                    service=planner,
                    planning_plugin_type=planning_plugin_type,
                )
                plugin_service.create(
                    db_session=schema_session,
                    service_plugin_in=service_plugin_in,
                )
            except HTTPException as e:
                log.error(f"failed to create service plugins , error:HTTPException : {str(e.detail)}")

            except Exception as e:
                log.error(f"failed to create service plugins: {str(e)}")


def init_schema(*, engine, organization: Organization, planner_code = "single_planner"):
    """Initializes a new schema."""
    import_database_models()
    schema_name = f"{DISPATCH_ORGANIZATION_SCHEMA_PREFIX}_{organization.code}"
    # insp = inspect(engine)
    # 2023-12-30 18:56:46 Migrated to sqlalchemy 2.0
    # if not insp.has_schema(schema_name):
    if not engine.dialect.has_schema(engine, schema_name):
        # with engine.connect() as connection:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema_name))

    # set the schema for table creation
    tables = get_tenant_tables()

    schema_engine = create_engine(
        str(config.SQLALCHEMY_DATABASE_URI),
        pool_size=100,
        max_overflow=100,
        # echo=True,
    )
    configure_mappers()

    schema_engine = schema_engine.execution_options(
        schema_translate_map={
            None: schema_name,
        }
    )
    # make_searchable(Base.metadata)

    Base.metadata.create_all(schema_engine, tables=tables)

    # put schema under version control. 2023-01-23 13:57:15, we should not migrate everyone when creating a new one.
    # version_schema_new(script_location=config.ALEMBIC_TENANT_REVISION_PATH)

    with schema_engine.begin() as connection:
        # we need to map this for full text search as it uses sql literal strings
        # and schema translate map does not apply
        for t in tables:
            t.schema = schema_name
        setup_fulltext_search(connection, tables)

    session = sessionmaker(bind=schema_engine)
    schema_session = session()

    organization = schema_session.merge(organization)
    schema_session.add(organization)
    # create any required default values in schema here
    #
    #
    # create defaultplanner
    init_planner_service(
        schema_session=schema_session,
        org_id = organization.id
    )
    
    p_service = planner_service.get_by_code(db_session=schema_session, code=planner_code)
        # create defaultTeam
    if not p_service:
        log.error(f"Failed to get planner for org {organization.id}")
    else:
        try:
            flex_form_data = copy.deepcopy(default_team_flex_form_data)
            flex_form_data.update(default_rust_env_config_data)
            flex_form_data["env_start_datetime"] = datetime.strftime(datetime.now() - timedelta(days=1), config.KANDBOX_DAY_FORMAT_ISO, ) + "T00:00:00"
            default_team = TeamCreate(
                code="default_team",
                name="default_team",
                org_id=organization.id,
                description="",
                planner_service=p_service,
                flex_form_data=flex_form_data,
            )
            team_service.create(db_session=schema_session, team_contact_in=default_team)
        except Exception as e:
            log.error(f"failed to create team: {str(e)}")

    schema_session.commit()
    # 把table 的schema 设置为空
    tables = get_tenant_tables()
    return organization

from sqlalchemy.schema import DDL 
def setup_fulltext_search(connection, tables):
    """Syncs any required fulltext table triggers and functions."""
    # parsing functions
    try:
        function_path = os.path.join(
            os.path.dirname(os.path.abspath(fulltext.__file__)), "expressions.sql"
        )
        # 2024-01-05 15:55:32 This statement failed in sqlalchemy 2.0 , with error : Not an executable object: \'DROP TRIGGER IF EXISTS service_search_vector_trigger ON dispatch_organization_ce."service"\'
        connection.execute(DDL(open(function_path).read()))
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
    except Exception as e:        
        log.error(f"SQLAlchemy 2.0 Issue: setup_fulltext_search failed, and ignored. : {e}")

