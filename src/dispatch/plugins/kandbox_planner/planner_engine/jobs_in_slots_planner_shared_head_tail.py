from dispatch.plugins.kandbox_planner.env.env_models import ActionDict, JobsInSlotsDispatchResult
from dispatch.plugins.kandbox_planner.env.env_enums import OptimizerSolutionStatus, ActionType
from datetime import datetime, timedelta
import pandas as pd


from ortools.sat.python import cp_model

import collections


from pprint import pprint

import sys

from dispatch import config
from dispatch.plugins.kandbox_planner.planner_engine.jobs_in_slots_trait import JobsInSlotsPlannerTrait
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util


from dispatch.plugins.kandbox_planner.travel_time_plugin import (
    MultiLayerCacheTravelTime as TravelTime,
)
from dispatch.plugins.bases.kandbox_planner import KandboxBatchOptimizerPlugin
import logging

log = logging.getLogger(__file__)


class NaivePlannerJobsInSlots(JobsInSlotsPlannerTrait):  # to fake OptimizerJobsInSlots

    title = "Kandbox Plugin - Batch Optimizer - opti1day"
    slug = "kandbox_opti1day"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Batch Optimizer - opti1day."
    version = "0.1.0"
    default_config = {"log_search_progress": True, "max_exec_seconds": 3}
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def dispatch_jobs_in_slots(self, working_time_slots: list=[], last_job_count=1):
        """Assign jobs to workers."""
        num_slots = len(working_time_slots)  # - 2
        num_workers = len(working_time_slots) - 2
        if num_workers < 1:
            num_workers = 1

        if num_slots < 1:
            return JobsInSlotsDispatchResult(
                status = OptimizerSolutionStatus.INFEASIBLE,
                changed_action_dict_by_job_code= {},
                all_assigned_job_codes=[],
                planned_job_sequence=[]
            )

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

            sorted_slot_assigned_job_codes = sorted(
                slot.assigned_job_codes[:-1], key=lambda x: self.env.jobs_dict[x].scheduled_start_minutes)

            all_jobs_to_begin = [slot.assigned_job_codes[-1]] + sorted_slot_assigned_job_codes
            (
                prev_travel,
                next_travel,
                inside_travel,
            ) = self.env.get_travel_time_jobs_in_slot(slot, all_jobs_to_begin)
            
            if len(slot.assigned_job_codes) <= 1:
                # if The job itself is the only one in considerattion.
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
            # slot.assigned_job_codes
            all_jobs_to_end = sorted_slot_assigned_job_codes + \
                [slot.assigned_job_codes[-1]]
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

        final_result = JobsInSlotsDispatchResult(
                status = OptimizerSolutionStatus.INFEASIBLE,
                changed_action_dict_by_job_code= {},
                all_assigned_job_codes=[],
                planned_job_sequence=[]
            ) 
        if is_ok_start:
            # job_start_minutes = max_start_from_begin
            job_start_minutes = current_min_start
        elif is_ok_end:
            job_start_minutes = current_max_last_start
        else:
            return final_result
        final_result.status = OptimizerSolutionStatus.SUCCESS

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
        final_result.changed_action_dict_by_job_code[job_code] = one_job_action_dict

        planned_job_sequence = []
        seq = 0
        for s in working_time_slots:
            planned_job_sequence.append([])
            if is_ok_start:
                planned_job_sequence[-1].append([job_start_minutes, job_code, seq, True])
                seq = len(planned_job_sequence[-1])
            for jcode in s.assigned_job_codes[:-1]:
                planned_job_sequence[-1].append([
                    self.env.jobs_dict[jcode].scheduled_start_minutes, 
                    jcode, seq, False])
                seq = len(planned_job_sequence[-1])
            if not is_ok_start:
                planned_job_sequence[-1].append([job_start_minutes, job_code, seq, True])
                seq = len(planned_job_sequence[-1])

        final_result.planned_job_sequence = planned_job_sequence
        return final_result



if __name__ == "__main__":

    import pickle

    slots = pickle.load(open("/tmp/working_time_slots.p", "rb"))

    opti_slot = NaivePlannerJobsInSlots()
    res = opti_slot.dispatch_jobs_in_slots(slots)
    print(res)
