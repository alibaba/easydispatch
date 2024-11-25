import os
import sys
import logging


import click
import uvicorn
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from tabulate import tabulate
from uvicorn import main as uvicorn_main

from dispatch import __version__, config
from dispatch.common.utils.kandbox_clear_data import clear_team_data_for_redispatching
from dispatch.org.enums import OrganizationType
from dispatch.plugins.kandbox_planner.env.env_enums import KandboxPlannerPluginType
# from dispatch.service.models import ServiceRead
from pprint import pprint
from dispatch.common.utils.cli import install_plugins, import_database_models

from dispatch.plugins.kandbox_planner.env.env_enums import (
    ActionScoringResultType,
    JobType,
    ActionType,
    JobPlanningStatus,
)

from dispatch.plugins.kandbox_planner.env.env_models import ActionDict

from dispatch.planner_env.planner_service import get_active_planner
import time
from dispatch.team import service as team_service

from .database import engine
from .exceptions import DispatchException
from .logging import configure_logging

# from .main import *  # noqa
from .plugins.base import plugins
# from .scheduler import scheduler

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def abort_if_false(ctx, param, value):
    if not value:
        ctx.abort()


@click.group()
@click.version_option(version=__version__)
def dispatch_cli():
    """Command-line interface to Dispatch."""
    configure_logging()


@dispatch_cli.group("util")
def plugins_group():
    """Data Generator for Testing and Simulation."""
    pass

import json

@plugins_group.command("gen_doc")
@click.option("--filename", default="dispatch_doc.html", help="file name")
def dispatch_job(filename):
    """Shows all available plugins"""

    from fastapi import FastAPI
    doc_api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, title="Kandbox Dispatch")
    from dispatch.api import doc_exposed_api_router
    doc_api.include_router(doc_exposed_api_router, prefix="/v1")




    HTML_TEMPLATE = """<!DOCTYPE html>
    <html>
    <head>
        <meta http-equiv="content-type" content="text/html; charset=UTF-8">
        <title>Dispatch API</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="shortcut icon" href="/icon/kandbox_logo.png">
        <style>
            body {
                margin: 0;
                padding: 0;
            }
        </style>
        <style data-styled="" data-styled-version="4.4.1"></style>
    </head>
    <body>
        <div id="redoc-container"></div>
        <script src="https://cdn.jsdelivr.net/npm/redoc/bundles/redoc.standalone.js"> </script>
        <script>
            var spec = %s;
            Redoc.init(spec, {}, document.getElementById("redoc-container"));
        </script>
    </body>
    </html>
    """

    with open(filename, "w") as fd:
        print(HTML_TEMPLATE % json.dumps(doc_api.openapi()), file=fd)

    print(f"Done to file: {filename}")


from dispatch.database_util.service import get_schema_session

@plugins_group.command("clear_team_data")
@click.option("--org_id", default=107, help="Organization id, only POC org can be cleared.")
@click.option("--team_id", default=1, help="int team_id")
@click.option("--org_code", default="dubai", help="int team_id")
@click.option("--delete_dispatch_user", default=None, help="是否删除 dispatch_core 里面创建的用户 ")
def clear_team_data(org_id, team_id, org_code,delete_dispatch_user=None):
    """Shows all available plugins"""
    # print(f"PURGE DB and RESET, DO NOT USE clear_team_data for org {org_id}, team {team_id}...")
    # return
    clear_team_data_operate(org_id, team_id, org_code,delete_dispatch_user)
    
def clear_team_data_operate(org_id, team_id, org_code,delete_dispatch_user=None):

    install_plugins()

    from dispatch.common.utils.kandbox_clear_data import clear_all_worker_jobs_in_team
    from dispatch.planner_env.planner_service import reset_planning_window_for_team

    from dispatch.org import service as org_service
    env = get_active_planner(org_id= org_id, team_id=team_id)

    db_session = get_schema_session(org_code=org_code)

    org = org_service.get(db_session=db_session, org_id= org_id)
    if org is None:
        print("Organization does not exist")
    if org.org_type != OrganizationType.POC:
        print("Only POC Organization can reset data in teams. Please consider removing reset_dataset setting ...")
    
    print(f"clear_team_data started for org {org_id}, team {team_id}...")
    clear_all_worker_jobs_in_team(
        db_session= db_session, 
        org_code = org.code, 
        team_id = team_id,
        delete_dispatch_user=delete_dispatch_user

    )
    reset_planning_window_for_team(org_id=org_id, team_id=team_id)

    print(f"Data is cleared for org {org_id}, team {team_id} ...")






@plugins_group.command("generate")
# @click.option("--bearer", default=None, help="token recieved after login call")
@click.option("--username", default=None, help="user name to retrive the HTTP JWT Token")
@click.option(
    "--password", default=None, help="password for the user to retrive the HTTP JWT Token"
)
@click.option("--start_day", default="2020112", help="start_day in format yyyymmdd")
@click.option("--end_day", default="20201014", help="end_day in format yyyymmdd")
@click.option("--team_code", default="default_team", help="team code")
@click.option("--dispatch_days", default=10, help="number of days in integer")
@click.option("--dataset", default="veo", help="dataset, for example veo")
@click.option("--filename", default="csv", help="dataset, for example veo")
@click.option("--generate_target", default='worker', help="worker, job, location, or all")
@click.option("--generate_worker_count", default=8, help="How many workers to generate, 0 means None")
@click.option("--generate_job_count", default=21, help="How many jobs to generate, 0 means None") 
@click.option("--job_start_index", default=20, help="how many jobs to generate")
@click.option("--auto_planning_flag", default=1, help="auto or not, 1 is yes/true")
@click.option(
    "--service_url",
    default="https://dispatch.easydispatch.uk/api/v1",
    help="Redirect generation to a different server",
)
def populate_data(
    username,
    password,
    start_day,
    end_day,
    team_code,
    dispatch_days,
    dataset,
    filename,
    generate_target,
    generate_worker_count,
    generate_job_count, 
    job_start_index,
    auto_planning_flag,
    service_url,
):
    # nbr_jobs = generate_job_count
    """Shows all available plugins"""
    log.debug(f"Populating sample data wtih username={username}, dataset = {dataset}...")

    # from dispatch.plugins.kandbox_planner.data_generator.london_data_generator import generate_all
    if dataset == "veo":
        from dispatch.plugins.kandbox_planner.data_generator.veo_data_generator import generate_all
    elif dataset == "london_realtime":
        from dispatch.contrib.plugins.data_generator.london_pick_drop_data_generator import (
            generate_all,
        )
    elif dataset == "singapore_pickdrop":
        from dispatch.plugins.kandbox_planner.data_generator.singapore_pickdrop_data_generator import generate_all

    elif dataset == "philippine_pldt_realtime":
        from dispatch.contrib.plugins.data_generator.philippine_pldt_realtime_data_generator import (
            generate_all,
        )
    # elif dataset == "singapore_realtime":
    #     from dispatch.contrib.plugins.data_generator.singapore_realtime_data_generator import (
    #         generate_all,
    #     )
    elif dataset == "dubai_baituo_pick_drop":
        from dispatch.contrib.plugins.data_generator.dubai_baituo_pick_drop_data_generator import (
            generate_all,
        )
    elif dataset == "oman":
        from dispatch.contrib.plugins.data_generator.oman_data_generator import generate_all
    elif dataset == "tsv_thailand":
        from dispatch.contrib.plugins.data_generator.vst_thailand_data_generator import generate_all
    elif dataset == "asiapac":
        from dispatch.contrib.plugins.data_generator.asiapac_data_generator import generate_all
    elif dataset == "asiapac_new":
        from dispatch.contrib.plugins.data_generator.asiapac_data_generator_new import generate_all
    elif dataset == "global_track":
        from dispatch.contrib.plugins.data_generator.global_track_v2_data_generator import generate_all
    elif dataset == "senheng":
        from dispatch.contrib.plugins.data_generator.senheng_data_generator import generate_all
    elif dataset == "jt":
        from dispatch.contrib.plugins.data_generator.jt_data_generator import generate_all
    elif dataset == "5gmax":
        # from dispatch.contrib.plugins.data_generator.data_generator_5gmax import generate_all
        from dispatch.contrib.plugins.data_generator.five_g_max_data_generator import generate_all
    elif dataset == "johnson":
        from dispatch.contrib.plugins.data_generator.data_generator_johnson import generate_all

    ORG_SQLALCHEMY_DATABASE_URI = config.SQLALCHEMY_DATABASE_URI

    # print("org_engine .SQLALCHEMY_DATABASE_URI=", config.SQLALCHEMY_DATABASE_URI)
    from sqlalchemy_utils import database_exists

    if not database_exists(str(ORG_SQLALCHEMY_DATABASE_URI)):  #
        print("Error, no db")
        exit(1)

    generate_all(
        {
            "service_url": service_url,  # "http://localhost:8000/api/v1",
            "username": username,
            "password": password,
            "start_day": start_day,
            "end_day": end_day,
            "dispatch_days": dispatch_days,
            "team_code": team_code,
            "generate_target":generate_target,
            "generate_worker_count": generate_worker_count,
            "generate_job_count": generate_job_count,
            "nbr_jobs": generate_job_count, # for compatability
            "filename":filename,
            "job_start_index": job_start_index,
            "auto_planning_flag": True if auto_planning_flag == 1 else False,
            "generate_target":generate_target,
        }
    )


@dispatch_cli.group("job")
def plugins_group():
    """Data Generator for Testing and Simulation."""
    pass


@plugins_group.command("dispatch")
@click.option("--start_day", default="2020112", help="start_day in format yyyymmdd")
@click.option("--end_day", default="20201014", help="end_day in format yyyymmdd")
@click.option("--team_code", default="london_t1", help="end_day in format yyyymmdd")
@click.option("--dispatch_days", default=10, help="end_day in format yyyymmdd")
def dispatch_job(start_day, end_day, team_code, dispatch_days):
    """Shows all available plugins"""

    print("Dispatch started...")

    from sqlalchemy.orm import sessionmaker

    sl = sessionmaker(bind=engine)
    session = sl()
    team_obj = team_service.get_by_code(db_session=session, code=team_code)
    if not team_obj:
        print(f"Failed to find team by team_code = {team_code }, aborted.")
        return

    from dispatch.plugins.kandbox_planner.data_generator.veo_data_generator import (
        dispatch_jobs_batch_optimizer,
    )

    dispatch_jobs_batch_optimizer(
        {
            "service_url": "http://localhost:8000/api/v1",
            "start_day": start_day,
            "end_day": end_day,
            "dispatch_days": dispatch_days,
            "team_id": team_obj.id,
        }
    )


@plugins_group.command("run_test_ortools_batch")
@click.option("--start_day", default="2020112", help="start_day in format yyyymmdd")
@click.option("--end_day", default="20201014", help="end_day in format yyyymmdd")
@click.option("--org_code", default="demo", help="org_code")
@click.option("--team_code", default="london_t1", help="team_code")
@click.option("--plugin_slug", default="kandbox_ortools_n_days_optimizer", help="plugin slug")
def run_test_ortools_batch(start_day, end_day, org_code, team_code, plugin_slug):
    """Shows all available plugins"""
    db_session = SessionLocal()
    team_obj = team_service.get_by_code(db_session=db_session, code=team_code)
    if not team_obj:
        print(f"Failed to find team by team_code = {team_code }, aborted.")
        return
    team_id = team_obj.id

    from dispatch.planner_plugin import service as service_plugin_service

    service_plugin_service.switch_agent_plugin_for_service(
        db_session=db_session,
        service_name="default_planner",
        agent_slug=plugin_slug,
        service_plugin_type=KandboxPlannerPluginType.kandbox_batch_optimizer,
        org_id=team_obj.org_id,
    )

    clear_team_data_for_redispatching(org_code, team_id)
    result_info, planner = reset_planning_window_for_team(org_code, team_id)
    rl_env = planner["planner_env"]

    planner["batch_optimizer"].dispatch_jobs(env=rl_env)
    log.info(f"Finished dispatching {len(rl_env.jobs_dict)} jobs. ")
    pprint(rl_env.get_planner_score_stats())


@dispatch_cli.group("plugins")
def plugins_group():
    """All commands for plugin manipulation."""
    pass


@plugins_group.command("list")
def list_plugins():
    """Shows all available plugins"""
    table = []
    for p in plugins.all():
        table.append([p.title, p.slug, p.version, p.type, p.author, p.description])
    click.secho(
        tabulate(table, headers=["Title", "Slug", "Version", "Type", "Author", "Description"]),
        fg="blue",
    )


def sync_triggers():
    from sqlalchemy_searchable import sync_trigger

    sync_trigger(engine, "job", "search_vector", ["code", "name", "description"])
    sync_trigger(
        engine,
        "worker",
        "search_vector",
        [
            "code",
            "name",
            "description",
            # "auth_username",
        ],
    )
    sync_trigger(
        engine, "location", "search_vector", ["code", "geo_address_text",],
    )
    sync_trigger(engine, "plugin", "search_vector", ["title", "slug", "type"])
    sync_trigger(engine, "service", "search_vector", ["code", "name", "description"])
    sync_trigger(
        engine, "team", "search_vector", ["code", "name", "description",],
    )
    # sync_trigger(engine, "tag", "search_vector", ["name"])


@dispatch_cli.group("database")
def dispatch_database():
    """Container for all dispatch database commands."""
    pass


@dispatch_database.command("sync-triggers")
def database_trigger_sync():
    """Ensures that all database triggers have been installed."""
    sync_triggers()

    click.secho("Success. sync-triggers is done.", fg="green")


def metadata_dump(sql, *multiparams, **params):
    # print or write to log or file etc
    print(sql.compile(dialect=engine.dialect))



@dispatch_database.command("init")
def database_init():
    """Initializes a new database."""
    click.echo("Initializing new database...")
    from .database_util.manage import init_database

    # import_database_models()

    init_database(engine)
    click.secho("Success.", fg="green")



@dispatch_database.command("setup_fulltext")
@click.option("--table-name", default=None, help="table to upgrade.")
def setup_fulltext(table_name):
    """Initializes a new database."""
    click.echo("Setup_fulltext for the database...")
    from .database import engine
    from .database_util.manage import (
        get_tenant_tables,
        setup_fulltext_search,
    )
    import sqlalchemy 

    import_database_models()

    conn = engine.connect()
    if table_name is None:
        return

    if table_name == "_ALL_":
        tenant_tables = get_tenant_tables(table_name = None)
    else:
        tenant_tables = get_tenant_tables(table_name = table_name)


    schema_names = sqlalchemy.inspect(engine).get_schema_names()
    for schema_name in schema_names:
        if not schema_name.startswith('dispatch_organization_'):
            continue
        click.secho(f"Detected a tenant schema {schema_name}, setup_fulltext for it...")

        for t in tenant_tables:
            t.schema = schema_name

        setup_fulltext_search(conn, tenant_tables)


    click.secho("Success.", fg="green")


@dispatch_database.command("restore")
@click.option("--dump-file", default="dispatch-backup.dump", help="Path to a PostgreSQL dump file.")
def restore_database(dump_file):
    """Restores the database via pg_restore."""
    import sh
    from sh import psql, createdb
    from dispatch.config import (
        DATABASE_HOSTNAME,
        DATABASE_NAME,
        DATABASE_PORT,
        DATABASE_CREDENTIALS,
    )

    username, password = str(DATABASE_CREDENTIALS).split(":")
    username = "org_template"
    password = "org_template"

    try:
        print(
            createdb(
                "-h",
                DATABASE_HOSTNAME,
                "-p",
                DATABASE_PORT,
                "-U",
                username,
                DATABASE_NAME,
                _env={"PGPASSWORD": password},
            )
        )
    except sh.ErrorReturnCode_1:
        print("Database already exists.")

    print(
        psql(
            "-h",
            DATABASE_HOSTNAME,
            "-p",
            DATABASE_PORT,
            "-U",
            username,
            "-d",
            DATABASE_NAME,
            "-f",
            dump_file,
            _env={"PGPASSWORD": password},
        )
    )
    click.secho("Success.", fg="green")


@dispatch_database.command("dump")
def dump_database():
    """Dumps the database via pg_dump."""
    from sh import pg_dump
    from dispatch.config import (
        DATABASE_HOSTNAME,
        DATABASE_NAME,
        DATABASE_PORT,
        DATABASE_CREDENTIALS,
    )

    username, password = str(DATABASE_CREDENTIALS).split(":")

    pg_dump(
        "-f",
        "dispatch-backup.dump",
        "-h",
        DATABASE_HOSTNAME,
        "-p",
        DATABASE_PORT,
        "-U",
        username,
        DATABASE_NAME,
        _env={"PGPASSWORD": password},
    )


@dispatch_database.command("drop")
@click.option("--yes", is_flag=True, help="Silences all confirmation prompts.")
def drop_database(yes):
    """Drops all data in database."""
    from sqlalchemy_utils import drop_database

    if yes:
        drop_database(str(config.SQLALCHEMY_DATABASE_URI))
        click.secho("Success.", fg="green")

    if click.confirm(
        f"Are you sure you want to drop: '{config.DATABASE_HOSTNAME}:{config.DATABASE_NAME}'?"
    ):
        drop_database(str(config.SQLALCHEMY_DATABASE_URI))
        click.secho("Success.", fg="green")


@dispatch_database.command("upgrade")
@click.option(
    "--tag", default=None, help="Arbitrary 'tag' name - can be used by custom env.py scripts."
)
@click.option(
    "--sql",
    is_flag=True,
    default=False,
    help="Don't emit SQL to database - dump to standard output instead.",
)
@click.option("--revision", nargs=1, default="head", help="Revision identifier.")
@click.option("--revision-type", type=click.Choice(["core", "tenant"]))
def upgrade_database(tag, sql, revision, revision_type):
    """Upgrades database schema to newest version."""
    import sqlalchemy
    from sqlalchemy import inspect
    from sqlalchemy_utils import database_exists
    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig

    from .database import engine

    from .database_util.manage import (
        get_core_tables,
        get_tenant_tables,
        init_database,
        setup_fulltext_search,
    )

    import_database_models()
    alembic_cfg = AlembicConfig(config.ALEMBIC_INI_PATH)

    if not database_exists(str(config.SQLALCHEMY_DATABASE_URI)):
        click.secho("Found no database to upgrade, initializing new database...")
        init_database(engine)
    else:
        conn = engine.connect()

        # detect if we need to convert to a multi-tenant schema structure
        schema_names = inspect(engine).get_schema_names()
        if "dispatch_core" not in schema_names:
            click.secho("Detected single tenant database, converting to multi-tenant...")
            conn.execute(sqlalchemy.text(open(config.ALEMBIC_MULTI_TENANT_MIGRATION_PATH).read()))

            # init initial triggers
            conn.execute("set search_path to dispatch_core")
            setup_fulltext_search(conn, get_core_tables())

            tenant_tables = get_tenant_tables()
            for t in tenant_tables:
                t.schema = "dispatch_organization_default"

            conn.execute("set search_path to dispatch_organization_default")
            setup_fulltext_search(conn, tenant_tables)

        if revision_type:
            if revision_type == "core":
                path = config.ALEMBIC_CORE_REVISION_PATH

            elif revision_type == "tenant":
                path = config.ALEMBIC_TENANT_REVISION_PATH

            alembic_cfg.set_main_option("script_location", path)
            alembic_command.upgrade(alembic_cfg, revision, sql=sql, tag=tag)
        else:
            for path in [config.ALEMBIC_CORE_REVISION_PATH, config.ALEMBIC_TENANT_REVISION_PATH]:
                alembic_cfg.set_main_option("script_location", path)
                alembic_command.upgrade(alembic_cfg, revision, sql=sql, tag=tag)

    click.secho("Success.", fg="green")


@dispatch_database.command("heads")
def head_database():
    """Shows the heads of the database."""
    alembic_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "alembic.ini")
    alembic_cfg = AlembicConfig(alembic_path)
    alembic_command.heads(alembic_cfg)


@dispatch_database.command("history")
def history_database():
    """Shows the history of the database."""
    alembic_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "alembic.ini")
    alembic_cfg = AlembicConfig(alembic_path)
    alembic_command.history(alembic_cfg)


@dispatch_database.command("downgrade")
@click.option(
    "--tag", default=None, help="Arbitrary 'tag' name - can be used by custom env.py scripts."
)
@click.option(
    "--sql",
    is_flag=True,
    default=False,
    help="Don't emit SQL to database - dump to standard output instead.",
)
@click.option("--revision", nargs=1, default="head", help="Revision identifier.")
@click.option("--revision-type", type=click.Choice(["core", "tenant"]), default="core")
def downgrade_database(tag, sql, revision, revision_type):
    """Downgrades database schema to next newest version."""
    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig

    if sql and revision == "-1":
        revision = "head:-1"

    alembic_cfg = AlembicConfig(config.ALEMBIC_INI_PATH)
    if revision_type == "core":
        path = config.ALEMBIC_CORE_REVISION_PATH

    elif revision_type == "tenant":
        path = config.ALEMBIC_TENANT_REVISION_PATH

    alembic_cfg.set_main_option("script_location", path)
    alembic_command.downgrade(alembic_cfg, revision, sql=sql, tag=tag)
    click.secho("Success.", fg="green")


@dispatch_database.command("stamp")
@click.argument("revision", nargs=1, default="head")
@click.option(
    "--tag", default=None, help="Arbitrary 'tag' name - can be used by custom env.py scripts."
)
@click.option(
    "--sql",
    is_flag=True,
    default=False,
    help="Don't emit SQL to database - dump to standard output instead.",
)
def stamp_database(revision, tag, sql):
    """Forces the database to a given revision."""
    alembic_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "alembic.ini")
    alembic_cfg = AlembicConfig(alembic_path)
    alembic_command.stamp(alembic_cfg, revision, sql=sql, tag=tag)


@dispatch_database.command("revision")
@click.option("-m", "--message", default=None, help="Revision message")
@click.option(
    "--autogenerate",
    is_flag=True,
    help=(
        "Populate revision script with candidate migration "
        "operations, based on comparison of database to model"
    ),
)
@click.option("--revision-type", type=click.Choice(["core", "tenant"]))
@click.option(
    "--sql", is_flag=True, help=("Don't emit SQL to database - dump to standard output " "instead")
)
@click.option(
    "--head",
    default="head",
    help=("Specify head revision or <branchname>@head to base new " "revision on"),
)
@click.option(
    "--splice", is_flag=True, help=('Allow a non-head revision as the "head" to splice onto')
)
@click.option(
    "--branch-label", default=None, help=("Specify a branch label to apply to the new revision")
)
@click.option(
    "--version-path", default=None, help=("Specify specific path from config for version file")
)
@click.option(
    "--rev-id", default=None, help=("Specify a hardcoded revision id instead of generating " "one")
)
def revision_database(
    message, autogenerate, revision_type, sql, head, splice, branch_label, version_path, rev_id
):
    """Create new database revision."""
    import types

    import_database_models()
    alembic_cfg = AlembicConfig(config.ALEMBIC_INI_PATH)

    if revision_type:
        if revision_type == "core":
            path = config.ALEMBIC_CORE_REVISION_PATH
        elif revision_type == "tenant":
            path = config.ALEMBIC_TENANT_REVISION_PATH

        alembic_cfg.set_main_option("script_location", path)
        alembic_cfg.cmd_opts = types.SimpleNamespace(cmd="revision")
        alembic_command.revision(
            alembic_cfg,
            message,
            autogenerate=autogenerate,
            sql=sql,
            head=head,
            splice=splice,
            branch_label=branch_label,
            version_path=version_path,
            rev_id=rev_id,
        )

    else:
        for path in [
            config.ALEMBIC_CORE_REVISION_PATH,
            config.ALEMBIC_TENANT_REVISION_PATH,
        ]:
            alembic_cfg.set_main_option("script_location", path)
            alembic_cfg.cmd_opts = types.SimpleNamespace(cmd="revision")
            alembic_command.revision(
                alembic_cfg,
                message,
                autogenerate=autogenerate,
                sql=sql,
                head=head,
                splice=splice,
                branch_label=branch_label,
                version_path=version_path,
                rev_id=rev_id,
            )
    click.secho("Success. The database scripts are revised.", fg="green")



@dispatch_cli.group("scheduler")
def dispatch_scheduler():
    """Container for all dispatch scheduler commands."""
    # we need scheduled tasks to be imported


@dispatch_scheduler.command("fix")
def fix_slots():
    """Prints and runs all currently configured periodic tasks, in seperate event loop."""
    install_plugins()
    from dispatch.planner_env.planner_service import get_active_planner
    env = get_active_planner( org_id=102, team_id=1,)
    # env.fix_missing_kmedoid_start_pos()
    # env.clear_stale_kmedoid_keys()
    click.secho(f"finished fixing...", fg="green")


@dispatch_scheduler.command("parse_logs")
@click.option(
    "--logfile", default="/Users/duan/Downloads/wemart_20230508_2.csv", help=("Specify a hardcoded revision id instead of generating " "one")
)
def parse_logs(logfile):
    install_plugins()
    import re
    from datetime import datetime
    from dispatch.planner_env.planner_service import get_active_planner
    env = get_active_planner( org_id=102, team_id=1,)
    with open(logfile, "r") as fs, open(f"{logfile}.single.csv","w") as single_fs, open(f"{logfile}.merged.csv","w") as merged_fs:
        for data in fs.readlines():
            try:
                order_date = str(datetime.fromtimestamp(int(re.findall(",(\d+),,",data)[0])))
                order_num = re.findall("order \(\'(\d+)",data)[0]
                jobs = data.split("available_free_minutes")[0].split("assigned_jobs")[1].split('JobInSlot')
                is_merge = False
                if len(jobs) > 3:
                    is_merge = True
                newline = f"{order_num},{order_date}," 
                for jobline in jobs[1:]:
                    job_code = re.findall("code='(.*)',",jobline)[0]
                    scheduled_start = env.env_decode_from_minutes_to_datetime(float(re.findall("scheduled_start_minutes=([\d\.]*),",jobline)[0]))
                    tolerance = env.env_decode_from_minutes_to_datetime(float(re.findall("tolerance_end_minutes=([\d\.]*)",jobline)[0]))
                    jl = jobline.replace(",","__")
                    newline += f"{job_code},{str(scheduled_start)},{str(tolerance)},{jl},"
                if is_merge:
                    merged_fs.write(f"{newline}\n")
                else:
                    single_fs.write(f"{newline}\n")
            except:
                print(f"failed on line: {data}")

    click.secho(f"finished parse_logs...", fg="green")



@dispatch_scheduler.command("list")
def list_tasks():
    """Prints and runs all currently configured periodic tasks, in seperate event loop."""
    table = []
    for task in scheduler.registered_tasks:
        table.append([task["name"], task["job"].period, task["job"].at_time])

    click.secho(tabulate(table, headers=["Task Name", "Period", "At Time"]), fg="blue")


# from dispatch.cloudmarket.instance.schduler import init_scheduler, front_scheduler
# from dispatch.bg_functions import init_ed_tasks
from dispatch.crontab import init_scheduler, back_scheduler

@dispatch_scheduler.command("start")
@click.argument("tasks", nargs=-1)
@click.option("--eager", is_flag=True, default=False, help="Run the tasks immediately.")
def start_tasks(tasks, eager):
    """Starts the scheduler."""
    install_plugins()
    init_scheduler()
    click.secho("Started background scheduler...", fg="blue")
    back_scheduler.start()

    # front_scheduler.start()
    # init_ed_tasks()

    # while True:
    #     time.sleep(30)



@dispatch_cli.group("server")
def dispatch_server():
    """Container for all dispatch server commands."""
    pass


@dispatch_server.command("routes")
def show_routes():
    """Prints all available routes."""
    from dispatch.main import api_router

    table = []
    for r in api_router.routes:
        auth = False
        for d in r.dependencies:
            if d.dependency.__name__ == "get_current_user":  # TODO this is fragile
                auth = True
        table.append([r.path, auth, ",".join(r.methods)])

    click.secho(tabulate(table, headers=["Path", "Authenticated", "Methods"]), fg="blue")


@dispatch_server.command("config")
def show_config():
    """Prints the current config as dispatch sees it."""
    import sys
    import inspect
    from dispatch import config

    func_members = inspect.getmembers(sys.modules[config.__name__])

    table = []
    for key, value in func_members:
        if key.isupper():
            table.append([key, value])

    click.secho(tabulate(table, headers=["Key", "Value"]), fg="blue")


# @dispatch_server.command("develop")
# @click.option(
#     "--log-level",
#     type=click.Choice(["debug", "info", "error", "warning", "critical"]),
#     default="debug",
#     help="Log level to use.",
# )
# def run_server(log_level):
#     """Runs a simple server for development."""
#     # Uvicorn expects lowercase logging levels; the logging package expects upper.
#     os.environ["KANDBOX_LOG_LEVEL"] = log_level.upper()
#     if not config.STATIC_DIR:
#         import atexit
#         from subprocess import Popen

#         # take our frontend vars and export them for the frontend to consume
#         envvars = os.environ.copy()
#         envvars.update({x: getattr(config, x) for x in dir(config) if x.startswith("VUE_APP_")})

#         p = Popen(["npm", "run", "serve"], cwd="src/dispatch/static/dispatch", env=envvars)
#         atexit.register(p.terminate)
#     uvicorn.run("dispatch.main:app", debug=True, log_level=log_level)


dispatch_server.add_command(uvicorn_main, name="start")


@dispatch_server.command("shell")
@click.argument("ipython_args", nargs=-1, type=click.UNPROCESSED)
def shell(ipython_args):
    """Starts an ipython shell importing our app. Useful for debugging."""
    import IPython
    from IPython.terminal.ipapp import load_default_config

    config = load_default_config()

    config.TerminalInteractiveShell.banner1 = f"""Python {sys.version} on {sys.platform}
IPython: {IPython.__version__}"""

    IPython.start_ipython(argv=ipython_args, user_ns={}, config=config)


@dispatch_server.command("start_rec")
def start_rec():
    """Star the Recommendation Server. This server :
    1. consumes the redis queue message
    2. run optimizer and push result to redis
    """
    from datetime import datetime
    import traceback


    log.info(f"{datetime.now()}, Installing plugins ...")
    install_plugins()
    start_datetime = datetime.now()
    log.info(f"{start_datetime}, Started Recommender. Please monitor redis messages. Use Ctrl-C to exit   ...")
    
    from dispatch.planner_env.planner_func import MultiplexPlannerHub
    planner_hub = MultiplexPlannerHub()
    i = 0
    sleep_intervals=(0.02, 0.06, 0.1, 0.2, 0.5, 1, 2,) 
    sleep_idx = 0
    while True:
        _, message_str = planner_hub.redis_conn.brpop(config.REDIS_JOB_QUEUE_REALTIME)
        try:
            planner_hub.process_message(message_str)
            # THERE IS a need to sleep here, intead I modified consumer_timeout_ms = 10_0000 # float("inf")
        except Exception as e:
            traceback.print_exc()
            log.info(f"{message_str}, error: {str(e)}")

        # time.sleep(1)

        i = i + 1
        if i % 30 == 1:
            log.info(
                f"Continuing after {i} loops, interval {datetime.now()-start_datetime}"
            )

@dispatch_server.command("train")
@click.option(
    "--org_id", default="0", help="Organization Code, for multi tenancy, internal usage only."
)
@click.option("--team_id", default=1, help="team_id")
# @click.option("--agent_slug", default="2", help="slug")
def start_train(org_id, team_id):
    """Train the PPO rl agent:
    1. consumes the kafka env_window messages
    2. run replay
    3. create recommendations
    """
    log.info(f"Acquiring Env for team_id={team_id} ...")

    planner = get_active_planner(org_id=org_id, team_id=team_id)
    rl_env = planner["planner_env"]

    pprint(rl_env.get_planner_score_stats())
    log.info(f"Starting Training for team_id={team_id},  use Ctrl-C to exit ...")

    print("Training Done.")


@dispatch_server.command("repair")
@click.option(
    "--org_code", default="0", help="Organization Code, for multi tenancy, internal usage only."
)
@click.option("--team_id", default=2, help="end_day in format yyyymmdd")
# @click.option("--agent_slug", default="2", help="slug")
def start_repair(org_code, team_id):
    """Train the PPO rl agent:
    1. consumes the kafka env_window messages
    2. run replay
    3. create recommendations
    """

    log = logging.getLogger("rl_env")
    log.setLevel(logging.ERROR)

    klog = logging.getLogger("kafka.conn")
    klog.setLevel(logging.ERROR)

    log = logging.getLogger("rl_env")
    log.setLevel(logging.ERROR)

    log = logging.getLogger("cli_repair")
    log.setLevel(logging.INFO)

    log.info(f"Acquiring Env for team_id={team_id} ...")

    planner = get_active_planner(org_code=org_code, team_id=team_id)
    rl_env = planner["planner_env"]
    rl_agent = planner["planner_agent"]
    rl_agent.config["nbr_of_actions"] = 2
    pprint(rl_env.get_planner_score_stats())

    log.info(f"Starting repair for team_id={team_id},  use Ctrl-C to exit ...")

    for job_code in rl_env.jobs_dict.keys():
        if (rl_env.jobs_dict[job_code].job_type == JobType.JOB) & (
            rl_env.jobs_dict[job_code].planning_status == JobPlanningStatus.UNPLANNED
        ):
            res = rl_agent.predict_action_dict_list(job_code=job_code)
            if len(res) < 1:
                log.warning(f"Failed to predict for job_code = {job_code}")
                continue
            one_job_action_dict = ActionDict(
                is_forced_action=True,
                job_code=job_code,
                # I assume that only in-planning jobs can appear here...
                action_type=ActionType.FLOATING,
                scheduled_worker_codes=res[0].scheduled_worker_codes,
                scheduled_start_minutes=res[0].scheduled_start_minutes,
                scheduled_duration_minutes=res[0].scheduled_duration_minutes,
            )
            internal_result_info = rl_env.mutate_update_job_by_action_dict(
                a_dict=one_job_action_dict, post_changes_flag=True
            )

            if internal_result_info.status_code != ActionScoringResultType.OK:
                log.warning(
                    f"JOB:{ job_code}: Failed to act on job={job_code}. "  # {internal_result_info}
                )
            else:
                log.info(f"JOB:{job_code}: Successfully Planned job, action={res[0]}. ")
    log.info("Repair Done, printing new scores...")
    pprint(rl_env.get_planner_score_stats())


def entrypoint():
    """The entry that the CLI is executed from""" 
    try:
        dispatch_cli()
    except DispatchException as e:
        click.secho(f"ERROR: {e}", bold=True, fg="red")
    except Exception as e:
        import traceback
        traceback.print_exc()
        log.error(e)
        print(e)


if __name__ == "__main__":
    entrypoint()
