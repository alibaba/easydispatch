import datetime
import json
import random
from datetime import datetime, timedelta

import holidays
import numpy as np
import pandas as pd
from dispatch.plugins.kandbox_planner.travel_time_plugin import HaversineTravelTime
from dispatch.database import SessionLocal
from dispatch import config
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util
from dispatch.plugins.bases.kandbox_planner import KandboxDataAdapterPlugin

from dispatch.location import service as location_service
from dispatch.team import service as team_service

from dispatch.location.models import Location
from dispatch.worker.models import Worker
from dispatch.worker import service as worker_service
from dispatch.job.models import Job, JobPlanningInfoUpdate
from dispatch.job import service as job_service

# from dispatch.participant.models import Participant, ParticipantType

from dispatch.plugins.bases.kandbox_planner import KandboxDataAdapterPlugin

from sqlalchemy import and_

MAX_CONFLICT_LEVEL = 2


MAX_CONFLICT_LEVEL = 2

# import dispatch.plugins.kandbox_planner.config as config
import logging

log = logging.getLogger(__name__)


class KPlannerDBAdapter(KandboxDataAdapterPlugin):
    def __del__(self):
        log.debug("KPlannerDBAdapter Destructor called, releasing db_session.")
        try:
            self.db_session.close()
        except:
            log.error("Error when releasing db_session.")

    def __init__(self, team_id=None):
        # Create the database connection.
        self.db_session = SessionLocal()
        self.cnx = self.db_session

        if team_id is None:
            # TODO In future, I get default from db
            raise Exception("internal error: team_id can not be None")
        else:
            self.team_id = team_id
            team = team_service.get(db_session=self.db_session, team_id=self.team_id)

            if team is None:
                raise Exception("team_id is invalid")

    def reload_data_from_db(self):
        """This is only for RLLib automatic training, I have to seperate data loading from original reset()
        In Heuristic search, do not call this one.
        """

        w_df = self.get_workers()  # .reset_index()
        w_df["worker_code_index"] = w_df["id"]
        # w_df.set_index("worker_code")
        self.workers_db_dict = w_df.set_index("worker_code_index").to_dict(orient="index")

        self.workers_dict_by_id = {}  # Dictionary of dict
        self.workers_by_code_dict = {}  # Dictionary of dict

        # for wi in self.db_adapter.workers_db_dict:
        #     self.db_adapter.workers_by_code_dict[
        #         self.db_adapter.workers_db_dict[wi]["code"]
        #     ] = self.db_adapter.workers_db_dict[wi]

        for ji, worker in self.workers_db_dict.items():

            self.workers_dict_by_id[worker["id"]] = worker
            self.workers_by_code_dict[worker["code"]] = worker

        # start_day=self.config["data_start_day"], end_day=self.config["data_end_day"],
        j_df = self.get_jobs()
        j_df["job_code"] = j_df["code"]
        j_df["job_code_index"] = j_df["code"]
        # j_df.set_index("job_code")
        self.jobs_db_dict = j_df.set_index("job_code_index").to_dict(orient="index")

        # absence_df = self.get_worker_absence()
        # absence_df["job_code"] = absence_df["absence_code"]
        # absence_df["index_abs_code"] = absence_df["absence_code"]
        # # absence_df.set_index("absence_code")
        # self.absence_db_dict = absence_df.set_index("index_abs_code").to_dict(orient="index")
        self.absence_db_dict = {}

        self.get_appointments()  # store to self inside the call

        log.info(
            f"TEAM:{self.team_id}:Finished reloading from DB with {len(self.workers_db_dict)} workers, {len(self.jobs_db_dict)} jobs, DB.team_contact.latest_env_kafka_offset = {self.get_team_env_window_latest_offset()}"
        )

    def get_team_env_window_latest_offset(self):
        team = team_service.get(db_session=self.db_session, team_id=self.team_id)
        return team.latest_env_kafka_offset

    def set_team_env_window_latest_offset(self, offset=0):
        team = team_service.get(db_session=self.db_session, team_id=self.team_id)
        team.latest_env_kafka_offset = offset
        self.db_session.add(team)
        self.db_session.commit()

        return True

    def get_team_flex_form_data(self):
        team = team_service.get(db_session=self.db_session, team_id=self.team_id)
        return team.flex_form_data

    def get_jobs(self, start_day=None, end_day=None):
        db_session = self.cnx
        k = pd.read_sql(
            db_session.query(
                Job,
                Location.location_code,
                Location.geo_longitude,
                Location.geo_latitude,
                Location.job_history_feature_data,
                Location.job_count,
                Location.avg_actual_start_minutes,
                Location.avg_actual_duration_minutes,
                Location.avg_days_delay,
                Location.stddev_days_delay,
                Worker.code.label("requested_primary_worker_code"),
            )
            .filter(Job.location_id == Location.id)
            .filter(Job.team_id == self.team_id)
            .filter(Job.requested_primary_worker_id == Worker.id)
            .statement,
            db_session.bind,
        )
        secondary_jobs_raw = pd.read_sql(
            "select job_id, worker_id, code as worker_code from job_scheduled_secondary_workers jssw, worker w where w.id = jssw.worker_id",
            db_session.bind,
        )
        secondary_jobs_df = (
            secondary_jobs_raw.groupby(["job_id"])
            .agg(
                scheduled_secondary_worker_codes=pd.NamedAgg(column="worker_code", aggfunc=list),
            )
            .reset_index()
            .copy()
        )
        k_df = pd.merge(
            k,
            secondary_jobs_df[["job_id", "scheduled_secondary_worker_codes"]],
            how="left",
            left_on=["id"],
            right_on=["job_id"],
        )
        # k_df["scheduled_worker_codes"].fillna([], inplace=True)
        # k_df["scheduled_worker_codes"] = k_df.apply(lambda x: [] if pd.isnull(x["scheduled_worker_codes"]) else x["scheduled_worker_codes"], axis=1,)
        k_df["scheduled_secondary_worker_codes"] = k_df.apply(
            lambda x: []
            if type(x["scheduled_secondary_worker_codes"]) != list
            else x["scheduled_secondary_worker_codes"],
            axis=1,
        )

        return k_df

    def get_worker_absence(self):
        #        return self.load_workers_original(start_day)
        # def load_workers_original(self,start_day = '20191101'):

        db_session = self.cnx
        team = team_service.get(db_session=db_session, team_id=self.team_id)

        if team is None:
            log.error(f"team_id={self.team_id} is invalid")

        absence_df = pd.read_sql(
            db_session.query(
                WorkerAbsence,
                Worker.code,
            )
            .filter(Worker.id == WorkerAbsence.scheduled_primary_worker_id)
            .filter(Worker.team_id == self.team_id)
            .filter(WorkerAbsence.scheduled_primary_worker_id == Worker.id)
            .statement,
            db_session.bind,
        )

        return absence_df

    def get_appointments(self):
        # return self.load_workers_original(start_day)
        # def load_workers_original(self,start_day = '20191101'):
        self.appointment_db_dict = {}
        return self.appointment_db_dict

        db_session = self.cnx
        # TODO,
        # Later to add org_code filter, but not on team level
        self.appointment_per_incident_df = pd.read_sql(
            db_session.query(Job.code, Job.id, Location.id, Location.location_code, Appointment)
            .join(Job, Job.appointment_id == Appointment.id)
            .join(Location, Job.location_id == Location.id)
            .filter(Appointment.appointment_status == "PENDING")
            .statement,
            db_session.bind,
        )

        tk = self.appointment_per_incident_df.to_dict(orient="index")

        for apptkey, appt in tk.items():
            if appt["appointment_code"] in self.appointment_db_dict.keys():
                self.appointment_db_dict[appt["appointment_code"]]["included_job_codes"].append(
                    appt["code"]
                )

                if (
                    self.appointment_db_dict[appt["appointment_code"]]["location_code"]
                    != appt["location_code"]
                ):
                    # There can not be different locations in one appt
                    log.error(
                        "multiple location ({},{}) code in one appt {}".format(
                            self.appointment_db_dict[appt["appointment_code"]]["location_code"],
                            appt["location_code"],
                            appt["appointment_code"],
                        )
                    )
            else:
                self.appointment_db_dict[appt["appointment_code"]] = appt
                self.appointment_db_dict[appt["appointment_code"]]["location_code"] = appt[
                    "location_code"
                ]
                self.appointment_db_dict[appt["appointment_code"]]["included_job_codes"] = [
                    appt["code"]
                ]
        return self.appointment_db_dict

    def get_workers(self, start_day=None):
        #        return self.load_workers_original(start_day)
        # def load_workers_original(self,start_day = '20191101'):
        db_session = self.cnx
        try:
            log.info(f"testing team_id = {self.team_id}")
            team = team_service.get(db_session=db_session, team_id=self.team_id)
            if team is None:
                log.error(f"team_id={self.team_id} is invalid")
        except Exception as e:
            print(e)
            log.error(f"team_id={self.team_id} is invalid")

        k_workers = pd.read_sql(
            db_session.query(Worker).filter(Worker.team_id == self.team_id).statement,
            db_session.bind,
        )

        return k_workers

    def save_changed_jobs(self, changed_jobs=[]):
        #        return self.load_workers_original(start_day)
        # def load_workers_original(self,start_day = '20191101'):
        db_session = self.cnx

        # This bulk update does not update secondary workers.
        db_session.bulk_update_mappings(
            Job,
            changed_jobs,
        )
        # db_session.flush()
        db_session.commit()

        for job in changed_jobs:
            job_to_update = JobPlanningInfoUpdate(
                code=job["code"],
                planning_status=job["planning_status"],
                scheduled_start_datetime=job["scheduled_start_datetime"],
                scheduled_duration_minutes=job["scheduled_duration_minutes"],
                scheduled_primary_worker_code=worker_service.get(
                    db_session=db_session, worker_id=job["scheduled_primary_worker_id"]
                ).code,
                scheduled_secondary_worker_codes=[
                    worker_service.get(db_session=db_session, worker_id=_id).code
                    for _id in job["scheduled_secondary_worker_ids"]
                ],
            )
            job_service.update_planning_info(db_session=self.cnx, job_in=job_to_update)

    def load_historical_location_features(self):
        job_location_w_df = pd.read_sql(
            sql="""
                select f.*
                from   kpdata_location_job_history_features f where 1=1  {}
        """.format(
                self.org_team_filter
            ),
            con=self.cnx,
        )

        w, d = self.load_transformed_workers(start_day="20190204")  # , nbr_days = 7

        loc_feature_dict = {}
        for index, f in job_location_w_df.iterrows():

            worker_bitmap = [0 for _ in self.workers_id_dict.keys()]
            worker_count_dict = json.loads(f["historical_serving_worker_distribution"])
            # TODO : Why Do i need "int()"
            for worker_count in worker_count_dict:  # .keys():
                worker_bitmap[self.workers_id_dict[worker_count[0]]] = worker_count[1]

            loc_feature_dict[f["location_code"]] = {
                "job_count": f["job_count"],
                "avg_actual_start_minutes": f["avg_actual_start_minutes"],
                "avg_days_delay": f["avg_days_delay"],
                "stddev_days_delay": f["stddev_days_delay"],
                "historical_serving_worker_distribution": worker_count_dict,
                "history_job_worker_count": worker_bitmap,
            }
        self.loc_feature_dict = loc_feature_dict
        return loc_feature_dict


if __name__ == "__main__":

    # exit(0)
    kdb = KPlannerDBAdapter()
    # workers, workers_id_dict  = kdb.load_workers(start_day = datetime.strptime('20190204',config.KANDBOX_DATE_FORMAT), nbr_days = 7)
