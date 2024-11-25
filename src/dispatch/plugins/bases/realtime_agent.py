from typing import List
from dispatch.models import PluginOptionModel
from dispatch.plugins.base.v1 import ConfigurablePlugin
from dispatch.plugins.kandbox_planner.env.env_enums import KandboxPlannerPluginType 
from dispatch.plugins.bases.kandbox_planner import   KandboxBatchOptimizerPlugin
# from dispatch.plugins.kandbox_planner.env.configurable_dispatch_env import ConfigurableDispatchEnv
from dispatch.job import service as job_service
from dispatch.plugins.kandbox_planner.env.configurable_dispatch_env import ConfigurableDispatchEnv
from dispatch.plugins.kandbox_planner.env.env_enums import ActionType
from dispatch.plugins.kandbox_planner.env.env_models import EnvAction, JobInSlot, RecommendedAction, WorkingTimeSlot

import logging
log = logging.getLogger("realtime_agent")


class KandboxAgentPlugin(KandboxBatchOptimizerPlugin):
    enabled = True
    required = False
    multiple = False
    config = None

    type = KandboxPlannerPluginType.kandbox_agent
    _schema = PluginOptionModel

    def load_model(self, env_config):
        pass

    def dispatch2slot(
        self,
        env, 
        env_jobs: List[JobInSlot],
        slots:List[WorkingTimeSlot],
        dist_list = None,
        dist_matrix = None
    ) -> List[dict]:
        raise NotImplemented("Pls call sub classes for KandboxAgentPlugin")

    def predict_action_dict_list(self, env:ConfigurablePlugin=None, job_code=None, db_session=None): 
        if env is None:
            env = self.env
        else:
            self.env = env
        reason_info = {}
        if job_code is None:
            log.error("job_code can not be None")
            return []
        curr_job = job_service.get_by_code(db_session = db_session, code=job_code)
        
        env_job = env.env_encode_single_job_db(curr_job)
        nearby_slots, dist_list, reason_info = env.get_nearby_slots(
            loc=[curr_job.geo_longitude, curr_job.geo_latitude, ],
            worker_blacklist = [],
            worker_whitelist = [],
            overwrite_max_orders_limit = False,
            area_code = curr_job.flex_form_data.get("area_code","A"),
            return_on_first_priority_worker = False,
            drop_off_location = None,
            order_info = curr_job.code,
            # min_free_items=env_job.requested_items,
            radius_max_meters = 100_000,
        )
        dispatched_result = self.dispatch2slot(
            env = env,
            env_jobs=[env_job],
            slots = nearby_slots,
            dist_list = dist_list,
        ) 
        result_rec_list = []
        for si, solution in enumerate(dispatched_result):
            slot = solution["slots"][0]
            reason_info.update({
                "travel_minutes_differance": solution["score"],
                "algo": solution["algo"],
            })

            a_rec = RecommendedAction(
                job_code=curr_job.code,
                scheduled_worker_codes=[slot.worker_code],
                scheduled_start_minutes=solution["start_minutes"],
                scheduled_duration_minutes=max(curr_job.scheduled_duration_minutes,1),
                score=solution["score"],
                score_detail=reason_info,
                scoped_slot_code_list=[slot.slot_code],
                job_plan_in_scoped_slots=[],
                unplanned_job_codes=[],
            )

            result_rec_list.append(a_rec)
            if len(result_rec_list) > self.config["nbr_of_actions"] : # 5
                break
        return result_rec_list ,reason_info


    def predict_action_list_for_virtual(self, env:ConfigurableDispatchEnv=None, job =None, db_session=None):
        """Search for actions for any given job in an env.
        """
        if env is None:
            env = self.env
        else:
            self.env = env

        if job  is None:
            log.error("job can not be None")
            return []
        curr_job = job
        env_job = env.env_encode_single_job_db(curr_job)
        nearby_slots, dist_list , reason_info = env.get_nearby_slots(
            loc=[curr_job.geo_longitude, curr_job.geo_latitude, ],
            worker_blacklist = [],
            worker_whitelist = [],
            overwrite_max_orders_limit = False,
            area_code = curr_job.flex_form_data.get("area_code","A"),
            return_on_first_priority_worker = False,
            drop_off_location = None,
            order_info = curr_job.code,
            # min_free_items=env_job.requested_items,
            radius_max_meters = 100_000,
        )
        dispatched_result = self.dispatch2slot(
            env = env,
            env_jobs=[env_job],
            slots = nearby_slots,
            dist_list = dist_list,
        )
        result_rec_list = []
        for si, solution in enumerate(dispatched_result):
            slot = solution["slots"][0]
            reason_info.update({
                "selected_slot":slot.slot_code,
                "travel_minutes_differance": solution["score"],
                "algo": solution["algo"],
            })

            a_rec = RecommendedAction(
                job_code=curr_job.code,
                scheduled_worker_codes=[slot.worker_code],
                scheduled_start_minutes=solution["start_minutes"],
                scheduled_duration_minutes=max(curr_job.scheduled_duration_minutes,1),
                score=solution["score"],
                score_detail=reason_info,
                scoped_slot_code_list=[slot.slot_code],
                job_plan_in_scoped_slots=[j.to_result(env=env) for j in slot.assigned_jobs],
                unplanned_job_codes=[],
            )

            result_rec_list.append(a_rec)
            if len(result_rec_list) > self.config["nbr_of_actions"] : # 5
                break
        return result_rec_list

    def predict_action(self, env: ConfigurableDispatchEnv, todo_action: EnvAction, db_session = None): 
        reason_info = {}
        if len(todo_action.jobs) in (1,2,):
            nearby_slots, dist_list ,reason_info= env.recall(
                todo_action = todo_action, 
            )

        else: #  (len(todo_action.jobs) < 1) or (len(todo_action.jobs) > 2):
            # Failed.
            log.error(f"error, 500: len_todo_action_jobs == {len(todo_action.jobs)} is_not_supported")
            todo_action.action_type = ActionType.TODO
            return todo_action,reason_info

        


        _env_jobs = [
            env.env_encode_single_job_db(cj)
            for cj in todo_action.jobs]
        dispatched_result = self.dispatch2slot(
            env = env,
            env_jobs= _env_jobs,
            slots = nearby_slots,
            dist_list = dist_list,
        ) 
        for si, solution in enumerate(dispatched_result):
            slot = solution["slots"][0]
            reason_info.update({
                "selected_slot":slot.slot_code,
                "travel_minutes_differance": solution["score"],
                "algo": solution["algo"],
            })

            todo_action.scheduled_slots = solution["slots"]
            todo_action.action_type = ActionType.FLOATING
            todo_action.score = solution["score"]
            return todo_action ,reason_info
            
        else:
            todo_action.action_type = ActionType.TODO
            return todo_action,reason_info
