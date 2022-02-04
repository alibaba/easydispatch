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
        overall_message = "Job ({}) requires items ({}) on workers {}. \n".format(
            job.job_code, job.requested_items, job.scheduled_worker_codes
        )
        metrics_detail = {"status_code": "OK"}
        total_loaded_items = {
            k:0
            for k in job.requested_items.keys()
        } 

        total_requested_items = dict(job.requested_items)
        inspected_jobs  = set()
        
        all_slots = []
        # First I aggregate all items from all workers
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

            # It should match only one, but if more, I take only first one.
            for jc in slot.assigned_job_codes:
                if jc in inspected_jobs:
                    # This should be summerized only once for more workers.
                    # Skip from this loop
                    continue
                else:
                    inspected_jobs.add(jc)
                    # move on to check
                r_items = env.jobs_dict[jc].requested_items
                for ik in r_items.keys():
                    if ik not in total_requested_items.keys():
                        total_requested_items[ik] =r_items[ik]
                    else:
                        total_requested_items[ik] +=r_items[ik]

                    if ik not in total_loaded_items.keys():
                        total_requested_items[ik] = 0


            # all_slots[0] is the first worker slot, i.e. primary
            all_slots.append(slot)
            # TODO check item_keys match as set, which should be faster.
            for k in slot.loaded_items.keys():
                if k in total_loaded_items.keys():
                    total_loaded_items[k] +=slot.loaded_items[k]

        # Second I verify that aggregated items list can fulfil job requirement
        # TODO, duan, 2021-10-23 22:13:35. I should loop through all depots in future.
        depot_key = list(env.depots_dict.keys())[0]
        inventory_dict = env.kp_data_adapter.get_depot_item_inventory_dict(
            depot_id = env.depots_dict[depot_key]["id"],
            requested_items = list(total_requested_items.keys())
            )
        # loaded_items_key_set = set(total_loaded_items.keys())
        for item_key in job.requested_items:
            item_qty = total_loaded_items[item_key]
            # if item_key in loaded_items_key_set:
            #     item_qty = total_loaded_items[item_key]

            if job.requested_items[item_key]  > item_qty:
                if job.requested_items[item_key] > inventory_dict[item_key]:
                    # This items is also NOT available in depot/warehouse
                    overall_message += ", requested {} > {}; but only {} found on workers {}, and {} found in depot!".format(
                        item_key,   
                        job.requested_items[item_key],
                        item_qty,
                        job.scheduled_worker_codes,
                        inventory_dict[item_key]
                    )
                    score = -1
                    metrics_detail = {"item":  item_key, "status_code":"ERROR" }
                    break
                else:
                    # This items IS available in depot/warehouse. 
                    # Then I will add a virtual replenish job and move on.
                    # The replenish job is only added to primary worker as all_slots[0]
                    # replenish_job = env.mutate_create_replenish_job(slot = all_slots[0], total_loaded_items = total_loaded_items)
                    # if replenish_job is None:
                    #     overall_message += ", requested {} > {}; only {} found on workers {}, and failed insert replenish job!".format(
                    #         item_key,   
                    #         job.requested_items[item_key],
                    #         item_qty,
                    #         job.scheduled_worker_codes, 
                    #     )
                    #     score = -1
                    #     metrics_detail = {"item":  item_key, "status_code":"ERROR" }
                    #     break


                    overall_message += ", requested {} > {}; only {} found on workers {}, and a replenishment job is needed!".format(
                        item_key,   
                        job.requested_items[item_key],
                        item_qty,
                        job.scheduled_worker_codes, 
                    )
                    score = 0
                    metrics_detail = {
                        "item":  item_key, 
                        "status_code":"WARNING",
                        # "slot_code":env.slot_server.get_time_slot_key(slot),
                        "slot":slot,
                        "total_requested_items":total_requested_items,
                        "total_loaded_items":total_loaded_items,
                         }
                    # allows to move on

                # Move on to check next item.
                # break

        score_res = ActionEvaluationScore(
            score=score,
            score_type=self.title,
            message=overall_message,
            metrics_detail=metrics_detail,
        )
        return score_res
