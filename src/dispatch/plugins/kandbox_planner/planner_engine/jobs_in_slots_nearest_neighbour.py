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


from dispatch.plugins.kandbox_planner.planner_engine.jobs_in_slots_trait import JobsInSlotsPlannerTrait
from dispatch.contrib.plugins.env.nearest_insertion  import NearestInsertion


from dispatch.plugins.kandbox_planner.travel_time_plugin import (
    MultiLayerCacheTravelTime as TravelTime,
)
from dispatch.plugins.bases.kandbox_planner import KandboxBatchOptimizerPlugin
import logging

log = logging.getLogger(__file__)


class NearestNeighbourPlannerJobsInSlots(JobsInSlotsPlannerTrait):  # to fake OptimizerJobsInSlots

    title = "Kandbox Plugin - internal - jobs in slots"
    slug = "kandbox_nearest_neighbour"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Batch Optimizer - nearest_neighbour."
    version = "0.1.0"
    default_config = { }
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def dispatch_jobs_in_slots(self, working_time_slots: list=[], last_job_count=1):
        """Assign jobs to workers.
        
        Note: THis works only for single worker, not shared.!
        """
        num_slots = len(working_time_slots)  # - 2
        num_workers = len(working_time_slots) - 2
        if num_workers < 1:
            num_workers = 1
        final_result = JobsInSlotsDispatchResult(
                status = OptimizerSolutionStatus.INFEASIBLE,
                changed_action_dict_by_job_code= {},
                all_assigned_job_codes=[],
                planned_job_sequence=[]
            ) 
        #     {
        #     "status": OptimizerSolutionStatus.INFEASIBLE,
        #     "changed_action_dict_by_job_code": {},
        #     "all_assigned_job_codes": [],
        #     "travel_minutes_difference": 0,
        # }
        if (num_slots < 1) or (
            len(working_time_slots[0].assigned_job_codes) > self.env.config["MAX_NBR_JOBS_IN_SLOT"]
        ):
            log.debug(f"Plan rejected, trying to plan {len(working_time_slots[0].assigned_job_codes)} jobs ...")
            return final_result


        # is_ok_end = True
        job_1_code = working_time_slots[0].assigned_job_codes[0-last_job_count]
        job_1 = self.env.jobs_dict[job_1_code]
        # I assume that job1 and job2 have same duration. 2021-07-06 07:16:06
        job_duration_minutes = self.env.get_encode_shared_duration_by_planning_efficiency_factor(
            requested_duration_minutes=job_1.requested_duration_minutes,
            nbr_workers=num_workers,
        )

        job_2_code = working_time_slots[0].assigned_job_codes[-1]
        job_2 = self.env.jobs_dict[job_2_code]



        slot = working_time_slots[0]
        horizon_start = self.env.get_env_planning_horizon_start_minutes()
        if horizon_start < slot.start_minutes:
            horizon_start = slot.start_minutes
        # orig_slot_job_codes = slot.assigned_job_codes[: 0 - last_job_count] 

        j_pick = []
        j_drop = []
        for jc in slot.assigned_job_codes:
            if jc.split("-")[-1] == "pick":
                j_pick.append(jc)
            else:
                j_drop.append(jc) 
        if len(j_pick) > 0:
            # prefix last pick as starting points for drop jobs.
            j_drop = [j_pick[-1]] + j_drop
        else:
            log.error("No pick job for assignment?")
        if len(j_drop) > 2:
            locations = [self.env.jobs_dict[j].location[0:2] for j in j_drop]
            ni  = NearestInsertion(locations=locations, travel_router=self.env.travel_router)
            solution_index, c, e = ni.solve_nn()
            solved_drop = [j_drop[i] for i in solution_index]
            # saved = sum(self.env.get_travel_time_jobs_in_slot(slot, j_drop)[2]) - sum(self.env.get_travel_time_jobs_in_slot(slot, solved_drop)[2])
            # print(f"saved: {saved}")
        else:
            solved_drop = j_drop
        if len(j_pick) > 0:
            solved_drop = solved_drop[1:]
        
        final_result.status = OptimizerSolutionStatus.SUCCESS 

        if len(j_pick) > 1:
            prev_start_time = self.env.jobs_dict[j_pick[-2]].scheduled_start_minutes  + 5 
            prev_loc =  self.env.jobs_dict[j_pick[-2]].location
        else:
            prev_start_time = horizon_start
            prev_loc = slot.start_location
        scheduled_start_minutes = prev_start_time + self.env.travel_router.get_travel_minutes_2locations(
            prev_loc, 
            job_1.location
            )

        all_worker_codes = [s.worker_id for s in working_time_slots]
        job_1_action_dict = ActionDict(
            is_forced_action=False,
            job_code=job_1_code,
            action_type=ActionType.FLOATING,
            scheduled_worker_codes=all_worker_codes,
            scheduled_start_minutes=scheduled_start_minutes,
            scheduled_duration_minutes=job_duration_minutes,
        )
        final_result.changed_action_dict_by_job_code[job_1_code] = job_1_action_dict

        job_list = j_pick + solved_drop
        final_result.all_assigned_job_codes = [job_list]

        current_start = job_1_action_dict.scheduled_start_minutes
        prev_job = job_1
        for job_i in list(range(len(j_pick), len(job_list))):
            j_code = job_list[job_i]
            curr_job = self.env.jobs_dict[j_code]
            current_start += prev_job.requested_duration_minutes + \
                self.env._get_travel_time_2jobs(prev_job, curr_job)
            _action_dict = ActionDict(
                is_forced_action=False,
                job_code=j_code,
                action_type=ActionType.FLOATING,
                scheduled_worker_codes=all_worker_codes,
                scheduled_start_minutes=current_start,
                scheduled_duration_minutes=curr_job.requested_duration_minutes,
            )
            final_result.changed_action_dict_by_job_code[j_code] = _action_dict
            prev_job = curr_job
 
        for job_i in list(range(0, len(j_pick)-1)):
            j_code = job_list[job_i]
            curr_job = self.env.jobs_dict[j_code]
            current_start = curr_job.scheduled_start_minutes
            _action_dict = ActionDict(
                is_forced_action=False,
                job_code=j_code,
                action_type=ActionType.FLOATING,
                scheduled_worker_codes=all_worker_codes,
                scheduled_start_minutes=current_start,
                scheduled_duration_minutes=curr_job.requested_duration_minutes,
            )
            final_result.changed_action_dict_by_job_code[j_code] = _action_dict
            prev_job = curr_job

        return final_result


if __name__ == "__main__":

    import pickle

    slots = pickle.load(open("/tmp/working_time_slots.p", "rb"))

    opti_slot = NearestNeighbourPlannerJobsInSlots()
    res = opti_slot.dispatch_jobs_in_slots(slots)
    print(res)
