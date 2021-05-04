import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util


from dispatch.plugins.bases.kandbox_planner import KandboxRulePlugin


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
    message_template = "Job time ({}-{}) is out of working hour"

    default_config = {
        "allow_overtime": False,
        #
        "overtim_minutes": 180,
    }
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

    def evalute_normal_single_worker_n_job(self, env=None, job=None):  # worker = None,
        worker = env.workers_dict[job["scheduled_primary_worker_id"]]
        result = {
            "score": 0,
            "message": "Job is between start and end time of the worker",
        }

        # return score, violated_rules (negative values)
        # return self.weight * 1
        for day_i, working_slot in enumerate(worker["working_minutes"]):
            working_slot_with_day = [
                working_slot[0] + (24 * 60 * day_i),
                working_slot[1] + (24 * 60 * day_i),
            ]
            cliped_slot = date_util.clip_time_period(
                p1=working_slot_with_day,
                p2=[
                    job["assigned_start_minutes"],
                    job["assigned_start_minutes"] + job["scheduled_duration_minutes"],
                ],
            )
            if len(cliped_slot) > 1:
                if (cliped_slot[0] == job["assigned_start_minutes"]) & (
                    cliped_slot[1] ==
                    job["assigned_start_minutes"] + job["scheduled_duration_minutes"]
                ):
                    result["score"] = 1
                    return result
                # Partial fit, reject for now #TODO
                result["score"] = -1
                result["message"] = self.message_template.format(
                    date_util.minutes_to_time_string(job["assigned_start_minutes"]),
                    date_util.minutes_to_time_string(
                        job["assigned_start_minutes"] + job["scheduled_duration_minutes"]
                    ),
                )
                return result

            else:
                continue
        # If the start time does not fall in working hour, reject it.
        result["score"] = -1
        result["message"] = self.message_template.format(
            job["assigned_start_minutes"],
            job["assigned_start_minutes"] + job["scheduled_duration_minutes"],
        )
        return result
