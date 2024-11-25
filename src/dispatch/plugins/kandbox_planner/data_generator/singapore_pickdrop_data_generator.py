from dispatch.config import DATA_START_DAY
from dispatch.plugins.kandbox_planner.env.env_enums import JobPlanningStatus, JobType
from dispatch.planner_service.scheduled import update_planning_window
from dispatch import config
from dispatch.planner_plugin.models import ServicePlugin
from dispatch.planner_plugin import service as service_plugin_service
from dispatch.planner_env.planner_service import get_active_planner, update_service_plugin_config
from dispatch.plugins.kandbox_planner.planner_engine.opti1day.opti1day_planner import (
    Opti1DayPlanner,
)
from dispatch.plugins.base import plugins 
from dispatch.plugins.kandbox_planner.data_adapter.kplanner_api_adapter import KPlannerAPIAdapter
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util
import json
import os
import random
from datetime import datetime, timedelta
from pprint import pprint
from random import randint
import copy
import pandas as pd
import requests
import logging

log = logging.getLogger(__name__)

FIXED_JOB_DURATION = 1

KANDBOX_DATE_FORMAT = config.KANDBOX_DATE_FORMAT  # '%Y%m%d'
# Singapore sample data was acquired from here:
# http://www.nationalarchives.gov.uk/doc/open-government-licence/version/2/
# https://data.london.gov.uk/dataset/gla-group-land-assets?q=gla%20asset
# https://github.com/qiyangduan/uk_address_convert_bng_longlat

df = pd.read_csv(
    "{}/plugins/kandbox_planner/util/singapore_postcode_longlat_20221111.csv".format(config.basedir),
    header=0,
    sep=",",
    encoding="utf_8",
)


df["postcode"] = df.apply(lambda x:  str(int(x['postcode'])).zfill(6) , axis=1 )

def generate_all_workers(opts):
    worker_count = opts["generate_worker_count"]
    list_to_insert = []
    gps_df = df.sample(n=worker_count,random_state=worker_count).reset_index(drop=True)
    for w_index, w in gps_df.iterrows():
        gps = {
            "code":"W{}_{}".format(w_index, w.postcode,),
            "geo_latitude" :w["latitude_mean"] ,
            "geo_longitude":w["longitude_mean"] ,
        }

        # print("adding worker: ", worker, gps)
        worker_code = "W{}".format(w_index)
        myobj = {
            "code": worker_code,
            "name": worker_code,
            "auth_username": worker_code,
            "is_active": True,
            "team": {
                "code": opts["team_code"], 
            },
            "location": gps,
            "flex_form_data": {
                "level": 1,
                "skills": ["level_1"],
                "assistant_to": None,
                "is_assistant": False, 
                "maxAcceptOrderCount": 6,  # random.randint(6, 14),
            },
            # "weekly_working_minutes": "[ [0, 0], [480, 1140],[480, 1140],[480, 1140],[480, 1140],[480, 1140],  [0, 0]]",
            # 'level': 0,
            "tags": [],
        }

        list_to_insert.append(myobj)
    return list_to_insert


def generate_one_day_orders(opts, worker_list, current_day):

    list_to_insert = []
    inserted_jobs = 0
    skills = [
        "level_1",
    ]

    pick_gps_df = df.sample(
        n=opts["generate_job_count"],
        random_state=opts["generate_job_count"] * 100
    ).reset_index(drop=True)

    drop_gps_df = df.sample(
        n=opts["generate_job_count"],
        random_state=opts["generate_job_count"] * 100
    ).reset_index(drop=True)

    drop_gps_df.columns = ['postcode_drop', 'longitude_drop', 'latitude_drop']
    gps_df = pd.concat([pick_gps_df, drop_gps_df], axis = 1)


    for loc_index, loc in gps_df.iterrows(): 
        # 首先是-取-的任务
        order_code = "ORD{}-{}".format(loc['postcode'], loc['postcode_drop'])

        pick_job_code = "{}-0-pick".format(order_code)
        pick_job = {
            "code": pick_job_code,
            "job_type": JobType.JOB,
            "name": pick_job_code,
            "flex_form_data": { 
                "job_schedule_type": "N", 
                "preceding_job_codes": []
            },
            "team": {
                "code": opts["team_code"], 
            },
            "location": None,
            "geo_latitude" :loc["latitude_mean"] ,
            "geo_longitude":loc["longitude_mean"] ,
            "planning_status": JobPlanningStatus.UNPLANNED,
            "requested_duration_minutes": FIXED_JOB_DURATION,
            "scheduled_duration_minutes": FIXED_JOB_DURATION,
            "requested_start_datetime": datetime.strftime(
                current_day + timedelta(minutes=880), "%Y-%m-%dT%H:%M:%S"
            ),
            "scheduled_start_datetime": None,
            "requested_primary_worker": {
                "code": "W1",  # worker_list[random.randint(0, 5)]["code"],
                "team": {
                        "code": opts["team_code"], 
                },
            },
            "scheduled_primary_worker": {
                "code": worker_list[random.randint(0, len(worker_list)-1)]["code"],
                "team": {
                    "code": opts["team_code"], 
                },
            },
            "auto_planning": False,
        }

        # 送的任务
        drop_job = copy.deepcopy(pick_job)
 
        drop_job.update(
            {
            "code": "{}-0-drop".format(order_code),
            "name": "{}-0-drop".format(order_code),
            "flex_form_data": {
                "job_schedule_type": "N", 
                "preceding_job_codes": [pick_job_code]
            },
            "team": {
                "code": opts["team_code"],
                "name": opts["team_code"],
            },
            "geo_latitude" :loc["latitude_drop"] ,
            "geo_longitude":loc["latitude_drop"] ,
            }
        )





        myobj ={ 
            "code": order_code,
            "order_type": "pickdrop", 
            "external_order_code": order_code, 
            "business_order_status": "not_started", 
            "team": { 
                "code": "default_team"
            },
            "job_list": [pick_job, drop_job]
        }
        list_to_insert.append(myobj)

        inserted_jobs += 1

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

    # update_planning_window(start_minutes=window_start_minutes, team_id=1)

    """
    return
    """
    kplanner_api = KPlannerAPIAdapter(
        service_url=opts["service_url"],
        username=opts["username"],
        password=opts["password"],
        team_code=opts["team_code"],
        access_token=opts.get('token',None),
    )
    worker_list = generate_all_workers(opts=opts)
    if opts["generate_target"] in ['worker','all']:
        kplanner_api.insert_all_workers(worker_list)
    else:
        print("worker data not saved.")

    if opts["generate_target"] in ['job','all']:
        current_day = GENERATOR_START_DATE + timedelta(days=0) 
        order_list = generate_one_day_orders(
            current_day=current_day, 
            worker_list=worker_list, 
            opts=opts
        )
        kplanner_api.insert_all_orders(order_list)
    else:
        print("job data not saved.")

    return


if __name__ == "__main__":
    # generate_all()
    print("pls call cli.py")
