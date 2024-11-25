from functools import wraps
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid1
from contextvars import ContextVar
from fastapi.responses import JSONResponse
import redis

from starlette.routing import compile_path

from sqlalchemy.orm import scoped_session
from sqlalchemy import inspect
from dispatch.database_util.service import get_schema_session
from dispatch.org.models import Organization

from dispatch.planner_env.planner_service import get_active_planner, planners_dict, planners_dict_lock
import time
import logging
from tabulate import tabulate
from os import path
import asyncio
from dispatch.cloudmarket.instance.schduler import init_scheduler

# from starlette.middleware.gzip import GZipMiddleware
from fastapi import FastAPI, status
# from sentry_asgi import SentryMiddleware
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import FileResponse, Response, StreamingResponse
from starlette.staticfiles import StaticFiles
import httpx

from dispatch.plugins.base import plugins
# from dispatch.zulip_server.core import unsubcribe_stream_by_days
from .config import DISPATCH_AUTHENTICATION_PROVIDER_SLUG, E6YUN_FLAG,FIVE_GMAX_RUN_FLAG,FIVE_GMAX_TEAM_ID,FIVE_GMAX_ORG_CODE,redis_pool,BASE_ENV, DISPATCH_VERSION, ORGANIZATIONJOBSCHEDUECALLLBACK, ENABLE_CLOUD_MARKET_SCHEDULER
from dispatch import config

from .api import api_router
from .common.utils.cli import install_plugins, install_plugin_events
# from .config import STATIC_DIR
# from .extensions import configure_extensions
from .logging import configure_logging
# from .metrics import provider as metric_provider
from dispatch.plugins.kandbox_planner.env.env_enums import (
    JobPlanningStatus,
    ActionScoringResultType,
)
from dispatch.planner_env.planner_service import reset_planning_window_for_team

from .database import engine, sessionmaker
from dispatch.job.service import set_all_job_finish
from fastapi.middleware.cors import CORSMiddleware
from .config import DISPATCH_UI_URL


if config.UU_START_FLAG == 'yes':
    from dispatch.contrib.uupaotui.processor.core import UUPaoNanCore

if config.BAITUO_INTEGRATION == 'yes':
    from dispatch.contrib.baituo.baituo_dispatch import BaiTuoCore
if config.RPA_INTEGRATION == 'yes':
    from dispatch.contrib.pldt.RPAPaidan import create_task


log = logging.getLogger(__name__)
# log = logging.getLogger("ipms_apms_rps_callback")
# we configure the logging level and format
configure_logging()

# we configure the extensions such as Sentry
# configure_extensions()

# we create the ASGI for the app
app = Starlette(debug=config.DEBUG)

# we create the Web API framework
api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


OVER_CURRENT_USER = None


def get_path_template(request: Request) -> str:
    if hasattr(request, "path"):
        return ",".join(request.path.split("/")[1:4])
    return ".".join(request.url.path.split("/")[1:4])


# @frontend.middleware("http")
# async def default_page(request, call_next):
#     response = await call_next(request)
#     if response.status_code == 404:
#         if STATIC_DIR:
#             return FileResponse(path.join(STATIC_DIR, "index.html"))
#         else:
#             async with httpx.AsyncClient() as client:
#                 remote_resp = await client.get(
#                     str(request.url.replace(port=8080)), headers=dict(request.headers)
#                 )
#                 return StreamingResponse(
#                     remote_resp.aiter_bytes(),
#                     headers=remote_resp.headers,
#                     status_code=remote_resp.status_code,
#                     media_type=remote_resp.headers.get("content-type"),
#                 )
#     return response


REQUEST_ID_CTX_KEY = "request_id"
_request_id_ctx_var: ContextVar[Optional[str]] = ContextVar(REQUEST_ID_CTX_KEY, default=None)


def get_request_id() -> Optional[str]:
    return _request_id_ctx_var.get()


def get_path_params_from_request(request: Request) -> str:
    path_params = {}
    for r in api_router.routes:
        path_regex, path_format, param_converters = compile_path(r.path)
        # remove the /api/v1 for matching
        path = f"/{request['path'].strip('/api/v1')}"
        match = path_regex.match(path)
        if match:
            path_params = match.groupdict()
    return path_params


@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    request_id = str(uuid1())

    # we create a per-request id such that we can ensure that our session is scoped for a particular request.
    # see: https://github.com/tiangolo/fastapi/issues/726
    ctx_token = _request_id_ctx_var.set(request_id)
    # path_params = get_path_params_from_request(request)

    # if this call is organization specific set the correct search path
    # organization_slug = path_params.get("organization")

    auth_plugin = plugins.get(DISPATCH_AUTHENTICATION_PROVIDER_SLUG)
    login_info = None
    try:
        login_info = auth_plugin.get_current_user_data(request)
    except Exception as e:
        _path = request.url.path
        if all(
            [
                i not in _path
                for i in [
                    "/register",
                    "/login",
                    "/register_eng",
                    "/register_customer",
                    "/edit_job",
                    "/job_edit_4_worker",
                ]
            ]
        ):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": [{"msg": "Signature has expired"}]},
            )

    organization_slug = login_info.get("org_code") if login_info else None
    if organization_slug and organization_slug != "-1":
        # request.state.organization = organization_slug
        schema = f"dispatch_organization_{organization_slug}"
        # TODO, move this to be module global variable. It should not be fetched everytime.
        # validate schema name
        schema_names = inspect(engine).get_schema_names()
        if schema in schema_names:
            # add correct schema mapping depending on the request
            schema_engine = engine.execution_options(
                schema_translate_map={
                    None: schema,
                }
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": [{"msg": "Forbidden, wrong organization"}]},
            )
    else:
        # add correct schema mapping depending on the request
        # can we set some default here?
        request.state.organization = "default"
        schema_engine = engine.execution_options(
            schema_translate_map={
                None: "dispatch_organization_default",
            }
        )
    try:
        session = scoped_session(sessionmaker(bind=schema_engine), scopefunc=get_request_id)
        request.state.auth_db = session()
        # request.state.auth_db.autocommit = True
        response = await call_next(request)
    finally:
        request.state.auth_db.close()

    _request_id_ctx_var.reset(ctx_token)
    return response


# @app.middleware("http")
# async def db_session_middleware(request: Request, call_next):
#     response = Response("Internal Server Error", status_code=500)
#     try:
#         if DISPATCH_AUTHENTICATION_PROVIDER_SLUG:
#             global OVER_CURRENT_USER
#             auth_plugin = plugins.get(DISPATCH_AUTHENTICATION_PROVIDER_SLUG)
#             OVER_CURRENT_USER = auth_plugin.get_current_user_data(request)
#             if any(i in request.url.path for i in ["auth/login", "auth/register"]):
#                 OVER_CURRENT_USER = None
#         request.state.auth_db = SessionLocal()
#         response = await call_next(request)
#     except Exception as e:
#         print(e)
#     finally:
#         request.state.auth_db.close()
#         if "db" in request.state._state.keys():
#             # if request.state.db is not None:
#             request.state.db.close()
#     return response


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
# app.add_middleware(SentryMiddleware)

# we add a middleware class for capturing metrics using Dispatch's metrics provider
# app.add_middleware(MetricsMiddleware)


origins = [DISPATCH_UI_URL]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# we install all the plugins
install_plugins()

# we add all the plugin event API routes to the API router
# install_plugin_events(api_router)

# ed_daily ed_pre ed_prod 
# we add all API routes to the Web API framework
api.include_router(api_router, prefix="/v1")
if BASE_ENV:
    BASE_ENV = BASE_ENV.replace("/","") # 如果原来有 / 就去掉, 保持统一 
    app_api_path = f"/{BASE_ENV}/api"
else:
    app_api_path = f"/api"

app.mount(app_api_path, app=api) 

# all scheduler
if ENABLE_CLOUD_MARKET_SCHEDULER:
    app.add_event_handler("startup", init_scheduler)

# we mount the frontend and app
# if STATIC_DIR:
#     frontend.mount("/", StaticFiles(directory=STATIC_DIR), name="app")

# app.mount("/", app=frontend)
print(f"Dispatch_Version: {DISPATCH_VERSION}, Env: {BASE_ENV}, api path: {app_api_path}, API Document: {app_api_path}/v1/docs")


# we print all the registered API routes to the console
table = []
for r in api_router.routes:
    auth = False
    for d in r.dependencies:
        if d.dependency.__name__ == "get_current_user":  # TODO this is fragile
            auth = True
    table.append([r.path, auth, ",".join(r.methods)])

log.debug("Available Endpoints \n" + tabulate(table, headers=["Path", "Authenticated", "Methods"]))


def _next_time(times):
    t = datetime.now()
    _time = 0
    if times == 0:
        t2 = (t + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        _time = time.mktime(time.strptime(t2, "%Y-%m-%d %H:%M:%S"))
    elif times == 1:
        t2 = (t + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
        _time = time.mktime(time.strptime(t2, "%Y-%m-%d %H:%M:%S"))
    elif times == 2:
        t2 = (t + timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M:%S")
        _time = time.mktime(time.strptime(t2, "%Y-%m-%d %H:%M:%S"))
    elif times == 3:
        t2 = (t + timedelta(minutes=120)).strftime("%Y-%m-%d %H:%M:%S")
        _time = time.mktime(time.strptime(t2, "%Y-%m-%d %H:%M:%S"))
    else:
        t2 = (t + timedelta(minutes=99990)).strftime("%Y-%m-%d %H:%M:%S")
        _time = time.mktime(time.strptime(t2, "%Y-%m-%d %H:%M:%S"))

    return _time


def delay_setting(redis_conn, job):
    # 设置延迟时间
    # 过滤规则
    #  value = (1,time) , 1 = 10min  2  = 30min  ,3 =60min  , 4  = 120min   120后过期 重新循环之前的重试规则

    flag = False
    try:
        if redis_conn.exists(job.job_code) <= 0:
            flag = True
            next_time = _next_time(0)
            redis_conn.zadd(job.job_code, {next_time: 1})
            redis_conn.expire(job.job_code, 2 * 60 * 60 + 60)
        else:
            job_tiem_list = redis_conn.zrange(job.job_code, 0, -1, withscores=True)
            time_limit = job_tiem_list[-1]
            t = datetime.now()
            t2 = t.strftime("%Y-%m-%d %H:%M:%S")
            now = time.mktime(time.strptime(t2, "%Y-%m-%d %H:%M:%S"))

            if now >= float(time_limit[0]):
                flag = True
                next_time = _next_time(len(job_tiem_list))
                redis_conn.zadd(job.job_code, {next_time: len(job_tiem_list) + 1})
    except:
        pass

    return flag


def e6yun_realtime_job(func):
    """
    TODO

        if now >= "23:50:00" and now <= "23:59:59":之间的任务跳过

    跳过<23:50:00  request_start_datetime = 明天的任务

    修改 job  每个订单改 [requested min tolerance  , resuested max tolerance] 为任务的当天
    判断订单是否可以修改，等规则
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:

            env = args[0]
            job = args[2]
            if not job.is_auto_planning or (job.planning_status != JobPlanningStatus.UNPLANNED):
                return
            org_code = env.config["org_code"]
            team_id = env.config["team_id"]
            if (
                org_code != config.e6yun_config_dict["org_code"]
                or team_id != config.e6yun_config_dict["team_id"]
            ):
                return func(*args, **kwargs)

            t = env.env_start_datetime
            day_now = t.strftime(config.KANDBOX_DATE_FORMAT)
            tomorrow_day = (t + timedelta(days=1)).strftime(config.KANDBOX_DATE_FORMAT)
            now = t.strftime("%H:%M:%S")
            flag = now >= "23:50:00" and now <= "23:59:59"
            if flag:
                return
            requested_start_minutes = args[2].requested_start_minutes
            request_start_datetime = env.env_decode_from_minutes_to_datetime(
                requested_start_minutes
            )
            request_start_datetime_day = request_start_datetime.strftime(config.KANDBOX_DATE_FORMAT)
            if request_start_datetime_day == tomorrow_day:
                # 明天任务
                if now >= "23:59:59":
                    return func(*args, **kwargs)
            elif request_start_datetime_day == day_now:
                return func(*args, **kwargs)
            else:
                return
        except:
            import traceback

            log.error(traceback.format_exc())

    return wrapper


@e6yun_realtime_job
def planner_job(rl_env, planner, job):
    if not job.is_auto_planning or (job.planning_status != JobPlanningStatus.UNPLANNED):
        return
    # 排除错误的skills
    if any([i in job.requested_skills for i in ["p0", "p1"]]):
        return
    # TODO redis key =job code ,
    delay_flag = delay_setting(rl_env.redis_conn, job)
    if not delay_flag:
        return
    log.info(
        f"job {job.job_code} will be auto planned. job.is_auto_planning and (job.planning_status == JobPlanningStatus.UNPLANNED)"
    )
    rl_agent = planner["planner_agent"]
    # TODO, use naive being/end to avoid re-arranging other inplanning jobs
    # In future, run all re-arrangement.
    rl_agent.use_naive_search_for_speed = True
    rl_agent.config["nbr_of_actions"] = 5

    res = rl_agent.predict_action_dict_list(job_code=job.job_code)
    if len(res) < 1:
        log.info(f"Failed to predict action for job {job.job_code}")
    else:
        # internal_result_info = rl_env.mutate_update_job_by_action_dict(
        #     a_dict=res[0].to_action_dict(rl_env), post_changes_flag=True
        # )
        filter_request_code = [
            i for i in res if job.requested_primary_worker_code in i.scheduled_worker_codes
        ]
        recommendation = filter_request_code[0] if filter_request_code else res[0]
        internal_result_info = rl_env.mutate_commit_recommendation(
            recommendation=recommendation, post_changes_flag=True
        )

        if internal_result_info.status_code == ActionScoringResultType.OK:
            log.info(f"Successfully committed action for job {job.job_code}.")
        else:
            log.warning(
                f"Failed to commit action for job {job.job_code}, action = {res[0]}, info = {internal_result_info}"
            )


async def RPACallBack(refresh_count: int, interval_seconds: int) -> None:

    for r_i in range(refresh_count):
        try:
            await asyncio.sleep(interval_seconds)
            planners_dict_keys = list(planners_dict.keys())

            for key in planners_dict_keys:
                try:
                    team_id = key[1]
                    _key = f"{team_id}_RPAPaidan"
                    rl_env = planners_dict[key]["planner_env"]
                    _conn = rl_env.redis_conn

                    if _conn.exists(_key) > 0 and _conn.llen(_key) > 0:
                        param_list = _conn.lrange(_key, 0, -1)
                        _conn.delete(_key)
                        param_list = [
                            eval(i.decode("utf-8")) if isinstance(i, bytes) else eval(i)
                            for i in param_list
                        ]
                        log.debug(f"RPACallBack start,lens:{len(param_list)}")
                        res_p0, res_p1, res_apms_p0, res_apms_p1 = create_task(param_list)
                        if res_p0[0] and res_p1[0] and res_apms_p0[0] and res_apms_p1[0]:
                            print(
                                f"\033[37;45m\t5: RPACallBack succeed {(res_p0, res_p1, res_apms_p0,res_apms_p1)}\033[0m"
                            )
                            print(f"\033[37;45m\t5: RPACallBack succeed {param_list}\033[0m")
                            log.info(f"RPACallBack susseed,lens:{len(param_list)}")
                        else:
                            print(f"\033[37;45m\t5: RPACallBack error {param_list}\033[0m")
                            log.error(
                                f"RPACallBack ,error: {((res_p0, res_p1,res_apms_p0, res_apms_p1))}"
                            )

                        log.debug(f"RPACallBack end,lens:{len(param_list)}")
                except ValueError as re:
                    print("RPACallBack ValueError: ", re)

        except Exception as e:
            print("Error in loop: ", e)

    log.debug("RPACallBack is all done.")


# https://fastapi.tiangolo.com/advanced/events/


redis_conn = redis.Redis(connection_pool=redis_pool)

async def run_dispatch_loop(refresh_count: int, interval_seconds: int) -> None:
    '''
    5gmax 定时跑排班任务
    '''
    # global over_callback_flag
    for r_i in range(refresh_count):
        try:
            await asyncio.sleep(interval_seconds)
            # with planners_dict_lock:
            # async with planners_dict_lock:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, planners_dict_lock.acquire)
            now = datetime.now()
            
            rl_env = planner["planner_env"]
            _key = f"dispatch_flag_{FIVE_GMAX_ORG_CODE}|{FIVE_GMAX_TEAM_ID}|{now.today()}"
            
            if now.hour>=5  and redis_conn.exists(_key) <= 0:
                # 根据orgnization 状态判断是否可以排班，设计计量计费
                result_info, planner = reset_planning_window_for_team(FIVE_GMAX_ORG_CODE, FIVE_GMAX_TEAM_ID)

                db_session = planner["planner_env"].kp_data_adapter.db_session
                org_data = db_session.query(Organization).filter(Organization.code == FIVE_GMAX_ORG_CODE).first()
                if org_data:
                    organization_status = org_data.organization_status
                    if organization_status =="1":                        
                        flag = planner["batch_optimizer"].dispatch_jobs(env=rl_env, rl_agent=planner["planner_agent"])
                        log.info(f"Finished dispatching {len(rl_env.jobs_dict)} ")
                        if not flag or flag == False:
                            result_info = {"status": "Error", "jobs_dispatched": 0}
                        else:
                            result_info = {"status": "OK", "jobs_dispatched": len(rl_env.jobs_dict)}

                    else:
                        print("Error in loop: run 5gmax", FIVE_GMAX_ORG_CODE +"is Stopped or Expired")
                
                redis_conn.set(_key,1,ex=3600*5)
            else:
                pass
                
        except Exception as e:
            print("Error in loop: ", str(e))
        finally:
            planners_dict_lock.release()

       
    log.debug("run_dispatch_loop is all done.")



# @app.on_event("startup")
# async def startup_event():

#     # 开启uu同步并接收订单数据
#     if config.UU_START_FLAG == "yes":
#         log.info("startup uu message processors...")
#         uu = UUPaoNanCore()
#         uu.start(f"{config.UU_API_URL}/data/sync{config.UU_API_TOKEN}", "main", city=0)

#     # pldt callback RPACallBack 30s/it
#     if config.PLDT_START_FLAG:
#         asyncio.create_task(
#             RPACallBack(
#                 refresh_count=999999999999,
#                 interval_seconds=70,
#             )
#         )

#     # pick drop dispatch job
#     if config.DISPATCH_PICK_DROP_FLAG:
#         log.info("startup baituo message processors...")
#         baituo = BaiTuoCore()
#         baituo.start()

#     # zulip switch for org is_active
#     # asyncio.create_task(unsubcribe_stream_by_days())

#     # e6yun task
#     if E6YUN_FLAG:
#         from dispatch.contrib.e6yun.core import E6YunCore
#         e6yun = E6YunCore(appkey=None, appsecret=None, config_dict=config.e6yun_config_dict)
#         e6yun.init_data()
#         e6yun.start()

#     if FIVE_GMAX_RUN_FLAG:
#         asyncio.create_task(
#             run_dispatch_loop(
#                 refresh_count=999999999999,
#                 interval_seconds=config.BACKGROUND_ENV_SYNC_INTERVAL_SECONDS,
#             )
#         )

from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
import traceback

# 捕获全部异常
@api.exception_handler(Exception)
async def all_exception_handler(request: Request, exc: Exception):
    log.error(f"Global 500 ERROR, URL:{request.url}\nHeaders:{request.headers}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"code": 500, "data": {"tip": "服务器错误"}, "message": "fail"},
    )
