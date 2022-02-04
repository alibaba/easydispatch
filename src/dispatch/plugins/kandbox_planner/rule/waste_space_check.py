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

class KandboxRulePluginWasteSpace(KandboxRulePlugin):

    """
    Has the following members
    """

    title = "Waste Space"
    slug = "kandbox_rule_waste_space_check"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Rule. Waste"
    version = "0.1.0"

    default_config = { 
    }
    config_form_spec = {
        "type": "object",
        "properties": {  },
    }

    def evalute_normal_single_worker_n_job(self, env, job=None):  # worker = None,
        # return score, violated_rules (negative values)
        # return self.weight * 1
        # Now check if this new job can fit into existing

        score = 1
        job_requested_items = job.requested_items
        requested_volume = sum([
            job_requested_items[item_key] * env.items_dict[item_key]["volume"]
            for item_key in job_requested_items.keys()
          ])
        requested_weight = sum([
            job_requested_items[item_key] * env.items_dict[item_key]["weight"]
            for item_key in job_requested_items.keys()
          ])

        overall_message = "Job ({}) produces waste of volume ({}), weight ({}). ".format(
            job.job_code, requested_volume, requested_weight
        )
        metrics_detail = {"status_code": "OK"}
        
        if (requested_volume < 0 ) or (requested_weight < 0):
        
            worker_code = job.scheduled_worker_codes[0] 
            overlapped_slots = env.slot_server.get_overlapped_slots(
                worker_id=worker_code, 
                start_minutes=job.scheduled_start_minutes, 
                end_minutes=job.scheduled_start_minutes + job.scheduled_duration_minutes
            )

            if len(overlapped_slots) < 1:
                overall_message += " but no slot was found!" 
                score = -1
                metrics_detail = {} 
            else:
                slot = overlapped_slots[0]  

                spare_weight =slot.max_weight - sum([
                    slot.loaded_items[item_key] * env.items_dict[item_key]["weight"]
                    for item_key in slot.loaded_items.keys()
                ])
                spare_volume =slot.max_weight - sum([
                    slot.loaded_items[item_key] * env.items_dict[item_key]["volume"]
                    for item_key in slot.loaded_items.keys()
                ])

                if (spare_weight +  requested_weight < 0) or (spare_volume +  requested_volume < 0):
                    overall_message += ", slot spare weight {} and  spare volume {} are found!".format(
                        spare_weight,   
                        spare_volume, 
                    )
                    score = -1
                    metrics_detail = {  } 
        else:
            overall_message = "Job ({}) produces no waste.".format(
                job.job_code 
            )
        score_res = ActionEvaluationScore(
            score=score,
            score_type=self.title,
            message=overall_message,
            metrics_detail=metrics_detail,
        )
        return score_res
