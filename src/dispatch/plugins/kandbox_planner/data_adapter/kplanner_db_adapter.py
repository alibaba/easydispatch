from typing import Dict, List
from sqlalchemy import or_, and_
import logging
import datetime
import json
import random
from datetime import datetime, timedelta

import holidays
import numpy as np
import pandas as pd
from dispatch.database_util.service import get_schema_session
from dispatch.plugins.kandbox_planner.env.env_enums import LocationType
from dispatch.plugins.kandbox_planner.env.env_models import JobLocation, JobLocationBase
from dispatch.plugins.kandbox_planner.travel_time_plugin import HaversineTravelTime
from dispatch.database import SessionLocal
from dispatch import config
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util
from dispatch.plugins.bases.kandbox_planner import KandboxDataAdapterPlugin

from dispatch.service_plugin import service as service_plugin_service
from dispatch.location.models import Location
from dispatch.service.models import Service
from dispatch.worker.models import Worker
from dispatch.job.models import Job, JobPlanningInfoUpdate

from dispatch.worker import service as worker_service
from dispatch.job import service as job_service
from dispatch.team import service as team_service
from dispatch.item_inventory import service as inventory_service  # import  get_by_depot_item_list
from dispatch.depot import service as depot_service
from dispatch.item import service as item_service
from dispatch.item_inventory_event import service as inventory_event_service


from dispatch.org import service as org_service

# from dispatch.participant.models import Participant, ParticipantType

from dispatch.plugins.bases.kandbox_planner import KandboxDataAdapterPlugin
from dispatch.plugins.kandbox_planner.util.kandbox_util import from_item_list_to_dict, from_item_dict_to_list

from fastapi import HTTPException

MAX_CONFLICT_LEVEL = 2


MAX_CONFLICT_LEVEL = 2

# import dispatch.plugins.kandbox_planner.config as config

log = logging.getLogger(__name__)


class KPlannerDBAdapter(KandboxDataAdapterPlugin):
    def __del__(self):
        log.debug("KPlannerDBAdapter Destructor called, releasing db_session.")
        try:
            self.db_session.close()
        except:
            log.error("Error when releasing db_session.")

    def __init__(self, org_code=None, team_id=None):
        # Create the database connection.
        self.db_session = get_schema_session(org_code)
        self.cnx = self.db_session
        self.db_schema = f"dispatch_organization_{org_code}"
        self.org_id = None

        if team_id is None:
            # TODO In future, I get default from db
            raise HTTPException(
                status_code=400, detail=f"internal error: team_id can not be None, or is not in your organization.",
            )
        team = team_service.get(db_session=self.db_session, team_id=team_id)
        if team is None:
            raise HTTPException(
                status_code=400, detail=f"The team is not found in your organization.",
            )
        org = org_service.get(db_session=self.db_session, org_code=org_code)
        if (org is None) or (org.id != team.org_id):
            raise HTTPException(
                status_code=400, detail=f"The team is not in your organization ( { org_code}).",
            )

        self.team = team
        self.team_id = team_id
        self.team_code = team.code
        self.org_code = org_code
        self.org_id = org.id

        self.workers_dict_by_id = {}  # Dictionary of dict
        self.workers_by_code_dict = {}  # Dictionary of dict
        self.workers_db_dict = {}
        self.jobs_db_dict = {}

    def sample_history_data_from_db(self, start_datetime=None, end_datetime=None, job_generation_max_count=30, nbr_observed_slots=7):
        """This is only for RLLib automatic training over history data, I have to seperate data loading from original reset()
        In Heuristic search, do not call this one.
        """

        w_df = self.get_workers()[0:nbr_observed_slots].reset_index()
        w_df["worker_code_index"] = w_df["id"]
        w_df["worker_code"] = w_df["code"]
        w_df.set_index("worker_code")
        self.workers_db_dict = w_df.set_index("worker_code_index").to_dict(orient="index")
        # self.workers_db_dict = {}
        # for worker in w_df:
        #     self.workers_db_dict[worker.id] = worker

        self.workers_dict_by_id = {}  # Dictionary of dict
        self.workers_by_code_dict = {}  # Dictionary of dict
        for ji, worker in self.workers_db_dict.items():
            self.workers_dict_by_id[worker["id"]] = worker
            self.workers_by_code_dict[worker["worker_code"]] = worker

        j_df = pd.read_sql(
            """ select job.*, loc.location_code, loc.geo_longitude , loc.geo_latitude
                from {}.job, {}.location loc
                where job.location_id = loc.id
                    and job.team_id = {}
                order by random() limit {};
                """.format(self.db_schema, self.db_schema, self.team_id, job_generation_max_count),
            self.cnx.bind,
        )
        j_df["job_code"] = j_df["code"]
        j_df["job_code_index"] = j_df["code"]
        j_df["scheduled_primary_worker_id"] = None
        j_df["planning_status"] = "U"

        self.jobs_db_dict = j_df.set_index("job_code_index").to_dict(orient="index")

        self.absence_db_dict = {}
        self.appointment_db_dict = {}

        log.info(
            f"TEAM:{self.team_id}:Finished reloading from DB with {len(self.workers_db_dict)} workers, {len(self.jobs_db_dict)} jobs, DB.team_contact.latest_env_kafka_offset = {self.get_team_env_window_latest_offset()}"
        )

    def get_depot_item_inventory_dict(self, depot_id: int, requested_items: List) -> Dict:
        item_inv = inventory_service.get_by_depot_item_list(
            db_session=self.db_session,
            depot_id=depot_id,
            requested_items=requested_items
        )
        inv_dict = {}
        for record in item_inv:
            inv_dict[record.Item.code] = record.ItemInventory.curr_qty

        return inv_dict

    def get_depots_dict(self) -> Dict:
        depots = depot_service.get_all(db_session=self.db_session)
        d_dict = {}
        for record in depots:

            d_location = JobLocation(
                geo_longitude=record.location.geo_longitude,
                geo_latitude=record.location.geo_latitude,
                location_type=LocationType.JOB,
                location_code=record.location.location_code,
                historical_serving_worker_distribution={},
                avg_actual_start_minutes=0,
                avg_days_delay=0,
                stddev_days_delay=0,
            )

            d_dict[record.code] = {
                "code": record.code,
                "id": record.id,
                "location": d_location
            }

        return d_dict

    def get_items_dict(self) -> Dict:
        depots = item_service.get_all(db_session=self.db_session)
        d_dict = {}
        for record in depots:
            d_dict[record.code] = {
                "code": record.code,
                "name": record.name,
                "id": record.id,
                "weight": record.weight,
                "volume": record.volume,
            }

        return d_dict

    def reload_data_from_db(self, start_datetime=None, end_datetime=None):
        """This is only for RLLib automatic training, I have to seperate data loading from original reset()
        In Heuristic search, do not call this one.
        """

        w_df = self.get_workers().reset_index()
        w_df["worker_code_index"] = w_df["id"]
        w_df["worker_code"] = w_df["code"]
        w_df.set_index("worker_code")
        self.workers_db_dict = w_df.set_index("worker_code_index").to_dict(orient="index")
        # self.workers_db_dict = {}
        # for worker in w_df:
        #     self.workers_db_dict[worker.id] = worker

        self.workers_dict_by_id = {}  # Dictionary of dict
        self.workers_by_code_dict = {}  # Dictionary of dict

        # for wi in self.db_adapter.workers_db_dict:
        #     self.db_adapter.workers_by_code_dict[
        #         self.db_adapter.workers_db_dict[wi]["code"]
        #     ] = self.db_adapter.workers_db_dict[wi]
        for ji, worker in self.workers_db_dict.items():

            self.workers_dict_by_id[worker["id"]] = worker
            self.workers_by_code_dict[worker["worker_code"]] = worker

        # start_day=self.config["data_start_day"], end_day=self.config["data_end_day"],
        j_df = self.get_jobs(start_datetime=start_datetime, end_datetime=end_datetime)
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

    def reload_data_from_db_by_code(self, worker_obj):
        """get worker to  env

        Args:
            worker_code ([type]): [description]
        """

        new_k_workers = worker_obj.__dict__
        new_k_workers['geo_latitude'] = worker_obj.location.geo_latitude
        new_k_workers['geo_longitude'] = worker_obj.location.geo_longitude
        new_k_workers['location_code'] = worker_obj.location.location_code
        new_k_workers["worker_code_index"] = new_k_workers["id"]
        new_k_workers["worker_code"] = new_k_workers["code"]
        if not self.workers_db_dict:
            self.workers_db_dict = {}
        self.workers_db_dict[new_k_workers["id"]] = new_k_workers

        self.workers_dict_by_id[new_k_workers["id"]] = new_k_workers
        self.workers_by_code_dict[new_k_workers["worker_code"]] = new_k_workers

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

    def get_jobs(self, start_datetime=None, end_datetime=None):
        if start_datetime is None:
            start_datetime = datetime.now()
            end_datetime = datetime.now() + timedelta(days=10)
        earliest_start_datetime = start_datetime - timedelta(days=14)
        db_session = self.cnx
        stmt = (db_session.query(
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
            .outerjoin(Worker, Job.requested_primary_worker_id == Worker.id)
            .filter(or_(
                    Job.requested_start_datetime == None, # "is None" does not work. 2022-01-12 14:29:13
                    and_(Job.requested_start_datetime >= earliest_start_datetime, 
                         Job.planning_status == 'U',
                         Job.requested_start_datetime < end_datetime),
                    and_(Job.scheduled_start_datetime >= start_datetime,
                         Job.scheduled_start_datetime < end_datetime),
                        )) 
            .statement)
        k = pd.read_sql(
            stmt,
            db_session.bind,
        )
        secondary_jobs_raw = pd.read_sql(
            f"select job_id, worker_id, code as worker_code from {self.db_schema}.job_scheduled_secondary_workers jssw, {self.db_schema}.worker w where w.id = jssw.worker_id",
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
            if type(x.get("scheduled_secondary_worker_codes", [])) != list
            else x.get("scheduled_secondary_worker_codes", []),
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
            db_session.query(Worker, Location.geo_latitude,
                             Location.geo_longitude, Location.location_code)
            # .filter(Location.id == Worker.location_id)
            .outerjoin(Location, Worker.location_id == Location.id)
            .filter(Worker.team_id == self.team_id)
            .statement,
            db_session.bind,
        )
        # k_workers = db_session.query(Worker).filter(Worker.team_id == self.team_id).all()
        mean_long = (team.flex_form_data.get("geo_longitude_max", 0) +
                     team.flex_form_data.get("geo_longitude_min", 0)) / 2
        mean_lat = (team.flex_form_data.get("geo_latitude_max", 0) +
                    team.flex_form_data.get("geo_latitude_min", 0)) / 2
        k_workers['geo_longitude'].fillna(mean_long, inplace=True)
        k_workers['geo_latitude'].fillna(mean_lat, inplace=True)
        k_workers['location_code'].fillna("central_loc", inplace=True)

        # TODO, fillna.

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

    def update_replenish_job(self, job, total_requested_items):
        r_job = job_service.get_by_code(db_session=self.db_session, code=job.job_code)

        curr_items = from_item_list_to_dict(r_job.flex_form_data["requested_items"])
        item_diff_dict = {}
        for ik in total_requested_items.keys():
            if ik in curr_items.keys():
                if curr_items[ik] < total_requested_items[ik]:
                    item_diff_dict[ik] = total_requested_items[ik] - curr_items[ik]
            else:
                item_diff_dict[ik] = total_requested_items[ik]
        if len(item_diff_dict) < 1:
            return r_job

        depot = depot_service.get_default_depot(db_session=self.cnx)
        depot_code = depot.code  # list(self.depots_dict.keys())[0]

        for item_code in item_diff_dict.keys():
            item = item_service.get_by_code(db_session=self.cnx, code=item_code)
            inv = inventory_service.get_by_item_depot(
                db_session=self.cnx,
                item_id=item.id,
                depot_id=depot.id,
                org_id=self.org_id
            ).first()
            inv.curr_qty -= item_diff_dict[item_code]
            if inv.curr_qty < 0:
                log.error(
                    f" Not enough inventory for item: {item_code}, depot: {depot_code}, org.id: {self.org_id}")
                continue
            inv.allocated_qty += item_diff_dict[item_code]
            self.cnx.add(inv)
            inventory_event_service.log(
                db_session=self.cnx,
                source="Env_Replenish",
                description=f"Allocated {item_diff_dict[item_code]} {item_code} from depot: {depot_code}",
                item_code=item_code,
                depot_code=depot_code,
                item_id=item.id,
                depot_id=depot.id
            )
        self.cnx.commit()

    def create_new_job(self, job_dict):
        # job_dict.update(
        #     "team" : {"code":self.team_code},
        # )
        a = job_service.create(
            db_session=self.cnx,
            code=job_dict["code"],
            job_type=job_dict["job_type"],
            org_id=self.org_id,
            org_code=self.org_code,
            name=job_dict["code"],
            planning_status=job_dict["planning_status"],
            tags=[],
            description=None,
            team={"code": self.team_code},
            location=job_dict["location"],
            flex_form_data=job_dict["flex_form_data"],
            requested_primary_worker=job_dict["requested_primary_worker"],  # : WorkerCreate
            requested_start_datetime=job_dict["requested_start_datetime"],
            requested_duration_minutes=job_dict["requested_duration_minutes"],
            scheduled_primary_worker=job_dict["scheduled_primary_worker"],  # : WorkerCreate
            scheduled_secondary_workers=job_dict["scheduled_secondary_workers"],
            scheduled_start_datetime=job_dict["scheduled_start_datetime"],
            scheduled_duration_minutes=job_dict["scheduled_duration_minutes"],
            auto_planning=job_dict["auto_planning"],
        )
        return a

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

    def get_plugin_service(self, service_plugin_type):

        service = self.db_session.query(Service).filter(
            Service.id == self.team.service_id).one_or_none()
        if not service:
            raise Exception(f"service is null,{self.team.service_id}")
        plugin = service_plugin_service.get_by_service_id_and_type(
            db_session=self.db_session,
            service_id=service.id,
            service_plugin_type=service_plugin_type,
        ).all()
        return plugin


if __name__ == "__main__":

    # exit(0)
    kdb = KPlannerDBAdapter()
    # workers, workers_id_dict  = kdb.load_workers(start_day = datetime.strptime('20190204',config.KANDBOX_DATE_FORMAT), nbr_days = 7)
