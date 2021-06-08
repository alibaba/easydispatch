import threading
import redis
from dispatch.plugins.kandbox_planner.env.env_enums import EnvRunModeType
import json
import logging
from builtins import KeyError
from typing import Optional, List

from fastapi.encoders import jsonable_encoder

# from prompt_toolkit.log import logger
from dispatch.config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, ONCALL_PLUGIN_SLUG

from dispatch.database import SessionLocal
from dispatch.plugins.base import plugins
from dispatch.plugins.bases.kandbox_planner import KandboxPlannerPluginType
from dispatch.plugins.kandbox_planner.data_adapter.kplanner_db_adapter import KPlannerDBAdapter
from dispatch.plugins.kandbox_planner.util.cache_dict import CacheDict
from dispatch.service_plugin import flows as service_plugin_flows
from dispatch.service_plugin import service as service_plugin_service
from dispatch.service_plugin.models import ServicePlugin
from dispatch.team.models import Team
from dispatch.team import service as team_service


from .models import Service, ServiceCreate, ServiceUpdate
from sqlalchemy.orm.attributes import flag_modified

# from dispatch.plugins.kandbox_planner.env.kprl_env_rllib_history_affinity import (
#     KPlannerHistoryAffinityTopNGMMEnv,
# )

# from dispatch.plugins.kandbox_planner.agent.kprl_agent_rllib_ppo import KandboxAgentRLLibPPO
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util

from dispatch.common.utils.kandbox_clear_data import clear_team_data_for_redispatching


import dispatch.config as config
import logging

log = logging.getLogger(__name__)
"""
import ray

if not ray.is_initialized():
    ray.init(ignore_reinit_error=False, log_to_driver=False, local_mode=True, num_cpus=1)
"""
planners_dict = CacheDict(cache_len=5)  # planners[(org_code,team_id,start_day)]= the_planner
# TODO org_code authentication.


if REDIS_PASSWORD == "":
    redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=None)
else:
    redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)


# import asyncio

planners_dict_lock = threading.Lock()
# planners_dict_lock = asyncio.Lock()
"""
def get(*, db_session, service_id: int) -> Optional[Service]:
    return db_session.query(Service).filter(Service.id == service_id).first()


def get_by_external_id(*, db_session, external_id: str) -> Optional[Service]:
    return db_session.query(Service).filter(Service.external_id == external_id).first()


def get_all(*, db_session):
    return db_session.query(Service)


def get_all_by_status(*, db_session, is_active: bool):
    return db_session.query(Service).filter(Service.is_active.is_(is_active))

"""


def update_env_config(*, db_session, service_plugin_id: int, new_config_dict: dict) -> Service:
    # query the db to find service_plugin with type env_proxy
    service_plugin = (
        db_session.query(ServicePlugin).filter(ServicePlugin.id == service_plugin_id).one_or_none()
    )

    if not service_plugin:
        # We get information about the plugin
        raise KeyError(f"Can not find service plugin by ID: {service_plugin_id}")

    # service_plugin_config =  service_plugin
    if not service_plugin.config:
        print("Env config Error, should not be None")
        service_plugin.config = {}

    for field in new_config_dict:
        service_plugin.config[field] = new_config_dict[field]
        # https://stackoverflow.com/questions/42559434/updates-to-json-field-dont-persist-to-db
        flag_modified(service_plugin, "config")

    db_session.add(service_plugin)
    db_session.commit()
    return service_plugin


def auto_exec_rl_planner_over_unplanned(planner=None):
    env = planner["planner_env"]
    observation = env._get_observation_numerical()
    # done = (env.current_job_i >= len(env.jobs))

    done = not (env._move_to_next_unplanned_job())
    for step_index in range(len(env.jobs)):
        if done:
            break
        if env.jobs[env.current_job_i].job_code in config.DEBUGGING_JOB_CODE_SET:
            print("pause for config.DEBUGGING_JOB_CODE_SET")
        action_list = planner["planner_agent"].predict_action_list()

        observation, reward, done, info = env.step(action_list[0])

        b_dict = planner["planner_env"].decode_action_into_dict(action_list[0])
        log.debug(b_dict)

    # env.commit_changed_jobs()


def load_planner(
    *, org_code: str, team_id: int, start_day: str, nbr_of_days_planning_window: int = 7
):

    kpdb = KPlannerDBAdapter(team_id=team_id)
    db_session = kpdb.db_session
    team = db_session.query(Team).filter(Team.id == team_id).first()
    service = db_session.query(Service).filter(Service.id == team.service_id).one()

    rules = service_plugin_service.get_by_service_id_and_type(
        db_session=db_session,
        service_id=service.id,
        service_plugin_type=KandboxPlannerPluginType.kandbox_rule,
    )

    env_rules = []
    for rule_plugin_record in rules:
        rule_plugin = plugins.get_class(rule_plugin_record.plugin.slug)
        env_rules.append(rule_plugin(config=rule_plugin_record.config))  # json.loads

    service_id = team.service_id
    envs = service_plugin_service.get_by_service_id_and_type(
        db_session=db_session,
        service_id=service_id,
        service_plugin_type=KandboxPlannerPluginType.kandbox_env_proxy,
    )

    if envs.count() != 1:  # len(envs) != 1:
        raise Exception("Wrong configuration, failed to identify not exactly one env proxy")
    env_config = envs[0].plugin.config.copy()
    if envs[0].config is not None:
        env_config.update(envs[0].config)
    # if "env_config" in team.flex_form_data.keys():
    env_config.update(team.flex_form_data)

    # env_config = (
    #     envs[0].config if envs[0].config is not None else envs[0].plugin.config
    # )  #  json.loads()
    env_config["org_code"] = org_code
    env_config["team_id"] = team_id
    if start_day != config.DEFAULT_START_DAY:
        env_config["env_start_day"] = start_day
        env_config["nbr_of_days_planning_window"] = nbr_of_days_planning_window
    # this blocks rules_slug_config_list from env.
    env_config["rules"] = env_rules

    env_config["service_plugin_id"] = envs[0].id

    env_proxy_plugin = plugins.get(envs[0].plugin.slug)
    new_env = env_proxy_plugin().get_env(config=env_config)

    # w, d = new_env.load_transformed_workers()
    # print(w.count().max(), d)

    agents = service_plugin_service.get_by_service_id_and_type(
        db_session=db_session,
        service_id=service_id,
        service_plugin_type=KandboxPlannerPluginType.kandbox_agent,
    )
    if agents.count() != 1:
        raise Exception("Wrong configuration, failed to identify exactly one agent")

    agent_config = agents[0].config  # json.loads()

    agent_cls = plugins.get_class(agents[0].plugin.slug)
    new_agent = agent_cls(config=agent_config, env_config=env_config, env=new_env)
    new_agent.load_model(env_config=env_config)

    # ================================================================================
    planner = {"planner_env": new_env, "planner_agent": new_agent, "db_session": db_session}
    # Batch is optional and attach it if defined
    batch_optimizers = service_plugin_service.get_by_service_id_and_type(
        db_session=db_session,
        service_id=service_id,
        service_plugin_type=KandboxPlannerPluginType.kandbox_batch_optimizer,
    )
    if batch_optimizers.count() > 1:
        raise Exception("Wrong configuration, failed to identify not exactly one batch_optimizer")
    elif batch_optimizers.count() == 1:
        agent_config = batch_optimizers[0].config  # json.loads()
        batch_optimizer_cls = plugins.get_class(batch_optimizers[0].plugin.slug)
        new_batch_optimizer = batch_optimizer_cls(
            config=agent_config  # , kandbox_env=planner["planner_env"]
        )
        planner["batch_optimizer"] = new_batch_optimizer

    # TODO:
    # observation = new_env.reset()
    if "replay" not in new_env.config.keys():
        new_env.config["replay"] = False
        new_env.config["auto_predict_unplanned"] = False

    if new_env.config["replay"]:
        # new_env.reset()   # replay_env already includes it
        new_env.run_mode = EnvRunModeType.REPLAY
        # new_env.replay_env()  # This is repeated, since it is already replay-ed in init
        log.debug("Replayed Env skipped: team_id={} ...".format(team_id))
        new_env.run_mode = EnvRunModeType.PREDICT
    # else:
    #     raise ValueError("Must replay for loading")

    if new_env.config["auto_predict_unplanned"]:
        log.debug("auto_predict_unplanned Env: {}, started ...".format(team_id))
        auto_exec_rl_planner_over_unplanned(planner)
    return planner


def get_active_planner(
    *,
    org_code: str,
    team_id: int,
    start_day: str,
    end_day: str = None,
    nbr_of_days_planning_window: int = None,
    force_reload: bool = False,
):
    if not nbr_of_days_planning_window:
        nbr_of_days_planning_window = date_util.days_between_2_day_string(
            start_day=start_day, end_day=end_day
        )
    team_id = int(team_id)

    with planners_dict_lock:
        # async with planners_dict_lock:
        if force_reload:
            log.warn("force_reload, be careful since this destroys all...")
            if (org_code, team_id, start_day, nbr_of_days_planning_window) in planners_dict.keys():
                del planners_dict[(org_code, team_id, start_day, nbr_of_days_planning_window)]
                # orig_planner = planners_dict.pop((org_code, team_id, start_day, end_day), None)
                # if orig_planner:
                log.debug(
                    f"force_reload==True, and orig_planner is removed from cache for org_code={org_code}, team_id={team_id}, start_day={start_day}"
                )
        if (org_code, team_id, start_day, nbr_of_days_planning_window) not in planners_dict.keys():
            new_planner = load_planner(
                org_code=org_code,
                team_id=team_id,
                start_day=start_day,
                nbr_of_days_planning_window=nbr_of_days_planning_window,
            )

            planners_dict[(org_code, team_id, start_day, nbr_of_days_planning_window)] = new_planner
            log.info(
                f"planner re-created for org_code={org_code}, team_id={team_id}, start_day={start_day}"
            )
        else:
            log.info(
                f"planner reused from cache for org_code={org_code}, team_id={team_id}, start_day={start_day}"
            )
        active_planner = planners_dict[(org_code, team_id, start_day, nbr_of_days_planning_window)]
        # Before returning env to user, replay message from Kafka to make sure it is reflecting the latest status from kafka and redis.
        active_planner["planner_env"].mutate_check_env_window_n_replay()

    return active_planner


def get_default_active_planner(
    org_code: str,
    team_id: int,
):
    planner = get_active_planner(
        org_code=org_code,
        team_id=int(team_id),
        start_day=config.DEFAULT_START_DAY,
        nbr_of_days_planning_window=-1,
    )

    return planner


def get_appt_dict_from_redis(appt_id: str) -> dict:

    appt_on_redis = redis_conn.hgetall(
        "{}{}".format(config.APPOINTMENT_ON_REDIS_KEY_PREFIX, appt_id)
    )

    return appt_on_redis


def get_appt_code_list_from_redis() -> List:

    res_appt_list = []
    for key in redis_conn.scan_iter(match=f"{config.APPOINTMENT_ON_REDIS_KEY_PREFIX}*"):
        job_code = key.decode("utf-8").split(config.APPOINTMENT_ON_REDIS_KEY_PREFIX)[1]
        res_appt_list.append(job_code)
    return res_appt_list


def reset_planning_window_for_team(org_code, team_id):

    team_env_key = "env_{}_{}".format(org_code, team_id)
    lock_key = "lock_env/env_{}_{}".format(org_code, team_id)

    log.debug(f"Trying to get lock for clearing env = {team_env_key}")
    with redis_conn.lock(
        lock_key, timeout=60
    ) as lock:
        for key in redis_conn.scan_iter(f"{team_env_key}/*"):
            redis_conn.delete(key)
    log.info(f"All redis records are cleared for env = {team_env_key}")

    planner = get_active_planner(
        org_code=org_code,
        team_id=team_id,
        start_day=config.DEFAULT_START_DAY,
        nbr_of_days_planning_window=-1,
        force_reload=True
    )
    rl_env = planner["planner_env"]
    # rl_env.replay_env_to_redis()

    result_info = {"status": "OK", "config": rl_env.config}
    return result_info, planner


def run_batch_optimizer(org_code, team_id):

    clear_team_data_for_redispatching(org_code, team_id)
    result_info, planner = reset_planning_window_for_team(org_code, team_id)
    rl_env = planner["planner_env"]

    planner["batch_optimizer"].dispatch_jobs(env=rl_env)
    log.info(f"Finished dispatching {len(rl_env.jobs_dict)} jobs for env={rl_env.jobs_dict}...")

    result_info = {"status": "OK", "jobs_dispatched": len(rl_env.jobs_dict)}
    return result_info
