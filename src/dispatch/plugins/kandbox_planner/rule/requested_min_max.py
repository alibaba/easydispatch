import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util
from dispatch.plugins.bases.kandbox_planner import KandboxRulePlugin
from dispatch.plugins.kandbox_planner.env.env_enums import *
from dispatch.plugins.kandbox_planner.env.env_models import (
    ActionDict,
    LocationTuple,
    JobLocation,
    Worker,
    ActionEvaluationScore,
)

from dispatch.plugins.kandbox_planner.env.env_enums import TimeSlotType

class KandboxRulePluginRequestedMinMax(KandboxRulePlugin):

    """
    Has the following members
    """

    # rule_code = "lunch_hour_break"
    # rule_name = "30 minutes between 12:00-14:00"

    title = "DateTime Tolerance" # "Requested Start Date Time Range Check"
    slug = "kandbox_rule_requested_min_max"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Rule. Requested Start Date Time Range Check"
    version = "0.1.0"

    default_config = { 
    }
    config_form_spec = {
        "type": "object",
        "properties": {  },
    }

    def evalute_normal_single_worker_n_job(self, env=None, job=None):  # worker = None,
        # action_dict = env.decode_action_into_dict(action)
        # if (action_dict['scheduled_start_minutes'] > 14*60 ) | (action_dict['scheduled_start_minutes'] + action_dict['scheduled_duration_minutes']< 12*60  ):
        # scheduled_start_minutes_local = job.scheduled_start_minutes % (24 * 60) 
        score = 1
        metrics_detail = {"status_code": "OK"}

        # scheduled_start_minutes = job.scheduled_start_minutes
        # job_start_minutes = job.scheduled_start_minutes
        # job_end_minutes = job.scheduled_start_minutes + job.scheduled_duration_minutes

        requested_start = job.requested_start_min_minutes
        requested_end = job.requested_start_max_minutes
        clipped_slot = date_util.clip_time_period(
            [requested_start, requested_end],
            [
                job.scheduled_start_minutes,
                job.scheduled_start_minutes + job.scheduled_duration_minutes,
            ],
        )
        overall_message =  f"Scheduled minutes {job.scheduled_start_minutes} is outside of requested range ( {requested_start} ~ {requested_end})"
        score = -1

        if len(clipped_slot) > 0:
            if (clipped_slot[0] == job.scheduled_start_minutes) & (
                clipped_slot[1] == job.scheduled_start_minutes + job.scheduled_duration_minutes
            ):
                overall_message =  f"Scheduled minutes {job.scheduled_start_minutes} is inside the requested range ( {requested_start} ~ {requested_end})"
                score = 1

        score_res = ActionEvaluationScore(
            score=score,
            score_type=self.title,
            message=overall_message,
            metrics_detail=metrics_detail,
        )
        return score_res

