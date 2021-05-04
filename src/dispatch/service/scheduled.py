import time
from datetime import datetime
import redis
from redis.exceptions import LockError

from schedule import every

from dispatch.config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD

from dispatch.plugins.kandbox_planner.data_adapter.kafka_adapter import KafkaAdapter

from dispatch.service.planner_service import (
    get_appt_code_list_from_redis,
    get_default_active_planner,
)

from dispatch.decorators import background_task
from dispatch.scheduler import scheduler

from dispatch.config import SAY_HELLO_SLEEP_TIME

import logging

log = logging.getLogger(__name__)


def update_planning_window(db_session=None, start_minutes=-1, org_code="0", team_id=2):
    if REDIS_PASSWORD == "":
        redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=None)
    else:
        redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)

    env_config = {}
    env_config["team_id"] = team_id
    env_config["org_code"] = org_code
    env_config["team_env_key"] = "env_{}_{}".format(env_config["org_code"], env_config["team_id"])
    env_config["env_inst_seq"] = redis_conn.incr(
        "{}/env/counter".format(env_config["team_env_key"])
    )
    env_config["env_inst_code"] = "{}_{}_{}".format(
        env_config["team_env_key"], env_config["env_inst_seq"], "duanmac15"
    )
    env_config["kafka_input_window_offset"] = 0

    env = type("new", (object,), env_config)

    kafka_server = KafkaAdapter(env=env)

    kafka_server.trigger_update_planning_window(start_minutes=start_minutes)

    log.error("Do Update Planning Window")


@scheduler.add(every(1).day.at("17:00"), name="update-planning-window")
@background_task
def update_planning_window_scheduled(db_session=None):
    update_planning_window(db_session, start_minutes=-1)


@scheduler.add(every(2).hours, name="refresh-recommendation")
@background_task
def refresh_recommendation(db_session=None):
    if REDIS_PASSWORD == "":
        redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=None)
    else:
        redis_conn = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD)

    env_config = {}
    env_config["team_id"] = 2
    env_config["org_code"] = "0"
    env_config["team_env_key"] = "env_{}_{}".format(env_config["org_code"], env_config["team_id"])
    env_config["env_inst_seq"] = redis_conn.incr(
        "{}/env/counter".format(env_config["team_env_key"])
    )
    env_config["env_inst_code"] = "{}_{}_{}".format(
        env_config["team_env_key"], env_config["env_inst_seq"], "duanmac15"
    )

    env_config["kafka_input_window_offset"] = 0
    env_config["kafka_slot_changes_offset"] = 0

    env = type("new", (object,), env_config)

    kafka_server = KafkaAdapter(env=env)

    appt_list = get_appt_code_list_from_redis()
    for job_code in appt_list:

        kafka_server.trigger_refresh_single_recommendation(job_code)

        time.sleep(2)

    log.error("Do Refresh Recommendation")


"""@scheduler.add(every(SAY_HELLO_SLEEP_TIME).seconds, name="health-check")
@background_task
def health_check(db_session=None):
    team_id = 2
    org_code = "0"

    begin_time = datetime.now()

    planner = get_default_active_planner(org_code=org_code, team_id=team_id)
    rl_env = planner["planner_env"]

    total_time = datetime.now() - begin_time

    rep = {
        "env_inst_code": rl_env.env_inst_code,
        "window_offset": rl_env.kafka_input_window_offset,
        "slot_offset": rl_env.kafka_slot_changes_offset,
    }
    log.error(
        f"Date: {begin_time}, Elapsed: {total_time}, Response = {rep}"
if __name__ == "__main__":
    health_check()
"""
