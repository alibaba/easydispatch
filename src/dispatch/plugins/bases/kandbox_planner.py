"""
.. module: dispatch.plugins.bases.kandbox_planner
    :platform: Unix
    :copyright: (c) 2020 by Qiyang Duan
    :license: Apache, see LICENSE for more details.
.. moduleauthor:: qiyang duan
"""
from dispatch.plugins.base import Plugin
from dispatch.models import PluginOptionModel

from dispatch.plugins.kandbox_planner.env.env_models import *

from dispatch.plugins.kandbox_planner.env.env_enums import ActionScoringMetricsCode

import gym
from enum import Enum
import logging

log = logging.getLogger(__file__)
import copy


class KandboxPlannerPluginType(str, Enum):
    kandbox_env_proxy = "kandbox_env_proxy"
    kandbox_env = "kandbox_env"
    kandbox_agent = "kandbox_agent"
    kandbox_batch_optimizer = "kandbox_batch_optimizer"
    kandbox_rule = "kandbox_rule"
    kandbox_travel_time = "kandbox_travel_time"
    kandbox_data_adapter = "kandbox_data_adapter"
    kandbox_data_generator = "kandbox_data_generator"


class KandboxPlugin:

    enabled = True
    required = False
    multiple = False
    config = None


class KandboxDataAdapterPlugin(Plugin):
    type = KandboxPlannerPluginType.kandbox_data_adapter
    _schema = PluginOptionModel

    def get_jobs(self, **kwargs):
        raise NotImplementedError

    def get_workers(self, **kwargs):
        raise NotImplementedError

    def update_single_job(self, **kwargs):
        raise NotImplementedError

    def update_batch_jobs(self, **kwargs):  # save_schedued_jobs
        raise NotImplementedError

# 2021-02-24 07:40:28 I tried to call different functions by kafka message, but this is useless
# It should be combined with kafka_adapter.process_env_out_message.
class KandboxKafkaOutputHandlerPlugin(Plugin):
    type = KandboxPlannerPluginType.kandbox_batch_optimizer
    _schema = PluginOptionModel

    def __init__(self, kafka_server):  # team_id is included in env
        self.kafka_server = kafka_server

    def dispatch_jobs(self, **kwargs):
        raise NotImplementedError


class KandboxEnvProxyPlugin(Plugin):
    type = KandboxPlannerPluginType.kandbox_env_proxy
    _schema = PluginOptionModel

    def get_env(self, config, kp_data_adapter=None):
        return self.env_class(kp_data_adapter=kp_data_adapter, env_config=config)


class KandboxEnvPlugin(gym.Env):
    type = KandboxPlannerPluginType.kandbox_env
    _schema = PluginOptionModel

    # **----------------------------------------------------------------------------
    # ## Utility functions
    # **----------------------------------------------------------------------------

    def encode_dict_into_action(self, a_dict):
        # DO NOT USE
        raise ValueError("# DO NOT USE")
        n = np.zeros(len(self.workers) + 4)
        worker_index = self.workers_dict[a_dict.scheduled_primary_worker_id].worker_index
        n[worker_index] = 1
        n[-4] = a_dict.scheduled_duration_minutes  #  * self.env.config['minutes_per_day']  +
        n[-3] = a_dict["scheduled_start_day"]  #  * self.env.config['minutes_per_day']  +
        n[-2] = a_dict.scheduled_start_minutes  # / 1600 # 288
        n[-1] = len(a_dict.scheduled_secondary_worker_ids) + 1  # / 200 # 60 - shared count

        return n

    def decode_action_into_dict(self, action):
        """
        action[0].shape=self.config['nbr_of_observed_workers']
        for iii in range(1,5):
        action[iii].shape=1
        new_act = list(action[0]) + list(action[1])  + list(action[2])  + list(action[3])  + list(action[4])
        """
        raise ValueError("# DO NOT USE")
        new_act = action.copy()
        max_i = np.argmax(new_act[0 : len(self.workers)])
        worker_code = self.workers[max_i].worker_code
        action_day = int(new_act[-3])
        job_start_time = (
            action_day * self.config["minutes_per_day"] + new_act[-2]
        )  # days * 1440 + minutes
        shared_count = int(new_act[-1])
        scheduled_secondary_worker_ids = []
        for i in range(1, shared_count):
            new_act[max_i] = 0
            max_i = np.argmax(new_act[0 : len(self.workers)])
            scheduled_secondary_worker_ids.append(self.workers[max_i].worker_code)

        a_dict = {
            "scheduled_primary_worker_id": worker_code,
            "scheduled_secondary_worker_ids": scheduled_secondary_worker_ids,
            "scheduled_start_day": action_day,
            "scheduled_start_minutes": new_act[-2],
            "assigned_start_day_n_minutes": int(job_start_time),
            "scheduled_duration_minutes": int(new_act[-4]),
        }

        return a_dict

    # **----------------------------------------------------------------------------
    # ## Extended functions
    # **----------------------------------------------------------------------------


class KandboxAgentPlugin(KandboxPlugin):
    type = KandboxPlannerPluginType.kandbox_agent
    _schema = PluginOptionModel

    def get(self, **kwargs):
        raise NotImplementedError

    def load_model(self, env_config):
        pass

    def dispatch_jobs(self, env):
        if env is not None:
            self.env = env
        else:
            env = self.env
        env.reset()
        (observation, reward, done, info) = env.replay_env()

        env.run_mode = EnvRunModeType.PREDICT
        step_result_flag = []
        # print("Prediction Game: {}, started ...".format(game_index))
        for step_index in range(len(env.jobs)):
            if done:
                break

            if "job_status" in env.jobs[env.current_job_i].keys() and (
                env.jobs[env.current_job_i].planning_status
                in [JobPlanningStatus.PLANNED, JobPlanningStatus.IN_PLANNING]
            ):
                print(
                    "job ({}) should not be in   {} status".format(
                        env.jobs[env.current_job_i].job_code,
                        env.jobs[env.current_job_i].planning_status,
                    )
                )
                continue
            else:
                action = self.predict_action(observation=observation)

            # action = gen_random_action()
            if (action is None) or (len(action) < 1):
                print(
                    "Failed to get prediction for job ({}) ".format(
                        env.jobs[env.current_job_i].job_code
                    )
                )

                break
            observation, reward, done, info = env.step(action)
            # pprint(env.render_action(action))
            #
            if done:  # or info=='error':
                # adict = env.decode_action_into_dict(action)
                print(
                    "Final Error for action step {}, current_job _i : {}, action: {}. Done".format(
                        step_index, env.current_job_i, action
                    )
                )
                break

            # print(info)
            step_result_flag.append(1 if info["message"] == "ok" else 0)

        print(
            "Dispatch Done: Job_count: {}, info_ok: {}".format(
                len(step_result_flag), sum(step_result_flag)
            )
        )

        env.commit_changed_jobs()


class KandboxBatchOptimizerPlugin(Plugin):
    type = KandboxPlannerPluginType.kandbox_batch_optimizer
    _schema = PluginOptionModel

    def dispatch_jobs(self, **kwargs):
        raise NotImplementedError


class KandboxRulePlugin(Plugin):
    type = KandboxPlannerPluginType.kandbox_rule
    multiple = True

    _schema = PluginOptionModel

    """
    Has the following members
  """

    rule_code = "generic_rule"
    rule_name = "Generic Rule (and it should not be used)"
    message_template = "Generic Rule"
    reward_range = [-1, 1]
    default_config = {}

    result = {
        "score": 0,
        "message": ["Not implemented"],
    }

    def __init__(self, weight=None, config=None):
        self.weight = weight
        if config is None:
            self.config = self.default_config
        else:
            self.config = config

    def evalute_normal_single_worker_n_job(self, env=None, job=None):  # worker = None,
        raise NotImplementedError


    def generate_virtual_job_from_action(self, env=None, a_dict=None):

        all_jobs = []
        # max_i = np.argmax(action[0:len(self.workers_dict)])
        # all_workers = a_dict.scheduled_worker_codes
        job = copy.deepcopy(env.jobs_dict[a_dict.job_code])
        job.scheduled_worker_codes = a_dict.scheduled_worker_codes
        job.scheduled_start_minutes = a_dict.scheduled_start_minutes
        job.scheduled_duration_minutes = a_dict.scheduled_duration_minutes

        return job
        # return score, violated_rules (negative values)

    def evalute_action_normal(self, env=None, action_dict=None):

        job_copy = self.generate_virtual_job_from_action(env=env, a_dict=action_dict)

        res = self.evalute_normal_single_worker_n_job(env=env, job=job_copy)

        return res

class KandboxTravelTimePlugin(Plugin):
    """
    get_travel_minutes_2locations() must be superceded to return minutes
    """

    type = KandboxPlannerPluginType.kandbox_travel_time
    _schema = PluginOptionModel

    def get_travel_minutes_2locations(self, loc_1, loc_2):  # get_travel_time_2locations
        raise NotImplementedError
