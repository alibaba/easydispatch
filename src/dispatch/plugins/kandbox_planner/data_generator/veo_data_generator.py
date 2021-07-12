from dispatch.config import DATA_START_DAY
from dispatch.plugins.kandbox_planner.env.env_enums import JobPlanningStatus, JobType
from dispatch.service.scheduled import update_planning_window
from dispatch import config
from dispatch.plugins.kandbox_planner.agent.kprl_agent_rllib_ppo import KandboxAgentRLLibPPO
from dispatch.service_plugin.models import ServicePlugin
from dispatch.service_plugin import service as service_plugin_service
from dispatch.service.planner_service import get_active_planner, update_env_config
from dispatch.plugins.kandbox_planner.planner_engine.opti1day.opti1day_planner import (
    Opti1DayPlanner,
)
from dispatch.plugins.base import plugins
from dispatch.job.scheduled import calc_historical_location_features_real_func
from dispatch.plugins.kandbox_planner.data_adapter.kplanner_api_adapter import KPlannerAPIAdapter
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util
import json
import os
import random
from datetime import datetime, timedelta
from pprint import pprint
from random import randint, seed

import pandas as pd
import requests
import logging

log = logging.getLogger(__name__)


KANDBOX_DATE_FORMAT = config.KANDBOX_DATE_FORMAT  # '%Y%m%d'
# London sample data is acquired from here:
# http://www.nationalarchives.gov.uk/doc/open-government-licence/version/2/
# https://data.london.gov.uk/dataset/gla-group-land-assets?q=gla%20asset
# https://github.com/qiyangduan/uk_address_convert_bng_longlat

df = pd.read_csv(
    "{}/plugins/kandbox_planner/util/sample_london_addreses.csv".format(config.basedir),
    header=0,
    sep="|",
    encoding="utf_8",
)
gps_df = df.sample(frac=1).reset_index(drop=True)


gps_df["Address"].fillna("N/A", inplace=True)
gps_df["Post_Code"].fillna("N/A", inplace=True)

job_addr = []
worker_addr = []
for _, loc in gps_df.iterrows():
    gps_dict = {
        "geo_latitude": loc["lat"],
        "geo_longitude": loc["long"],
        "geo_address_text": loc["Address"],
        "geo_json": {"postcode": loc["Post_Code"], "formatted_address_text": loc["Address"]},
    }
    if random.randint(0, 20) > 2:
        job_addr.append(gps_dict)
    else:
        worker_addr.append(gps_dict)


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


def get_skills(worker):
    skills = []
    for step in range(1, 5):
        if step <= worker["electric"]:
            skills.append("electric_{}".format(step))

    for step in range(1, 5):
        if step <= worker["mechanic"]:
            skills.append("mechanic_{}".format(step))
    return skills


def generate_all_workers():
    # url = '{}/kpdata/workers/'.format(kplanner_service_url)
    worker_df = pd.read_csv(
        "{}/plugins/kandbox_planner/util/worker_spec_veo.csv".format(config.basedir),
        header=0,
        sep=";",
        encoding="utf_8",
    )
    list_to_insert = []
    for loc_index, worker in worker_df.iterrows():
        # if random.randint(0, 20) > 2:
        gps = worker_addr[loc_index]
        gps["location_code"] = "{}-{}".format(worker["name"].replace(" ", "_"), loc_index)

        # print("adding worker: ", worker, gps)
        skills = get_skills(worker)

        myobj = {
            "code": worker["name"],
            "name": worker["name"],
            "auth_username": worker["name"].replace(" ", "_"),
            # 'skills': '[1]',
            "is_active": True,
            "team": {
                "code": "london_t1",
                "name": "london_t1",
            },
            "location": {
                "location_code": gps["location_code"],
                "geo_latitude": gps["geo_latitude"],
                "geo_longitude": gps["geo_longitude"],
            },
            "flex_form_data": {
                "level": worker["electric"],
                "skills": skills,
                # "weekly_working_minutes": "[ [0, 0], [480, 1140],[480, 1140],[480, 1140],[480, 1140],[480, 1140],  [0, 0]]",
                # "max_overtime_minutes": 180,
                "assistant_to": None,
                "is_assistant": False,
            },
            # "weekly_working_minutes": "[ [0, 0], [480, 1140],[480, 1140],[480, 1140],[480, 1140],[480, 1140],  [0, 0]]",
            # 'level': 0,
            "tags": [],
        }

        list_to_insert.append(myobj)
    return list_to_insert


def generate_one_day_orders(current_day, worker_list, nbr_jobs, job_start_index, auto_planning_flag):

    job_df = pd.read_csv(
        "{}/plugins/kandbox_planner/util/job_spec_veo.csv".format(config.basedir),
        header=0,
        sep=";",
        encoding="utf_8",
    )
    loc_job_index = job_start_index
    list_to_insert = []
    inserted_jobs = 0
    if nbr_jobs < job_df.count().max():
        job_df = job_df.sample(n=nbr_jobs)
    for _, job_schedule_type in job_df.iterrows():

        skills = [
            "electric_{}".format(job_schedule_type["electric"]),
            "mechanic_{}".format(job_schedule_type["mechanic"]),
        ]

        for job_i in range(job_schedule_type["Quantity"]):
            loc_job_index += 1
            loc_index = random.randint(0, len(job_addr) - 1)

            gps = job_addr[loc_index]
            gps["location_code"] = "job_loc_{}".format(loc_index)

            job_code = "{}-{}-{}-{}".format(
                datetime.strftime(current_day, "%m%d"),
                loc_job_index,
                job_schedule_type["name"].split(" ")[0],
                loc_index,
            )
            myobj = {
                "code": job_code,
                "job_type": JobType.JOB,  # "visit"
                "name": job_code,
                "flex_form_data": {
                    "requested_min_level": 1,
                    "requested_skills": skills,
                    "job_schedule_type": "N",
                    "mandatory_minutes_minmax_flag": 0,
                    "tolerance_start_minutes": -1440,
                    "tolerance_end_minutes": 2880,
                    "min_number_of_workers": 1,
                    "max_number_of_workers": 1,
                    "priority": job_schedule_type["priority"],
                    "included_job_codes": []
                },
                "team": {
                    "code": "london_t1",
                    "name": "london_t1",
                },
                "location": gps,
                "planning_status": JobPlanningStatus.UNPLANNED,
                "requested_duration_minutes": job_schedule_type["Duration"],
                "scheduled_duration_minutes": job_schedule_type["Duration"],
                "requested_start_datetime": datetime.strftime(
                    current_day + timedelta(minutes=0), "%Y-%m-%dT%H:%M:%S"
                ),
                "scheduled_start_datetime": datetime.strftime(
                    current_day + timedelta(minutes=0), "%Y-%m-%dT%H:%M:%S"
                ),
                "requested_primary_worker": {
                    "code": "Alexia",  # worker_list[random.randint(0, 5)]["code"],
                    "team": {
                        "code": "london_t1",
                        "name": "london_t1",
                    },
                },
                "scheduled_primary_worker": {
                    "code": worker_list[random.randint(0, 5)]["code"],
                    "team": {
                        "code": "london_t1",
                        "name": "london_t1",
                    },
                },
                "auto_planning": auto_planning_flag,
            }
            list_to_insert.append(myobj)
            inserted_jobs += 1
            if inserted_jobs >= nbr_jobs:
                return list_to_insert

    return list_to_insert


def dispatch_jobs_batch_optimizer(opts):
    ss = str(opts["start_day"])
    # ee = str(opts["end_day"])
    GENERATOR_START_DATE = datetime.strptime(ss, KANDBOX_DATE_FORMAT)
    # GENERATOR_END_DATE = datetime.strptime(ee, KANDBOX_DATE_FORMAT)

    day_seq = (GENERATOR_START_DATE - datetime.strptime(DATA_START_DAY, "%Y%m%d")).days
    window_start_minutes = day_seq * 1440 + 510  # -1  #
    update_planning_window(start_minutes=window_start_minutes, team_id=1)
    #TODO, remove
    opts["org_code"] = "0"
    planner = get_active_planner(
        org_code=opts["org_code"],
        team_id=opts["team_id"],
        start_day=datetime.strftime(GENERATOR_START_DATE, KANDBOX_DATE_FORMAT),
        nbr_of_days_planning_window=opts["dispatch_days"],
        force_reload=True,
    )

    # for day_i in range(opts["training_days"]):  # [0]:  #
    #     current_day = GENERATOR_START_DATE + timedelta(days=day_i)
    # if current_day >= GENERATOR_END_DATE:
    #     break

    # next_day = GENERATOR_START_DATE + timedelta(days=day_i + 1)
    rl_env = planner["planner_env"]
    planner["batch_optimizer"].dispatch_jobs(env=rl_env)
    log.info(f"Finished dispatching {len(rl_env.jobs_dict)} jobs...")

    current_minutes = (
        GENERATOR_START_DATE - datetime.strptime(DATA_START_DAY, KANDBOX_DATE_FORMAT)
    ).days * 1440 + 1
    update_planning_window(start_minutes=current_minutes)


def generate_all(opts):

    ss = str(opts["start_day"])
    ee = str(opts["end_day"])

    GENERATOR_START_DATE = datetime.strptime(ss, KANDBOX_DATE_FORMAT)
    GENERATOR_END_DATE = datetime.strptime(ee, KANDBOX_DATE_FORMAT)

    data_start_datetime = datetime.strptime(DATA_START_DAY, KANDBOX_DATE_FORMAT)
    window_start_minutes = int((GENERATOR_START_DATE - data_start_datetime).total_seconds() / 60)

    update_planning_window(start_minutes=window_start_minutes, team_id=1)
    """
    return
    """
    kplanner_api = KPlannerAPIAdapter(
        service_url=opts["service_url"],
        username=opts["username"],
        password=opts["password"],
        team_code=opts["team_code"],
    )
    worker_list = generate_all_workers()
    if opts["generate_worker"] == 1:
        kplanner_api.insert_all_workers(worker_list)
    else:
        print("worker data not saved.")

    for day_i in range(999):
        current_day = GENERATOR_START_DATE + timedelta(days=day_i)
        if current_day >= GENERATOR_END_DATE:
            break
        job_list = generate_one_day_orders(
            current_day=current_day, worker_list=worker_list, nbr_jobs=opts[
                "nbr_jobs"], job_start_index=opts["job_start_index"],
            auto_planning_flag=opts["auto_planning_flag"]
        )
        kplanner_api.insert_all_orders(job_list)
        #
    # opts["dispatch_days"] = opts["dispatch_days"]
    # dispatch_jobs_batch_optimizer(opts)
    return
    """
    pprint(res)

    with open('job_addr.json', 'w') as outfile:
        json.dump(job_addr, outfile)

    with open('job_addr.json', 'w') as outfile:
        json.dump(job_addr, outfile)


    with open('job_list.json', 'w') as outfile:
        json.dump(job_list, outfile)

        
    PREDICT_START_DATE = datetime.strptime(opts["start_day"], KANDBOX_DATE_FORMAT) + timedelta(
        days=opts["training_days"]
    )

    print("Started location feature calc ...")

    db_session = SessionLocal()
    calc_historical_location_features_real_func(db_session=db_session)

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
    db_session.close()

    # This is to specifically train ppo agent
    """

    """
    kandbox_agent_rllib_ppo_cls = plugins.get_class("kandbox_agent_rllib_ppo")(
        config=None
    )
    # ray.init(ignore_reinit_error=True, log_to_driver=False)

    db_session = SessionLocal()
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
        update_env_config(
            db_session=db_session,
            service_plugin_id=planner["planner_env"].config["service_plugin_id"],
            new_config_dict={"ppo_checkpoint_path": checkpoint_path},
        )
        print(f"Training finished for {current_day} - {next_day}, saved to {checkpoint_path}")

    planning_window = 1
    list_of_agent_slugs = [
        "kandbox_agent_rl_heuristic"
    ]  # , "kandbox_agent_rl_heuristic"       kandbox_agent_history_replay_dense      kandbox_agent_rllib_ppo
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

            planner["planner_env"].config["org_code"] = opts["org_code"]
            planner["planner_env"].config["team_id"] = int(opts["team_id"])

            # rl_agent.load_model(env_config=planner["planner_env"].config)

            rl_agent.dispatch_jobs(env=planner["planner_env"])

            print("Finished regression for (DATE={}: AGENT slug={}) ".format(current_day, slug))

    db_session.close()
        """


if __name__ == "__main__":
    # generate_all()
    print("pls call cli.py")
