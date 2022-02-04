from dispatch.plugins.kandbox_planner.env.env_models import ActionDict, JobsInSlotsDispatchResult
from dispatch.plugins.kandbox_planner.env.env_enums import OptimizerSolutionStatus, ActionType
from datetime import datetime, timedelta
import pandas as pd


from ortools.sat.python import cp_model

import collections


from pprint import pprint

import sys

from dispatch import config
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util


from dispatch.plugins.kandbox_planner.travel_time_plugin import (
    MultiLayerCacheTravelTime as TravelTime,
)
from dispatch.plugins.bases.kandbox_planner import KandboxBatchOptimizerPlugin
import logging

log = logging.getLogger(__file__)

#  Must have sub class
class JobsInSlotsPlannerTrait:  

    title = "Kandbox Plugin - internal - Generic"
    slug = "kandbox_Generic"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Batch Optimizer - Generic."
    version = "0.1.0"
    default_config = { }
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, env, config=None):
        self.env = env
        self.travel_router = env.travel_router  # TravelTime(travel_speed=25)
        self.config = config or self.default_config 

    def _get_travel_time_from_location_to_job(self, location, job_code_2):
        # y_1,x_1= site1.split(':')
        # y_2,x_2= site2.split(':')
        site2 = self.env.jobs_dict[job_code_2]
        new_time = self.travel_router.get_travel_minutes_2locations(
            location,
            [site2.location.geo_longitude, site2.location.geo_latitude],
        )
        if new_time > config.TRAVEL_MINUTES_WARNING_LEVEL:
            log.debug(
                f"JOB:{job_code_2}:{ location[0], location[1]}:{site2.location.geo_longitude, site2.location.geo_latitude}:very long travel time: {new_time} minutes. "
            )
            return config.TRAVEL_MINUTES_WARNING_RESULT
        # print("travel: ", new_time)
        return int(new_time / 1)

    def _get_travel_time_2_sites(self, job_code_1, job_code_2): 
        site1 = self.env.jobs_dict[job_code_1]
        site2 = self.env.jobs_dict[job_code_2]

        new_time = self.travel_router.get_travel_minutes_2locations(
            [site1.location.geo_longitude, site1.location.geo_latitude],
            [site2.location.geo_longitude, site2.location.geo_latitude],
        )
        if new_time > 200:
            log.warn(
                [site1.location.geo_longitude, site1.location.geo_latitude],
                [site2.location.geo_longitude, site2.location.geo_latitude],
                (new_time),
            )
            return 10000
        # print("travel: ", new_time)
        return int(new_time / 1)

    def dispatch_jobs_in_slots(self, working_time_slots: list=[], last_job_count=1):
        """Assign jobs to workers."""
        raise NotImplemented("Pls use sub class")
