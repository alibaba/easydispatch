import threading
from collections import OrderedDict
import numpy as np
import os
import math
import copy
from dispatch.location_group.service import get_worker_code_by_location_group_code
from dispatch.plugins.bases.realtime_agent import KandboxAgentPlugin, KandboxRLAgentPlugin

import torch

from datetime import datetime

import logging
from dispatch.config import ALLOWED_MAXIMUM_MINUTES, APPOINTMENT_DEBUG_LIST,   MAX_NBR_JOB_IN_WORKER
from dispatch.plugins.kandbox_planner.env.configurable_dispatch_env import ConfigurableDispatchEnv
from dispatch.plugins.kandbox_planner.env.env_enums import (
    ActionType,
    OptimizerSolutionStatus,
    JobPlanningStatus,
    PlannerType,
)
from dispatch.plugins.kandbox_planner.env.env_models import EnvAction, JobsInSlotsDispatchResult, NoAvailableSlots, RecommendedAction, WorkingTimeSlot
from dispatch.contrib.training.slotattention.train_job2slot.training_util import (
    load_model, select_action
)
from dispatch.plugins.kandbox_planner.env.env_enums import (
    EnvRunModeType,
    JobPlanningStatus,
    ActionCommandType,
)
from dispatch.contrib.training.pomo.job2slot.Job2SlotEnv import Job2SlotEnv 
from dispatch.contrib.training.pomo.job2slot.Job2SlotModel import Job2SlotModel 

from dispatch.contrib.training.pomo.pickdrop_2in1.pickdrop_2in1_env import PickDrop2in1Env
from dispatch.contrib.training.pomo.pickdrop_2in1.pickdrop_2in1_model import PickDrop2in1Model

from dispatch.contrib.training.pomo.pick_drop_tsp_with_start.pick_drop_tsp_with_start_env import PickDropWithStartTSPEnv
from dispatch.contrib.training.pomo.pick_drop_tsp_with_start.pick_drop_tsp_with_start_model import PickDropWithStartTSPModel


import pymap3d

log = logging.getLogger("pomo_online_realtime_agent")

from dispatch.contrib.training.pomo.pomo_params import ( 
    env_params, model_params, optimizer_params, trainer_params, logger_params, 
    DEBUG_MODE, USE_CUDA)


from dispatch.contrib.training.slotattention.train_job2slot.training_util import (
    device, 
    get_env_config
)
from dispatch.contrib.training.slotattention.train_job2slot.train_args_parser import parser

from dispatch.config import ROOT_DIR
from dispatch.utils.path_config import ROOT_PATH , DISPATCH_PATH 
import traceback


from dispatch.config import ROOT_DIR
class POMOOnlineRTAgent(KandboxRLAgentPlugin):
    """ For PickDrop2in1Env
        pickdrop_pomo_2in1
    """
    title = "Kandbox Plugin - Agent - by POMO transformer"
    slug = "pomo_online_realtime_agent"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "Realtime Agent - by pytorch POMO direct inference."
    version = "0.1.0"
    default_config = {
        "direct_dispatch_min_meters": 2_000,
        "nbr_of_actions": 4,
        "n_epochs": 1000,
        "nbr_of_days_planning_window": 1,
        "working_dir": "/tmp",
        "load_model": True,
        "coordinate": "wgs84_minmax", # wgs84_minmax, enu_normal
        "generate_worker_when_needed":0,
        "job2slot_model_single_path":f"{ROOT_PATH}/online_models/us_la_20230604_135643_job2slot_checkpoint_1360_score6026.pt",
        "job2slot_model_path":f"{ROOT_PATH}/online_models/dubai_pickdrop_job2slot_2in1_latest.pt",
        "tsp_with_start_model_path":f"{ROOT_PATH}/online_models/dubai_pickdrop_tsp_with_start_latest.pt",
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "job2slot_model_path": {
                "type": "string",
                "default": "/tmp",
                "title": "job2slot_model_path",
            },
            "tsp_with_start_model_path": {
                "type": "string",
                "default": "/tmp",
                "title": "tsp_with_start_model_path",
            },
            "coordinate": {
                "type": "string",
                "default": "wgs84_minmax",
                "title": "coordinate normalization method",
                "description": "Coordinate normalization method",
                "enum": ["wgs84_minmax", "enu_normal"],
            },
        
        },
    }
    planner_type = PlannerType.PICKDROP

    def __init__(self, config=None):
        self.config = self.default_config.copy()
        if config is not None:
            self.config.update(config)
        # self.trained_model = trained_model
        self.create_datetime = datetime.now()

        # pdb.set_trace()

        self.decode_type = "greedy"
        ###
        local_env_params = copy.deepcopy(env_params)
        local_env_params["pomo_size"] = 1
        local_env_params["solve_tsp_in_each_step"] = True
        local_env_params["serving_only_n_no_reward"] = True
        model_params['eval_type'] == 'argmax'


        self.job2slot_env = Job2SlotEnv(local_env_params, model_params)
        self.job2slot_model = Job2SlotModel(model_params)


        self.pomo_env = PickDrop2in1Env(local_env_params, model_params)
        self.pomo_model = PickDrop2in1Model(model_params)

        self.tsp_with_start_env = PickDropWithStartTSPEnv(local_env_params, model_params)
        self.tsp_with_start_model = PickDropWithStartTSPModel(model_params)

        self.pomo_model.training = False
        self.tsp_with_start_model.training = False
        self.batch_size = 1
        self.pomo_size = 1
        self.worker_size = 1
        self.max_job_in_worker_size = local_env_params['max_job_in_worker_size']


        if self.config["load_model"]:
            self.load_model()
        else:
            log.info(f"POMOOnlineRTAgent is initialized randomly. ")
        # model_params = {model_params}, local_env_params = {local_env_params}
        log.info(f"pomo_online_realtime_agent __init__done__ ... thread: {threading.current_thread().ident}")

    def __del__(self):
        print(f'Destructor_called pomo_online_realtime_agent, {self} is deleted, thread: {threading.current_thread().ident}')
        del self.tsp_with_start_model
        del self.pomo_model

    def load_model(self,):  # , allow_empty = None
        # TODO, env_config
        # self.config["job2slot_model_path"] = f"{ROOT_PATH}/online_models/dubai_pickdrop_job2slot_2in1_latest.pt"
        # self.config["tsp_with_start_model_path"] = f"{ROOT_PATH}/online_models/dubai_pickdrop_tsp_with_start_latest.pt"

        job2slot_model_single_path = self.config["job2slot_model_single_path"].replace("/usr/src/dispatch",ROOT_DIR)
        checkpoint = torch.load(job2slot_model_single_path, map_location=device)
        self.job2slot_model.load_state_dict(checkpoint['model_state_dict'])
        log.info(f'Loaded single job2slot model from {job2slot_model_single_path}'  )

        checkpoint_fullname = self.config["job2slot_model_path"].replace("/usr/src/dispatch",ROOT_DIR)
        # checkpoint_fullname = "/Users/qiyang/git/ed/easydispatch//online_models/dubai_20230208_013658_pickdrop_job2slot_tsp_2in1_checkpoint_1390_score352.pt"
        checkpoint = torch.load(checkpoint_fullname, map_location=device)
        self.pomo_model.load_state_dict(checkpoint['model_state_dict'])
        self.start_epoch = 1 + checkpoint['epoch']

        log.info(f'Loaded pick-drop job2slot model from {checkpoint_fullname}'  )

        tsp_checkpoint = torch.load(
            self.config["tsp_with_start_model_path"].replace("/usr/src/dispatch",ROOT_DIR) , 
            map_location=device)
        self.tsp_with_start_model.load_state_dict(
            tsp_checkpoint['model_state_dict']
        )
        self.pomo_model.training = False
        self.tsp_with_start_model.training = False
       
        log.info(f'Loaded tsp with start model from {self.config["tsp_with_start_model_path"]}'  )
        return 0

    def train_model(self):
        log.error("not implemented: train_model")

    def _compare_agaist_greedy(self, slot, todo_job_list, env, other_solution_job_list: list): 

        greedy_solution = self._dispatch_pickdrop_greedy(
            slot, todo_job_list, env,)
        if greedy_solution is None:
            log.info(f"greedy_solution_failed, returning solution")
            return other_solution_job_list

        greedy_minutes = env.get_travel_minutes_loc_list(
            loc_list = [
                [j.geo_longitude, j.geo_latitude] for j in greedy_solution
            ])
        
        curr_minutes =  env.get_travel_minutes_loc_list(
            loc_list = [
                [j.geo_longitude, j.geo_latitude] for j in other_solution_job_list
            ])
        
        if sum(curr_minutes) < sum(greedy_minutes) * 1.1:
            log.info(f"curr_minutes {curr_minutes} is better than greedy_solution: {greedy_minutes}, returning solution")
            return other_solution_job_list, sum(curr_minutes)
        else:
            log.info(f"curr_minutes {curr_minutes} is worse than greedy_solution: {greedy_minutes}, returning greedy_solution")
            return greedy_solution, sum(greedy_minutes)



    def _run_dispatch(self, env: ConfigurableDispatchEnv, todo_action: EnvAction): 
        # self.loc2worker_idx = []
        # self.loc2job_idx = []
        reason_info = {}

        todo_job_list = [
            env.env_encode_single_job_db(job)
            for job in todo_action.jobs
        ]
        # TODO, proper wrap
        # if todo_action.order.location_group_code is not None:
        #     lg_worker_code = get_worker_code_by_location_group_code(
        #         db_session=env.db_session,
        #         location_group_code=todo_action.order.location_group_code
        #         )
        #     if lg_worker_code is not None and lg_worker_code not in todo_action.worker_blacklist:
        #         target_slots = env.get_working_slot_list(worker_code=lg_worker_code, active_only=True)
        #         for slot in target_slots:
        #             if len(slot.assigned_jobs) < 2:
        #                 log.info(f"order {todo_action.order.code} is assigned to worker {lg_worker_code} by location group {todo_action.order.location_group_code}")
        #                 return slot, slot.assigned_jobs + todo_job_list

        #             elif len(slot.assigned_jobs) < env.get_config_max_nbr_jobs_allowed() - 1:
        #                 log.info(f"order {todo_action.order.code} is assigned to worker {lg_worker_code} by location group {todo_action.order.location_group_code}")
        #                 return slot, self._dispatch_pickdrop_tsp_with_start(slot, slot.assigned_jobs + todo_job_list, env)
        #             else:
        #                 log.info(f"order {todo_action.order.code} is tried to worker {lg_worker_code} by location group {todo_action.order.location_group_code} but failed by job length {len(slot.assigned_jobs)}")

        # todo_action.overwrite_max_orders_limit = True
        pick_start_location = [todo_job_list[0].geo_longitude, todo_job_list[0].geo_latitude,]
        if len(todo_job_list) > 1:
            drop_off_location =  [todo_job_list[1].geo_longitude, todo_job_list[1].geo_latitude,]
        else:
            drop_off_location = None
        if todo_action.order:
            _order_code = todo_action.order.code
            _area_code = todo_action.order.flex_form_data.get("area_code","A")
            # prev_failed_list = env.get_job_failed_slot(_order_code)
        else:
            _order_code = todo_job_list[0].code
            _area_code = "A"
        prev_failed_list = env.get_job_failed_slot(_order_code)

        log.info(f"_run_dispatch started for order {_order_code},  pick_start_location = {pick_start_location}, prev_failed_list = {prev_failed_list}...")
        nearby_slots, dist_list ,reason_info = env.get_nearby_slots(
            loc=pick_start_location,
            worker_blacklist = todo_action.worker_blacklist + prev_failed_list,
            worker_whitelist = todo_action.worker_whitelist,
            overwrite_max_orders_limit = todo_action.overwrite_max_orders_limit,
            area_code = _area_code,
            return_on_first_priority_worker = True,
            drop_off_location = drop_off_location,
            order_info = _order_code,
        )
        
        if len(nearby_slots) == 0:
            raise NoAvailableSlots
        if len(nearby_slots) == 1:
            slot = nearby_slots[0]
            if not todo_action.overwrite_max_orders_limit and (len(slot.assigned_jobs) > MAX_NBR_JOB_IN_WORKER - 1) :
                raise NoAvailableSlots

            if len(slot.assigned_jobs) < 2:
                return slot, slot.assigned_jobs + todo_job_list, reason_info

            if len(todo_job_list) > 1:
                tsp_solution = self._dispatch_pickdrop_tsp_with_start(
                    slot, slot.assigned_jobs + todo_job_list,
                    env)
                
                final_job_list,_ = self._compare_agaist_greedy(
                    slot, slot.assigned_jobs + todo_job_list,env,
                    other_solution_job_list = tsp_solution
                )
                return slot, final_job_list ,reason_info
            else:
                return self._dispatch_tsp_router(
                    env=env,
                    slot=slot,
                    todo_job_list=slot.assigned_jobs + todo_job_list)  ,reason_info              

        for si, slot in enumerate(nearby_slots):
            if dist_list[si] < self.config["direct_dispatch_min_meters"]:
                if (len(slot.assigned_jobs) < 1):
                    log.info(f"{si}-th closest slot {slot.slot_code} to order {todo_action.order.code} is empty, meters = {dist_list[si]}, dispatched straight away.")
                    return slot, todo_job_list ,reason_info
            else:
                break

        # else:
        # Multiple slot candidates. Use model to select
        if len(todo_job_list) > 1:
            
            
            _selected_slot, _selected_slot_assigned_jobs_todo_job_list = self._dispatch_pickdrop_job2slot_2in1(
                env, todo_job_list, nearby_slots,
                overwrite_max_orders_limit = todo_action.overwrite_max_orders_limit,
                )
            return _selected_slot, _selected_slot_assigned_jobs_todo_job_list ,reason_info
        else:
            _selected_slot, _selected_slot_assigned_jobs_todo_job_list  = self._dispatch_job2slot_plus_tsp(
                env, todo_job_list, nearby_slots,
                overwrite_max_orders_limit = todo_action.overwrite_max_orders_limit,
                )
            return _selected_slot, _selected_slot_assigned_jobs_todo_job_list, reason_info
        

    def _dispatch_pickdrop_tsp_with_start(self, slot, todo_job_list, env): 
        # return todo_job_list
        all_locs_list = [[slot.start_longitude, slot.start_latitude, ALLOWED_MAXIMUM_MINUTES, 0]]
        loc2job_orig_list = [todo_job_list[0] ]
        loc2job_code_list = [todo_job_list[0].code]

        _slot_orders = OrderedDict()
        for job in todo_job_list[1:]:
            order_code = job.code[:-2]
            job_type = job.code[-1]
            if order_code in _slot_orders:
                if job_type == 'p':
                    _slot_orders[order_code][0] = job
                else:
                    _slot_orders[order_code][1] = job
            else:
                _slot_orders[order_code] = [job, job]
        

        _loc_idx = 1
        horizon_minutes = env.get_env_planning_horizon_start_minutes()
        for job_pair in _slot_orders.values():
            loc2job_code_list.append(job_pair[0].code)
            loc2job_code_list.append(job_pair[1].code)

            loc2job_orig_list.append(job_pair[0])
            loc2job_orig_list.append(job_pair[1])

            all_locs_list.append([job_pair[0].geo_longitude, job_pair[0].geo_latitude, job_pair[0].tolerance_end_minutes - horizon_minutes, 0])
            all_locs_list.append([job_pair[1].geo_longitude, job_pair[1].geo_latitude, job_pair[1].tolerance_end_minutes - horizon_minutes, 1])
            _loc_idx += 2

 

        loc_xy = torch.tensor(all_locs_list)

        loc_length = len(_slot_orders) * 2 + 1
        flat_length = torch.tensor([loc_length])
        job_loc_idx = torch.tensor([i for i in range(loc_length)] ).view(
            self.batch_size, 1, loc_length)

        # Normalize locations
        loc_xy=self.normalize_addr(loc_xy, env)
        loc_xy = loc_xy[None,:,:].float()

        self.loc2job_code_list = loc2job_code_list

        self.job_loc_size = len(self.loc2job_code_list)
        
        tsp_next_job_index = self.pomo_env.next_job_indexer[flat_length,:].view(
                self.batch_size, 1, self.max_job_in_worker_size)
        tsp_next_job_mask = self.pomo_env.pad_masker[flat_length,:].view(
            self.batch_size, 1, self.max_job_in_worker_size+1)

        self.tsp_with_start_env.problem_size = loc_length
        self.tsp_with_start_env.load_jobs(
            loc_xy = loc_xy, 
            dist_matrix= None,
            worker_loc_idx = None,
            job_loc_idx = job_loc_idx,
            next_job_idx = tsp_next_job_index,
            next_job_mask = tsp_next_job_mask,
        )
        step_state, reward, done = self.tsp_with_start_env.reset()

        self.tsp_with_start_model.pre_forward(step_state.reset_state)
        while not done:
            selected, prob, _probs = self.tsp_with_start_model(step_state)
            # shape: (batch, pomo)
            step_state, reward, done = self.tsp_with_start_env.step(selected)

        # 然后根据worker_selected_loc_length 和选择的job 生成TSP 的env。
        

        job_loc_list = self.tsp_with_start_env.selected_node_list.squeeze().tolist()
        final_job_list = [todo_job_list[0]]
        visited_final_job_code_set = set([todo_job_list[0].code])
        for ji in range(1, loc_length):
            job = loc2job_orig_list[job_loc_list[ji]]
            if job.code not in visited_final_job_code_set:
                visited_final_job_code_set.add(job.code)
                final_job_list.append(job)
        log.info(f"tsp_with_start decided: worker: {slot.worker_code}, jobs: {[j.code for j in final_job_list]}")        
        return final_job_list


    def _dispatch_tsp_router(
            self, slot, todo_job_list, env,  ): 
        if len(todo_job_list) < 2:
            assert False, "not enough to dispatch!"
            start_loc = [slot.start_longitude, slot.start_latitude, ]
            current_start = slot.start_minutes
        # else:
        start_loc = [todo_job_list[0].geo_longitude, todo_job_list[0].geo_latitude, ]
        current_start = todo_job_list[0].scheduled_start_minutes + todo_job_list[0].scheduled_duration_minutes + 1
        assigned_job_locs = [start_loc] + [
            (j.geo_longitude, j.geo_latitude) for j in todo_job_list[1:]] 
        assigned_jobs = [None] + todo_job_list[1:] 

        new_seq, start_distance = env.get_travel_router().solve_tsp(loc_list = assigned_job_locs )

        # Then generate jobs by this seq
        _assigned_new = todo_job_list[0:1]
        for j_idx, ji in enumerate(new_seq):
            if j_idx < 1:
                continue
            job = assigned_jobs[ji]
            current_start += start_distance[j_idx] + job.scheduled_duration_minutes
            job.prev_travel = start_distance[j_idx]
            job.scheduled_start_minutes=current_start + start_distance[j_idx]
            _assigned_new.append(job)
        slot.assigned_jobs = _assigned_new
        return slot, slot.assigned_jobs

    def _dispatch_pickdrop_greedy(
            self, slot, todo_job_list, env,  ): 

        # assigned_jobs = slot.assigned_jobs + todo_job_list 
        loc_length = len(todo_job_list)
        
        loc_list = []
        next_loc_list = [-1 for _ in range(loc_length )]
        curr_loc_mask = [-1] + [0 for _ in range(loc_length - 1)]
        job_pre_dict = {}
        for ji, job in enumerate(todo_job_list):
            loc_list.append([job.geo_longitude, job.geo_latitude])
            job_type = job.code[-1]
            order_code = job.code[:-2]
            if job_type == 'p':
                job_pre_dict[order_code] = ji

        for ji, job in enumerate(todo_job_list):
            job_type = job.code[-1]
            order_code = job.code[:-2]
            if job_type == 'd':
                if order_code in job_pre_dict:
                    next_loc_list[job_pre_dict[order_code]] = ji
                    curr_loc_mask[ji] = 1
        # Finally, set first node visited.
        curr_loc_mask[next_loc_list[0]] = 0
            

        solution_idx = env.solve_greedy_pickdrop_locations( 
            loc_list = loc_list,
            next_loc_list = next_loc_list,
            curr_loc_mask = curr_loc_mask,
            )

        try:
            final_job_list = [todo_job_list[0]]
            # log.info(f"greedy_solved: todo_job_list={todo_job_list}, solution_idx={solution_idx}")  
            for ji in range(1, loc_length):
                job = todo_job_list[solution_idx[ji]] 
                final_job_list.append(job)
            log.info(f"greedy decided: worker: {slot.worker_code}, final_job_list: {[j.code for j in final_job_list]}, solution_idx={solution_idx}")        
            return final_job_list
        except Exception as e:
            
            traceback.print_exc()
            log.error(f"_dispatch_pickdrop_greedy failed for slot {slot}. 500 error." )
            log.info(f"greedy_solver_failed: loc_list={loc_list}, next_loc_list={next_loc_list}, curr_loc_mask={curr_loc_mask}, slot = {slot}, todo_job_list={todo_job_list}")  
            return None


    def _dispatch_pickdrop_job2slot_2in1(
            self, env, todo_job_list, nearby_slots,
            overwrite_max_orders_limit,): 
        all_locs_list = []
        loc2job_orig_list = [ ]
        loc2job_code_list = []

        worker_locs = []
        job_locs = []
        horizon_minutes = env.get_env_planning_horizon_start_minutes()

        pick_job = todo_job_list[0]
        drop_job = todo_job_list[1]

        for si,slot in enumerate(nearby_slots):
            # self.loc2worker_idx.append(slot.slot_code)
            loc2job_orig_list.append(None)
            all_locs_list.append([slot.start_longitude, slot.start_latitude, ALLOWED_MAXIMUM_MINUTES, 0] )
            worker_locs.append(si)
        worker_loc_idx = torch.tensor(worker_locs)[None,None,:]
        self.batch_size, self.pomo_size, self.worker_size = worker_loc_idx.size()

        loc2job_code_list.append(pick_job.code)
        loc2job_code_list.append(drop_job.code)
        new_job_loc_idx_pair = [len(all_locs_list), len(all_locs_list)+1]
        # todo_jobinslot_pair = todo_action.jobs
        job_locs.append(new_job_loc_idx_pair)
        loc2job_orig_list.append(pick_job)
        loc2job_orig_list.append(drop_job)
        all_locs_list.append([
            pick_job.geo_longitude, pick_job.geo_latitude, 
            # pick_job.scheduled_start_minutes + 
            pick_job.tolerance_end_minutes - horizon_minutes, 0
        ])
        all_locs_list.append([
            drop_job.geo_longitude, drop_job.geo_latitude, 
            # drop_job.scheduled_start_minutes + 
            drop_job.tolerance_end_minutes - horizon_minutes, 1
        ])
        
        worker_loc_lengths = [1 for _ in range(len(nearby_slots))]
        worker_selected_loc_list = [
            [wi for _ in range(env_params['max_job_in_worker_size'] + 8)] 
            for wi in range(len(nearby_slots))
        ]

        # tsp_pad_mask_list = [
        #     [-pi*1e20 for pi in range(env_params['max_job_in_worker_size']+1)] 
        #     for _ in range(len(nearby_slots))
        # ]
        # tsp_next_job_index_list = [
        #     [env_params['max_job_in_worker_size'] for _ in range(env_params['max_job_in_worker_size'])] 
        #     for wi in range(len(nearby_slots))
        # ]


        available_worker_count = 0
        for si,slot in enumerate(nearby_slots):
            if len(slot.assigned_jobs) < 1:
                available_worker_count += 1
                continue

            # 2023-01-01 00:19:58
            # 需要记录worker_selected_loc_length
            # 如果只剩下一个drop 任务，那么复制成两个drop做一组。
            _slot_orders = OrderedDict()
            assigned_jobs = slot.assigned_jobs # env.decode_working_slot_assigned_jobs()
            for job in assigned_jobs:
                order_code = job.code[:-2]
                job_type = job.code[-1]
                if order_code in _slot_orders:
                    if job_type == 'p':
                        _slot_orders[order_code][0] = job
                    else:
                        _slot_orders[order_code][1] = job
                else:
                    _slot_orders[order_code] = [job, job]
            
            worker_loc_lengths[si] = min(len(_slot_orders) * 2 + 1, MAX_NBR_JOB_IN_WORKER - 1)
            if overwrite_max_orders_limit or (worker_loc_lengths[si] < MAX_NBR_JOB_IN_WORKER - 1) :
                available_worker_count += 1

            _loc_idx = 1
            for job_pair in _slot_orders.values():
                loc2job_code_list.append(job_pair[0].code)
                loc2job_code_list.append(job_pair[1].code)

                _temp_new_loc_idx_pair = [len(all_locs_list),len(all_locs_list)+1]
                worker_selected_loc_list[si][_loc_idx:_loc_idx+2] = _temp_new_loc_idx_pair
                loc2job_orig_list.append(job_pair[0])
                loc2job_orig_list.append(job_pair[1])
                all_locs_list.append([job_pair[0].geo_longitude, job_pair[0].geo_latitude, job_pair[0].tolerance_end_minutes - horizon_minutes, 0])
                all_locs_list.append([job_pair[1].geo_longitude, job_pair[1].geo_latitude, job_pair[1].tolerance_end_minutes - horizon_minutes, 1])
                _loc_idx += 2
                if _loc_idx > MAX_NBR_JOB_IN_WORKER - 1:
                    break


            # # 2023-01-02 17:31:28, using job by itself. No need of order.
            # _drop_locs = {}
            # _pick_locs = {}
            # _loc_idx = 1
            # for job in slot.assigned_jobs:
            #     # len(all_locs_list) is the location index of this job's loc
            #     curr_loc_i = len(all_locs_list)
            #     worker_selected_loc_list[si][_loc_idx] = curr_loc_i
            #     # worker_selected_job_orig_list[si][_loc_idx] = job
            #     # This is a fake data. Only job_locs[0] matters, with current job to disptach.7
            #     job_locs.append([curr_loc_i,curr_loc_i+1]) 
            #     if job.code[-1] == 'd':
            #         # order_code = job.code[:-2]
            #         _drop_locs[job.code[:-2]] = _loc_idx
            #     else:
            #         tsp_pad_mask_list[si][_loc_idx] = 0
            #         _pick_locs[job.code] = _loc_idx
            #     # Though this is a drop off job, but it is already enabled.
            #     # TODO, seperate this pick_drop_ind, 4th dimension out of transformer encoding.
            #     loc2job_orig_list.append(job)
            #     all_locs_list.append([job.geo_longitude, job.geo_latitude, job.tolerance_end_minutes - horizon_minutes, 0])
            #     _loc_idx += 1

            # for job in slot.assigned_jobs:
            #     if job.code[-1] == 'p':
            #         # order_code = job.code[:-2]
            #         if job.code[:-2] in _drop_locs:
            #             tsp_next_job_index_list[si][_pick_locs[job.code]] = _drop_locs[job.code[:-2]] 
            
            # in all cases, 2nd job should be ready to be planned, since 1st if already in execution.
            # tsp_pad_mask_list[si][1] = 0
            # worker_loc_lengths[si] += len(slot.assigned_jobs)
            # Here there must be jobs in slot, first location is a job, not slot start location.
            # if len(slot.assigned_jobs) > 0:
            #     worker_loc_lengths[si] = worker_loc_lengths[si] - 1
        if available_worker_count < 1:
            log.warning(f"all slots are full, lengths are: {worker_loc_lengths}")
            raise NoAvailableSlots
        job_loc_idx = torch.tensor(job_locs )[None,None,:,:]
        worker_loc_length_t = torch.tensor(worker_loc_lengths )[None,None,:]
        try:
            worker_selected_loc_t = torch.tensor(worker_selected_loc_list )[None,None,:,:] 
        except ValueError as e:
            print(str(e))
            assert False
        loc_xy = torch.tensor(all_locs_list)

        # Normalize locations
        loc_xy=self.normalize_addr(loc_xy, env)
        loc_xy = loc_xy[None,:,:].float()
        # worker_locs = torch.tensor([w.curr_slot.start_location[0:2] for w in env.workers_dict.values()])
        # job_locs_1 = [env.jobs_dict[jc].location[0:2] for jc in env.jobs_dict.values()]
        # job_locs_2 = env.job_log_df[["end_x","end_y"]].values

        self.loc2job_code_list = loc2job_code_list


        self.job_loc_size = len(self.loc2job_code_list)
        self.worker_loc_size = len(worker_locs)

        dist_matrix = None
        # This matrix tracks relatinship: Pick-->Drop for each paired job
        next_job_idx = None

        # This matrix tracks mask: Job-->(1 as valid for select or 0, not -inf) for each paired job
        # one extra job position for void masking setting .
        next_job_mask = None

        self.pomo_env.load_jobs(
            loc_xy = loc_xy, 
            dist_matrix= dist_matrix,
            worker_loc_idx = worker_loc_idx,
            job_loc_idx = job_loc_idx,
            next_job_idx = next_job_idx,
            next_job_mask = next_job_mask,
        )
        step_state, reward, done = self.pomo_env.set_state_to_length(
            worker_loc_length = worker_loc_length_t,
            worker_selected_loc = worker_selected_loc_t,
            enable_ninf_mask = not overwrite_max_orders_limit)

        self.pomo_model.pre_forward(step_state.reset_state)
        # try:
        selected, prob, _probs = self.pomo_model(step_state)
        # except Exception as e:
        #     print(str(e))
        #     print("Error self.pomo_model(step_state)")
        selected_scalar = selected.item()
        flat_length = self.pomo_env.step_state.worker_selected_loc_length[0,0,selected_scalar]
        flat_length_scalar = flat_length.item()
        _selected_slot = nearby_slots[selected_scalar]
        if flat_length_scalar < 2: 
            # 1 must be only start loc, and 1 drop off job. First job can not be changed.
            # 2 could only be 1 pick, 1 drop
            return _selected_slot, _selected_slot.assigned_jobs + todo_job_list
            # print("flat_length_scalar:",flat_length_scalar)

        elif flat_length_scalar > 9 and flat_length_scalar <= self.pomo_env.max_job_in_worker_size - 2: # self.pomo_env.max_job_in_worker_size - 2
            # 如果超过了最多任务数，用tsp算法，而不是继续用job2slot的算法计算tsp。
            return _selected_slot, self._dispatch_pickdrop_tsp_with_start(_selected_slot, _selected_slot.assigned_jobs + todo_job_list, env)

        elif flat_length_scalar > self.pomo_env.max_job_in_worker_size - 2:
            log.error(f"# of job {flat_length_scalar} overflow max {self.pomo_env.max_job_in_worker_size - 2}, no optimization")
            return _selected_slot, _selected_slot.assigned_jobs + todo_job_list
        
        step_state, reward, done = self.pomo_env.step(selected)
        self.pomo_model.pre_tsp_forward(step_state)
        step_state.tsp_pre_forward_done = 1
        # Fix the first job in TSP
        selected_position_1 = torch.ones(self.batch_size, self.worker_size).long()
        step_state, reward, done = self.pomo_env.step(selected_position_1)
        # AI Does the rest
        while not done:
            selected, prob, _probs = self.pomo_model(step_state)
            # shape: (batch, pomo)
            step_state, reward, done = self.pomo_env.step(selected)

        # 然后根据worker_selected_loc_length 和选择的job 生成TSP 的env。
        

        job_loc_list = step_state.tsp_selected_loc_idx[0,selected_scalar]
        final_job_list = []
        visited_final_job_code_set = set()
        # ? Who changed flat_length_scalar? 2023-01-08 07:20:04
        flat_length_scalar = self.pomo_env.step_state.worker_selected_loc_length[0,0,selected_scalar].item()
        for ji in range(1, flat_length_scalar):
            job = loc2job_orig_list[job_loc_list[ji]]
            if job.code not in visited_final_job_code_set:
                visited_final_job_code_set.add(job.code)
                final_job_list.append(job)

            

        slot = nearby_slots[selected_scalar] 
        
        new_final_job_list, job2slot_kpi = self._compare_agaist_greedy(
            slot, slot.assigned_jobs + todo_job_list,env,
            other_solution_job_list = final_job_list
        )

        if selected_scalar != 0:
            if len(slot.assigned_jobs) < 2:
                job2slot_original_travel_minutes = [0]
            else:
                job2slot_original_travel_minutes = env.get_travel_minutes_loc_list(
                    loc_list = [
                        [j.geo_longitude, j.geo_latitude] for j in slot.assigned_jobs
                    ])
            if len(nearby_slots[0].assigned_jobs) < 2:
                closest_original_travel_minutes = [0]
            else:
                closest_original_travel_minutes = env.get_travel_minutes_loc_list(
                    loc_list = [
                        [j.geo_longitude, j.geo_latitude] for j in nearby_slots[0].assigned_jobs
                    ])

            closest_final_job_list, closest_kpi = self._compare_agaist_greedy(
                nearby_slots[0], nearby_slots[0].assigned_jobs + todo_job_list, env,
                other_solution_job_list = nearby_slots[0].assigned_jobs + todo_job_list
            )
            if closest_kpi - sum(closest_original_travel_minutes) < job2slot_kpi - sum(job2slot_original_travel_minutes):
                log.info(f"job2slot_greedy_first: worker: {nearby_slots[selected_scalar].worker_code}, after planning jobs: {[j.code for j in closest_final_job_list]}")       
                return nearby_slots[0], closest_final_job_list
            # else:
        
        log.info(f"job2slot decided: worker: {nearby_slots[selected_scalar].worker_code}, {selected_scalar}-th slots, jobs: {[j.code for j in final_job_list]}, after planning: {[j.code for j in new_final_job_list]}")    
        return slot, new_final_job_list 

    def _dispatch_job2slot_plus_tsp(
            self, env, todo_job_list, nearby_slots,
            overwrite_max_orders_limit,): 
        all_locs_list = []
        loc2job_orig_list = [ ]
        loc2job_code_list = []

        worker_locs = []
        job_locs = []
        horizon_minutes = env.get_env_planning_horizon_start_minutes()

        the_job = todo_job_list[0]

        for si,slot in enumerate(nearby_slots):
            # self.loc2worker_idx.append(slot.slot_code)
            loc2job_orig_list.append(None)
            all_locs_list.append([slot.start_longitude, slot.start_latitude, 
                                #   ALLOWED_MAXIMUM_MINUTES, 0
                                  ] )
            worker_locs.append(si)
        worker_loc_idx = torch.tensor(worker_locs)[None,None,:]
        self.batch_size, self.pomo_size, self.worker_size = worker_loc_idx.size()

        loc2job_code_list.append(the_job.code) 
        job_locs.append(len(all_locs_list))
        loc2job_orig_list.append(the_job)
        all_locs_list.append([
            the_job.geo_longitude, the_job.geo_latitude, 
            # the_job.tolerance_end_minutes - horizon_minutes, 1
        ])
        
        worker_loc_lengths = [1 for _ in range(len(nearby_slots))]
        worker_selected_loc_list = [
            [wi for _ in range(env_params['max_job_in_worker_size'] + 8)] 
            for wi in range(len(nearby_slots))
        ]

        available_worker_count = 0
        for si,slot in enumerate(nearby_slots):
            if len(slot.assigned_jobs) < 1:
                available_worker_count += 1
                continue

            # 2023-01-01 00:19:58
            # 需要记录worker_selected_loc_length
            # 如果只剩下一个drop 任务，那么复制成两个drop做一组。 
            assigned_jobs = slot.assigned_jobs # env.decode_working_slot_assigned_jobs()
            _loc_idx = 1
            for job in assigned_jobs: 
                loc2job_code_list.append(job.code) 
                worker_selected_loc_list[si][_loc_idx] = len(all_locs_list)
                loc2job_orig_list.append(job) 
                all_locs_list.append([job.geo_longitude, job.geo_latitude, 
                                    #   job_pair[0].tolerance_end_minutes - horizon_minutes, 0
                                      ])
                _loc_idx += 1
                if _loc_idx > MAX_NBR_JOB_IN_WORKER - 1:
                    break

            worker_loc_lengths[si] = min(len(assigned_jobs) + 1, MAX_NBR_JOB_IN_WORKER - 1)
            if overwrite_max_orders_limit or (worker_loc_lengths[si] < MAX_NBR_JOB_IN_WORKER - 1) :
                available_worker_count += 1


        if available_worker_count < 1:
            log.warning(f"all slots are full, lengths are: {worker_loc_lengths}")
            raise NoAvailableSlots
        job_loc_idx = torch.tensor(job_locs )[None,None,:]
        worker_loc_length_t = torch.tensor(worker_loc_lengths )[None,None,:]
        try:
            worker_selected_loc_t = torch.tensor(worker_selected_loc_list )[None,None,:,:] 
        except ValueError as e:
            print(str(e))
            assert False
        loc_xy = torch.tensor(all_locs_list)

        # Normalize locations
        loc_xy=self.normalize_addr(loc_xy, env)
        loc_xy = loc_xy[None,:,:].float()
        # worker_locs = torch.tensor([w.curr_slot.start_location[0:2] for w in env.workers_dict.values()])
        # job_locs_1 = [env.jobs_dict[jc].location[0:2] for jc in env.jobs_dict.values()]
        # job_locs_2 = env.job_log_df[["end_x","end_y"]].values

        self.loc2job_code_list = loc2job_code_list


        self.job_loc_size = len(self.loc2job_code_list)
        self.worker_loc_size = len(worker_locs)

        dist_matrix = None
        # This matrix tracks relatinship: Pick-->Drop for each paired job
        next_job_idx = None

        # This matrix tracks mask: Job-->(1 as valid for select or 0, not -inf) for each paired job
        # one extra job position for void masking setting .
        next_job_mask = None

        self.job2slot_env.load_jobs(
            loc_xy = loc_xy, 
            dist_matrix= dist_matrix,
            worker_loc_idx = worker_loc_idx,
            job_loc_idx = job_loc_idx,
            next_job_idx = next_job_idx,
            next_job_mask = next_job_mask,
        )
        step_state, reward, done = self.job2slot_env.set_state_to_length(
            worker_loc_length = worker_loc_length_t,
            worker_selected_loc = worker_selected_loc_t,
            enable_ninf_mask = not overwrite_max_orders_limit)

        self.job2slot_model.pre_forward(step_state.reset_state)
        # try:
        selected, prob, _probs = self.job2slot_model(step_state)
        # except Exception as e:
        #     print(str(e))
        #     print("Error self.job2slot_model(step_state)")
        selected_scalar = selected.item()
        flat_length = self.job2slot_env.step_state.worker_selected_loc_length[0,0,selected_scalar]
        flat_length_scalar = flat_length.item()
        _selected_slot = nearby_slots[selected_scalar]
        if flat_length_scalar < 3: 
            # 1 must be only start loc, and 1 drop off job. First job can not be changed.
            # 2 could only be 1 pick, 1 drop
            return _selected_slot, _selected_slot.assigned_jobs + todo_job_list
            # print("flat_length_scalar:",flat_length_scalar)

        # elif flat_length_scalar > 9 and flat_length_scalar <= self.job2slot_env.max_job_in_worker_size - 2: # self.pomo_env.max_job_in_worker_size - 2
        #     # 如果超过了最多任务数，用tsp算法，而不是继续用job2slot的算法计算tsp。
        #     return _selected_slot, self._dispatch_pickdrop_tsp_with_start(_selected_slot, _selected_slot.assigned_jobs + todo_job_list, env)

        # elif flat_length_scalar > self.job2slot_env.max_job_in_worker_size - 2:
        #     log.error(f"# of job {flat_length_scalar} overflow max {self.job2slot_env.max_job_in_worker_size - 2}, no optimization")
        #     return _selected_slot, _selected_slot.assigned_jobs + todo_job_list

        return self._dispatch_tsp_router(
            env=env,
            slot=_selected_slot,
            todo_job_list=_selected_slot.assigned_jobs + todo_job_list)

        step_state, reward, done = self.job2slot_env.step(selected)
        self.pomo_model.pre_tsp_forward(step_state)
        step_state.tsp_pre_forward_done = 1
        # Fix the first job in TSP
        selected_position_1 = torch.ones(self.batch_size, self.worker_size).long()
        step_state, reward, done = self.job2slot_env.step(selected_position_1)
        # AI Does the rest
        while not done:
            selected, prob, _probs = self.pomo_model(step_state)
            # shape: (batch, pomo)
            step_state, reward, done = self.job2slot_env.step(selected)

        # 然后根据worker_selected_loc_length 和选择的job 生成TSP 的env。
        

        job_loc_list = step_state.tsp_selected_loc_idx[0,selected_scalar]
        final_job_list = []
        visited_final_job_code_set = set()
        # ? Who changed flat_length_scalar? 2023-01-08 07:20:04
        flat_length_scalar = self.job2slot_env.step_state.worker_selected_loc_length[0,0,selected_scalar].item()
        for ji in range(1, flat_length_scalar):
            job = loc2job_orig_list[job_loc_list[ji]]
            if job.code not in visited_final_job_code_set:
                visited_final_job_code_set.add(job.code)
                final_job_list.append(job)

        log.info(f"job2slot decided: worker: {nearby_slots[selected_scalar].worker_code}, jobs: {[j.code for j in final_job_list]}")        

        slot = nearby_slots[selected_scalar] 
        
        new_final_job_list = self._compare_agaist_greedy(
            slot, slot.assigned_jobs + todo_job_list,env,
            other_solution_job_list = final_job_list
        )
        return slot, new_final_job_list 
        

    def set_current_job(self): 
        # jc =env.unplanned_job_code_list[0]
        # print(env.trial_step_count, jc)
        return self.pomo_env.step_state

    def predict_action(self, 
                       env: ConfigurableDispatchEnv, todo_action: EnvAction, db_session = None
                       )->EnvAction: 
        if todo_action.order:
            _order_code = todo_action.order.code
        else:
            _order_code = todo_action.jobs[0].code


        selected_slot, final_job_list , reason_info = self._run_dispatch(env, todo_action)
        # TODO, check selected_slot is not changed by other processes. 
        # 
        env_horizon_minutes = env.get_env_planning_horizon_start_minutes()
        if len(final_job_list) <=2: # 2 are the current pick and drop
            # Start from slot start point
            all_locs_list = [[selected_slot.start_longitude, selected_slot.start_latitude]] + [
                [j.geo_longitude, j.geo_latitude] for j in final_job_list
            ]
            curr_start = max([selected_slot.start_minutes, env_horizon_minutes])
            curr_job_i = 0
        else:
            # Start from first job
            all_locs_list =[
                [j.geo_longitude, j.geo_latitude] for j in final_job_list
            ]
            curr_start = max([final_job_list[0].scheduled_start_minutes, env_horizon_minutes])
            curr_job_i = 1

        travel_minute_list = env.get_travel_router().get_travel_minutes_path(
            loc_list=all_locs_list)
        
        block_late_delivery_flag = str(env.config.get("block_late_delivery_flag", "1")) == '1'
        late_delivery_tolerance_max_minutes = int(env.config.get("late_delivery_tolerance_max_minutes", "45"))  
        late_delivery_found = False

        for minute_i, minutes in enumerate(travel_minute_list):
            final_job_list[curr_job_i].scheduled_start_minutes = curr_start + minutes
            final_job_list[curr_job_i].prev_travel = minutes
            curr_start += minutes + final_job_list[curr_job_i].scheduled_duration_minutes
            
            _tolerance = final_job_list[curr_job_i].tolerance_end_minutes + late_delivery_tolerance_max_minutes
            if len(final_job_list) > 2:
                # If it is only one order (2 jobs), skip late delivery control.
                if final_job_list[curr_job_i].code[-2:] == '-d':
                    # I check only the drop off job, since only drop off is committed to the customer.
                    if final_job_list[curr_job_i].scheduled_start_minutes > _tolerance:
                        log.debug(f"while dispatching order {_order_code}, job {final_job_list[curr_job_i].code} is scheduled at {final_job_list[curr_job_i].scheduled_start_minutes}, later_than_tolerance {_tolerance}. ")
                        late_delivery_found = True
            curr_job_i +=1

        selected_slot.available_free_minutes = selected_slot.end_minutes - curr_start
        selected_slot.assigned_jobs = final_job_list
        todo_action.scheduled_slots = [selected_slot]
        # overwrite_max_orders_limit = True
        # timeout switch if  true , ignore , must be succes planing
        if todo_action.overwrite_max_orders_limit:
            late_delivery_found = False 
        
        todo_action.action_type = ActionType.TODO
        if block_late_delivery_flag and late_delivery_found:
            env.save_job_failed_slot(_order_code, selected_slot.worker_code)
            log.warning(f"Dispatching_order_late_delivery_failed: {_order_code}, horizon: {env_horizon_minutes}, recorded failed order->worker {(todo_action.order.code, selected_slot.worker_code)}, jobs: {todo_action.scheduled_slots[0].slot_code}, {[(j.code, j.scheduled_start_minutes, j.tolerance_end_minutes) for j in  todo_action.scheduled_slots[0].assigned_jobs]}")
            todo_action.action_type = ActionType.DELAY_BLOCKED
            
        else:
            log.info(f"Dispatching_order_success: {_order_code}, horizon: {env_horizon_minutes}, jobs: {todo_action.scheduled_slots[0].slot_code}, {[(j.scheduled_start_minutes,j.code) for j in  todo_action.scheduled_slots[0].assigned_jobs]}")
            todo_action.action_type = ActionType.FLOATING

        return todo_action,reason_info

