import copy
from dispatch.plugins.kandbox_planner.env.configurable_dispatch_env import ConfigurableDispatchEnv
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util


from dispatch.plugins.bases.kandbox_planner import KandboxRulePlugin
from dispatch.plugins.kandbox_planner.env.env_models import (
    ActionDict,
    # Worker,
    # Job,
    # Appointment,
    # Absence,
    ActionEvaluationScore,
)


class KandboxRulePluginWithinWorkingHour(KandboxRulePlugin):
    """
    Has the following members
    """

    title = "Within Working Hour"
    slug = "kandbox_rule_within_working_hour"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Env for GYM for RL."
    version = "0.1.0"

    # rule_code = "within_working_hour"
    # rule_name = "Job is between start and end time of the worker"
    message_template = "Job time ({}-{}) ({}-{}) is out of working hour, available overtime = {} minutes "
    success_message_template = "Job time ({}-{}) ({}-{}) is within working hour"
    overtime_allowed_message_template = (
        "Job time ({}-{}) ({}-{}) is not in working hour, but overtime ({} mins) allows it"
    )
    default_config = copy.copy(KandboxRulePlugin.default_config)


    default_config.update({
        "allow_overtime": False,
        #
        "overtim_minutes": 180,
    })
    config_form_spec = {
        "type": "object",
        "properties": {
            "allow_overtime": {
                "type": "boolean",
                "description": "This affects timing, allow_overtime.",
            },
            "overtim_minutes": {"type": "number", "title": "Number of minutes for overtim_minutes"},
        },
    }

    def evalute_action_normal(self, env:ConfigurableDispatchEnv, action:ActionDict):
        job = action.jobs[0]
        overall_message = ""
        score = 1
        metrics_detail = {"status_code": "OK"}

        for worker_code in action.scheduled_worker_codes:
            overlapped_slots = env.get_working_slot_list(
                worker_code=worker_code,
                active_only=False,
                start_minutes=action.scheduled_start_minutes - 1,
                end_minutes=action.scheduled_start_minutes + 1,
                ) 
            for slot in overlapped_slots:
                if slot.end_minutes < action.scheduled_start_minutes or slot.start_minutes > action.scheduled_start_minutes:
                    continue
                overall_message += f"Slot {slot.slot_code} was found at time {str(env.env_decode_from_minutes_to_datetime(action.scheduled_start_minutes))}!" 
                score_res = ActionEvaluationScore(
                    score=score,
                    score_type=self.title,
                    message=overall_message,
                    metrics_detail=metrics_detail,
                )
                return score_res
            else:   # if len(overlapped_slots) < 1:
                overall_message += f"No slot was found at time {str(env.env_decode_from_minutes_to_datetime(action.scheduled_start_minutes))}! Note: Overtime not implemented" 
                score = -1
                return ActionEvaluationScore(
                    score=score,
                    score_type=self.title,
                    message=overall_message,
                    metrics_detail={"status_code": "ERROR"},
                )
        score_res = ActionEvaluationScore(
            score=score,
            score_type=self.title,
            message=overall_message,
            metrics_detail=metrics_detail,
        )
        return score_res