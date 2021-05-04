import logging
from datetime import datetime
import json

import pandas as pd
from schedule import every
from sqlalchemy import func

from dispatch.decorators import background_task
from dispatch.enums import Visibility
from dispatch.extensions import sentry_sdk
from dispatch.job.models import Job
from dispatch.worker import service as worker_service
from dispatch.worker.models import Worker
from dispatch.location.models import Location

from dispatch.plugins.base import plugins
from dispatch.plugins.kandbox_planner.data_adapter.kplanner_db_adapter import KPlannerDBAdapter
from dispatch.scheduler import scheduler
from dispatch.service import service as service_service
from dispatch.tag import service as tag_service
from dispatch.tag.models import Tag


from .enums import JobPlanningStatus
from .service import calculate_cost, get_all, get_all_by_status, get_all_last_x_hours_by_status

log = logging.getLogger(__name__)


@scheduler.add(every(1).hours, name="job-tagger")
@background_task
def auto_tagger(db_session):
    """Attempts to take existing tags and associate them with jobs."""
    tags = tag_service.get_all(db_session=db_session).all()
    log.debug(f"Fetched {len(tags)} tags from database.")

    tag_strings = [t.name.lower() for t in tags if t.discoverable]
    phrases = build_term_vocab(tag_strings)
    matcher = build_phrase_matcher("dispatch-tag", phrases)

    p = plugins.get(
        INCIDENT_PLUGIN_STORAGE_SLUG
    )  # this may need to be refactored if we support multiple document types

    for job in get_all(db_session=db_session).all():
        log.debug(f"Processing job. Name: {job.name}")

        doc = job.job_document
        try:
            mime_type = "text/plain"
            text = p.get(doc.resource_id, mime_type)
        except Exception as e:
            log.debug(f"Failed to get document. Reason: {e}")
            sentry_sdk.capture_exception(e)
            continue

        extracted_tags = list(set(extract_terms_from_text(text, matcher)))

        matched_tags = (
            db_session.query(Tag)
            .filter(func.upper(Tag.name).in_([func.upper(t) for t in extracted_tags]))
            .all()
        )

        job.tags.extend(matched_tags)
        db_session.commit()

        log.debug(f"Associating tags with job. Job: {job.name}, Tags: {extracted_tags}")


@scheduler.add(every(3000).seconds, name="calc_historical_location_features")
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
            Job.id.label("job_id"),
            Job.scheduled_start_datetime,
            Job.scheduled_duration_minutes,
            Job.requested_start_datetime,
            Job.location_id,
            Location.geo_longitude,
            Location.geo_latitude,
        )
        .filter(Job.location_id == Location.id)
        .filter(Job.planning_status != JobPlanningStatus.unplanned)
        .statement,
        db_session.bind,
    )
    if job_loc_df.count().max() < 1:
        # raise ValueError("job_loc_df.count().max() < 1, no data to proceed")
        print(
            "calc_historical_location_features_real_func: job_loc_df.count().max() < 1, no data to proceed"
        )
        return

    from dispatch.plugins.kandbox_planner.util.kandbox_date_util import (
        extract_minutes_from_datetime,
    )

    job_loc_df["actual_start_minutes"] = job_loc_df.apply(
        lambda x: extract_minutes_from_datetime(x["scheduled_start_datetime"]),
        axis=1,
    )
    job_loc_df["days_delay"] = job_loc_df.apply(
        lambda x: (x["scheduled_start_datetime"] - x["requested_start_datetime"]).days, axis=1
    )

    loc_gmm_df = (
        job_loc_df.groupby(["location_id"])
        .agg(
            # job_count=pd.NamedAgg(column='location_code', aggfunc='count')
            avg_geo_longitude=pd.NamedAgg(column="geo_longitude", aggfunc="mean"),
            avg_geo_latitude=pd.NamedAgg(column="geo_latitude", aggfunc="mean"),
            std_geo_longitude=pd.NamedAgg(column="geo_longitude", aggfunc="std"),
            std_geo_latitude=pd.NamedAgg(column="geo_latitude", aggfunc="std"),
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
    from collections import Counter

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
