import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util
from dispatch.plugins.bases.kandbox_planner import KandboxRulePlugin
from dispatch.plugins.kandbox_planner.env.env_enums import *
from dispatch.plugins.kandbox_planner.env.env_models import (
    ActionDict,
    LocationTuple,
    JobLocation,
    Worker,
    Job,
    Appointment,
    Absence,
    ActionEvaluationScore,
)

from dispatch.plugins.kandbox_planner.env.env_enums import TimeSlotType

class KandboxRulePluginVehicleType(KandboxRulePlugin):

    """
    Has the following members
    """ 
    title = "Requested Vehicle"
    slug = "kandbox_rule_vehicle_type"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Rule. Requested Vehicle"
    version = "0.1.0"

    default_config = { 
    }
    config_form_spec = {
        "type": "object",
        "properties": {  },
    }

    def evalute_normal_single_worker_n_job(self, env=None, job=None):  # worker = None,

        score = 1
        requested_vehicle_type = job.flex_form_data["requested_vehicle_type"] 
        overall_message = "Job ({}) requests {}. ".format(
            job.job_code, requested_vehicle_type 
        )
        metrics_detail = {"status_code": "OK"}

        for worker_code in job.scheduled_worker_codes:
            worker = env.workers_dict[worker_code]
            overlapped_slots = env.slot_server.get_overlapped_slots(
                worker_id=worker_code, 
                start_minutes=job.scheduled_start_minutes, 
                end_minutes=job.scheduled_start_minutes + job.scheduled_duration_minutes
            )
            if len(overlapped_slots) < 1:
                overall_message += " but no slot was found!" 
                score = -1
                metrics_detail = {}
                break
            slot = overlapped_slots[0]
            if requested_vehicle_type != slot.vehicle_type:
                overall_message += " ,  worker has {} only {}!".format(
                        worker_code,    
                        slot.vehicle_type
                    )
                score = -1
                metrics_detail = {"less_value":  slot.vehicle_type }
                break

        score_res = ActionEvaluationScore(
            score=score,
            score_type=self.title,
            message=overall_message,
            metrics_detail=metrics_detail,
        )
        return score_res

