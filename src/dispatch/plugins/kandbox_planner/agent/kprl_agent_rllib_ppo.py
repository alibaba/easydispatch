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


from datetime import datetime

import logging
from dispatch.config import APPOINTMENT_DEBUG_LIST

log = logging.getLogger("ri_agent_rl_ppo")

# from ray.rllib.utils.framework import try_import_tf

# tf1, tf, tfv = try_import_tf()


class KandboxAgentRLLibPPO(KandboxAgentPlugin):
    title = "Kandbox Plugin - Agent - realtime - by rllib ppo"
    slug = "ri_agent_rl_ppo"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "RLLibPPO for GYM for RL."
    version = "0.1.0"
    default_config = {
        "nbr_of_actions": 4,
        "n_epochs": 1000,
        "nbr_of_days_planning_window": 6,
        "model_path": "default_model_path",
        "working_dir": "/tmp",
        "checkpoint_path_key": "ppo_checkpoint_path",
    }
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, agent_config, kandbox_config):
        self.agent_config = agent_config
        self.current_best_episode_reward_mean = -99

        env_config = agent_config["env_config"]

        if "rules_slug_config_list" not in env_config.keys():
            if "rules" not in env_config.keys():
                log.error("no rules_slug_config_list and no rules ")
            else:
                env_config["rules_slug_config_list"] = [
                    [rule.slug, rule.config] for rule in env_config["rules"]
                ]
                env_config.pop("rules", None)

        # self.env_class = env_class = agent_config["env"]

        self.kandbox_config = self.default_config.copy()
        self.kandbox_config.update(kandbox_config)

        # self.trained_model = trained_model
        self.kandbox_config["create_datetime"] = datetime.now()

        # self.trainer = None
        self.env_config = env_config
        # self.load_model(env_config=self.env_config)
        print(
            f"KandboxAgentRLLibPPO __init__ called, at time {self.kandbox_config['create_datetime']}"
        )
        # import pdb

        # pdb.set_trace()
        if not ray.is_initialized():
            ray.init(ignore_reinit_error=True, log_to_driver=False)
        # ray.init(redis_address="localhost:6379")

    def build_model(self):

        trainer_config = DEFAULT_CONFIG.copy()

        trainer_config["num_workers"] = 0
        # trainer_config["train_batch_size"] = 640
        # trainer_config["sgd_minibatch_size"] = 160
        # trainer_config["num_sgd_iter"] = 100

        trainer_config["exploration_config"] = {
            "type": "Random",
        }
        # EpsilonGreedy(Exploration):
        # trainer_config["exploration_config"] = {
        #         "type": "Curiosity",
        #         "eta": 0.2,
        #         "lr": 0.001,
        #         "feature_dim": 128,
        #         "feature_net_config": {
        #             "fcnet_hiddens": [],
        #             "fcnet_activation": "relu",
        #         },
        #         "sub_exploration": {
        #             "type": "StochasticSampling",
        #         }
        #     }

        # trainer_config["log_level"] = "DEBUG"
        """
        if env_config is not None:
            for x in env_config.keys():
                trainer_config[x] = env_config[x]
        """

        # trainer_config["env_config"] = copy.deepcopy(env_config)  #  {"rules": "qiyang_role"}

        trainer_config.update(self.agent_config)

        self.trainer = PPOTrainer(trainer_config, self.agent_config["env"])
        # self.config["trainer"] = self.trainer
        return self.trainer

    def load_model(self):  # , allow_empty = None
        env_config = self.agent_config["env_config"]
        self.trainer = self.build_model()

        # if (model_path is not None) & (os.path.exists(model_path)):
        if "ppo_checkpoint_path" in env_config.keys():
            # raise FileNotFoundError("can not find model at path: {}".format(model_path))
            if os.path.exists(env_config["ppo_checkpoint_path"]):
                self.trainer.restore(env_config["ppo_checkpoint_path"])
                print("Reloaded model from path: {} ".format(env_config["ppo_checkpoint_path"]))

            else:
                print(
                    "Env_config has ppo_checkpoint_path = {}, but no files found. I am returning an initial model".format(
                        env_config["ppo_checkpoint_path"]
                    )
                )

        else:
            print("Env_config has no ppo_checkpoint_path, returning an initial model")
        # self.config["model_path"] = model_path
        # self.config["trainer"] = self.trainer
        # self.config["policy"] = self.trainer.workers.local_worker().get_policy()
        self.policy = self.trainer.workers.local_worker().get_policy()
        return self.trainer

    def train_model(self):

        # self.trainer = self.build_model()
        for i in range(self.kandbox_config["n_epochs"]):
            result = self.trainer.train()
            # print(pretty_print(result))
            print(
                "Finished training iteration {}, Result: episodes_this_iter:{}, policy_reward_max: {}, episode_reward_max {}, episode_reward_mean {}, info.num_steps_trained: {}...".format(
                    i,
                    result["episodes_this_iter"],
                    result["policy_reward_max"],
                    result["episode_reward_max"],
                    result["episode_reward_mean"],
                    result["info"]["num_steps_trained"],
                )
            )
            if result["episode_reward_mean"] > self.current_best_episode_reward_mean * 1.1:
                model_path = self.save_model()
                print(
                    "Model is saved after 10 percent increase, episode_reward_mean = {},  file = {}".format(
                        result["episode_reward_mean"], model_path
                    )
                )
                self.current_best_episode_reward_mean = result["episode_reward_mean"]

        return self.save_model()

    def save_model(self):

        checkpoint_dir = "{}/model_checkpoint_org_{}_team_{}".format(
            self.agent_config["env_config"]["working_dir"],
            self.agent_config["env_config"]["org_code"],
            self.agent_config["env_config"]["team_id"],
        )
        _path = self.trainer.save(checkpoint_dir=checkpoint_dir)

        # exported_model_dir = "{}/exported_ppo_model_org_{}_team_{}".format(
        #     self.agent_config["env_config"]["working_dir"], self.agent_config["env_config"]["org_code"], self.agent_config["env_config"]["team_id"]
        # )
        # self.trainer.get_policy().export_model(exported_model_dir + "/1")

        return _path  # self.trainer

    def predict_action(self, observation=None):

        action = self.trainer.compute_action(observation)
        return action

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

        observation = env._get_observation()

        # export_dir = "/Users/qiyangduan/temp/kandbox/exported_ppo_model_org_duan3_team_3/1"
        # loaded_policy = tf.saved_model.load(export_dir)
        # loaded_policy.signatures["serving_default"](observations=observation)

        predicted_action = self.trainer.compute_action(observation)
        # V predicted_action = self.policy.compute_action(observation)

        for _ in range(len(env.workers)):  # hist_job_workers_ranked:
            if len(actions) >= self.config["nbr_of_actions"]:
                return actions
            actions.append(list(predicted_action).copy())
            max_i = np.argmax(predicted_action[0: len(env.workers)])
            predicted_action[max_i] = 0

        return actions

    def predict_action_dict_list(self, env=None, job_code=None, observation=None):
        if env is not None:
            self.env = env
        else:
            env = self.env

        curr_job = copy.deepcopy(env.jobs_dict[job_code])

        if job_code is None:
            job_i = env.current_job_i
        else:
            job_i = curr_job.job_index
            env.current_job_i = job_i

        observation = env._get_observation()

        action = self.predict_action(observation=observation)
        action_dict = env.decode_action_into_dict_native(action=action)

        action_day = int(action_dict.scheduled_start_minutes / 1440)
        curr_job.requested_start_min_minutes = action_day * 1440
        curr_job.requested_start_max_minutes = (action_day + 1) * 1440

        action_dict_list = self.env.recommendation_server.search_action_dict_on_worker_day(
            a_worker_code_list=action.scheduled_worker_codes,
            curr_job=curr_job,
            max_number_of_matching=3,
        )
        return action_dict_list
