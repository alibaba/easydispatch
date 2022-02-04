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


class KandboxRulePluginLunchBreak(KandboxRulePlugin):

    """
    Has the following members
    """

    # rule_code = "lunch_hour_break"
    # rule_name = "30 minutes between 12:00-14:00"

    title = "Lunch Break"
    slug = "kandbox_rule_lunch_break"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Rule lunch_hour_break for GYM for RL."
    version = "0.1.0"

    default_config = {
        "lunch_break_minutes":30,
        "lunch_start_hour":12,
        "lunch_end_hour":14,
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "lunch_break_minutes": {
                "type": "number",
                "default": 30,
                "title": "Lunch break Minutes (integer)"
            },
            "lunch_start_hour": {
                "type": "number",
                "default": 12,
                "title": "Minimum start hour (integer)"
            },
            "lunch_end_hour": {
                "type": "number",
                "default": 14,
                "title": "Maximum start hour (integer)"
            },
        },
    }

    def evalute_normal_single_worker_n_job(self, env=None, job=None):  # worker = None,
        # action_dict = env.decode_action_into_dict(action)
        # if (action_dict['scheduled_start_minutes'] > 14*60 ) | (action_dict['scheduled_start_minutes'] + action_dict['scheduled_duration_minutes']< 12*60  ):
        # scheduled_start_minutes_local = job.scheduled_start_minutes % (24 * 60) 
        score = 1
        metrics_detail = {"status_code": "OK"}

        action_day = int(job.scheduled_start_minutes / 24 / 60)

        job_lunch_start = action_day * 24 * 60 + (self.config["lunch_start_hour"] * 60)
        job_lunch_end = action_day * 24 * 60 + (self.config["lunch_end_hour"] * 60)
        overlap_lunch = date_util.clip_time_period(
            [job_lunch_start, job_lunch_end],
            [
                job.scheduled_start_minutes,
                job.scheduled_start_minutes + job.scheduled_duration_minutes,
            ],
        )
        if len(overlap_lunch) < 1:
            overall_message = "The Job is not at lunch time"

            score_res = ActionEvaluationScore(
                score=score,
                score_type=self.title,
                message=overall_message,
                metrics_detail=metrics_detail,
            )
            return score_res

        overall_message = f"Lunch break > {self.config['lunch_break_minutes']} minutes"
        # scheduled_start_minutes = job.scheduled_start_minutes
        job_start_minutes = job.scheduled_start_minutes
        job_end_minutes = job.scheduled_start_minutes + job.scheduled_duration_minutes

        # for job_i in range(len(env.workers_dict[worker_code]["assigned_jobs"])):
        # for worker_id in [job.scheduled_worker_codes[0]] + job["scheduled_secondary_worker_ids"]:
        for worker_id in job.scheduled_worker_codes:

            total_avail_lunch_break = job_lunch_end - job_lunch_start
            overlapped_slots = env.slot_server.get_overlapped_slots(
                worker_id=worker_id, start_minutes=job_start_minutes, end_minutes=job_end_minutes
            )
            # all_jobs = reduce(lambda x, y: x.assigned_job_codes + y.assigned_job_codes, overlapped_slots)

            for a_slot in overlapped_slots:

                (
                    prev_travel,
                    next_travel,
                    inside_travel,
                ) = env.get_travel_time_jobs_in_slot(a_slot, a_slot.assigned_job_codes)
                all_prev_travel_minutes = [prev_travel] + inside_travel  # + inside_travel
                if a_slot.slot_type == TimeSlotType.JOB_FIXED:
                    total_avail_lunch_break -= (
                        prev_travel +
                        # env.jobs_dict[job.job_code].scheduled_duration_minutes
                        job.scheduled_duration_minutes
                    )
                elif a_slot.slot_type == TimeSlotType.FLOATING:
                    for job_seq, job_code in enumerate(a_slot.assigned_job_codes):
                        a_job = env.jobs_dict[job_code]
                        a_job_period = [
                            a_job.scheduled_start_minutes - all_prev_travel_minutes[job_seq],
                            a_job.scheduled_start_minutes + a_job.scheduled_duration_minutes,
                        ]
                        a_job_period_lunch_overlap = date_util.clip_time_period(
                            [job_lunch_start, job_lunch_end], a_job_period
                        )
                        if len(a_job_period_lunch_overlap) > 1:
                            total_avail_lunch_break -= (
                                a_job_period_lunch_overlap[1] - a_job_period_lunch_overlap[0]
                            )
                else:
                    # raise LookupError("unknown slot type - E?")
                    pass  # lunch break in dairy events/absence

            if total_avail_lunch_break < self.config["lunch_break_minutes"]:
                # For now, lunch break does not enforce to -1, lowest is 0, as warning
                score = 0
                overall_message = f"total_avail_lunch_break = {total_avail_lunch_break}, which is less than MINIMUM({self.config['lunch_break_minutes']}) for worker {worker_id}"

        score_res = ActionEvaluationScore(
            score=score,
            score_type=self.title,
            message=overall_message,
            metrics_detail=metrics_detail,
        )
        return score_res
