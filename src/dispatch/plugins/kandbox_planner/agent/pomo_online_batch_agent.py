import threading 
import numpy as np
import os
import math
import copy
from dispatch.plugins.bases.kandbox_planner import KandboxAgentPlugin 
import sqlalchemy
import torch

from datetime import datetime

import logging
from dispatch.config import APPOINTMENT_DEBUG_LIST
from dispatch.plugins.kandbox_planner.env.env_enums import (
    OptimizerSolutionStatus,
    JobPlanningStatus,
)
from dispatch.plugins.kandbox_planner.env.env_models import JobsInSlotsDispatchResult, RecommendedAction
from dispatch.contrib.training.slotattention.train_job2slot.training_util import (
    load_model, select_action
)
from dispatch.plugins.kandbox_planner.env.env_enums import (
    EnvRunModeType,
    JobPlanningStatus,
    ActionCommandType,
)

from dispatch.contrib.training.pomo.pick_drop_job2slot.pick_drop_job2slot_env import PickDropJob2SlotEnv 
# from dispatch.contrib.training.pomo.pick_drop_job2slot.online_pick_drop_job2slot_env import OnlinePickDropJob2SlotEnv 
from dispatch.contrib.training.pomo.pick_drop_job2slot.online_pick_drop_job2slot_model import OnlinePickDropJob2SlotModel 



log = logging.getLogger("pomo_transformer_realtime_agent")

from dispatch.contrib.training.pomo.pomo_params import ( 
    env_params, model_params, optimizer_params, trainer_params, logger_params, 
    DEBUG_MODE, USE_CUDA)


from dispatch.contrib.training.slotattention.train_job2slot.training_util import (
    device, 
    get_env_config
)
from dispatch.contrib.training.slotattention.train_job2slot.train_args_parser import parser


class POMOOnlineBatchAgent(KandboxAgentPlugin):
    """ For slot attention model v1. 2021-07-17 15:30:22
    """
    title = "Kandbox Plugin - Agent - by POMO transformer"
    slug = "pomo_transformer_realtime_agent"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "Realtime Agent - by pytorch POMO direct inference."
    version = "0.1.0"
    default_config = {
        # "model_path": "/home/dispatch/uu_easydispatch/easydispatch/project/uupaotui/trained_model/v100/transformer_layer4/checkpoint_002901/transformer_layer4_reward_910_v100.torch",
        # "n_encode_layers": 4,

        # "model_path": "",
        "n_encode_layers": 6,
        "embedding_dim": 128,
        "transformer_model": "v13_flatten_impl",
        #
        "nbr_of_actions": 4,
        "n_epochs": 1000,
        "nbr_of_days_planning_window": 1,
        "working_dir": "/tmp",
        "checkpoint_path_key": "slot_attention_transformer_model_path",
    }
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, config=None, env_config=None, env=None):
        self.rl_env = env
        self.config = self.default_config.copy()
        # self.trained_model = trained_model
        self.config["create_datetime"] = datetime.now()
        self.config["model_path"] =  model_params.get("job2slot_model_path", None)

        if config is not None:
            self.config.update(config)

        if env_config is None:
            env_config = env.config
        # model_config = {
        #     "env_config": env_config,
        # }
        # self.trainer = None
        self.env_config = env_config
        # pdb.set_trace()

        self.decode_type = "greedy"
        ###
        env_params["pomo_size"] = 1
        self.pomo_env = PickDropJob2SlotEnv( env_params, model_params)
        # self.Env = OnlinePickDropJob2SlotEnv


        self.pomo_model = OnlinePickDropJob2SlotModel(model_params)

        log.info(f"POMOOnlineBatchAgent model initialized ...")

        # self.load_model(env_config=self.env_config)

    def load_model(self, env_config=None):  # , allow_empty = None
        # TODO, env_config
        checkpoint_fullname =  self.config["model_path"]  
        checkpoint = torch.load(checkpoint_fullname, map_location=device)
        self.pomo_model.load_state_dict(checkpoint['model_state_dict'])
        self.start_epoch = 1 + checkpoint['epoch']

        log.info(f'Loaded RL model from: {checkpoint_fullname}'  )
        return 0

    def train_model(self):

        log.error("not implemented: train_model")
    def translate_env_data(self): 
        all_locs_list = []
        self.loc2worker_idx = []
        self.loc2job_idx = []
        loc2job_idx_pick = []
        loc2job_idx_drop = []

        worker_locs = []
        job_locs = []

        for wi,w in enumerate(self.rl_env.workers_dict.values()):
            self.loc2worker_idx.append(w.worker_code)
            all_locs_list.append(w.curr_slot.start_location[0:2] )
            worker_locs.append(wi)
        worker_loc_idx = torch.tensor(worker_locs)[None,None,:]

        for j_i,j_code in enumerate(self.rl_env.unplanned_job_code_list):
            pick_job = self.rl_env.jobs_dict[
                self.rl_env.jobs_dict[j_code].included_job_codes[0]]
            drop_job = self.rl_env.jobs_dict[
                self.rl_env.jobs_dict[j_code].included_job_codes[1]]
            loc2job_idx_pick.append(pick_job.job_code)
            loc2job_idx_drop.append(drop_job.job_code)
 
            job_locs.append([len(all_locs_list), len(all_locs_list)+1])
            all_locs_list.append(pick_job.location[0:2])
            all_locs_list.append(drop_job.location[0:2])

        all_locs_list = all_locs_list 

        job_loc_idx = torch.tensor(job_locs )[None,None,:,:]

        dist_matrix_np = self.rl_env.travel_router.get_travel_minutes_matrix(
            loc_list=all_locs_list)

        longitude_max = self.rl_env.config["geo_longitude_max"]
        longitude_min = self.rl_env.config["geo_longitude_min"]
        latitude_max = self.rl_env.config["geo_latitude_max"]
        latitude_min = self.rl_env.config["geo_latitude_min"] 
        loc_xy = torch.tensor(all_locs_list)
        dist_matrix = torch.tensor(dist_matrix_np)[None,:,:].float()
        loc_xy[:,0] = (loc_xy[:,0] - longitude_min) / (longitude_max - longitude_min)
        loc_xy[:,1] = (loc_xy[:,1] - latitude_min) / (latitude_max - latitude_min)
        loc_xy = loc_xy[None,:,:].float()
        # worker_locs = torch.tensor([w.curr_slot.start_location[0:2] for w in self.rl_env.workers_dict.values()])
        # job_locs_1 = [self.rl_env.jobs_dict[jc].location[0:2] for jc in self.rl_env.jobs_dict.values()]
        # job_locs_2 = self.rl_env.job_log_df[["end_x","end_y"]].values

        inplanning_job_codes = []
        for w in self.rl_env.workers_dict.values():
            inplanning_job_codes += w.curr_slot.assigned_job_codes

        all_job_codes = inplanning_job_codes + self.rl_env.unplanned_job_code_list




        self.batch_size = 1
        self.pomo_size = 1
        self.job_loc_size = len(all_job_codes)
        self.worker_loc_size = len(worker_locs)

        # This matrix tracks relatinship: Pick-->Drop for each paired job
        next_job_idx = torch.cat( (
            torch.zeros(self.pomo_size, self.worker_loc_size) + (self.job_loc_size*2) + self.worker_loc_size,
            (torch.arange(self.job_loc_size))[None,:].repeat(self.pomo_size,1) + self.job_loc_size + self.worker_loc_size,
            torch.zeros(self.pomo_size, self.job_loc_size) + (self.job_loc_size*2) + self.worker_loc_size,
            ), dim = 1
        ).long()[None,:,:]

        # This matrix tracks mask: Job-->(1 as valid for select or 0, not -inf) for each paired job
        # one extra job position for void masking setting .
        next_job_mask = torch.cat( (
            torch.zeros(self.pomo_size, self.worker_loc_size + self.job_loc_size) ,  # + 1
            torch.zeros(self.pomo_size, self.job_loc_size + 1) + float("-inf"),  # + 0
            ), dim = 1
        )[None,:,:] 

        self.pomo_env.load_jobs(
            aug_factor=1, 
            loc_xy = loc_xy, 
            dist_matrix= dist_matrix,
            worker_loc_idx = worker_loc_idx,
            job_loc_idx = job_loc_idx,
            next_job_idx = next_job_idx,
            next_job_mask = next_job_mask,
        )
        return self.pomo_env.reset()

    def set_current_job(self): 
        # jc =self.rl_env.unplanned_job_code_list[0]
        # print(self.rl_env.trial_step_count, jc)
        return self.pomo_env.step_state

    def predict_action(self, obs): 
        step_state = obs
        with torch.no_grad():
            # self.pomo_model.pre_forward(reset_state)

            # POMO Rollout
            ###############################################
            # , reward, done = self.pomo_env.pre_step()
            slot_selected, prob, slot_probs = self.pomo_model(step_state)
            # shape: (batch, pomo)
            step_state, reward, done = self.pomo_env.step(slot_selected)
                
        # print(f"travel: {reward}, Done!!!")
        action = [0, 0, [0, 0], 0]
        action[1] = slot_selected.item()
        action[0] = ActionCommandType.DISPATCH

        slot_probs = slot_probs.squeeze(1)

        selected_log_p = torch.gather(slot_probs, -1, slot_selected).log()
        return action, selected_log_p, slot_probs
        # exit(0)