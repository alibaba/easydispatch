import gym
from gym import spaces
import numpy as np
import ray
from ray.rllib.agents.ppo import PPOTrainer, DEFAULT_CONFIG
import os
import math
from ray.tune.logger import pretty_print
import copy
from dispatch.plugins.bases.kandbox_planner import KandboxAgentPlugin

import torch
from dispatch.contrib.training.slotattention.nets.slot_attention_transformer import SlotAttentionModel
from datetime import datetime

import logging
from dispatch.config import APPOINTMENT_DEBUG_LIST
from dispatch.plugins.kandbox_planner.env.env_enums import (
    OptimizerSolutionStatus,
    JobPlanningStatus,
)
from dispatch.plugins.kandbox_planner.env.env_models import RecommendedAction

log = logging.getLogger("slot_attention_realtime_agent")

opts = {
    "problem": "slotattention",
    "graph_size": 10,
    "batch_size": 512,
    "epoch_size": 512,
    "val_size": 512,
    "val_dataset": None,
    "model": "slot_attention_toy",
    "embedding_dim": 128,
    "hidden_dim": 128,
    "n_encode_layers": 4,
    "tanh_clipping": 10.0,
    "normalization": "batch",
    "lr_model": 1e-06,
    "lr_critic": 1e-07,
    "lr_decay": 0.999,
    "eval_only": False,
    "n_epochs": 200,
    "seed": 1234,
    "max_grad_norm": 1.0,
    "no_cuda": False,
    "exp_beta": 0.8,
    "baseline": "exponential",
    "bl_alpha": 0.05,
    "bl_warmup_epochs": 0,
    "eval_batch_size": 512,
    "checkpoint_encoder": False,
    "shrink_size": None,
    "data_distribution": None,
    "log_step": 50,
    "log_dir": "logs",
    "run_name": "pure_train_20210322T072908",
    "output_dir": "outputs",
    "epoch_start": 0,
    "checkpoint_epochs": 1000,
    "load_path": "etc/trained_models/trained_20210321T180459.pt",
    "resume": None,
    "no_tensorboard": True,
    "no_progress_bar": True,
    "use_cuda": False,
    "save_dir": "outputs/slotattention_10/pure_train_20210322T072908",
}


class SlotAttentionRealtimeAgentTransformer(KandboxAgentPlugin):
    title = "Kandbox Plugin - Agent - by pytorch transformer"
    slug = "slot_attention_realtime_agent"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "Realtime Agent - by pytorch transformer env rllib_env_job2slot."
    version = "0.1.0"
    default_config = {
        "nbr_of_actions": 4,
        "n_epochs": 1000,
        "nbr_of_days_planning_window": 1,
        # "model_path": "/tmp/model_trained/slot_attention_transformer.good.8jobs",
        "model_path": "/Users/qiyangduan/git/kandbox/kandbox_dispatch/etc/saved_model/slot_attention_transformer_layer_4_reward_250",
        "working_dir": "/tmp",
        "checkpoint_path_key": "slot_attention_transformer_model_path",
    }
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, config=None, env_config=None, env=None):
        self.env = env
        self.config = self.default_config.copy()
        if config is not None:
            self.config.update(config)
        # self.trained_model = trained_model
        self.config["create_datetime"] = datetime.now()

        # self.trainer = None
        self.env_config = env_config
        # self.load_model(env_config=self.env_config)
        # pdb.set_trace()
        self.policy_net = SlotAttentionModel(
            slot_input_dim=17,
            job_input_dim=10,
            slot_embedding_dim=opts["embedding_dim"] * 2,
            job_embedding_dim=opts["embedding_dim"],  # 128
            n_encode_layers=opts["n_encode_layers"],
            mask_inner=True,
            mask_logits=True,
            normalization=opts["normalization"],
            tanh_clipping=opts["tanh_clipping"],
            checkpoint_encoder=opts["checkpoint_encoder"],
            shrink_size=opts["shrink_size"],
        ).to("cpu")

    def load_model(self, env_config=None):  # , allow_empty = None
        #TODO, env_config

        model_path = self.config["model_path"]
        if os.path.exists(model_path):
            checkpoint = torch.load(model_path, map_location='cpu',)
            self.policy_net.load_state_dict(checkpoint["model_state_dict"])
            self.epoch = checkpoint["epoch"]
            self.current_max_avg_episode_reward = checkpoint["current_max_avg_episode_reward"]
            # policy_net.load_state_dict(torch.load(model_path))
            log.info(f"{datetime.now()}, Reloaded model from path: {model_path}, epoch={self.epoch}, current_max_avg_episode_reward={self.current_max_avg_episode_reward} ...")

        else:
            log.info(
                f"{datetime.now()}, model_path = {model_path}, but no files found. returning an initial model")
            self.epoch = 0
            self.current_max_avg_episode_reward = 0
            # raise FileNotFoundError("can not find model at path: {}".format(model_path))

        return self.epoch

    def train_model(self):

        log.error("not implemented")

    def predict_action(self, obs):
        # action_numpy = np.zeros(len(self.env.internal_obs_slot_list))

        # action = self.trainer.compute_action(observation)
        with torch.no_grad():
            selected, log_p = self.policy_net(
                slot_input=torch.tensor(obs["slots"]).float()[None, :, :].to("cpu"),
                job_input=torch.tensor(obs["jobs"]).float()[None, :, :].to("cpu"), )
        # action_numpy[selected] = 1

        # return action_numpy
        return selected.to("cpu").numpy()

    def predict_action_list(self, env=None, job_code=None, observation=None):
        actions = []
        if env is not None:
            self.env = env
        else:
            env = self.env

        if job_code is None:
            job_i = env.current_job_i
        else:
            job_i = env.jobs_dict[job_code].job_index
            env.current_job_i = job_i
            assert env.jobs[job_i].job_code == job_code

        observation = env._get_observation()

        # new_act = action.copy()
        # max_i = np.argmax(new_act[0: len(self.internal_obs_slot_list)])  #
        # if max_i >= len(self.internal_obs_slot_list):
        #     log.error("Wrong,max_i >= len(self.internal_obs_slot_list)")
        #     return []

        predicted_action = self.predict_action(observation)
        return [predicted_action]

    def predict_action_dict_list(self, env=None, job_code=None, observation=None):
        action_list = self.predict_action_list(env, job_code, observation)
        if len(action_list) < 1:
            return []
        if env is None:
            env = self.env
        max_i = action_list[0][0, 0]

        temp_slot = copy.deepcopy(env.internal_obs_slot_list[max_i])
        temp_slot.assigned_job_codes.append(env.jobs[env.current_job_i].job_code)
        shared_time_slots_optimized = [temp_slot]

        res = env.naive_opti_slot.dispatch_jobs_in_slots(shared_time_slots_optimized)
        if res["status"] == OptimizerSolutionStatus.SUCCESS:
            selected_action = res["changed_action_dict_by_job_code"][job_code]
            # scheduled_start_datetime = env.env_decode_from_minutes_to_datetime(
            #     input_minutes=selected_action.scheduled_start_minutes
            # )

            # from dispatch.service.planner_models import GenericJobAction
            # action_dict = GenericJobAction(
            #     scheduled_worker_codes=selected_action.scheduled_worker_codes,
            #     scheduled_duration_minutes=selected_action.scheduled_duration_minutes,
            #     scheduled_start_datetime=scheduled_start_datetime,
            #     score=1,
            #     score_detail=[],
            # )

            a_rec = RecommendedAction(
                job_code=job_code,
                # action_type=ActionType.JOB_FIXED,
                # JobType = JOB, which can be acquired from self.jobs_dict[job_code]
                job_plan_in_scoped_slots=[],
                unplanned_job_codes=[],
                scheduled_worker_codes=selected_action.scheduled_worker_codes,
                scheduled_start_minutes=selected_action.scheduled_start_minutes,
                scheduled_duration_minutes=selected_action.scheduled_duration_minutes,
                scoped_slot_code_list=[],
                score=1,
                score_detail=[],
            )

            return [a_rec]

        return []
