from dispatch.plugins.kandbox_planner.env.env_enums import JobPlanningStatus
from dispatch.plugins.kandbox_planner.env.kprl_env_rllib_history_affinity import (
    KPlannerHistoryAffinityTopNGMMEnv,
)
from dispatch.plugins.kandbox_planner.agent.kprl_agent_rllib_ppo import KandboxAgentRLLibPPO
import json
import os
import random
from datetime import datetime, timedelta
from pprint import pprint
from random import randint, seed

import pandas as pd
import requests

import dispatch.plugins.kandbox_planner.config as config
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util
from dispatch.database import get_session_4_org
from dispatch.plugins.kandbox_planner.data_adapter.kplanner_api_adapter import KPlannerAPIAdapter
from dispatch.plugins.kandbox_planner.data_adapter.kplanner_db_adapter import KPlannerDBAdapter

from dispatch.incident.scheduled import calc_historical_location_features_real_func

from dispatch.plugins.base import plugins
from dispatch.plugins.kandbox_planner.planner_engine.opti1day.opti1day_planner import (
    Opti1DayPlanner,
)
from dispatch.planner_env.planner_service import get_active_planner, update_service_plugin_config
from dispatch.planner_plugin import service as service_plugin_service
from dispatch.planner_plugin.models import ServicePlugin

from dispatch.config import MINUTES_PER_DAY, MAX_NBR_OF_JOBS_PER_DAY_WORKER
# Sample Basic Auth Url with login values as username and password
import ray

# seed random number generator
seed(1978)

# import config.settings.local as config

KANDBOX_DATE_FORMAT = config.KANDBOX_DATE_FORMAT  # '%Y%m%d'


print("config.basedir=", config.basedir)
with open("{}/util/job_addr.json".format(config.basedir), "r") as in_file:
    job_addr = json.load(in_file)
    JOB_GPS_LIST = job_addr


with open("{}/util/worker_addr.json".format(config.basedir), "r") as in_file:
    worker_addr = json.load(in_file)
    WORKER_GPS_LIST = worker_addr


def get_worker_location(loc_i):
    # distance = haversine(loc_1[0] , loc_1[1] , loc_2[0], loc_2[1])

    ll = worker_addr[loc_i]["latlong"]

    x = ll[1]
    y = ll[0]
    return "{}:{}".format(x, y)


def get_job_location(loc_i):
    # distance = haversine(loc_1[0] , loc_1[1] , loc_2[0], loc_2[1])

    ll = job_addr[loc_i]["latlong"]

    x = ll[1]
    y = ll[0]
    return "{}:{}".format(x, y)

    return "{}:{}".format(x, y)


def generate_and_save_one_day_orders(current_day, current_shifts, worker_list, kplanner_api=None):
    for index, shift in enumerate(current_shifts):
        # for shift in current_shifts:
        # [0, 'FS', '7:12', 108, 60, 32]
        loc_i = random.randint(0, len(job_addr) - 2)
        shift[2] = get_job_location(
            loc_i
        )  # '{}:{}'.format(x,y) x, y = randint(1, 99), randint(1, 99)
        shift[3] = randint(560, 1040)
        shift[5] = randint(3 * 5, 30 * 5)
        shift[6] = "loc_{}".format(loc_i)

    generate_all_orders(
        current_day=current_day,
        current_shifts=current_shifts,
        worker_list=worker_list,
        kplanner_api=kplanner_api,
    )


def select_all_workers():
    url = "http://localhost:5000/api/v1/worker"
    response = requests.get(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Token {}".format(access_token),
        },
    )
    resp_json = response.json()

    return resp_json

    if resp_json["count"] < 1:
        print("it is already empty!")
        return []


def generate_all_workers(worker_list=None, kplanner_api=None):
    # url = '{}/kpdata/workers/'.format(kplanner_service_url)
    index = 0
    list_to_insert = []
    for worker in worker_list:
        gps = get_worker_location(index)

        print("adding worker: ", worker, gps)

        index += 1
        myobj = {
            "email": worker[1],
            "name": "{}-{}".format(worker[1], worker[0]),
            "username": "{}-{}".format(worker[1], worker[0]),
            # 'skills': '[1]',
            "is_active": True,
            "team": {"email": "beijing_t1", "name": "beijing_t1", },
            "worker_form_data": {
                "level": 5,
                "skills": ["skill_1"],
                "weekly_working_minutes": "[ [0, 0], [480, 1140],[480, 1140],[480, 1140],[480, 1140],[480, 1140],  [0, 0]]",
                "code": "{}-loc-{}".format(worker[1], worker[0]),
                "geo_latitude": gps.split(":")[1],
                "geo_longitude": gps.split(":")[0],
            },
            "weekly_working_minutes": "[ [0, 0], [480, 1140],[480, 1140],[480, 1140],[480, 1140],[480, 1140],  [0, 0]]",
            # 'level': 0,
            "terms": [],
        }

        list_to_insert.append(myobj)
    kplanner_api.insert_all_workers(list_to_insert)


def delete_all_workers(kplanner_api=None):

    kplanner_api.delete_all_workers()
    return

    url = "{}/kpdata/workers/".format(kplanner_service_url)
    response = requests.get(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Token {}".format(access_token),
        },
    )
    resp_json = response.json()
    # Convert JSON to dict and print
    # print(resp_json)
    if len(resp_json) < 1:
        print("it is already empty!")
        return

    for worker in resp_json:
        print("deleting worker: ", worker)
        url = "{}/kpdata/workers/".format(kplanner_service_url) + str(worker.worker_code) + ""
        # print(url)
        response = requests.delete(url, headers={"Authorization": "Token {}".format(access_token)})
        print(response.text)


def select_all_orders(current_day=None):

    return
    url = "http://localhost:5000/api/v1/workorder"
    if current_day is not None:
        url = "http://localhost:5000/api/v1/workorder/?q=(filters:!((col:requested_start_date,opr:eq,value:{})),order_columns:order_code,order_direction:desc)".format(
            datetime.strftime(current_day, KANDBOX_DATE_FORMAT)
        )
        # ,columns:!(order_code,name,planning_status,requested_start_date,scheduled_start_time,geo_latitude,geo_longitude,fixed_date_time_flag,requested_start_time,requested_duration_minutes)
        print(url)
    response = requests.get(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Token {}".format(access_token),
        },
    )
    resp_json = response.json()

    return resp_json


def select_orders_by_workers_TODO(workers=[]):
    url = "http://localhost:5000/api/v1/workorder"
    response = requests.get(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Token {}".format(access_token),
        },
    )
    resp_json = response.json()

    return resp_json


def generate_all_orders(current_day, current_shifts, worker_list=None, kplanner_api=None):
    list_to_insert = []
    for order in current_shifts:
        # print('adding order: ',order)
        # [100, 'FS', '06:00', 18, 60, 32]
        job_code = "{}-{}-{}".format(datetime.strftime(current_day, "%m%d"), order[0], order[1])
        myobj = {
            "job_code": job_code,
            "title": job_code,
            "description": job_code,
            "job_form_data": {
                "requested_min_level": 1,
                "requested_skills": ["skill_1"],
                "job_schedule_type": order[1],
                "mandatory_minutes_minmax_flag": 1 if order[1] == "FS" else 0,
                "requested_start_min_minutes": order[3],
                "requested_start_max_minutes": order[3],
            },
            "team": {"email": "beijing_t1", "name": "beijing_t1", },
            # "job_schedule_type": order[1],
            # "requested_min_level": 0,
            # "code": "{}-{}".format(order[0], order[1]),
            "location": {
                "code": "{}-{}".format(order[0], order[1]),
                "geo_latitude": order[2].split(":")[1],
                "geo_longitude": order[2].split(":")[0],
                "geo_address_text": "北京天安门-{}-{}".format(order[0], order[1]),
                # "geo_json": "testing",
            },
            "planning_status": JobPlanningStatus.UNPLANNED,
            "requested_duration_minutes": order[5],
            "scheduled_duration_minutes": order[5],
            "requested_start_datetime": datetime.strftime(
                current_day + timedelta(minutes=order[3]), "%Y-%m-%dT%H:%M:%S"
            ),
            "scheduled_start_datetime": datetime.strftime(
                current_day + timedelta(minutes=order[3]), "%Y-%m-%dT%H:%M:%S"
            ),
            "requested_primary_worker": {
                "email": worker_list[random.randint(0, 5)][1],
                "team": {"email": "email_fake", "name": "email_fake"},
            },
            "scheduled_primary_worker": {
                "email": worker_list[random.randint(0, 5)][1],
                "team": {"email": "email_fake", "name": "email_fake"},
            },
            "auto_plan_flag": False,
        }
        list_to_insert.append(myobj)

    kplanner_api.insert_all_jobs(list_to_insert)


def save_RL_dispatched_orders_one_day(solution_json):
    # print(worker_day)
    # {'duration': 100, 'job_code': '0-FS', 'fixed_schudule': {'fs_indicator': 'FT', 'fixed_minute_time_slot': [148.0, 148.0]}, 'job_gps': [57.0, 98.0], 'history_job_worker_count': [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], 'history_minute_start_time': 0, 'tolerated_day_min': 0, 'tolerated_day_max': 0, 'expected_job_day': 0, 'expected_job_day_orig': 0, 'actual_job_worker': None, 'actual_job_day': 1, 'actual_job_start_minute': 148, 'actual_job_duration': 20},
    for task in solution_json:
        task_id = task["job_code"]  # + 1
        worker_code = task["VisitOwner_worker_code"]
        url = "http://localhost:5000/api/v1/workorder/" + str(task_id)
        start_time_minute = task["start_time_minute"]
        updated_order = {}  # latest_order_dict[id]
        updated_order.update(
            {
                "planning_status": JobPlanningStatus.IN_PLANNING,
                "scheduled_worker_rel": worker_code,
                "actual_worker_rel": worker_code,
                "scheduled_start_time": date_util.minutes_to_time_string(start_time_minute),
                "actual_start_time": date_util.minutes_to_time_string(start_time_minute),
                "scheduled_duration_minutes": task["duration"],
                "actual_duration_minutes": task["duration"],
            }
        )
        print(updated_order)
        response = requests.put(
            url,
            json=updated_order,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Token {}".format(access_token),
            },
        )

        # Convert JSON to dict and print
        print(response.text)


def delete_all_orders(kplanner_api=None):
    kplanner_api.delete_all_orders()
    return

    url = "{}/kpdata/jobs/".format(
        kplanner_service_url
    )  # http://localhost:5000/api/v1/workorder/1'
    response = requests.get(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Token {}".format(access_token),
        },
    )
    resp_json = response.json()
    # Convert JSON to dict and print
    # print(resp_json)
    if len(resp_json) < 1:
        print("it is already empty!")
        return

    for worker in resp_json:
        print("deleting order: ", worker)
        url = "{}/kpdata/jobs/".format(kplanner_service_url) + str(worker.job_code) + ""
        print(url)
        response = requests.delete(url, headers={"Authorization": "Token {}".format(access_token)})
        print(response.text)


def init_service_n_plugins(db_session=None):
    pass


def generate_all(opts):

    _SHIFTS = [
        [0, "FS", "7:12", 108, 60, 32],
        [1, "N", "8:3", 26, 68, 22],
        [2, "N", "06:4", 66, 121, 25],
        [3, "N", "15:5", 20, 72, 12],
        [4, "N", "11:4", 133, 189, 16],
        [5, "N", "13:2", 2, 19, 17],
        [6, "N", "20:5", 91, 131, 34],
        [7, "N", "21:7", 8, 30, 52],
        [8, "FS", "3:45", 180, 190, 60],
        [9, "N", "5:49", 38, 80, 22],
        [10, "FS", "14:54", 43, 90, 37],
        [11, "N", "13:60", 169, 169, 25],
        [12, "FS", "19:55", 218, 215, 37],
        [13, "N", "20:59", 196, 234, 38],
        [14, "N", "20:48", 235, 248, 13],
        [15, "FS", "14:54", 43, 90, 37],
        [16, "N", "13:60", 169, 169, 25],
        [17, "FS", "19:55", 218, 215, 37],
        [18, "N", "20:59", 196, 234, 38],
        [19, "N", "20:48", 235, 248, 13],
        [20, "N", "20:59", 196, 234, 38],
        [21, "N", "20:48", 235, 248, 13],
    ]
    for s in _SHIFTS:
        s[4] = 0
        s.append("loc_?")

    # worker_day =[[[1, 55, 22], [7, 82, 52], ['sink']], [[0, 108, 32], [2, 143, 25], [9, 174, 22], ['sink']], [[3, 20, 12], [5, 35, 17], [4, 55, 16], [6, 91, 34], ['sink']], [[8, 180, 60], ['sink']], [[11, 146, 25], [12, 218, 37], [14, 258, 13], ['sink']], [[10, 43, 37], [13, 84, 38], ['sink']]]

    people = ("Tom", "Mike", "Harry", "Slim", "Jim", "Duan")
    worker_list = [[wi, people[wi], get_worker_location(wi)] for wi in range(len(people))]

    ss = str(opts["start_day"])
    ee = str(opts["end_day"])
    GENERATOR_START_DATE = datetime.strptime(ss, KANDBOX_DATE_FORMAT)
    GENERATOR_END_DATE = datetime.strptime(ee, KANDBOX_DATE_FORMAT)

    PREDICT_START_DATE = datetime.strptime(opts["start_day"], KANDBOX_DATE_FORMAT) + timedelta(
        days=opts["training_days"]
    )
    db_session = get_session_4_org(org_code=opts["org_code"])

    """
        """

    kplanner_api = KPlannerAPIAdapter(
        service_url=opts["service_url"],
        access_token=opts["bearer_token"],
        team_code=opts["team_id"],
    )
    generate_all_workers(worker_list, kplanner_api)

    # delete_all_workers()
    # purge_all_workers_jobs()
    # delete_all_jobs()

    for day_i in range(999):
        current_day = GENERATOR_START_DATE + timedelta(days=day_i)
        if current_day >= GENERATOR_END_DATE:
            break
        generate_and_save_one_day_orders(
            current_day, current_shifts=_SHIFTS, worker_list=worker_list, kplanner_api=kplanner_api
        )
        #

    for day_i in range(opts["training_days"]):
        current_day = GENERATOR_START_DATE + timedelta(days=day_i)
        if current_day >= GENERATOR_END_DATE:
            break

        next_day = GENERATOR_START_DATE + timedelta(days=day_i + 1)
        planner = get_active_planner(
            org_code=opts["org_code"],
            team_id=opts["team_id"],
            start_day=datetime.strftime(current_day, KANDBOX_DATE_FORMAT),
            end_day=datetime.strftime(next_day, KANDBOX_DATE_FORMAT),
        )
        planner["batch_optimizer"].dispatch_jobs(env=planner["planner_env"])

    # pprint(res)

    print("Started location feature calc ...")

    calc_historical_location_features_real_func(db_session=db_session)
    db_session.close()

    db_session = get_session_4_org(org_code=opts["org_code"])

    service_plugin_service.switch_agent_plugin_for_service(
        db_session=db_session,
        service_name="planner",
        agent_slug="kandbox_agent_history_replay_dense",
    )

    # This is to specifically train kandbox_agent_history_replay_dense
    kandbox_agent_history_replay_dense = plugins.get_class("kandbox_agent_history_replay_dense")(
        config=None
    )
    # new_agent = agent_cls
    kandbox_agent_history_replay_dense.train_model_by_replaying_history(
        org_code=opts["org_code"],
        team_id=opts["team_id"],
        start_day=opts["start_day"],
        end_day=datetime.strftime(
            datetime.strptime(opts["start_day"], KANDBOX_DATE_FORMAT)
            + timedelta(days=opts["training_days"]),
            KANDBOX_DATE_FORMAT,
        ),
    )

    # This is to specifically train ppo agent
    """
    kandbox_agent_rllib_ppo_cls = plugins.get_class("kandbox_agent_rllib_ppo")(
        config=None
    )
    """
    # ray.init(ignore_reinit_error=True, log_to_driver=False)

    """

    service_plugin_service.switch_agent_plugin_for_service(
        db_session=db_session, service_name="planner", agent_slug="kandbox_agent_rllib_ppo"
    )

    for day_i in [0]:  # range(opts["training_days"]):
        current_day = PREDICT_START_DATE + timedelta(days=day_i)
        if current_day >= GENERATOR_END_DATE:
            break

        next_day = PREDICT_START_DATE + timedelta(days=day_i + 1)
        planner = get_active_planner(
            org_code=opts["org_code"],
            team_id=opts["team_id"],
            start_day=datetime.strftime(current_day, KANDBOX_DATE_FORMAT),
            end_day=datetime.strftime(next_day, KANDBOX_DATE_FORMAT),
        )
        rl_agent = planner["planner_agent"]

        planner["planner_env"].config["org_code"] = opts["org_code"]
        planner["planner_env"].config["team_id"] = opts["team_id"]

        rl_agent.load_model(env_config=planner["planner_env"].config)
        checkpoint_path = rl_agent.train_model(env_config=planner["planner_env"].config)
        update_service_plugin_config(
            db_session=db_session,
            service_plugin_id=planner["planner_env"].config["service_plugin_id"],
            new_config_dict={"ppo_checkpoint_path": checkpoint_path},
        )
        print(f"Training finished for {current_day} - {next_day}, saved to {checkpoint_path}")
        """

    planning_window = 1
    list_of_agent_slugs = [
        "kandbox_agent_rentokil_heuristic"
    ]  # , "kandbox_agent_rl_heuristic" kandbox_agent_rentokil_heuristic      kandbox_agent_history_replay_dense      kandbox_agent_rllib_ppo
    for slug in list_of_agent_slugs:
        service_plugin_service.switch_agent_plugin_for_service(
            db_session=db_session, service_name="planner", agent_slug=slug
        )

        for day_i in [0, 1]:  # range(0, 999, planning_window):  #
            current_day = PREDICT_START_DATE + timedelta(days=day_i)

            next_day = PREDICT_START_DATE + timedelta(days=day_i + planning_window)
            if next_day > GENERATOR_END_DATE:
                break

            planner = get_active_planner(
                org_code=opts["org_code"],
                team_id=opts["team_id"],
                start_day=datetime.strftime(current_day, KANDBOX_DATE_FORMAT),
                end_day=datetime.strftime(next_day, KANDBOX_DATE_FORMAT),
            )
            rl_agent = planner["planner_agent"]

            # planner["planner_env"].config["org_code"] = opts["org_code"]
            # planner["planner_env"].config["team_id"] = int(opts["team_id"])

            # rl_agent.load_model(env_config=planner["planner_env"].config)

            rl_agent.dispatch_jobs(env=planner["planner_env"])

            print("Finished regression for (DATE={}: AGENT slug={}) ".format(current_day, slug))

    db_session.close()
    ray.shutdown()


if __name__ == "__main__":
    # generate_all()
    print("pls call cli.py")
