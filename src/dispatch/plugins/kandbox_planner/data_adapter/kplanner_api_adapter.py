import requests
import pandas as pd

import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util


from datetime import datetime
from datetime import timedelta

from pprint import pprint
from dispatch import config

import logging

log = logging.getLogger(__name__)


class KPlannerAPIAdapter:
    # access_token = 0
    def __init__(
        self,
        service_url=None,
        username=None,
        password=None,
        access_token=None,
        team_code=None,
        log_level=logging.DEBUG,
    ):
        # Create your connection.
        # TODO: use same config.
        self.service_url = service_url
        self.access_token = self.get_access_token(username=username, password=password)

        if team_code is None:
            self.team_code = "london_t1"
        else:
            self.team_code = team_code

        log.setLevel(log_level)

    def get_access_token(self, username=None, password=None):
        url = f"{self.service_url}/auth/login"
        login_info = {"email": username, "password": password}

        response = requests.post(url, json=login_info, headers={"Content-Type": "application/json"})
        resp_json = response.json()
        return resp_json["token"]

    def insert_all_workers(self, worker_list):
        url = "{}/workers/".format(self.service_url)

        for myobj in worker_list:
            # print(myobj)

            myobj["team"]["code"] = self.team_code
            log.debug(url)
            log.debug(myobj)

            response = requests.post(
                url,
                json=myobj,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer {}".format(self.access_token),
                },
            )

            try:
                # Convert JSON to dict and print
                print("Saved worker: ", response.json()["code"])
            except:
                print("Failed to save worker: ", response)

    def delete_all_workers(self):
        url = "{}/kpdata/workers/".format(self.service_url)
        response = requests.get(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {}".format(self.access_token),
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
            url = "{}/kpdata/workers/".format(self.service_url) + str(worker["worker_code"]) + ""
            # print(url)
            response = requests.delete(
                url, headers={"Authorization": "Bearer {}".format(self.access_token)}
            )
            print(response.text)

    def get_solution(self, team_code=None):
        env_url = "planner_service/get_planner_worker_job_dataset/?team_id=1&start_day=20210419&end_day=20210425&force_reload=false"
        url = "{}/{}".format(self.service_url, env_url)
        response = requests.get(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {}".format(self.access_token),
            },
        )
        try:
            return response.json()
        except:
            print("Failed to get job solution", response)
            print(f"url={url}")
            return {}

    def insert_all_orders(self, jobs_list):
        url = "{}/jobs/".format(self.service_url)
        for myobj in jobs_list:
            myobj["team_code"] = self.team_code

            # log.debug(url)
            # log.debug(myobj)
            response = requests.post(
                url,
                json=myobj,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer {}".format(self.access_token),
                },
            )
            # print(response)
            # Convert JSON to dict and print
            try:
                print("Saved job: ", response.json()["code"])
            except:
                print("Failed to save job", response)

    def delete_all_orders(self):
        url = "{}/kpdata/jobs/".format(
            self.service_url
        )  # http://localhost:5000/api/v1/workorder/1"
        response = requests.get(
            url,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {}".format(self.access_token),
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
            url = "{}/kpdata/jobs/".format(self.service_url) + str(worker["job_code"]) + ""
            print(url)
            response = requests.delete(
                url, headers={"Authorization": "Bearer {}".format(self.access_token)}
            )
            print(response.text)


if __name__ == "__main__":

    # /5 minutes
    # GPS fixed

    _SHIFTS = [
        [0, "FS", "7:12", 108, 60, 32],
        [1, "N", "8:3", 26, 68, 22],
        [2, "N", "06:4", 66, 121, 25],
        [3, "FS", "15:5", 20, 72, 12],
        [4, "N", "11:4", 133, 189, 16],
        [5, "N", "13:2", 2, 19, 17],
        [6, "FS", "20:5", 91, 131, 34],
        [7, "N", "21:7", 8, 30, 52],
        [8, "FS", "3:45", 180, 190, 60],
        [9, "N", "5:49", 38, 80, 22],
        [10, "FS", "14:54", 43, 90, 37],
        [11, "N", "13:60", 169, 169, 25],
        [12, "FS", "19:55", 218, 215, 37],
        [13, "N", "20:59", 196, 234, 38],
        [14, "N", "20:48", 235, 248, 13],
    ]

    _EMP = [
        "-0.1960066034365281:51.44627780733451",
        "-0.12320152380185012:51.50874451583848",
        "-0.1727406536075019:51.43884800126409",
        "-0.14559645789574854:51.45238536979151",
        "-0.1944764936594672:51.479491652786834",
        "-0.16707857157978992:51.433456197551315",
    ]
    # worker_day =[[[1, 55, 22], [7, 82, 52], ['sink']], [[0, 108, 32], [2, 143, 25], [9, 174, 22], ['sink']], [[3, 20, 12], [5, 35, 17], [4, 55, 16], [6, 91, 34], ['sink']], [[8, 180, 60], ['sink']], [[11, 146, 25], [12, 218, 37], [14, 258, 13], ['sink']], [[10, 43, 37], [13, 84, 38], ['sink']]]

    people = ("Tom", "Mike", "Harry", "Slim", "Jim", "Duan")
    worker_list = [[wi, people[wi], _EMP[wi]] for wi in range(len(people))]

    # for i in range(10):
    #    print(get_normalized_location(i))

    GENERATOR_START_DATE = datetime.strptime("20190101", config.KANDBOX_DATE_FORMAT)
    GENERATOR_RANGE = 5

    """
    delete_all_workers()
    insert_all_workers(worker_list)

    delete_all_orders()
    generate_and_save_orders(GENERATOR_START_DATE =  GENERATOR_START_DATE, TRAINING_DAYS=GENERATOR_RANGE,  current_shifts = _SHIFTS,  worker_list = worker_list) # This genearte 450 orders
    """
