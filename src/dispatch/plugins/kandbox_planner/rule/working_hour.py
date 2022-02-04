import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util


from dispatch.plugins.bases.kandbox_planner import KandboxRulePlugin
from dispatch.plugins.kandbox_planner.env.env_models import (
    Worker,
    Job,
    Appointment,
    Absence,
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
        overall_message = ""
        score = 1
        metrics_detail = {"status_code": "OK"}

        for worker_code in job.scheduled_worker_codes:
            worker = env.workers_dict[worker_code]

            day_seq = int(job.scheduled_start_minutes / 1440)
            weekday_i = env.env_encode_day_seq_to_weekday(day_seq)
            slot_in_day_count = len(worker.weekly_working_slots[weekday_i])
            slot_intersected=False
            slot_covered = False
            for slot_in_day_i, slot_in_day in enumerate(worker.weekly_working_slots[weekday_i]):
                working_slot_in_the_day = [
                    slot_in_day[0] + (24 * 60 * day_seq),
                    slot_in_day[1] + (24 * 60 * day_seq),
                ]
                clipped_slot = date_util.clip_time_period(
                    p1=working_slot_in_the_day,
                    p2=[
                        job.scheduled_start_minutes,
                        job.scheduled_start_minutes + job.scheduled_duration_minutes,
                    ],
                )
                if len(clipped_slot) > 1:
                    slot_intersected = True
                    if (clipped_slot[0] == job.scheduled_start_minutes) & (
                        clipped_slot[1] == job.scheduled_start_minutes + job.scheduled_duration_minutes
                    ):
                        overall_message = self.success_message_template.format(
                            date_util.minutes_to_time_string(job.scheduled_start_minutes),
                            date_util.minutes_to_time_string(
                                job.scheduled_start_minutes + job.scheduled_duration_minutes
                            ),
                            job.scheduled_start_minutes,
                            job.scheduled_start_minutes + job.scheduled_duration_minutes,
                        )
                        # move on to next worker
                        slot_covered = True
                        break
            if slot_covered:
                continue
            available_overtime = env.get_worker_available_overtime_minutes(
                worker_code=worker_code, day_seq=day_seq
            )
            # if self.config["allow_overtime"]:
            if slot_intersected & (available_overtime > 0):
                start_with_overtime = working_slot_in_the_day[0]
                if slot_in_day_i ==0:
                    start_with_overtime -= available_overtime

                end_with_overtime = working_slot_in_the_day[1]
                if slot_in_day_i == slot_in_day_count - 1:
                    end_with_overtime += available_overtime


                if (
                    ( 
                        start_with_overtime < job.scheduled_start_minutes
                    ) & (
                        end_with_overtime > job.scheduled_start_minutes + job.scheduled_duration_minutes
                    ) & (
                        working_slot_in_the_day[1]
                        - working_slot_in_the_day[0]
                        + available_overtime
                        > job.scheduled_duration_minutes
                    )
                ):
                    score = 0
                    overall_message = self.overtime_allowed_message_template.format(
                        date_util.minutes_to_time_string(job.scheduled_start_minutes),
                        date_util.minutes_to_time_string(
                            job.scheduled_start_minutes + job.scheduled_duration_minutes
                        ),
                        job.scheduled_start_minutes,
                        job.scheduled_start_minutes + job.scheduled_duration_minutes,
                        available_overtime,
                    )
                    # move on to next worker
                    print(overall_message)
                    continue
            
            # If the time slot were ok (i.e. included in any slot), it should have been skipped by continue  
            # If the start time does not fully fall in one working slot for any worker, reject it instantly.
            score = -1
            overall_message = self.message_template.format(
                date_util.minutes_to_time_string(job.scheduled_start_minutes),
                date_util.minutes_to_time_string(
                    job.scheduled_start_minutes + job.scheduled_duration_minutes
                ),
                job.scheduled_start_minutes,
                job.scheduled_start_minutes + job.scheduled_duration_minutes,
                available_overtime,
            )
            return ActionEvaluationScore(
                score=score,
                score_type=self.title,
                message=overall_message,
                metrics_detail={"status_code": "ERROR"},
            )

        return ActionEvaluationScore(
            score=score,
            score_type=self.title,
            message=overall_message,
            metrics_detail=metrics_detail,
        )
