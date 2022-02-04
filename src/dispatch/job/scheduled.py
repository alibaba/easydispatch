import logging
from datetime import datetime
import json

import pandas as pd
import numpy as np

from schedule import every
from sqlalchemy import func

from dispatch.decorators import background_task
from dispatch.job.models import Job
from dispatch.team.models import TeamUpdate
from dispatch.worker import service as worker_service
from dispatch.worker.models import Worker, WorkerUpdate
from dispatch.location.models import Location, LocationUpdate
from dispatch.scheduler import scheduler
from dispatch.service import service as service_service


from collections import Counter

from dispatch.plugins.kandbox_planner.env.env_enums import JobPlanningStatus, JobType

log = logging.getLogger(__name__)

# TODO, at night.


@scheduler.add(every(60 * 60 * 24).seconds, name="calc_historical_location_features")
@background_task
def calc_historical_location_features(db_session=None):
    """Calculates the cost of all jobs."""

    log.debug(
        f"calc_historical_location_features - worker started worker.served_location_gmm  ......"
    )
    calc_historical_location_features_real_func(db_session)


def calc_historical_location_features_real_func(db_session=None):

    job_loc_df = pd.read_sql(
        db_session.query(
            Job.scheduled_primary_worker_id,
            Worker.code.label("scheduled_primary_worker_code"),
            Job.id.label("job_id"),
            Job.scheduled_start_datetime,
            Job.scheduled_duration_minutes,
            Job.requested_start_datetime,
            Job.flex_form_data,
            Job.location_id,
            Location.geo_longitude,
            Location.geo_latitude,
        )
        .filter(Job.location_id == Location.id)
        .filter(Job.scheduled_primary_worker_id == Worker.id)
        .filter(Job.planning_status.in_((JobPlanningStatus.FINISHED,)))
        .statement,
        db_session.bind,
    )
    if job_loc_df.count().max() < 1:
        # raise ValueError("job_loc_df.count().max() < 1, no data to proceed")
        log.error(
            "calc_historical_location_features_real_func: job_loc_df.count().max() < 1, no data to proceed"
        )
        return

    def get_actual_primary_worker_code(x):
        if "actual_primary_worker_code" in x["flex_form_data"]:
            return x["flex_form_data"]["actual_start_datetime"]
        else:
            return x["scheduled_primary_worker_code"]

    job_loc_df["actual_primary_worker_code"] = job_loc_df.apply(
        lambda x: get_actual_primary_worker_code(x),
        axis=1,
    )
    # actual_start_datetime
    # job_loc_df["days_delay"] = job_loc_df.apply(
    #     lambda x: (x["scheduled_start_datetime"] - x["requested_start_datetime"]).days, axis=1
    # )

    worker_job_gmm_df = (
        job_loc_df.groupby(["actual_primary_worker_code"])
        .agg(
            # job_count=pd.NamedAgg(column='location_code', aggfunc='count')
            avg_geo_longitude=pd.NamedAgg(column="geo_longitude", aggfunc="mean"),
            avg_geo_latitude=pd.NamedAgg(column="geo_latitude", aggfunc="mean"),
            std_geo_longitude=pd.NamedAgg(column="geo_longitude", aggfunc="std"),
            std_geo_latitude=pd.NamedAgg(column="geo_latitude", aggfunc="std"),
            list_geo_longitude=pd.NamedAgg(column="geo_longitude", aggfunc=list),
            list_geo_latitude=pd.NamedAgg(column="geo_latitude", aggfunc=list),
            # cov_geo =pd.NamedAgg(column=("geo_longitude","geo_latitude"), aggfunc=np.cov),
            job_count=pd.NamedAgg(column="scheduled_primary_worker_id", aggfunc="count"),
        )
        .reset_index()
    )  # .sort_values(['location_code'], ascending=True)

    def get_cov(x):
        arr = np.array([x["list_geo_longitude"], x["list_geo_latitude"], ])
        arr_cov = np.cov(arr)
        return arr_cov.tolist()
    worker_job_gmm_df["cov_geo"] = worker_job_gmm_df.apply(
        lambda x: get_cov(x),
        axis=1,
    )
    worker_job_gmm_df = worker_job_gmm_df[worker_job_gmm_df["job_count"] > 2]

    worker_job_gmm_df["job_history_feature_data"] = worker_job_gmm_df.apply(
        lambda x: {
            "mean": {"longitude": x["avg_geo_longitude"], "latitude": x["avg_geo_latitude"]},
            "std": {"longitude": x["std_geo_longitude"], "latitude": x["std_geo_latitude"]},
            "cov": x["cov_geo"],
            "job_count": x["job_count"],
        },
        axis=1,
    )

    for _, w in worker_job_gmm_df.iterrows():
        worker = worker_service.get_by_code(
            db_session=db_session,
            code=w["actual_primary_worker_code"])

        worker.job_history_feature_data = w["job_history_feature_data"]
        db_session.add(worker)
        db_session.commit()

        # a=worker.__dict__
        # # a["team"]=worker.team.__dict__
        # # a["team"]=TeamUpdate(**worker.team.__dict__)
        # # a["location"]=LocationUpdate(**worker.location.__dict__)
        # # a["job_history_feature_data"] = w["job_history_feature_data"]
        # # worker_in = WorkerUpdate(**a)
        # worker_in = worker
        # worker_in.job_history_feature_data = w["job_history_feature_data"]

        # new_worker = worker_service.update(
        #     db_session=db_session,
        #     worker=worker,
        #     worker_in=worker_in)
        # print(worker)
    print(f"{worker_job_gmm_df.count().max()} workers are updated.")
    return

    loc_gmm_df = (
        job_loc_df.groupby(["location_id"])
        .agg(
            # job_count=pd.NamedAgg(column='location_code', aggfunc='count')
            avg_geo_longitude=pd.NamedAgg(column="geo_longitude", aggfunc="mean"),
            avg_geo_latitude=pd.NamedAgg(column="geo_latitude", aggfunc="mean"),
            std_geo_longitude=pd.NamedAgg(column="geo_longitude", aggfunc="std"),
            std_geo_latitude=pd.NamedAgg(column="geo_latitude", aggfunc="std"),
            cov_geo=pd.NamedAgg(column=["geo_longitude", "geo_latitude"], aggfunc=np.cov),
            job_count=pd.NamedAgg(column="scheduled_primary_worker_id", aggfunc="count"),
            list_scheduled_worker_code=pd.NamedAgg(
                column="scheduled_primary_worker_id", aggfunc=list
            ),
            avg_actual_start_minutes=pd.NamedAgg(column="actual_start_minutes", aggfunc="mean"),
            avg_actual_duration_minutes=pd.NamedAgg(
                column="scheduled_duration_minutes", aggfunc="mean"
            ),
            avg_days_delay=pd.NamedAgg(column="days_delay", aggfunc="mean"),
            stddev_days_delay=pd.NamedAgg(column="days_delay", aggfunc="std"),
        )
        .reset_index()
    )  # .sort_values(['location_code'], ascending=True)

    loc_gmm_df["job_historical_worker_service_dict"] = loc_gmm_df.apply(
        lambda x: Counter(x["list_scheduled_worker_code"]),
        axis=1,
    )
    # Then I should get "job_historical_worker_service_dict": {"19": 3, "18":1}

    loc_gmm_df["job_history_feature_data"] = loc_gmm_df.apply(
        lambda x: {
            "mean": {"longitude": x["avg_geo_longitude"], "latitude": x["avg_geo_latitude"]},
            "std": {"longitude": x["std_geo_longitude"], "latitude": x["std_geo_latitude"]},
            "job_count": x["job_count"],  # TODO same as out side, it should be here.!
            "job_historical_worker_service_dict": x["job_historical_worker_service_dict"],
        },
        axis=1,
    )

    loc_feature_df = loc_gmm_df[
        [
            "location_id",
            "job_history_feature_data",
            "job_count",
            "avg_actual_start_minutes",
            "avg_actual_duration_minutes",
            "avg_days_delay",
            "stddev_days_delay",
        ]
    ]
    loc_feature_df.rename(columns={"location_id": "id"}, inplace=True)

    loc_update_dict_list = json.loads(loc_feature_df.to_json(orient="records"))

    db_session.bulk_update_mappings(
        Location,
        loc_update_dict_list,
    )
    # db_session.flush()
    db_session.commit()

    log.debug(
        f"calc_historical_location_features - Finished Location features, now started worker.served_location_gmm. "
    )

    job_loc_df = job_loc_df[
        [
            "scheduled_primary_worker_id",
            "location_id",
            "geo_longitude",
            "geo_latitude",
        ]
    ]

    worker_loc_df = pd.read_sql(
        db_session.query(
            Worker.id.label("scheduled_primary_worker_id"),
            Worker.location_id,
            Location.geo_longitude,
            Location.geo_latitude,
        )
        .filter(Worker.location_id == Location.id)
        .statement,
        db_session.bind,
    )
    # worker_loc_df.rename(columns={"id": "scheduled_primary_worker_id"}, inplace=True)

    """
    job_loc_df = pd.read_sql(
        db_session.query(Job).filter(Job.planning_status != JobPlanningStatus.unplanned).statement,
        db_session.bind,
    )
    # TO attach home location for each worker.

    worker_loc_df = pd.read_sql(
        db_session.query(Worker)
        .filter(Job.planning_status != JobPlanningStatus.unplanned)
        .statement,
        db_session.bind,
    )
    worker_loc_df.rename(columns={"id": "scheduled_primary_worker_id"}, inplace=True)

    job_loc_with_worker_home = pd.concat(
        [
            visit[["actual_worker_code", "location_code", "geo_longitude", "geo_latitude"]],
            worker_df,
        ]
    ).copy()

    """
    # job_loc_with_worker_home = job_loc_df

    job_loc_with_worker_home = pd.concat(
        [
            job_loc_df,
            worker_loc_df,
        ]
    ).copy()
    log.debug(f"calc_historical_location_features - worker loaded from db ...")

    #

    worker_gmm_df = (
        job_loc_with_worker_home.groupby(["scheduled_primary_worker_id"])
        .agg(
            # job_count=pd.NamedAgg(column='location_code', aggfunc='count')
            avg_geo_longitude=pd.NamedAgg(column="geo_longitude", aggfunc="mean"),
            avg_geo_latitude=pd.NamedAgg(column="geo_latitude", aggfunc="mean"),
            std_geo_longitude=pd.NamedAgg(column="geo_longitude", aggfunc="std"),
            std_geo_latitude=pd.NamedAgg(column="geo_latitude", aggfunc="std"),
            job_count=pd.NamedAgg(column="scheduled_primary_worker_id", aggfunc="count"),
        )
        .reset_index()
    )  # .sort_values(['location_code'], ascending=True)

    # json.dumps(
    worker_gmm_df["job_history_feature_data"] = worker_gmm_df.apply(
        lambda x: {
            "mean": {"longitude": x["avg_geo_longitude"], "latitude": x["avg_geo_latitude"]},
            "std": {"longitude": x["std_geo_longitude"], "latitude": x["std_geo_latitude"]},
            "count": x["job_count"],
        },
        axis=1,
    )

    worker_gmm_df.rename(columns={"scheduled_primary_worker_id": "id"}, inplace=True)
    update_dict_list = json.loads(
        worker_gmm_df[["id", "job_history_feature_data"]].to_json(orient="records")
    )

    # worker_gmm_df.rename(columns={"job_history_feature_data": "notes"}, inplace=True)

    db_session.bulk_update_mappings(
        Worker,
        update_dict_list,
    )
    # db_session.flush()
    db_session.commit()

    log.debug(f"calc_historical_location_features finished ...")
