from dispatch.plugins.kandbox_planner.env.env_models import ActionDict
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


class NaivePlannerJobsInSlots:  # to fake OptimizerJobsInSlots

    title = "Kandbox Plugin - Batch Optimizer - opti1day"
    slug = "kandbox_opti1day"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Batch Optimizer - opti1day."
    version = "0.1.0"
    default_config = {"log_search_progress": True, "max_exec_time": 3}
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, env, config=None):
        self.env = env
        self.travel_router = env.travel_router  # TravelTime(travel_speed=25)
        self.config = config or self.default_config
        # self.kandbox_env = kandbox_env
        # self.kandbox_env.reset()
        # if max_exec_time is not None:
        #    self.max_exec_time = max_exec_time

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
        # y_1,x_1= site1.split(':')
        # y_2,x_2= site2.split(':')
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

    def dispatch_jobs_in_slots(self, working_time_slots: list):
        """Assign jobs to workers."""
        num_slots = len(working_time_slots)  # - 2
        num_workers = len(working_time_slots) - 2
        if num_workers < 1:
            num_workers = 1

        if num_slots < 1:
            return {
                "status": OptimizerSolutionStatus.INFEASIBLE,
                "changed_action_dict_by_job_code": {},
                "not_changed_job_codes": [],
            }

        is_ok_start = True
        is_ok_end = True
        job_code = working_time_slots[0].assigned_job_codes[-1]
        job_duration_minutes = self.env.get_encode_shared_duration_by_planning_efficiency_factor(
            requested_duration_minutes=self.env.jobs_dict[job_code].requested_duration_minutes,
            nbr_workers=num_workers,
        )

        # Common earlist start of all slots
        current_min_start = max([s.start_minutes for s in working_time_slots])
        # Common latest start of all slots
        current_max_last_start = min(
            [s.end_minutes - job_duration_minutes for s in working_time_slots]
        )

        # The latest start if start from beginning. Try to align to first job rather than morning start.
        max_start_from_begin = current_max_last_start

        # NO need to track last start.
        # min_start_from_end = current_min_start

        for slot_i in range(num_slots):
            slot = working_time_slots[slot_i]

            all_jobs_to_begin = [slot.assigned_job_codes[-1]] + slot.assigned_job_codes[:-1]
            (
                prev_travel,
                next_travel,
                inside_travel,
            ) = self.env.get_travel_time_jobs_in_slot(slot, all_jobs_to_begin)
            if len(slot.assigned_job_codes) <= 1:
                if (
                    current_min_start + prev_travel + job_duration_minutes + next_travel >
                    slot.end_minutes
                ):
                    is_ok_start = False
                    is_ok_end = False
                    break
                else:
                    if current_min_start < slot.start_minutes:
                        current_min_start = slot.start_minutes

                    if current_max_last_start > (
                        slot.end_minutes - next_travel - job_duration_minutes
                    ):
                        current_max_last_start = (
                            slot.end_minutes - next_travel - job_duration_minutes
                        )
                    continue

            if current_min_start < slot.start_minutes:
                log.error("Should not happend: current_min_start < slot.start_minutes")
                current_min_start = slot.start_minutes

            first_job = self.env.jobs_dict[all_jobs_to_begin[1]]
            if (
                current_min_start + prev_travel + job_duration_minutes + inside_travel[0] >
                first_job.scheduled_start_minutes
            ):
                is_ok_start = False
            else:
                _new_start = (
                    first_job.scheduled_start_minutes - inside_travel[0] - job_duration_minutes
                )
                if max_start_from_begin > _new_start:
                    max_start_from_begin = _new_start

            all_jobs_to_end = slot.assigned_job_codes
            (
                prev_travel,
                next_travel,
                inside_travel,
            ) = self.env.get_travel_time_jobs_in_slot(slot, all_jobs_to_end)
            last_job = self.env.jobs_dict[all_jobs_to_end[-2]]

            if (
                last_job.scheduled_start_minutes +
                last_job.scheduled_duration_minutes +
                inside_travel[-1] +
                job_duration_minutes +
                next_travel
            ) > slot.end_minutes:
                is_ok_end = False

            if (
                last_job.scheduled_start_minutes +
                last_job.scheduled_duration_minutes +
                inside_travel[-1]
            ) < current_max_last_start:
                current_max_last_start = (
                    last_job.scheduled_start_minutes +
                    last_job.scheduled_duration_minutes +
                    inside_travel[-1]
                )

        final_result = {
            "status": OptimizerSolutionStatus.INFEASIBLE,
            "changed_action_dict_by_job_code": {},
            "not_changed_job_codes": [],
        }
        if is_ok_start:
            job_start_minutes = max_start_from_begin
        elif is_ok_end:
            job_start_minutes = current_max_last_start
        else:
            return final_result
        final_result["status"] = OptimizerSolutionStatus.SUCCESS

        all_worker_codes = [s.worker_id for s in working_time_slots]
        one_job_action_dict = ActionDict(
            is_forced_action=False,
            job_code=job_code,
            action_type=ActionType.FLOATING,
            scheduled_worker_codes=all_worker_codes,
            scheduled_start_minutes=job_start_minutes,
            scheduled_duration_minutes=job_duration_minutes,
            # slot_code_list =
        )
        final_result["changed_action_dict_by_job_code"][job_code] = one_job_action_dict

        planned_job_sequence = []
        for s in working_time_slots:
            planned_job_sequence.append([])
            if is_ok_start:
                planned_job_sequence[-1].append([job_start_minutes, job_code, 0, True])
            for jcode in s.assigned_job_codes[:-1]:
                planned_job_sequence[-1].append([-1, jcode, -1, False])
            if not is_ok_start:
                planned_job_sequence[-1].append([job_start_minutes, job_code, 0, True])

        final_result["slots"] = planned_job_sequence
        return final_result


if __name__ == "__main__":

    import pickle

    slots = pickle.load(open("/tmp/working_time_slots.p", "rb"))

    opti_slot = OptimizerJobsInSlots()
    res = opti_slot.dispatch_jobs_in_slots(slots)
    print(res)
