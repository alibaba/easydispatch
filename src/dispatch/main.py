from dispatch.service.planner_service import planners_dict, planners_dict_lock
import time
import logging
from tabulate import tabulate
from os import path
import asyncio

# from starlette.middleware.gzip import GZipMiddleware
from fastapi import FastAPI
from sentry_asgi import SentryMiddleware
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import FileResponse, Response, StreamingResponse
from starlette.staticfiles import StaticFiles
import httpx

from dispatch.plugins.base import plugins
from .config import DISPATCH_AUTHENTICATION_PROVIDER_SLUG


from .api import api_router
from .common.utils.cli import install_plugins, install_plugin_events
from .config import STATIC_DIR
from .database import SessionLocal
from .extensions import configure_extensions
from .logging import configure_logging
from .metrics import provider as metric_provider
from dispatch.plugins.kandbox_planner.env.env_enums import JobPlanningStatus, ActionScoringResultType

log = logging.getLogger(__name__)


# we configure the logging level and format
configure_logging()

# we configure the extensions such as Sentry
configure_extensions()

# we create the ASGI for the app
app = Starlette()

# we create the ASGI for the frontend
frontend = Starlette()

# we create the Web API framework
api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def get_path_template(request: Request) -> str:
    if hasattr(request, "path"):
        return ",".join(request.path.split("/")[1:4])
    return ".".join(request.url.path.split("/")[1:4])


@frontend.middleware("http")
async def default_page(request, call_next):
    response = await call_next(request)
    if response.status_code == 404:
        if STATIC_DIR:
            return FileResponse(path.join(STATIC_DIR, "index.html"))
        else:
            async with httpx.AsyncClient() as client:
                remote_resp = await client.get(
                    str(request.url.replace(port=8080)), headers=dict(request.headers)
                )
                return StreamingResponse(
                    remote_resp.aiter_bytes(),
                    headers=remote_resp.headers,
                    status_code=remote_resp.status_code,
                    media_type=remote_resp.headers.get("content-type"),
                )
    return response


@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    response = Response("Internal Server Error", status_code=500)
    try:
        request.state.auth_db = SessionLocal()
        response = await call_next(request)
    finally:
        request.state.auth_db.close()
        if "db" in request.state._state.keys():
            # if request.state.db is not None:
            request.state.db.close()
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000 ; includeSubDomains"
    return response


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path_template = get_path_template(request)

        # exclude non api requests e.g. static content
        if "api" not in path_template:
            return await call_next(request)

        method = request.method
        tags = {"method": method, "endpoint": path_template}

        try:
            start = time.perf_counter()
            response = await call_next(request)
            elapsed_time = time.perf_counter() - start
        except Exception as e:
            metric_provider.counter("server.call.exception.counter", tags=tags)
            raise e from None
        else:
            tags.update({"status_code": response.status_code})
            metric_provider.timer("server.call.elapsed", value=elapsed_time, tags=tags)
            metric_provider.counter("server.call.counter", tags=tags)

        return response


# we add a middleware class for logging exceptions to Sentry
app.add_middleware(SentryMiddleware)

# we add a middleware class for capturing metrics using Dispatch's metrics provider
app.add_middleware(MetricsMiddleware)

# we install all the plugins
install_plugins()

# we add all the plugin event API routes to the API router
install_plugin_events(api_router)

# we add all API routes to the Web API framework
api.include_router(api_router, prefix="/v1")

# we mount the frontend and app
if STATIC_DIR:
    frontend.mount("/", StaticFiles(directory=STATIC_DIR), name="app")

app.mount("/api", app=api)
app.mount("/", app=frontend)

# we print all the registered API routes to the console
table = []
for r in api_router.routes:
    auth = False
    for d in r.dependencies:
        if d.dependency.__name__ == "get_current_user":  # TODO this is fragile
            auth = True
    table.append([r.path, auth, ",".join(r.methods)])

log.debug("Available Endpoints \n" + tabulate(table, headers=["Path", "Authenticated", "Methods"]))


async def background_env_sync_all(refresh_count: int, interval_seconds: int) -> None:

    for r_i in range(refresh_count):
        await asyncio.sleep(interval_seconds)
        # with planners_dict_lock:
        # async with planners_dict_lock:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, planners_dict_lock.acquire)

        planners_dict_keys = list(planners_dict.keys())

        for key in planners_dict_keys:
            try:
                rl_env = planners_dict[key]["planner_env"]
                log.debug(
                    f"key = {key}, env offset = {rl_env.kafka_input_window_offset}, redis offset = {rl_env.get_env_window_replay_till_offset()}, input topic = {rl_env.kafka_server.get_env_window_topic_name()}"
                )
                rl_env.mutate_check_env_window_n_replay()
                for job in rl_env.jobs:
                    if job.is_auto_planning and (job.planning_status == JobPlanningStatus.UNPLANNED):
                        log.info(
                            f"job {job.job_code} will be auto planned. job.is_auto_planning and (job.planning_status == JobPlanningStatus.UNPLANNED)"
                        )
                        rl_agent = planners_dict[key]["planner_agent"]
                        # TODO, use naive being/end to avoid re-arranging other inplanning jobs
                        # In future, run all re-arrangement.
                        rl_agent.use_naive_search_for_speed = True
                        rl_agent.config["nbr_of_actions"] = 5

                        res = rl_agent.predict_action_dict_list(job_code=job.job_code)
                        if len(res) < 1:
                            log.info(
                                f"Failed to predict action for job {job.job_code}"
                            )
                        else:
                            internal_result_info = rl_env.mutate_update_job_by_action_dict(
                                a_dict=res[0].to_action_dict(rl_env), post_changes_flag=True
                            )

                            if internal_result_info.status_code == ActionScoringResultType.OK:
                                log.info(
                                    f"Successfully committed action for job {job.job_code}."
                                )
                            else:
                                log.warn(
                                    f"Failed to commit action for job {job.job_code}, action = {res[0]}, info = {internal_result_info}"
                                )
            except ValueError as re:
                print("ValueError: ", re)

            # except RuntimeError as re:
            #     print("RuntimeError: ", re)
            # except Exception as e:
            #     print("Unknown: ", e)

        planners_dict_lock.release()

        log.info(
            f"Done for work - hello r_i = {r_i}, len env = {len(planners_dict_keys)}, list of env = {planners_dict_keys}")
    log.debug("background_env_sync_all is all done.")


# https://fastapi.tiangolo.com/advanced/events/
@app.on_event("startup")
async def startup_event():
    log.debug(f"")
    refresh_task = asyncio.create_task(
        background_env_sync_all(
            refresh_count=1300,
            interval_seconds=5,
        )
    )
    # await refresh_task
    log.debug(
        f"on_event startup, I have started the task to refresh envs in background. Not implemented yet."
    )
