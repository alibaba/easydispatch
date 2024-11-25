from dispatch.plugins.kandbox_planner.env.configurable_dispatch_env import ConfigurableDispatchEnv
from dispatch.plugins.kandbox_planner.env.env_enums import (
    OptimizerSolutionStatus,
    ActionType,
    JobPlanningStatus,
    ActionScoringResultType,
) 
from dispatch.plugins.kandbox_planner.env.env_models import (
    EnvAction,
    JobInSlot,
    RecommendedAction,
    OptiJobLoc,
    LocationTuple,
    Worker,
    ActionEvaluationScore,
    TimeSlotType,
    WorkingTimeSlot,
)

import numpy as np
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util
from dispatch.plugins.kandbox_planner.util.kandbox_util  import encode_job_flex_form2rustenv

# from dispatch.location_group import service as location_group_service

from dispatch.plugins.bases.realtime_agent import KandboxAgentPlugin

import vroom

import pandas as pd

from dispatch.config import APPOINTMENT_DEBUG_LIST, JOB_RECOMMENDATION_INTERVAL, VROOM_SOLVER_NB_THREADS
import copy

# from collections import namedtuple
from datetime import datetime
from typing import List

SLUG_NAME = "pickdrop_realtime_rt5"
import logging
log = logging.getLogger(SLUG_NAME)
from dispatch.plugins.kandbox_planner.env.env_enums import PlannerType


class PickdropVroomRealtimeAgentPlugin(KandboxAgentPlugin):
    """
    RT5 is vroom solver based realtime agent for pickdrop job dispatch.

    """
    title = "Kandbox Plugin - Pickdrop Agent - RT5"
    slug = SLUG_NAME
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "real time recommendation for Pickdrop job dispatching by incremental optimizer"
    version = "0.1.0"
    default_config = {
        "nbr_of_actions": 4,
        "try_location_group": True,
        "trace_progress": True,
        "max_jobs_per_worker": 0,
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "nbr_of_actions": {
                "type": "number",
                "default": 5,
                "title": "nbr_of_actions",
            }, 
    },
    }
    planner_type = PlannerType.PICKDROP

    def __init__(self, config=None, env_config=None, env=None):
        self.config = copy.deepcopy(self.default_config)
        if config:
            self.config.update(config)

        self.env = env


    def dispatch2slot(
        self,
        env: ConfigurableDispatchEnv, 
        env_jobs: List[JobInSlot],
        slots:List[WorkingTimeSlot],
        dist_list = None,
        dist_matrix = None

    ) -> List[dict]:
        if len(slots) < 1 or len(env_jobs) < 1:
            return []

        begin_time = datetime.now()
        log.info(f"Started dispatching at time: {begin_time}, with config: {self.config}")
        jobs_locs = []

        vehicle_max_nbr_order = 9999
        max_travel_time = 999999999999

        worker_start_loc_idx = {}
        # worker_return_loc_idx = {}
        job2loc_idx_dict={}
        vehicle_list = []
        opti_model = vroom.Input()

        for si, s in enumerate(slots): 
            jobs_locs.append(
                    OptiJobLoc(
                        geo_longitude = s.start_longitude,
                        geo_latitude = s.start_latitude,
                        node_type = "slot",
                        orig_index = si,
                        code = s.slot_code,
                        c_weight = 0,
                        c_volume = 0,
                        c_time_window = [],
                        fixed_worker_index = si,
                        requested_duration_minutes = 1,
                        # flex_form_data= j.flex_form_data
                    )
                )
            worker_start_loc_idx[s.slot_code] = len(jobs_locs) - 1

            vehicle_list.append(vroom.Vehicle(
                si, 
                start=len(jobs_locs) - 1, 
                end=None, # return_idx,
                skills = {si}, #  self.worker_code2index[s.worker_code]
                # capacity=vehicle_capacity,
                max_tasks=vehicle_max_nbr_order,
                max_travel_time = max_travel_time,
                time_window=[0, 1440]
            ))

        opti_model.add_vehicle(vehicle_list)
        order_dict = {}
        all_job_index=len(jobs_locs)
        for si, _slot in enumerate(slots): 
            for j in  _slot.assigned_jobs:
                job = OptiJobLoc(
                    geo_longitude = j.geo_longitude,
                    geo_latitude = j.geo_latitude,
                    node_type = "job",
                    orig_index = all_job_index,
                    code = j.code,
                    c_weight = 1,
                    c_volume = 1,
                    c_time_window = [],
                    fixed_worker_index = si,
                    requested_duration_minutes = j.scheduled_duration_minutes if j.scheduled_duration_minutes is not None else 1,
                    flex_form_data= j.flex_form_data
                )
                order_code = job.code[:-2]
                job_type = job.code[-1]
                if order_code not in order_dict:
                    order_dict[order_code] = [None, None]

                if job_type == 'p':
                    order_dict[order_code][0] = job
                else:
                    order_dict[order_code][1] = job

                jobs_locs.append(job)
                job2loc_idx_dict[j.code] = all_job_index
                all_job_index +=1
        # add pick_job
        target_job_idx = [all_job_index, all_job_index+1]
        job2loc_idx_dict[env_jobs[0].code] = all_job_index
        job2loc_idx_dict[env_jobs[1].code] = all_job_index+1

        for j in env_jobs:
            job = OptiJobLoc(
                geo_longitude = j.geo_longitude,
                geo_latitude = j.geo_latitude,
                node_type = "job",
                orig_index = all_job_index,
                code = j.code,
                c_weight = 1,
                c_volume = 1,
                c_time_window = [],
                fixed_worker_index = None,
                requested_duration_minutes = j.scheduled_duration_minutes if j.scheduled_duration_minutes is not None else 1,
                flex_form_data= j.flex_form_data
            )
            jobs_locs.append(job)
            all_job_index+=1
        
        order_dict[env_jobs[0].code[:-2]] = jobs_locs[-2:]

        # pick_job = env_jobs[0]
        # jobs_locs.append(
        #             OptiJobLoc(
        #                 geo_longitude = pick_job.geo_longitude,
        #                 geo_latitude = pick_job.geo_latitude,
        #                 node_type = "job",
        #                 orig_index = all_job_index,
        #                 code = pick_job.code,
        #                 c_weight = 1,
        #                 c_volume = 1,
        #                 c_time_window = [],
        #                 fixed_worker_index = None,
        #                 requested_duration_minutes = pick_job.scheduled_duration_minutes 
        #                     if pick_job.scheduled_duration_minutes is not None 
        #                     else 1, 
        #             )
        #         )


        long_lat_list = [(j.geo_longitude, j.geo_latitude) for j in jobs_locs]
        dist_mat_np = env.get_travel_router().get_travel_minutes_matrix(
            long_lat_list, return_type="duration"
            ) * float(self.config.get("travel_minutes_scale_factor",1))
        dist_mat = dist_mat_np.astype(int).tolist()
        log.info(f"distance matrix statistics: (max = {dist_mat_np.max()}, min = {dist_mat_np.min()}, sum = {round(dist_mat_np.sum(),2)}, mean = {round(dist_mat_np.mean(),2)}, median = {round(np.median(dist_mat_np),2)})")
 
        opti_model.set_durations_matrix(
            profile="car",
            matrix_input=dist_mat,
        )
        """
        clients = []
        for idx in range(1, len(jobs_locs) ):
            job = jobs_locs[idx]
            if job.node_type != "job":
                continue
            job_delivery = None
            # job_delivery=[1, 1]
            # if int(self.config.get("enable_weight_constraint", 0)) == 1:
            #     job_delivery[0] = int(job.c_weight)

            # if int(self.config.get("enable_volume_constraint", 0)) == 1:
            #     job_delivery[1] = int(job.c_volume)
            job_skills = None
            if job.fixed_worker_index is not None:
                job_skills = {job.fixed_worker_index}
            j = vroom.Job(
                id=idx, location=idx,
                delivery=job_delivery,
                service=job.requested_duration_minutes, 
                skills = job_skills,
                time_windows=job.c_time_window
            )

            clients.append(j)
        opti_model.add_job(clients)

        """
        for _oc, _ord in order_dict.items():
            is_order_flag = True
            if _ord[0] is None:
                is_order_flag = False
                todo_job = _ord[1]
            elif _ord[1] is None:
                is_order_flag = False
                todo_job = _ord[0]
            else:
                todo_job = _ord[0]

            job_skills = None
            if todo_job.fixed_worker_index is not None:
                job_skills = {todo_job.fixed_worker_index}

            if is_order_flag: 
                pick_step = vroom.ShipmentStep(
                    id=_ord[0].orig_index,
                    location=_ord[0].orig_index,  
                )
                drop_step = vroom.ShipmentStep(
                    id=_ord[1].orig_index,
                    location=_ord[1].orig_index,  
                )
                opti_model.add_shipment(
                    pickup = pick_step,
                    delivery = drop_step,
                    skills = job_skills,
                )
            else:
                loc_idx = todo_job.orig_index
                opti_model.add_job(
                    vroom.Job(
                        id=loc_idx, location=loc_idx,
                        delivery=None,
                        service=todo_job.requested_duration_minutes, 
                        skills = job_skills,
                        time_windows=job.c_time_window
                    )
                )                

        solution = opti_model.solve(exploration_level=5, nb_threads=VROOM_SOLVER_NB_THREADS)
        log.info(f"VRoom Dispatching result: solution.summary.cost = {solution.summary.cost}, violations = {solution.summary.violations._types}, waiting_time = {solution.summary.waiting_time}, unassigned = {solution.summary.unassigned}") 
        # return
        # Print solution on console.
        if solution:
            # print(f'Solver status: {routing.status()}, Objective: {solution.ObjectiveValue()}') 
            # self.print_solution(manager, routing, solution, worker_slots_all, jobs_locs, dist_mat)
            return self.parse_solution_record(env, solution, slots, jobs_locs, dist_mat,target_job_idx,job2loc_idx_dict )

        else:
            log.warning("RT5_realtime_Dispatching_Failed.")
        return []



    def parse_solution_record(
            self, env: ConfigurableDispatchEnv, solution, 
            slots, jobs_locs, dist_mat,  target_job_idx,job2loc_idx_dict
        ):
        selected_row = solution.routes[
            (solution.routes["location_index"].isin(target_job_idx) ) & 
            (solution.routes["type"] == 'pickup')
        ][["vehicle_id",]].copy() # "location_index"
        selected_slot_i = selected_row["vehicle_id"].item()
        selected_df = pd.merge(
            left=solution.routes[["location_index","vehicle_id", "arrival","type"]],
            right=selected_row,
            left_on="vehicle_id",
            right_on="vehicle_id",
        )
        result_rec_list = []
        selected_slot = slots[selected_slot_i]
        orig_job_list = selected_slot.assigned_jobs
        # prev_loc = (selected_slot.start_longitude, selected_slot.start_latitude, )
        prev_idx = selected_slot_i
        orig_travel = 0
        for job in orig_job_list:
            curr_idx = job2loc_idx_dict[job.code]
            orig_travel += dist_mat[prev_idx][curr_idx]
            prev_idx = curr_idx

        selected_slot.assigned_jobs = []

        env_horizon = env.get_env_planning_horizon_start_minutes()

        pre_arrival = rec_start_minutes = slot_start_minutes = max(selected_slot.start_minutes, env_horizon)
        prev_idx = selected_slot_i
        new_travel = 0

        for index, job_row in selected_df.iterrows():
            if job_row["type"] not in  ("job", "pickup","delivery"):
                prev_idx = job_row["location_index"]
                continue
            opti_job = jobs_locs[job_row["location_index"]]
            curr_idx = job2loc_idx_dict[opti_job.code]
            assert curr_idx == job_row["location_index"]
            new_travel += dist_mat[prev_idx][curr_idx]
            prev_idx = curr_idx

            selected_slot.assigned_jobs.append( 
                JobInSlot(
                    scheduled_start_minutes = slot_start_minutes + job_row["arrival"],
                    code=opti_job.code,
                    geo_longitude = opti_job.geo_longitude,
                    geo_latitude = opti_job.geo_latitude,
                    prev_travel = dist_mat[prev_idx][curr_idx],
                    scheduled_duration_minutes = 1,
                    tolerance_end_minutes = slot_start_minutes + job_row["arrival"] + 1440, # TODO
                    flex_form_data=opti_job.flex_form_data,  #encode_job_flex_form2rustenv
            ) )
            pre_arrival = job_row["arrival"]
            if target_job_idx == curr_idx:
                rec_start_minutes = job_row["arrival"]

        travel_minutes_diff = new_travel - orig_travel
        
        solution = {
            "score": round(travel_minutes_diff, 2),
            "slots": [selected_slot],
            "start_minutes":rec_start_minutes,
            "dist":  round(travel_minutes_diff, 2),
            "algo": "rt5",
        }
        
        result_rec_list.append(solution)

        return result_rec_list # sorted(result_rec_list, key=lambda a: a["score"], reverse=False)