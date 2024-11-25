# This was first version for japan setagaya dataset. job2slot and tsp are seperated.
# 2023-01-08 07:27:18
from collections import OrderedDict
import numpy as np
import os
import math
import copy
from dispatch.plugins.bases.kandbox_planner import KandboxAgentPlugin

import torch

from datetime import datetime

import logging
from dispatch.config import ALLOWED_MAXIMUM_MINUTES, APPOINTMENT_DEBUG_LIST
from dispatch.plugins.kandbox_planner.env.env_enums import (
    ActionType,
    OptimizerSolutionStatus,
    JobPlanningStatus,
)
from dispatch.plugins.kandbox_planner.env.env_models import EnvAction, JobsInSlotsDispatchResult, NoAvailableSlots, RecommendedAction
from dispatch.contrib.training.slotattention.train_job2slot.training_util import (
    load_model, select_action
)
from dispatch.plugins.kandbox_planner.env.env_enums import (
    EnvRunModeType,
    JobPlanningStatus,
    ActionCommandType,
)

from dispatch.contrib.training.pomo.pick_drop_job2slot.pick_drop_job2slot_env import PickDropJob2SlotEnv 
from dispatch.contrib.training.pomo.pick_drop_job2slot.online_pick_drop_job2slot_model import OnlinePickDropJob2SlotModel 



log = logging.getLogger("pomo_transformer_job2slot_tsp_2steps_agent")

from dispatch.contrib.training.pomo.pomo_params import ( 
    env_params, model_params, optimizer_params, trainer_params, logger_params, 
    DEBUG_MODE, USE_CUDA)


from dispatch.contrib.training.slotattention.train_job2slot.training_util import (
    device, 
    get_env_config
)
from dispatch.contrib.training.slotattention.train_job2slot.train_args_parser import parser


class POMOOnlineRTAgent(KandboxAgentPlugin):
    """ For slot attention model v1. 2021-07-17 15:30:22
    """
    title = "Kandbox Plugin - Agent - by POMO transformer"
    slug = "pomo_transformer_job2slot_tsp_2steps_agent"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "Realtime Agent - by pytorch POMO direct inference."
    version = "0.1.0"
    default_config = {
        # "model_path": "/home/dispatch/uu_easydispatch/easydispatch/project/uupaotui/trained_model/v100/transformer_layer4/checkpoint_002901/transformer_layer4_reward_910_v100.torch",
        # "n_encode_layers": 4,

        "model_path": "",
        "n_encode_layers": 6,
        "embedding_dim": 128,
        "transformer_model": "v13_flatten_impl",
        #
        "direct_dispatch_min_meters": 1800,
        "nbr_of_actions": 4,
        "n_epochs": 1000,
        "nbr_of_days_planning_window": 1,
        "working_dir": "/tmp",
        "load_model": True,
        "checkpoint_path_key": "slot_attention_transformer_model_path",
    }
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, config=None):
        self.config = self.default_config.copy()
        if config is not None:
            self.config.update(config)
        # self.trained_model = trained_model
        self.create_datetime = datetime.now()

        # pdb.set_trace()

        self.decode_type = "greedy"
        ###
        env_params["pomo_size"] = 1
        self.pomo_env = PickDropJob2SlotEnv( env_params, model_params)
        # self.Env = OnlinePickDropJob2SlotEnv

        self.pomo_model = OnlinePickDropJob2SlotModel(model_params)
        self.batch_size = 1
        self.pomo_size = 1
        self.worker_size = 1
        self.max_job_in_worker_size = env_params['max_job_in_worker_size']

        log.info(f"POMOOnlineRTAgent env and model initialized ...")

        if self.config["load_model"]:
            self.load_model()

    def load_model(self,):  # , allow_empty = None
        # TODO, env_config
        checkpoint_fullname = model_params["job2slot_model_path"] 
        checkpoint = torch.load(checkpoint_fullname, map_location=device)
        self.pomo_model.load_state_dict(checkpoint['model_state_dict'])
        self.start_epoch = 1 + checkpoint['epoch']

        log.info(f'Loaded job2slot model from {checkpoint_fullname}'  )
        return 0

    def train_model(self):
        log.error("not implemented: train_model")

    def _run_dispatch(self, env, todo_action: EnvAction): 
        all_locs_list = []
        self.loc2worker_idx = []
        self.loc2job_idx = []
        loc2job_code_list = []

        worker_locs = []
        job_locs = []
        horizon_minutes = env.get_env_planning_horizon_start_minutes()

        nearby_slots, dist_list = env.get_nearby_slots(
            loc=[todo_action.jobs[0].geo_longitude, todo_action.jobs[0].geo_latitude,]
        )
        if len(nearby_slots) < 1:
            raise NoAvailableSlots
        for si, slot in enumerate(nearby_slots):
            if (len(slot.assigned_jobs) < 1) and (dist_list[si] < self.config["direct_dispatch_min_meters"]):
                log.info(f"{si}-th closest slot {slot.slot_code} to order {todo_action.order.code} is empty, meters = {dist_list[si]}, dispatched straight away.")
                return slot, todo_action.jobs

        for si,slot in enumerate(nearby_slots):
            self.loc2worker_idx.append(slot.slot_code)
            all_locs_list.append([slot.start_longitude, slot.start_latitude, ALLOWED_MAXIMUM_MINUTES] )
            worker_locs.append(si)
        worker_loc_idx = torch.tensor(worker_locs)[None,None,:]



        pick_job = todo_action.jobs[0]
        drop_job = todo_action.jobs[1]
        loc2job_code_list.append(pick_job.code)
        loc2job_code_list.append(drop_job.code)
        new_job_loc_idx_pair = [len(all_locs_list), len(all_locs_list)+1]
        # todo_jobinslot_pair = todo_action.jobs
        job_locs.append(new_job_loc_idx_pair)
        all_locs_list.append([pick_job.geo_longitude, pick_job.geo_latitude, pick_job.tolerance_end_minutes - horizon_minutes])
        all_locs_list.append([drop_job.geo_longitude, drop_job.geo_latitude, drop_job.tolerance_end_minutes - horizon_minutes])
        
        worker_loc_lengths = [1 for _ in range(len(nearby_slots))]
        worker_selected_loc_list = [
            [wi for _ in range(env_params['max_job_in_worker_size'])] 
            for wi in range(len(nearby_slots))
        ]

        tsp_pad_mask_list = [
            [-pi*1e20 for pi in range(env_params['max_job_in_worker_size']+1)] 
            for _ in range(len(nearby_slots))
        ]
        tsp_next_job_index_list = [
            [env_params['max_job_in_worker_size'] for _ in range(env_params['max_job_in_worker_size'])] 
            for wi in range(len(nearby_slots))
        ]

        worker_selected_job_orig_list = [
            [None for _ in range(env_params['max_job_in_worker_size'])] 
            for wi in range(len(nearby_slots))
        ]

        for si,slot in enumerate(nearby_slots):
            if len(slot.assigned_jobs) < 1:
                continue

            # 2023-01-01 00:19:58
            # 需要记录worker_selected_loc_length
            # 如果只剩下一个drop 任务，那么复制成两个drop做一组。
            # _slot_orders = OrderedDict()
            # assigned_jobs = slot.assigned_jobs # env.decode_working_slot_assigned_jobs()
            # for job in assigned_jobs:
            #     order_code = job.code[:-2]
            #     job_type = job.code[-1]
            #     if order_code in _slot_orders:
            #         if job_type == 'p':
            #             _slot_orders[order_code][0] = job
            #         else:
            #             _slot_orders[order_code][1] = job
            #     else:
            #         _slot_orders[order_code] = [job, job]
            
            # worker_loc_lengths[si] += len(_slot_orders) * 2
            # _loc_idx = 1
            # for job_pair in _slot_orders.values():
            #     loc2job_code_list.append(job_pair[0].code)
            #     loc2job_code_list.append(job_pair[1].code)

            #     _temp_new_loc_idx_pair = [len(all_locs_list),len(all_locs_list)+1]
            #     worker_selected_loc_list[si][_loc_idx:_loc_idx+2] = _temp_new_loc_idx_pair
            #     worker_selected_job_orig_list[si][_loc_idx:_loc_idx+2] = job_pair
            #     _loc_idx += 2
            #     job_locs.append(_temp_new_loc_idx_pair)
            #     all_locs_list.append([job_pair[0].geo_longitude, job_pair[0].geo_latitude, job_pair[0].tolerance_end_minutes - horizon_minutes])
            #     all_locs_list.append([job_pair[1].geo_longitude, job_pair[1].geo_latitude, job_pair[1].tolerance_end_minutes - horizon_minutes])

            # 2023-01-02 17:31:28, using job by itself. No need of order.
            _drop_locs = {}
            _pick_locs = {}
            _loc_idx = 0
            for job in slot.assigned_jobs:
                # len(all_locs_list) is the location index of this job's loc
                worker_selected_loc_list[si][_loc_idx] = len(all_locs_list)
                worker_selected_job_orig_list[si][_loc_idx] = job
                # This is a fake data. Only job_locs[0] matters, with current job to disptach.7
                job_locs.append([len(all_locs_list),len(all_locs_list)+1])# len(all_locs_list))
                if job.code[-1] == 'd':
                    # order_code = job.code[:-2]
                    _drop_locs[job.code[:-2]] = _loc_idx
                else:
                    tsp_pad_mask_list[si][_loc_idx] = 0
                    _pick_locs[job.code] = _loc_idx
                all_locs_list.append([job.geo_longitude, job.geo_latitude, job.tolerance_end_minutes - horizon_minutes])
                _loc_idx += 1

            for job in slot.assigned_jobs:
                if job.code[-1] == 'p':
                    # order_code = job.code[:-2]
                    if job.code[:-2] in _drop_locs:
                        tsp_next_job_index_list[si][_pick_locs[job.code]] = _drop_locs[job.code[:-2]] 
            
            # in all cases, 2nd job should be ready to be planned, since 1st if already in execution.
            tsp_pad_mask_list[si][1] = 0
            worker_loc_lengths[si] += len(slot.assigned_jobs)
            # Here there must be jobs in slot, first location is a job, not slot start location.
            if len(slot.assigned_jobs) > 0:
                worker_loc_lengths[si] = worker_loc_lengths[si] - 1

        job_loc_idx = torch.tensor(job_locs )[None,None,:,:]
        worker_loc_length_t = torch.tensor(worker_loc_lengths )[None,None,:]
        # try:
        worker_selected_loc_t = torch.tensor(worker_selected_loc_list )[None,None,:,:] 
        # except IndexError as e:
        #     print(str(e))
        loc_xy = torch.tensor(all_locs_list)

        # Normalize locations
        longitude_max = env.config["geo_longitude_max"]
        longitude_min = env.config["geo_longitude_min"]
        latitude_max = env.config["geo_latitude_max"]
        latitude_min = env.config["geo_latitude_min"] 
        loc_xy[:,0] = (loc_xy[:,0] - longitude_min) / (longitude_max - longitude_min)
        loc_xy[:,1] = (loc_xy[:,1] - latitude_min) / (latitude_max - latitude_min)
        loc_xy[:,2] = (loc_xy[:,2] - 0) / ALLOWED_MAXIMUM_MINUTES
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
            worker_selected_loc = worker_selected_loc_t)

        selected, prob, _probs = self.pomo_model(step_state)

        # 然后根据worker_selected_loc_length 和选择的job 生成TSP 的env。
        selected_scalar = selected.item()
        chosen_worker_job_list = worker_selected_job_orig_list[selected_scalar]

        flat_length = self.pomo_env.step_state.worker_selected_loc_length[0,0,selected_scalar:selected_scalar + 1]
        flat_length_scalar = flat_length.item()

        if flat_length_scalar < 2: 
            # 1 could be only start loc, or with 1 job.
            # 2 could only be 1 pick, 1 drop
            return nearby_slots[selected_scalar], nearby_slots[selected_scalar].assigned_jobs + todo_action.jobs
            # print("flat_length_scalar:",flat_length_scalar)

        # if flat_length_scalar < 3: # 1 means only start loc, 2 means with 1 job.
        #     return nearby_slots[selected_scalar], chosen_worker_job_list[0:1] + todo_action.jobs



        # 在选中的worker后面放上两个新job（1个order），做TSP。
        self.pomo_env.step_state.worker_selected_loc_idx[0,0,selected_scalar,flat_length_scalar:flat_length_scalar+2
            ] = torch.tensor(new_job_loc_idx_pair)
        chosen_worker_job_list[flat_length_scalar:flat_length_scalar+2] = todo_action.jobs
        
        # Here there there must be jobs in slot, first location is a job, not slot start location.
        flat_length = flat_length + 2 
        flat_length_scalar += 2 

        tsp_pad_mask1 = self.pomo_env.pad_masker[flat_length,:].view(
            self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size+1)
        tsp_next_job_index1 = self.pomo_env.next_job_indexer[flat_length,:].view(
            self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size)

        tsp_pad_mask_list[selected_scalar][0:2] = [float("-inf"), 0]
        tsp_pad_mask = torch.tensor(tsp_pad_mask_list[selected_scalar]).view(
            self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size+1)
        tsp_next_job_index = torch.tensor(tsp_next_job_index_list[selected_scalar]).view(
            self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size)



        gathering_index = self.pomo_env.pad_indexer[flat_length,:].view(
            self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size)

        _I4D_Worker = torch.tensor([0])[None,None,:,None]
        tsp_gathered_job_indexes = self.pomo_env.step_state.worker_selected_loc_idx[:,:,selected_scalar:selected_scalar+1,:][
                self.pomo_env.I4D_Batch, self.pomo_env.I4D_Pomo, _I4D_Worker, gathering_index
            ] # add the last X,Y (long/lat) index
        
        all_xy = self.pomo_env.step_state.reset_state.loc_xy[:, None, None, :, :].expand(-1, self.pomo_size, self.worker_size, -1, -1)
        ordered_jobs = all_xy.gather(
            dim=3, 
            index=tsp_gathered_job_indexes[:,:,:,:, None].expand(-1, -1, -1,-1, self.pomo_env.step_state.reset_state.loc_dim))
        # shape: (batch, pomo, self.woker_size, self.max_job_in_worker_size, loc_dim)


        self.pomo_env.solve_tsp_problem(
            ordered_jobs, tsp_pad_mask, tsp_next_job_index
            )

        node_list = self.pomo_env.tsp_env.selected_node_list.view(self.max_job_in_worker_size).tolist()
        job_idx_list = tsp_gathered_job_indexes.view(self.max_job_in_worker_size).tolist()
        final_job_list = []
        visited_final_job_code_set = set()
        for ji in range(0, flat_length_scalar):
            job = chosen_worker_job_list[node_list[ji]]
            if job.code not in visited_final_job_code_set:
                visited_final_job_code_set.add(job.code)
                final_job_list.append(job)
        
        return nearby_slots[selected_scalar], final_job_list

    def set_current_job(self): 
        # jc =env.unplanned_job_code_list[0]
        # print(env.trial_step_count, jc)
        return self.pomo_env.step_state

    def predict_action(self, env, todo_action: EnvAction): 
        selected_slot, final_job_list = self._run_dispatch(env, todo_action)
        # TODO, check selected_slot is not changed by other processes. 
        # 
        if len(final_job_list) <=2:
            # Start from slot start point
            all_locs_list = [[selected_slot.start_longitude, selected_slot.start_latitude]] + [
                [j.geo_longitude, j.geo_latitude] for j in final_job_list
            ]
            curr_start = max([selected_slot.start_minutes, env.get_env_planning_horizon_start_minutes()])
            curr_job_i = 0
        else:
            # Start from first job
            all_locs_list =[
                [j.geo_longitude, j.geo_latitude] for j in final_job_list
            ]
            curr_start = final_job_list[0].scheduled_start_minutes
            curr_job_i = 1

        travel_minute_list = env.get_travel_router().get_travel_minutes_path(
            loc_list=all_locs_list)

        for minute_i, minutes in enumerate(travel_minute_list):
            final_job_list[curr_job_i].scheduled_start_minutes = curr_start + minutes
            final_job_list[curr_job_i].prev_travel = minutes
            curr_start += minutes + final_job_list[curr_job_i].scheduled_duration_minutes
            curr_job_i +=1

        selected_slot.available_free_minutes = selected_slot.end_minutes - curr_start
        selected_slot.assigned_jobs = final_job_list
        todo_action.scheduled_slots = [selected_slot]
        # todo_action.scheduled_worker_codes = [selected_slot.worker_code]
        todo_action.action_type = ActionType.FLOATING

        return todo_action

