from dispatch.plugins.kandbox_planner.env.configurable_dispatch_env import ConfigurableDispatchEnv
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util
from dispatch.plugins.bases.kandbox_planner import KandboxRulePlugin
from dispatch.plugins.kandbox_planner.env.env_enums import *
from dispatch.plugins.kandbox_planner.env.env_models import (
    ActionDict,
    LocationTuple,
    JobLocation,  
    ActionEvaluationScore,
)

from dispatch.plugins.kandbox_planner.env.env_enums import TimeSlotType
import copy

class KandboxRulePluginRequestedItem(KandboxRulePlugin):

    """
    Item (material) check.
    Items are the materials/tools/assets requested for performing the job.
    """

    title = "Requested Items"
    slug = "kandbox_rule_requested_items"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Rule. Material"
    version = "0.1.0"

    default_config = copy.copy(KandboxRulePlugin.default_config)
    # { 
    # }
    config_form_spec = {
        "type": "object",
        "properties": {  },
    }

    def evalute_action_normal(self, env:ConfigurableDispatchEnv, action:ActionDict):
        # return score, violated_rules (negative values)
        # return self.weight * 1
        # Now check if this new job can fit into existing
        job = action.jobs[0]
        score = 1
        assert False, ("Wrong, deprecated by jobinslot.flex_form_data")
        overall_message = "Job ({}) requires items ({}) on workers {}. \n".format(
            job.code, job.requested_items, action.scheduled_worker_codes
        )
        metrics_detail = {"status_code": "OK"}
        total_requested_items = dict()
        for k_v in job.requested_items:
            k,v = k_v.split(":")
            total_requested_items[k] = float(v)
        
        all_slots = []
        # First I aggregate all items from all workers
        for worker_code in action.scheduled_worker_codes:
            overlapped_slots = env.get_working_slot_list(
                worker_code=worker_code,active_only=True,
                start_minutes=action.scheduled_start_minutes - 1,
                end_minutes=action.scheduled_start_minutes + 1,
                ) 
            if len(overlapped_slots) < 1:
                overall_message += " but no slot was found!" 
                score = -1
                # metrics_detail = {}
                break
            slot = overlapped_slots[0] 
            _free_items = slot.accum_items
            # It should match only one, but if more, I take only first one.
            for ik_str in total_requested_items.keys():
                ik = ik_str.encode('utf-8')
                if ik not in _free_items.keys():
                    overall_message += f" But product {ik} was not found in slot {slot.slot_code}!" 
                    score = -1
                    # metrics_detail = {}
                    break
                else:
                    item_qty = float(_free_items[ik])
                    if item_qty < total_requested_items[ik_str]:
                        overall_message += f" But product {ik}={_free_items[ik]} is less than requested={total_requested_items[ik_str]} on slot {slot.slot_code}!" 
                        score = -1
                        break
                    else:
                        overall_message += f"{ik}={_free_items[ik]} >= requested={total_requested_items[ik_str]}, !" 
            else:
                overall_message += f" slot {slot.slot_code} can fulfill job {job.code}!" 

        score_res = ActionEvaluationScore(
            score=score,
            score_type=self.title,
            message=overall_message,
            metrics_detail=metrics_detail,
        )
        return score_res
