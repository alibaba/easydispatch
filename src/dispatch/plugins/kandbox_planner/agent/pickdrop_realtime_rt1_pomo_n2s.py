
import torch
import pandas as pd
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

from dispatch.plugins.bases.realtime_agent_rl import KandboxRLAgentPlugin

import logging
SLUG_NAME = "pickdrop_realtime_rt1"

log = logging.getLogger(SLUG_NAME)
from dispatch.contrib.training.pomo.pickdrop_pomo_n2s.pickdrop_pomo_n2s_env import PickDropPomoN2SEnv
from dispatch.contrib.training.pomo.pickdrop_pomo_n2s.pickdrop_pomo_n2s_model import PickDropPomoN2SModel

from dispatch.config import (
    APPOINTMENT_DEBUG_LIST, JOB_RECOMMENDATION_INTERVAL, MODEL_ROOT_DIR, 
    REDIS_JOB_QUEUE_REALTIME, REDIS_JOB_QUEUE_OPTIMIZER) 


# from dispatch.contrib.training.pomo.pomo_params import ( 
#     env_params, model_params, optimizer_params, trainer_params, logger_params, 
#     DEBUG_MODE, USE_CUDA, device)



class PickdropPOMON2SRealtimeAgentPlugin(KandboxRLAgentPlugin):
    """ 
    RT1 is pomo n2s based realtime agent for pickdrop job dispatch.

        
    """
    title = "Kandbox Plugin - Agent - RT1"
    slug = SLUG_NAME
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "real time recommendation for pickdrop job dispatching by reinforcement learning"
    version = "0.1.0"
    default_config = {
        "load_model": True,
        "coordinate": "enu_normal", # wgs84_minmax, enu_normal
        "job2slot_model_path":"$ROOT/ed_model/pomo_n2s/20231212_001743_pickdrop_pomo_n2s_checkpoint_2930_score5.pt",
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "job2slot_model_path": {
                "type": "string",
                "default": "$ROOT/ed_model/pomo_n2s/20231212_001743_pickdrop_pomo_n2s_checkpoint_2930_score5.pt",
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
    planner_type = PlannerType.PICKDROP


    # def __init__(self, config=None,):
    #     self.config = copy.deepcopy(self.default_config)
    #     if config:
    #         self.config.update(config)

    #     self.decode_type = "greedy"
    #     ###
    #     local_env_params = copy.deepcopy(env_params)
    #     local_env_params["pomo_size"] = 1
    #     model_params['eval_type'] == 'argmax'


    #     self.job2slot_env = PickDropPomoN2SEnv(local_env_params, model_params)
    #     self.job2slot_model = PickDropPomoN2SModel(model_params)

    #     self.job2slot_env.training = False

    #     self.batch_size = 1
    #     self.pomo_size = 1
    #     self.worker_size = 1
    #     self.max_job_in_worker_size = local_env_params['max_job_in_worker_size']


    #     self.load_model()


    def load_model(self, checkpoint):
        self.job2slot_env = PickDropPomoN2SEnv(self.env_params, self.model_params)
        self.job2slot_model = PickDropPomoN2SModel(self.model_params)
        self.job2slot_model.load_state_dict(checkpoint['model_state_dict'])
        # self.start_epoch = 1 + checkpoint['epoch']

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
        begin_time = datetime.now()
        log.info(f"Started dispatching at time: {begin_time}, with config: {self.config}")

        all_locs_list = []
        loc2job_orig_list = [ ]
        # loc2job_code_list = []

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

        order2job_dict = {}
        next_job_code_dict = {_slot.slot_code:'EOF' for _slot in  nearby_slots}
        
        for si, _slot in enumerate(nearby_slots): 
            prev_code = _slot.slot_code
            for j,job in  enumerate(_slot.assigned_jobs):
                next_job_code_dict[prev_code] = job.code
                prev_code = job.code

                order_code = job.code[:-2]
                job_type = job.code[-1]
                if order_code not in order2job_dict:
                    if job_type == 'p':
                        order2job_dict[order_code] = [job, None, _slot, si, (si*1000_000 + j) ]
                    else:
                        order2job_dict[order_code] = [job, job, _slot, si, (si*1000_000 + j) ]
                else:
                    if job_type == 'p':
                        log.error(f"corrupted_data_second_job_is_pickup:{job.code}")
                    else:
                        order2job_dict[order_code][1] = job
            if len(_slot.assigned_jobs) > 0:
                next_job_code_dict[_slot.assigned_jobs[-1].code] = 'EOF'

        worker_job_size = len(nearby_slots) + (len(order2job_dict)*2) + 2
        solution_list = [worker_job_size for _ in range(worker_job_size+1)]
        solution_pre_list = list(range(worker_job_size+1))
        job2loc_idx_dict["EOF"] = worker_job_size

        worker_loc_lengths = [1 for _ in  nearby_slots]
        loc2slot_idx_list = list(range(len(nearby_slots)))
        all_order_list = []
        for k,v in order2job_dict.items():
            if v[0] is None:
                v[0] = v[1]
            elif v[1] is None:
                log.error(f"corrupted_data_ONLY_PICK_JOB_LEFT:{k}")
                return []
            all_order_list.append(v)
        
        all_order_list.append(
            [env_jobs[0], env_jobs[1], None, -1001, -100001 ]
        )

        for pick_drop_seq in (0,1):
            for ordr in all_order_list:
                job = ordr[pick_drop_seq]
                job2loc_idx_dict[job.code] = len(all_locs_list)
                all_locs_list.append([job.geo_longitude, job.geo_latitude,])
                loc2job_orig_list.append(job)

                slot_i = ordr[3]
                loc2slot_idx_list.append(slot_i)
                if slot_i >= 0:
                    # else it is target_job, not assigned yet
                    worker_loc_lengths[slot_i]+=1



        for ordr in all_order_list:
            curr_loc_pair = (job2loc_idx_dict[ordr[0].code], job2loc_idx_dict[ordr[1].code])
            job_locs.append(curr_loc_pair)

        job2slot_current_loc_i = len(job_locs) - 1
        target_pick_job_loc_i = len(nearby_slots) + job2slot_current_loc_i
        solution_list[target_pick_job_loc_i] = target_pick_job_loc_i + len(job_locs)
        solution_pre_list[target_pick_job_loc_i + len(job_locs)] = target_pick_job_loc_i
        
        # job_locs.append((target_pick_job_loc_i, target_pick_job_loc_i + len(all_order_list) ))

        for wi,slot in enumerate(nearby_slots):
            next_i = job2loc_idx_dict[next_job_code_dict[slot.slot_code]]
            solution_list[wi] = next_i
            solution_pre_list[next_i] = job2loc_idx_dict[slot.slot_code]


        for pick_drop_seq in (0,1):
            for ordr in all_order_list[:-1]:
                jc = ordr[pick_drop_seq].code
                prev_i = job2loc_idx_dict[jc]
                next_i = job2loc_idx_dict[next_job_code_dict[jc]]

                solution_list[prev_i] = next_i
                solution_pre_list[next_i] = prev_i
        solution_pre_list[-1] = worker_job_size
        # available_worker_count = 0
        # for si,slot in enumerate(nearby_slots):
        #     if len(slot.assigned_jobs) >= nbr_jobs_per_slot:
        #         log.warning(f"len(slot.assigned_jobs) >= nbr_jobs_per_slot. This should have been filtered out at earlier stage.")
        #         continue
        #     available_worker_count += 1
        #     slot_prev_i = si
        #     tracked_order_codes = set()
        #     order_pick_loc_idx = {}

        #     for ji,job in enumerate(slot.assigned_jobs):
        #         order_code = job.code[:-2]
        #         job_type = job.code[-1]
        #         if order2job_dict[order_code][0].code == order2job_dict[order_code][1].code:
        #             if order_code in tracked_order_codes:
        #                 log.error(f"wrong_data_tracked")
        #                 continue
        #             solution_list[slot_prev_i] = slot_curr_i
    
        #             loc2job_code_list.append(job.code)
        #             order_pick_loc_idx[order_code] = len(all_locs_list)
        #             job2loc_idx_dict[job.code] = len(all_locs_list)
        #             loc2slot_idx_list.append(si)
        #             loc2job_orig_list.append(job)
        #             all_locs_list.append([job.geo_longitude, job.geo_latitude,])
        #             slot_prev_i = slot_curr_i
        #             slot_curr_i += 1


        #         tracked_order_codes.add(order_code)

        #         solution_list[slot_prev_i] = slot_curr_i
        #         loc2job_code_list.append(job.code)
        #         assert slot_curr_i == len(all_locs_list) 
        #         job2loc_idx_dict[job.code] = len(all_locs_list)
        #         loc2slot_idx_list.append(si)
        #         loc2job_orig_list.append(job)
        #         if job_type == 'd':
        #             if order_code not in order_pick_loc_idx:
        #                 log.error(f"wrong_data_tracked_no_pickup")
        #                 continue
        #             curr_loc_pair = (order_pick_loc_idx[order_code], job2loc_idx_dict[job.code])
        #             job_locs.append(curr_loc_pair)
        #         else:
        #             order_pick_loc_idx[order_code] = len(all_locs_list)

        #         all_locs_list.append([job.geo_longitude, job.geo_latitude,])
                
        #         slot_prev_i = slot_curr_i
        #         slot_curr_i += 1
            
            # solution_list[slot_prev_i] = worker_job_size
            
            # worker_loc_lengths[si] += len(tracked_order_codes)*2

        # if available_worker_count < 1:
        #     log.warning(f"all_slots_are_full, lengths are: {worker_loc_lengths}")
        #     return []

        # target_pick_job_loc_i = len(all_locs_list)
        # solution_list[target_pick_job_loc_i] = target_pick_job_loc_i + 1
        # for cjob in env_jobs:
        #     # loc2job_code_list.append(cjob.code)
        #     loc2job_orig_list.append(cjob)
        #     loc2slot_idx_list.append(-1001)
        #     job2loc_idx_dict[cjob.code] = len(all_locs_list)
        #     all_locs_list.append([
        #         cjob.geo_longitude, cjob.geo_latitude, 
        #     ])

        # job2slot_current_loc_i = len(job_locs)
        # job_locs.append((target_pick_job_loc_i, target_pick_job_loc_i + 1))


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
            job_loc_idx = torch.tensor(job_locs)[None,None,:,:],
        )
        step_state, reward, done = self.job2slot_env.set_state_to_length(
            worker_loc_length = torch.tensor(worker_loc_lengths)[None,:],
            solution = torch.tensor(solution_list)[None,:],
            solution_pre_idx = torch.tensor(solution_pre_list)[None,:],
            solution_worker_idx = torch.tensor(loc2slot_idx_list)[None,:],
            job2slot_current_job_i = job2slot_current_loc_i,
            max_job_in_worker_size = max(worker_loc_lengths) + 2,
            enabled_slot_map = None # select from all
        )
 
        self.job2slot_model.pre_forward(step_state.reset_state)
        # try:
        selected, prob, _probs = self.job2slot_model(step_state)

        selected_pick_job_i = selected[0,3].item()
        selected_slot_i = loc2slot_idx_list[selected_pick_job_i]
        flat_length_scalar = worker_loc_lengths[selected_slot_i] 
        # _selected_slot = nearby_slots[selected_slot_i]
        if flat_length_scalar <= 1: 
            solution_list[selected_slot_i] = target_pick_job_loc_i
        elif  flat_length_scalar == 2: 
            tail_job_i = solution_list[selected_slot_i]
            solution_list[tail_job_i] = target_pick_job_loc_i
        else:
            nbr_swap_steps = 6
            if flat_length_scalar < 6:  
                nbr_swap_steps = 2
            elif flat_length_scalar < 12:  
                nbr_swap_steps = 4
            
            slot_map = [0 for _ in range(len(nearby_slots))]
            slot_map[selected_slot_i] = 1 # Do swap only on the selected slot
            step_state.enabled_slot_map = torch.tensor(slot_map)[None,:].bool()
            # AI Does the rest
            for _ in range(nbr_swap_steps):
                step_state, reward, done = self.job2slot_env.step(selected)
                selected, prob, _probs = self.job2slot_model(step_state)
                if done:
                    break
            
            orig_solution_list = solution_list

            best_solution = step_state.prev_best_solution[0,:,1]
            solution_list = best_solution.tolist()

        
        # new_assigned_jobs = self.calc_travel_time(
        #     slot = _selected_slot, 
        #     job_codes = [j.code for j in [_selected_slot.assigned_jobs + env_jobs]],
        #     dist_mat = dist_mat,
        #     fix_first_flag = False)
        # Now I collect and return result
        
        result_rec_list = []
        selected_slot = nearby_slots[selected_slot_i]
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
        rec_start_minutes = max(selected_slot.start_minutes, env_horizon)
        prev_idx = selected_slot_i
        new_travel = 0
        # _curr_loc_i = selected_slot_i
        tmp_saved_job_codes = set()
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
                    tolerance_end_minutes = _new_start + 1440, # TODO
                    flex_form_data={},
            ) )
            tmp_saved_job_codes.add(opti_job.code)
            if job2slot_current_loc_i == curr_idx:
                rec_start_minutes = _new_start

            prev_idx = curr_idx

        travel_minutes_diff = new_travel - orig_travel
        
        solution = {
            "score": round(travel_minutes_diff, 2),
            "slots": [selected_slot],
            "start_minutes":rec_start_minutes,
            "dist":  round(travel_minutes_diff, 2),
            "algo": "rt1",
        }
        
        result_rec_list.append(solution)

        return result_rec_list # sorted(result_rec_list, key=lambda a: a["score"], reverse=False)