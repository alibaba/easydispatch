"""
.. module: dispatch.plugins.bases.kandbox_planner
    :platform: Unix
    :copyright: (c) 2020 by Qiyang Duan
    :license: Apache, see LICENSE for more details.
.. moduleauthor:: qiyang duan
"""
import copy
import math
from dispatch.plugins.base import Plugin, ConfigurablePlugin
from dispatch.models import PluginOptionModel
from dispatch import config as dconfig

from dispatch.plugins.kandbox_planner.env.env_enums import KandboxPlannerPluginType
from dispatch.plugins.kandbox_planner.env.env_models import *  
from dispatch.plugins.kandbox_planner.env.env_models import  OptiJobLoc, OptiContext

from dispatch.team.models import Team
from dispatch.job.models import Job
from typing import List, Dict, Any, Optional
import pydantic 



# import gym
from enum import Enum
import logging

log = logging.getLogger(__file__)


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


# class KandboxKafkaOutputHandlerPlugin(Plugin):
#     type = KandboxPlannerPluginType.kandbox_kafka_handler
#     _schema = PluginOptionModel

#     def __init__(self, kafka_server):  # team_id is included in env
#         self.kafka_server = kafka_server

    # def dispatch_jobs(self, **kwargs):
    #     raise NotImplementedError


class KandboxEnvProxyPlugin(Plugin):
    type = KandboxPlannerPluginType.kandbox_env_proxy
    _schema = PluginOptionModel

    def get_env(self, config, kp_data_adapter=None):
        # kp_data_adapter=kp_data_adapter,
        new_config = copy.deepcopy(self.default_config)
        new_config.update(config)
        return self.env_class(config=new_config)


class KandboxEnvPlugin: # (gym.Env)
    type = KandboxPlannerPluginType.kandbox_env
    _schema = PluginOptionModel

    # **----------------------------------------------------------------------------
    # ## Utility functions
    # **----------------------------------------------------------------------------

    def encode_dict_into_action(self, a_dict):
        # DO NOT USE
        raise ValueError("# DO NOT USE")
        n = np.zeros(len(self.workers) + 4)
        worker_index = self.workers_dict[a_dict.scheduled_primary_worker_code].worker_index
        n[worker_index] = 1
        n[-4] = a_dict.scheduled_duration_minutes  # * self.env.config['minutes_per_day']  +
        n[-3] = a_dict["scheduled_start_day"]  # * self.env.config['minutes_per_day']  +
        n[-2] = a_dict.scheduled_start_minutes  # / 1600 # 288
        n[-1] = len(a_dict.scheduled_secondary_worker_codes) + 1  # / 200 # 60 - shared count

        return n

    def decode_action_into_dict(self, action):
        """
        action[0].shape=self.config['nbr_observed_slots']
        for iii in range(1,5):
        action[iii].shape=1
        new_act = list(action[0]) + list(action[1])  + list(action[2])  + list(action[3])  + list(action[4])
        """
        raise ValueError("# DO NOT USE")
        new_act = action.copy()
        max_i = np.argmax(new_act[0: len(self.workers)])
        worker_code = self.workers[max_i].worker_code
        action_day = int(new_act[-3])
        job_start_time = (
            action_day * self.config["minutes_per_day"] + new_act[-2]
        )  # days * 1440 + minutes
        shared_count = int(new_act[-1])
        scheduled_secondary_worker_codes = []
        for i in range(1, shared_count):
            new_act[max_i] = 0
            max_i = np.argmax(new_act[0: len(self.workers)])
            scheduled_secondary_worker_codes.append(self.workers[max_i].worker_code)

        a_dict = {
            "scheduled_primary_worker_code": worker_code,
            "scheduled_secondary_worker_codes": scheduled_secondary_worker_codes,
            "scheduled_start_day": action_day,
            "scheduled_start_minutes": new_act[-2],
            "assigned_start_day_n_minutes": int(job_start_time),
            "scheduled_duration_minutes": int(new_act[-4]),
        }

        return a_dict

    # **----------------------------------------------------------------------------
    # ## Extended functions
    # **----------------------------------------------------------------------------
class ConfigurableKandboxEnvPlugin(ConfigurablePlugin):
    type = KandboxPlannerPluginType.configurable_kandbox_env
    # _schema = PluginOptionModel


class Job2SlotDispatcherPlugin(KandboxPlugin):
    type = KandboxPlannerPluginType.internal_dispatcher
    _schema = PluginOptionModel

    def load_model(self, env_config):
        pass

    def dispatch_job2slot(self, jobs, slots, order= None, env = None ):
        """ return [score, slot, job_list]"""
        raise NotImplemented("Pls call sub classes for internal_dispatcher")



class KandboxBatchOptimizerPlugin(ConfigurablePlugin):
    type = KandboxPlannerPluginType.kandbox_batch_optimizer
    _schema = PluginOptionModel

    def dispatch_jobs(self, **kwargs):
        raise NotImplementedError

    def convert_opti_jobs(self, 
        db_job_list: List[JobInSlot], 
        worker_slots_all: List[WorkingTimeSlot], 
        ctx:OptiContext,
        gen_depot_job = True
    ): 
        enable_time_window_constraint =  str(self.config.get("enable_time_window_constraint", "0"))  == "1"
        jobs_locs = [ ]
        to_verify_inplanning = set()

        ctx.worker_code2index = {}
        all_job_index=0
        for si, s in enumerate(worker_slots_all):
            ctx.worker_code2index[s.worker_code] = si
            for sj in s.assigned_jobs:
                jobs_locs.append(
                    OptiJobLoc(
                        geo_longitude = sj.geo_longitude, # end_longitude,
                        geo_latitude = sj.geo_latitude, # end_latitude,
                        node_type = "job",
                        orig_index = all_job_index,
                        code = sj.code,
                        c_weight = 0,
                        c_volume = 0,
                        c_time_window = [],
                        fixed_worker_index = si,
                        requested_duration_minutes = 1,
                        flex_form_data= sj.flex_form_data
                    )
                )
                all_job_index+=1

        ctx.location_group2worker_index = {}
        if int(self.config.get("enable_location_group_constraint", 0)) == 1:
            for lg_code in ctx.lg2worker_code.keys():
                if ctx.lg2worker_code[lg_code] in ctx.worker_code2index:
                    ctx.location_group2worker_index[lg_code] = ctx.worker_code2index[ctx.lg2worker_code[lg_code]]
            log.info(f"enable_location_group_constraint or enable_fix_planned_constraint is true, with lg={ctx.lg2worker_code}, lg2work_index: {ctx.location_group2worker_index}, ctx.worker_code2index = {ctx.worker_code2index}")

        # all_job_list = [None]
        for ji, j in enumerate(db_job_list):
            # if j.planning_status not in (JobPlanningStatus.UNPLANNED, JobPlanningStatus.IN_PLANNING, JobPlanningStatus.PLANNED):
            #     continue 
            if j.planning_status in (JobPlanningStatus.IN_PLANNING, JobPlanningStatus.PLANNED):
                if j.code in to_verify_inplanning:
                    continue
                else:
                    log.error(f"Missing_inplanning_job: { j.code} from env, planning this time. Please_check ...") 

            c_weight = math.ceil(float(j.flex_form_data.get(self.config.get("weight_constraint_code", dconfig.DEFAULT_WEIGHT_CONSTRAINT_CODE), 1))) # *1.5 
            c_volume = math.ceil(float(j.flex_form_data.get(self.config.get("volume_constraint_code", dconfig.DEFAULT_VOLUME_CONSTRAINT_CODE), 1))) # *1.5
            # c_time_window = from_time_window_str_to_list( j.flex_form_data.get("time_window_list", "")) # *1.5
            if enable_time_window_constraint:
                c_time_window = ctx.env.from_time_window_flex_form_to_list(j.flex_form_data) # *1.5
            else:
                c_time_window = []
            fixed_worker_index = None
            # 2024-08-18 23:38:11, TODO, 
            # if j.planning_status == JobPlanningStatus.PLANNED:
            #     if str(self.config.get("enable_fix_planned_constraint", "0")) == "1":
            #         fixed_worker_index = ctx.worker_code2index[j.scheduled_primary_worker_code]
            #     else:
            #         log.warning(f"job: {j.code} is planned, but enable_fix_planned_constraint is not enabled. Job Skipped")
            #         # continue
            # if j.planning_status == JobPlanningStatus.IN_PLANNING:
            #     if str(j.flex_form_data.get("allow_in_planning2others", "0")) == "0":
            #         fixed_worker_index = ctx.worker_code2index[j.scheduled_primary_worker_code]
            #     else:
            #         log.warning(f"job: {j.code} is planned, but enable_fix_planned_constraint is not enabled. Job Skipped")
            #         # continue

            if int(self.config.get("enable_location_group_constraint", 0)) == 1:
                lg_code = j.flex_form_data.get('location_group_code', None)
                if lg_code:
                    if lg_code in ctx.location_group2worker_index:
                        if fixed_worker_index is not None:
                            if ctx.location_group2worker_index[lg_code] != fixed_worker_index:
                                log.error(f"{j.code} is skipped. location group {lg_code} specifying different worker {ctx.location_group2worker_index[lg_code]} than planned {fixed_worker_index}.")
                                continue
                        else:
                            fixed_worker_index = ctx.location_group2worker_index[lg_code]
                    else:
                        log.warning(f"{lg_code} is not found from location_group2worker_index.")
            skills = None
            if str(self.config.get("enable_skills", '0')) == '1':
                skill_code_str = j.flex_form_data.get('skills', "")
                if len(skill_code_str) > 0:
                    skills = ctx.convert_skills(skill_code_str.split(dconfig.SEPERATOR_FLEX_0)) 

            jobs_locs.append(
                OptiJobLoc(
                    geo_longitude = j.geo_longitude,
                    geo_latitude = j.geo_latitude,
                    node_type = "job",
                    orig_index = ji,
                    code = j.code,
                    c_weight = c_weight,
                    c_volume = c_volume,
                    c_time_window = c_time_window,
                    fixed_worker_index = fixed_worker_index,
                    requested_duration_minutes = j.scheduled_duration_minutes if j.scheduled_duration_minutes is not None else 1,
                    skills = skills,
                    flex_form_data= j.flex_form_data
                )
            )
            # ctx.job_loc_idx[j.code] = len(all_job_list)-1
            # all_job_list.append(j)
            # all_job_index +=1
        if False and (str(self.config.get("enable_return2home_constraint", "0")) == "1" or (
            str(self.config.get("enable_start_from_home_constraint", "0")) == "1"  
           )):
            for si, s in enumerate(worker_slots_all):
                if round(s.start_longitude,5) != round(ctx.depot_longlat[0],5
                ) or round(s.start_latitude,5) != round(ctx.depot_longlat[1],5):
                    if enable_time_window_constraint:
                        c_time_window = [[
                            s.start_minutes - ctx.env.get_env_start_minutes(),
                            s.end_minutes - ctx.env.get_env_start_minutes()
                        ]]
                    else:
                        c_time_window = []
                    jobs_locs.append(
                        OptiJobLoc(
                            geo_longitude = s.start_longitude, # end_longitude,
                            geo_latitude = s.start_latitude, # end_latitude,
                            node_type = "slot",
                            orig_index = si,
                            code = s.slot_code,
                            c_weight = 0,
                            c_volume = 0,
                            c_time_window = c_time_window,
                            fixed_worker_index = None,
                            requested_duration_minutes = 1,
                            flex_form_data= j.flex_form_data,
                            skills = None,
                        )
                    )
                    ctx.worker_loc_idx[s.slot_code] = len(jobs_locs) - 1
        

        # For vrp-rust, I need depot loc at the end.
        # https://reinterpretcat.github.io/vrp/concepts/pragmatic/routing/format.html
        if not gen_depot_job:
            return jobs_locs
        
        depot_job = OptiJobLoc(
            geo_longitude = ctx.depot_longlat[0],
            geo_latitude = ctx.depot_longlat[1],
            node_type = "depot",
            orig_index = 0,
            code = "depot",
            c_weight = 0,
            c_volume = 0,
            c_time_window = [],
            skills = None,
            fixed_worker_index = None
            # flex_form_data={}
        )
        if ctx.depot_at_head:
            jobs_locs =  [depot_job] + jobs_locs
        else:
            jobs_locs.append(depot_job)
        return jobs_locs

class KandboxSimpleOptimizerPlugin(Plugin):
    type = KandboxPlannerPluginType.kandbox_simple_optimizer
    _schema = PluginOptionModel

    def run_optimizer(self, **kwargs):
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
    default_config = {
        "env_lang":"python" # rust for redis rules
    }

    result = {
        "score": 0,
        "message": ["Not implemented"],
    }

    def __init__(self, weight=None, config=None):
        self.weight = weight
        self.config = copy.deepcopy(self.default_config)
        if config:
            self.config.update(config) 

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

    def evalute_action_normal(self, env=None, action=None):

        # res = self.evalute_normal_single_worker_n_job(env=env, action=action)

        return {}

