import torch
import numpy as np

import copy

from typing import Any, List
from datetime import datetime


from dispatch.plugins.kandbox_planner.env.configurable_dispatch_env import ConfigurableDispatchEnv
from dispatch.plugins.kandbox_planner.env.env_enums import PlannerType

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
from dispatch.job import service as job_service
from dispatch.order import service as order_service


import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util

from dispatch.plugins.bases.realtime_agent_rl import  KandboxRLAgentPlugin

import logging
log = logging.getLogger("single_realtime_rt4")

from dispatch.contrib.training.pomo.single_job2slot_n2s.single_job2slot_n2s_env import SingleJob2SlotN2SEnv
from dispatch.contrib.training.pomo.single_job2slot_n2s.single_job2slot_n2s_model import SingleJob2SlotN2SModel


from dispatch.config import (
    APPOINTMENT_DEBUG_LIST, JOB_RECOMMENDATION_INTERVAL, ROOT_DIR, 
    REDIS_JOB_QUEUE_REALTIME, REDIS_JOB_QUEUE_OPTIMIZER) 


# from dispatch.contrib.training.pomo.pomo_params import ( 
#     env_params, model_params, optimizer_params, trainer_params, logger_params, 
#     DEBUG_MODE, USE_CUDA, device)

device = torch.device('cpu')

class SinglePOMON2SRealtimeAgentPlugin(KandboxRLAgentPlugin):
    """
    single_pomo_n2s
    RT4 is pomo n2s based realtime agent for single job dispatch.
    It requires torch model and env.
    """
    title = "Kandbox Plugin - Agent - RT4"
    slug = "single_realtime_rt4"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "real time recommendation for job dispatching by incremental optimizer"
    version = "0.1.0"
    default_config = {
        "load_model": True,
        "coordinate": "enu_normal", # wgs84_minmax, enu_normal
        "job2slot_model_path":"$ROOT/online_models/dubai_pickdrop_job2slot_2in1_latest.pt",
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "job2slot_model_path": {
                "type": "string",
                "default": "$ROOT/tmp/temp.dt",
                "title": "job2slot_model_path",
            },
            "coordinate": {
                "type": "string",
                "default": "enu_normal",
                "title": "coordinate normalization method",
                "description": "Coordinate normalization method",
                "enum": ["wgs84_minmax", "enu_normal"],
            },
        },
    }
    planner_type = PlannerType.SINGLE




    def load_model(self, checkpoint):
        self.job2slot_env = SingleJob2SlotN2SEnv(self.env_params, self.model_params)
        self.job2slot_model = SingleJob2SlotN2SModel(self.model_params)

        self.job2slot_model.load_state_dict(checkpoint['model_state_dict'])
        self.start_epoch = 1 + checkpoint['epoch']

        # self.model_loaded_flag = True

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

        nearby_slots = slots
        the_job = env_jobs[0]
        begin_time = datetime.now()
        log.info(f"Started dispatching at time: {begin_time}, with config: {self.config}")

        all_locs_list = []
        loc2job_orig_list = [ ]
        loc2job_code_list = []

        worker_locs = []
        job_locs = []
        job2loc_idx_dict={}
        nbr_jobs_per_slot = env.get_config_max_nbr_jobs_allowed()

        for si,slot in enumerate(nearby_slots):
            # self.loc2worker_idx.append(slot.slot_code)
            loc2job_orig_list.append(None)
            all_locs_list.append([slot.start_longitude, slot.start_latitude, ] )
            worker_locs.append(si)
            job2loc_idx_dict[slot.slot_code] = si

        # loc2worker_idx_list = [i for i in range(len(nearby_slots))]
        worker_loc_lengths = [
            len(_s.assigned_jobs)+1 
            for _s in  nearby_slots
        ]
        worker_job_size = sum(worker_loc_lengths) + 1 # one reserved for incoming job
        solution_list = [worker_job_size for _ in range(worker_job_size+1)]
        solution_pre_list = list(range(worker_job_size+1))
        loc2slot_idx_list = [
            i for i in range(len(nearby_slots))
        ]

        available_worker_count = 0
        slot_curr_i = len(nearby_slots)
        for si,slot in enumerate(nearby_slots):
            if len(slot.assigned_jobs) >= nbr_jobs_per_slot:
                continue
            available_worker_count += 1
            slot_prev_i = si
            for ji,job in enumerate(slot.assigned_jobs):
                solution_list[slot_prev_i] = slot_curr_i
                solution_pre_list[slot_curr_i] = slot_prev_i
                loc2job_code_list.append(job.code)
                assert slot_curr_i == len(all_locs_list)
                job_locs.append(len(all_locs_list))
                job2loc_idx_dict[job.code] = len(all_locs_list)
                loc2slot_idx_list.append(si)
                # loc2worker_idx_list.append(si)
                loc2job_orig_list.append(job)
                all_locs_list.append([job.geo_longitude, job.geo_latitude,])
                
                slot_prev_i = slot_curr_i
                slot_curr_i += 1

        if available_worker_count < 1:
            log.warning(f"all slots are full, lengths are: {worker_loc_lengths}")
            return []

        loc2job_code_list.append(the_job.code)
        loc2job_orig_list.append(the_job)
        loc2slot_idx_list.append(-1001)
        job2slot_current_loc_i = len(all_locs_list)
        job2loc_idx_dict[the_job.code] = len(all_locs_list)
        job_locs.append(job2slot_current_loc_i)
        all_locs_list.append([
            the_job.geo_longitude, the_job.geo_latitude, 
        ])


        # long_lat_list = [(j.geo_longitude, j.geo_latitude) for j in all_locs_list]
        dist_mat_np = env.get_travel_router().get_travel_minutes_matrix(
            all_locs_list, return_type="duration"
            )# * float(self.config.get("travel_minutes_scale_factor",1))
        dist_mat = dist_mat_np.tolist()
        log.info(f"distance matrix statistics: (max = {dist_mat_np.max()}, min = {dist_mat_np.min()}, sum = {round(dist_mat_np.sum(),2)}, mean = {round(dist_mat_np.mean(),2)}, median = {round(np.median(dist_mat_np),2)})")

        loc_xy = self.normalize_addr(torch.tensor(all_locs_list), env)
        
        self.job2slot_env.load_jobs(
            loc_xy = loc_xy[None,:,:],
            dist_matrix= torch.tensor(dist_mat_np)[None,:,:],
            worker_loc_idx = torch.tensor(worker_locs)[None,None,:],
            job_loc_idx = torch.tensor(job_locs )[None,None,:],
        )
        step_state, reward, done = self.job2slot_env.set_state_to_length(
            worker_loc_length = torch.tensor(worker_loc_lengths)[None,:],
            solution = torch.tensor(solution_list)[None,:],
            solution_pre_idx = torch.tensor(solution_pre_list)[None,:],
            solution_worker_idx = torch.tensor(loc2slot_idx_list)[None,:],
            job2slot_current_job_i = job2slot_current_loc_i - len(nearby_slots),
            max_job_in_worker_size = max(worker_loc_lengths) + 2,
        )
 
        self.job2slot_model.pre_forward(step_state.reset_state)
        # try:
        selected, prob, _probs = self.job2slot_model(step_state)


        selected_job_i = selected[0,2].item()
        selected_slot_i = loc2slot_idx_list[selected_job_i]
        flat_length_scalar = worker_loc_lengths[selected_slot_i] 
        # _selected_slot = nearby_slots[selected_slot_i]
        if flat_length_scalar == 1: 
            solution_list[selected_slot_i] = job2slot_current_loc_i
        elif  flat_length_scalar == 2: 
            tail_job_i = solution_list[selected_slot_i]
            solution_list[tail_job_i] = job2slot_current_loc_i
        else:
            nbr_swap_steps = 5
            if flat_length_scalar < 10:  
                nbr_swap_steps = 4
            elif flat_length_scalar < 6:  
                nbr_swap_steps = 2
            elif flat_length_scalar < 4:  
                nbr_swap_steps = 1
            
            slot_map = [0 for _ in range(len(nearby_slots))]
            slot_map[selected_slot_i] = 1
            step_state.enabled_slot_map = torch.tensor(slot_map)[None,:].bool()
            # AI Does the rest
            for _ in range(nbr_swap_steps):
                step_state, reward, done = self.job2slot_env.step(selected)
                selected, prob, _probs = self.job2slot_model(step_state)
                if done:
                    break
            
            best_solution = step_state.prev_best_solution[0,:,1]
            solution_list = best_solution.tolist()

        
        # new_assigned_jobs = self.calc_travel_time(
        #     slot = _selected_slot, 
        #     job_codes = [j.code for j in [_selected_slot.assigned_jobs + env_jobs]],
        #     dist_mat = dist_mat,
        #     fix_first_flag = False)
        # Now I collect and return result
        
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

        pre_arrival = rec_start_minutes = slot_start_minutes = selected_slot.start_minutes
        prev_idx = selected_slot_i
        new_travel = 0
        # _curr_loc_i = selected_slot_i
        for step_i in range(worker_job_size):
            curr_idx = solution_list[prev_idx]
            if curr_idx == worker_job_size:
                break


            new_travel += dist_mat[prev_idx][curr_idx]
            _new_start = rec_start_minutes + new_travel

            opti_job = loc2job_orig_list[curr_idx]
            selected_slot.assigned_jobs.append( 
                JobInSlot(
                    scheduled_start_minutes = _new_start,
                    code=opti_job.code,
                    geo_longitude = opti_job.geo_longitude,
                    geo_latitude = opti_job.geo_latitude,
                    prev_travel = new_travel,
                    scheduled_duration_minutes = 1,
                    tolerance_end_minutes = 0,
                    flex_form_data={},
            ) )
            if job2slot_current_loc_i == curr_idx:
                rec_start_minutes = _new_start

            prev_idx = curr_idx

        travel_minutes_diff = new_travel - orig_travel
        
        solution = {
            "score": round(travel_minutes_diff, 2),
            "slots": [selected_slot],
            "start_minutes":rec_start_minutes,
            "dist":  round(travel_minutes_diff, 2),
            "algo": "rt4",
        }
        
        result_rec_list.append(solution)

        return result_rec_list # sorted(result_rec_list, key=lambda a: a["score"], reverse=False)