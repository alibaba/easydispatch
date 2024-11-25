import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util

from dispatch.plugins.bases.kandbox_planner import KandboxRulePlugin

from dispatch.plugins.kandbox_planner.env.env_models import ActionEvaluationScore

class KandboxRulePluginSufficientTravelTime(KandboxRulePlugin):
    """
    Has the following members

    rule_code = "sufficient_travel_time_previous_n_next"
    rule_name = "Job is not blocked by other jobs"
    message_template = (
        "Job ({}) to Job ({}) requires {} minutes, but there are only {} minutes in between"
    )
    success_message_template = (
        "Job ({}) to Job ({}) requires {} minutes, and there are  now {} minutes."
    )
    """

    result = {
        "score": 0,
        "message": "",
        "prev_job_index": None,
        "prev_travel_time": 0,
    }

    title = "Enough Travel"
    slug = "kandbox_rule_sufficient_travel_time"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Rule sufficient_travel_time for GYM for RL."
    version = "0.1.0"

    default_config = {
        "mininum_travel_minutes": 2,
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "mininum_travel_minutes": {
                "type": "number",
                "title": "Number of minutes for mininum_travel_minutes",
            },
        },
    }

    def evalute_normal_single_worker_n_job(self, env=None, job=None):  # worker = None,
        # return score, violated_rules (negative values)
        # return self.weight * 1
        # Now check if this new job can fit into existing slots by checking travel time
        res = ActionEvaluationScore(
            score=1,
            score_type=self.title,
            message="no workers or jobs found",
            metrics_detail={"status_code": "OK"},
        )
        if len(job.scheduled_worker_codes) < 1:
            return res
        
        overall_message = ""
        for worker_code in job.scheduled_worker_codes:
            travel_time = 0
            prev_job = None
            next_job = None
            new_job_loc_i = 0
            overall_message += f" worker: {worker_code}, "
            
            job_start_time = job.scheduled_start_minutes
            all_job_codes = []
            all_slot_keys = sorted(env.slot_server.get_time_slot_keys_4_worker(worker_code))
            for slot_key in all_slot_keys:
                slot = env.slot_server.get_slot(redis_handler = None,slot_code = slot_key)
                all_job_codes = all_job_codes + slot.assigned_job_codes

            for job_code in all_job_codes:
                a_job = env.jobs_dict[job_code]
                if a_job.scheduled_start_minutes <= job_start_time:
                    prev_job = a_job
                if a_job.scheduled_start_minutes > job_start_time:  # can not be equal
                    next_job = a_job
                    break

            if prev_job:
                # same job , one is virtual for checking.

                prev_travel_time = env._get_travel_time_2jobs(prev_job, job, )
                # print( job['job_index'] , prev_job['job_index'])
                if job.job_code == prev_job.job_code:
                    print("same job in travel_time:", job.job_code, prev_job.job_code)
                    pass
                else:  # (job['job_index'] != prev_job['job_index'])  :
                    # no more room in this time slot
                    overall_message += f" prev_job: {prev_job.job_code}, prev_travel_time: {prev_travel_time},  "

                if (
                    job_start_time - prev_travel_time <
                    prev_job.scheduled_start_minutes + prev_job.scheduled_duration_minutes
                ):
                    overall_message += "Not enough travel time from prev_job: {}, rejected.".format(
                        prev_job.job_code
                    )
                    res.message = overall_message
                    res.score = -1
                    return res
                else:
                    overall_message += "(Prev_job={}, travel_time={}) ".format(
                        prev_job.job_code, int(prev_travel_time)
                    )
            else:
                overall_message += f"no previous job found on worker {worker_code}. " 

            if next_job:
                # next_travel_time = env._get_travel_time_2jobs(job.job_code, next_job.job_code)
                next_travel_time = env._get_travel_time_2jobs(job, next_job)

                if job.job_code == next_job.job_code:
                    print("same next job in travel_time:", job.job_code, next_job.job_code)
                    pass
                else:   
                    # no more room in this time slot
                    overall_message += f" next_job: {next_job.job_code}, prev_travel_time: {next_travel_time},  "

                if (
                    next_travel_time >
                    next_job.scheduled_start_minutes -
                    job_start_time -
                    job.scheduled_duration_minutes
                ):
                    # no more room in this time slot  
                    overall_message += "Not enough travel time from next_job: {}, rejected.".format(
                        next_job.job_code
                    )
                    res.message = overall_message
                    res.score = -1

                    return res
                else:
                    overall_message += "(Next_job={}, next_travel_time={}) ".format(
                        next_job.job_code, int(next_travel_time)
                    )
            else:
                overall_message += f"no next job found on worker {worker_code}. " 

            overall_message += f"all jobs are clear on worker {worker_code}. " 

        # if No workers assigned, then it returns default   
        res.message = overall_message
        return res

    """
    def evalute_action_normal(self, env=None, action = None, job_i=None):
        a_job = self.generate_virtual_job_from_action(env = env, action = action, job_i=job_i)

        worker = env.workers_dict[a_job['scheduled_primary_worker_code']]
        return self.evalute_normal_single_worker_n_job(env, worker, a_job)

    """
