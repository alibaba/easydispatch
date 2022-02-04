import os
import sys
import logging


import click
import uvicorn
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy.engine import create_engine
from tabulate import tabulate
from uvicorn import main as uvicorn_main

from dispatch import __version__, config
from dispatch.service.models import ServiceRead
from pprint import pprint

from dispatch.plugins.kandbox_planner.env.env_enums import (
    EnvRunModeType,
    ActionScoringResultType,
    JobType,
    ActionType,
    JobPlanningStatus,
)

from dispatch.plugins.kandbox_planner.env.env_models import ActionDict
from dispatch.service.planner_service import get_default_active_planner, get_active_planner
import time


from .database import Base, SessionLocal, engine
from .exceptions import DispatchException
from .logging import configure_logging
# from .main import *  # noqa
from .plugins.base import plugins
from .scheduler import scheduler

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


@plugins_group.command("generate")
# @click.option("--bearer", default=None, help="token recieved after login call")
@click.option("--username", default=None, help="user name to retrive the HTTP JWT Token")
@click.option(
    "--password", default=None, help="password for the user to retrive the HTTP JWT Token"
)
@click.option("--start_day", default="2020112", help="start_day in format yyyymmdd")
@click.option("--end_day", default="20201014", help="end_day in format yyyymmdd")
@click.option("--team_code", default="t", help="team code")
@click.option("--dispatch_days", default=10, help="number of days in integer")
@click.option("--dataset", default="veo", help="dataset, for example veo")
@click.option("--generate_worker", default=0, help="whether to create worker or not")
@click.option("--nbr_jobs", default=1, help="how many jobs to generate")
@click.option("--job_start_index", default=20, help="how many jobs to generate")
@click.option("--auto_planning_flag", default=1, help="auto or not, 1 is yes/true")
@click.option("--service_url", default="https://dispatch.easydispatch.uk/api/v1", help="Redirect generation to a different server")
def populate_data(username, password, start_day, end_day, team_code, dispatch_days, dataset, generate_worker, nbr_jobs, job_start_index, auto_planning_flag, service_url):
    """Shows all available plugins"""
    log.debug(f"Populating sample data wtih username={username}, dataset = {dataset}...")

    # from dispatch.plugins.kandbox_planner.data_generator.london_data_generator import generate_all
    if dataset == "veo":
        from dispatch.plugins.kandbox_planner.data_generator.veo_data_generator import generate_all
    else:
        raise ValueError("No such dataset.")
    ORG_SQLALCHEMY_DATABASE_URI = config.SQLALCHEMY_DATABASE_URI

    # print("org_engine .SQLALCHEMY_DATABASE_URI=", config.SQLALCHEMY_DATABASE_URI)
    from sqlalchemy_utils import database_exists, create_database

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
            "generate_worker": generate_worker,
            "nbr_jobs": nbr_jobs,
            "job_start_index": job_start_index,
            "auto_planning_flag": True if auto_planning_flag == 1 else False
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
    from dispatch.team import service as team_service
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
        engine,
        "location",
        "search_vector",
        [
            "location_code",
            "geo_address_text",
        ],
    )
    sync_trigger(engine, "plugin", "search_vector", ["title", "slug", "type"])
    sync_trigger(engine, "service", "search_vector", ["code", "name", "description"])
    sync_trigger(
        engine,
        "team",
        "search_vector",
        [
            "code",
            "name",
            "description",
        ],
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


@dispatch_database.command("init database")
def database_init():
    """Initializes a new database."""
    click.echo("Initializing new database...")
    from .database_util.manage import (
        init_database,
    )

    init_database(engine)
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
    from .scheduler import daily_reload_data


@dispatch_scheduler.command("list")
def list_tasks():
    """Prints and runs all currently configured periodic tasks, in seperate event loop."""
    table = []
    for task in scheduler.registered_tasks:
        table.append([task["name"], task["job"].period, task["job"].at_time])

    click.secho(tabulate(table, headers=["Task Name", "Period", "At Time"]), fg="blue")


@dispatch_scheduler.command("start")
@click.argument("tasks", nargs=-1)
@click.option("--eager", is_flag=True, default=False, help="Run the tasks immediately.")
def start_tasks(tasks, eager):
    """Starts the scheduler."""
    if tasks:
        for task in scheduler.registered_tasks:
            if task["name"] not in tasks:
                scheduler.remove(task)

    if eager:
        for task in tasks:
            for r_task in scheduler.registered_tasks:
                if task == r_task["name"]:
                    click.secho(f"Eagerly running: {task}", fg="blue")
                    r_task["func"]()
                    break
            else:
                click.secho(f"Task not found. TaskName: {task}", fg="red")

    click.secho("Starting scheduler...", fg="blue")
    scheduler.start()


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


@dispatch_server.command("develop")
@click.option(
    "--log-level",
    type=click.Choice(["debug", "info", "error", "warning", "critical"]),
    default="debug",
    help="Log level to use.",
)
def run_server(log_level):
    """Runs a simple server for development."""
    # Uvicorn expects lowercase logging levels; the logging package expects upper.
    os.environ["KANDBOX_LOG_LEVEL"] = log_level.upper()
    if not config.STATIC_DIR:
        import atexit
        from subprocess import Popen

        # take our frontend vars and export them for the frontend to consume
        envvars = os.environ.copy()
        envvars.update({x: getattr(config, x) for x in dir(config) if x.startswith("VUE_APP_")})

        p = Popen(["npm", "run", "serve"], cwd="src/dispatch/static/dispatch", env=envvars)
        atexit.register(p.terminate)
    uvicorn.run("dispatch.main:app", debug=True, log_level=log_level)


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
@click.option(
    "--org_code", default="0", help="Organization Code, for multi tenancy, internal usage only."
)
@click.option("--team_id", default=1, help="int team_id")
@click.option("--reset_window", default="no", help="Whether or not reset the planning window.")
@click.option("--start_day", default="2020112", help="start_day in format yyyymmdd")
@click.option("--end_day", default="20201014", help="end_day in format yyyymmdd")
def start_rec(org_code, team_id, reset_window, start_day, end_day):
    """Star the Recommendation Server. This server :
    1. consumes the kafka env_window messages
    2. run replay
    3. create recommendations
    """
    log.info(f"Acquiring Env for team_id={team_id} ...")

    if reset_window == "yes":
        planner = get_active_planner(
            org_code=org_code,
            team_id=team_id,
            start_day=start_day,
            end_day=end_day,
            force_reload=True,
        )
        rl_env = planner["planner_env"]
        rl_env.replay_env_to_redis()

        planner = get_active_planner(
            org_code=org_code,
            team_id=team_id,
            start_day=start_day,
            end_day=end_day,
            force_reload=True,
        )
    else:
        planner = get_default_active_planner(org_code=org_code, team_id=team_id)
        rl_env = planner["planner_env"]

    log.info(
        f"Started Recommender for(org_code={org_code}, team_id={team_id}), kafka topic = {rl_env.kafka_server.get_env_window_topic_name()}  use Ctrl-C to exit ..."
    )
    i = 0
    while True:
        check_env_n_act(planner=planner)
        if i % 30 == 1:
            log.info(
                f"Continuing after {i} loops, {int(i/60/60/24)} days, {int((i/60) % (60*60*24))} minutes, env_inst_code = {rl_env.env_inst_code}, kafka_input_window_offset = {rl_env.kafka_input_window_offset}, kafka_slot_changes_offset = {rl_env.kafka_slot_changes_offset}"
            )
        # THERE IS a need to sleep here, intead I modified consumer_timeout_ms = 10_0000 # float("inf")
        time.sleep(1)

        i = i + 1

    # print("Recommendation Done.")
    # rl_env.run_mode = EnvRunModeType.REPLAY
    # rl_env.mutate_check_env_window_n_replay()


@dispatch_server.command("train")
@click.option(
    "--org_code", default="0", help="Organization Code, for multi tenancy, internal usage only."
)
@click.option("--team_id", default=1, help="team_id")
# @click.option("--agent_slug", default="2", help="slug")
def start_train(org_code, team_id):
    """Train the PPO rl agent:
    1. consumes the kafka env_window messages
    2. run replay
    3. create recommendations
    """
    log.info(f"Acquiring Env for team_id={team_id} ...")

    planner = get_default_active_planner(org_code=org_code, team_id=team_id)
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

    planner = get_default_active_planner(org_code=org_code, team_id=team_id)
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
                log.warn(f"Failed to predict for job_code = {job_code}")
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
                log.warn(
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


if __name__ == "__main__":
    entrypoint()
