import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util


class RewardFunction:
    """
    Has the following members
  """

    rule_code = "generic_rule"
    rule_name = "Generic Rule (and it should not be used)"
    message_template = "Generic Rule"
    reward_range = [-1, 1]

    result = {
        "score": 0,
        "message": ["Not implemented"],
    }

    def __init__(self, weight=None):
        self.weight = weight
        pass

    """
  def evalute_weighted(self, env=None, job_index_list = []):
    # return score, violated_rules (negative values)
    return  self.evalute_normal(env, job_index_list) * self.weight
  def evalute(self, env=None, job_index_list = []):
    # return score, violated_rules (negative values)
    return  self.evalute_weighted(env, job_index_list)

  # Each reward function should rewrite evalute()
  def evalute_normal(self, env=None, job_index_list = []):
    return 1
    # return score, violated_rules (negative values)
  """

    def generate_virtual_job_from_action(self, env=None, a_dict=None, job_i=None):
        if job_i is None:
            job_i = env.current_job_i

        all_jobs = []
        # max_i = np.argmax(action[0:len(self.workers_dict)])
        all_workers = [a_dict["scheduled_primary_worker_id"]] + a_dict[
            "scheduled_secondary_worker_ids"
        ]
        for w_i, worker_code in enumerate(all_workers):
            job = env.jobs[job_i].copy()

            rest_workers = all_workers.copy()
            job["scheduled_primary_worker_id"] = worker_code
            rest_workers.pop(w_i)
            job["scheduled_secondary_worker_ids"] = rest_workers
            if len(all_workers) < 2:  # Only ==1
                job["scheduled_share_status"] = "N"
            else:
                if w_i == 0:
                    job["scheduled_share_status"] = "P"
                else:
                    job["scheduled_share_status"] = "S"

            action_day = a_dict["scheduled_start_day"]

            if action_day > env.config["nbr_of_days_planning_window"]:
                return []

            job_start_time = a_dict["assigned_start_day_n_minutes"]

            job["scheduled_start_day"] = action_day
            job["scheduled_start_minutes"] = a_dict["scheduled_start_minutes"]
            job["assigned_start_day"] = action_day
            job["assigned_start_minutes"] = (
                action_day * env.config["minutes_per_day"] + a_dict["scheduled_start_minutes"]
            )
            job["scheduled_duration_minutes"] = job["requested_duration_minutes"]
            job["current_job_i"] = env.current_job_i
            all_jobs.append(job)

        return all_jobs
        # return score, violated_rules (negative values)

    def evalute_action_normal(self, env=None, action_dict=None, job_i=None):

        result = {"score": 0, "message": []}
        all_jobs = self.generate_virtual_job_from_action(env=env, a_dict=action_dict, job_i=job_i)
        for a_job in all_jobs:
            res = self.evalute_normal_single_worker_n_job(env=env, job=a_job)
            if res["score"] == -1:
                result["score"] == -1
            result["message"].append(res)  # ['message']

        if result["score"] > -1:
            result["score"] = sum([r["score"] for r in result["message"]])

        return result
