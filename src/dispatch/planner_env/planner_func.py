
import json
from typing import List
from dispatch.plugins.kandbox_planner.agent.pickdrop_realtime_rt5_vroom import PickdropVroomRealtimeAgentPlugin
from dispatch.plugins.kandbox_planner.agent.pickdrop_realtime_rt1_pomo_n2s import  PickdropPOMON2SRealtimeAgentPlugin
from dispatch.plugins.kandbox_planner.agent.single_realtime_rt3 import SingleVroomRealtimeAgentPlugin
from dispatch.plugins.kandbox_planner.agent.pomo_online_realtime_agent import POMOOnlineRTAgent
from dispatch.plugins.kandbox_planner.agent.kandbox_heuristic_realtime_agent import KandboxHeuristicRealtimeAgentPlugin
from dispatch.plugins.kandbox_planner.agent.single_realtime_rt4 import SinglePOMON2SRealtimeAgentPlugin

# from dispatch.plugins.kandbox_planner.env.configurable_dispatch_env import ConfigurableDispatchEnv
# from dispatch.plugins.kandbox_planner.env.env_models import JobInSlot, WorkingTimeSlot
from dispatch.planner_env.planner_service import  get_active_planner 
import redis
from dispatch.config import redis_pool

from datetime import datetime



import logging
log = logging.getLogger("planner_func")

class MultiplexPlannerHub:
    """ For slot attention model v1. 2021-07-17 15:30:22
    """
    title = "Kandbox Plugin - MultiplexPlannerHub"
    slug = "multiplex_planner_hub"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "multiplex_planner_hub."
    version = "0.1.0"
    default_config = { 
        "a": 1,
    }
    def __init__(self, config=None):
        self.config = self.default_config.copy()
        if config is not None:
            self.config.update(config)
        rt1_config = {
            "job2slot_model_path": "$ROOT/ed_model/pomo_n2s/enu/20230908_144215_pickdrop_pomo_n2s_checkpoint_11770_score5.pt"
        }

        rt4_config = {
            "job2slot_model_path": "/home/dispatch/git/easydispatch/online_models/us_la_haversine_20231103_234048_single_job2slot_n2s_checkpoint_2760_score899.pt"
        }


        self.rt_planner_dict={
            "rt1": PickdropPOMON2SRealtimeAgentPlugin(config = rt1_config),
            "rt2": None, # POMOOnlineRTAgent(),
            "rt3": SingleVroomRealtimeAgentPlugin(),
            "rt4": SinglePOMON2SRealtimeAgentPlugin(config = rt4_config),
            "rt5": PickdropVroomRealtimeAgentPlugin(config = rt4_config),
            "heur": KandboxHeuristicRealtimeAgentPlugin()
        }

        self.redis_conn = redis.Redis(connection_pool=redis_pool)

    def process_message(self, message_str): 
        dispatch_request = json.loads(message_str)
        dispatcher = self.rt_planner_dict[dispatch_request["algo"]]
        job_code = dispatch_request["id"]

        env = get_active_planner(
            org_id=int(dispatch_request["org"]),
            team_id=int(dispatch_request["team"]),
            force_reload=False,
        )
        env_jobs = env.decode_working_slot_assigned_jobs(dispatch_request["jobs"])
        decoded_slots = [
            env.decode_str_2_working_slot(s)
            for s in dispatch_request["slots"]]

        dispatch_result = dispatcher.dispatch2slot(
            env = env,
            env_jobs = env_jobs,
            slots = decoded_slots,
        )
        mapping = {}
        for solution in dispatch_result:
            solution["slots"] = [
                env.encode_working_slot_2_str(s)
                for s in solution["slots"]
            ]
            mapping[json.dumps(solution)] = solution["score"]
        # for   in  dispatch_result:
        if len(mapping) > 0:
            zset_key = env.get_redis_key_result_name_realtime(job_code)
            self.redis_conn.zadd(name = zset_key, mapping = mapping)
            self.redis_conn.expire(name = zset_key, time=120)

        self.redis_conn.lpush(env.get_redis_key_result_notify_realtime(job_code), dispatch_request["algo"])
        self.redis_conn.expire(name = env.get_redis_key_result_notify_realtime(job_code), time=60)

        log.info("Rec_job_finished_for {} with {} solutions by {} at {}".format(
            job_code,
            len(dispatch_result),
            dispatch_request["algo"],
            datetime.now(),
        ))