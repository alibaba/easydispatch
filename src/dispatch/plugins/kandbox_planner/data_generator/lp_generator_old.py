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
    "{}/plugins/kandbox_planner/util/ExportToDataIntelligenceV3.csv".format(config.basedir),
    header=0,
    sep=";",
    encoding="utf_8",
)
gps_df = df.sample(frac=1).reset_index(drop=True)


gps_df["LongitudeGPS"].fillna("N/A", inplace=True)
gps_df["LatitudeGPS"].fillna("N/A", inplace=True)
gps_df["HouseNumber"].fillna("N/A", inplace=True)
gps_df["Street"].fillna("N/A", inplace=True)
gps_df["ZipCode"].fillna("N/A", inplace=True)
gps_df["City"].fillna("N/A", inplace=True)


team_dict = {
    'BT': 'Bettembourg region',
    'LD': 'Luxembourg city region',
    'RO': 'Roost region'
}


def init_data():
    '''
    {
        job_id: {
            worker_id:123,
            job_addr:{} 
            row:{}           
        }

    }
    '''

    worker_id_set = set()
    job_id_set = set()
    group_job_dict = {}
    worker_addr = {}
    return_data = {}

    for _, loc in gps_df.iterrows():
        job_id = f"{str(loc['CenterID'])}{str(loc['RouteID'])}{str(loc['Sequence'])}{str(loc['LongitudeGPS'])}"
        if job_id not in group_job_dict:
            group_job_dict[job_id] = []
        group_job_dict[job_id].append(str(loc['ParcelBarcode']))

    for _, loc in gps_df.iterrows():
        worker_id = f"W{str(loc['RouteID'])}{str(loc['CenterID'])}"
        job_id = f"{str(loc['CenterID'])}{str(loc['RouteID'])}{str(loc['Sequence'])}{str(loc['LongitudeGPS'])}"

        if job_id in job_id_set:
            continue
        job_id_set.add(job_id)

        if len(group_job_dict[job_id]) > 4:
            real_job_id = ''.join(group_job_dict[job_id])
        else:
            real_job_id = ''.join(group_job_dict[job_id][:4]) + str(random.randint(0, 10))

        address = f"{loc['City']} {loc['HouseNumber']} {loc['Street']} {loc['ZipCode']} "
        gps_dict = {
            "geo_latitude": loc["LatitudeGPS"],
            "geo_longitude": loc["LongitudeGPS"],
            "geo_address_text": address,
            "geo_json": {"postcode": loc["ZipCode"], "formatted_address_text": address, }
        }

        return_data[real_job_id] = {
            "worker_id": worker_id,
            "job_addr": gps_dict,
            'row': loc
        }
        worker_addr[worker_id] = gps_dict

    return return_data, worker_addr


group_job_data, worker_addr_dict = init_data()


def get_skills(worker):
    skills = []
    for step in range(1, 5):
        # if step <= worker["electric"]:
        skills.append("electric_{}".format(step))

    for step in range(1, 5):
        # if step <= worker["mechanic"]:
        skills.append("mechanic_{}".format(step))
    return skills


def generate_all_workers():
    # url = '{}/kpdata/workers/'.format(kplanner_service_url)
    worker_df = pd.read_csv(
        "{}/plugins/kandbox_planner/util/ExportToDataIntelligenceV3.csv".format(config.basedir),
        header=0,
        sep=";",
        encoding="utf_8",
    )
    list_to_insert = []
    worker_id_set = set()
    for loc_index, worker in worker_df.iterrows():
        worker_id = f"W{str(worker['RouteID'])}{str(worker['CenterID'])}"
        if worker_id in worker_id_set:
            continue
        worker_id_set.add(worker_id)

        gps = worker_addr_dict[worker_id]
        gps["location_code"] = "{}-{}".format('Wname' + str(worker_id), loc_index)

        # print("adding worker: ", worker, gps)
        skills = get_skills(worker)

        myobj = {
            "code": worker_id,
            "name": worker_id,
            "auth_username": worker_id,
            # 'skills': '[1]',
            "is_active": True,
            "team": {
                "code": worker['CenterID'],
                "name": team_dict[worker['CenterID']],
            },
            "location": {
                "location_code": gps["location_code"],
                "geo_latitude": gps["geo_latitude"],
                "geo_longitude": gps["geo_longitude"],
            },
            "flex_form_data": {
                "level": 5,
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

    loc_job_index = job_start_index
    list_to_insert = []

    job_id_set = set()

    skills = [
        "electric_1",
        "mechanic_1",
    ]
    i = 0
    for real_job_id, job_item in group_job_data.items():
        i += 1
        row = job_item['row']
        job_code = "{}-{}-{}".format(
            datetime.strftime(current_day, "%m%d"),
            loc_job_index, real_job_id
        )
        gps = job_item['job_addr']
        gps["location_code"] = "job_loc_{}".format(i)
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
                "priority": random.randint(1, 3),
                "included_job_codes": []
            },
            "team": {
                "code": row['CenterID'],
                "name": team_dict[row['CenterID']],
            },
            "location": gps,
            "planning_status": JobPlanningStatus.UNPLANNED,
            "requested_duration_minutes": 1,
            "scheduled_duration_minutes": 1,
            "requested_start_datetime": datetime.strftime(
                current_day + timedelta(minutes=0), "%Y-%m-%dT%H:%M:%S"
            ),
            "scheduled_start_datetime": datetime.strftime(
                current_day + timedelta(minutes=0), "%Y-%m-%dT%H:%M:%S"
            ),
            "requested_primary_worker": {
                "code": job_item['worker_id'],
                "team": {
                    "code": row['CenterID'],
                    "name": team_dict[row['CenterID']],
                },
            },
            "scheduled_primary_worker": {
                "code": job_item['worker_id'],
                "team": {
                    "code": row['CenterID'],
                    "name": team_dict[row['CenterID']],
                },
            },
            "auto_planning": auto_planning_flag,
        }

        list_to_insert.append(myobj)

        if len(list_to_insert) >= nbr_jobs:
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
    # TODO, remove
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
        pass
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
    # opts["dispatch_days"] = opts["dispatch_days"]
    # dispatch_jobs_batch_optimizer(opts)
    return


if __name__ == "__main__":
    # generate_all()
    print("pls call cli.py")
