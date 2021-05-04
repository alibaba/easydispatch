import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util


from dispatch.plugins.bases.kandbox_planner import KandboxRulePlugin
from dispatch.plugins.kandbox_planner.env.env_models import (
    ActionDict,
    LocationTuple,
    Worker,
    Job,
    Appointment,
    Absence,
    ActionEvaluationScore,
)


class KandboxRulePluginRequestedSkills(KandboxRulePlugin):
    """
    Has the following members
    """

    # rule_code = "check_job_skill"
    # rule_name = "Worker can handle skills requested by job"
    error_message_template = "Job ({}) requires skill ({}) , which worker {} does not have."
    success_message_template = "Job ({}) requires skill ({}) , which worker {} has."
    """
    result = {
      'score': 0,
      'message':'',
    }
    """

    title = "Requested Skills"
    slug = "kandbox_rule_requested_skills"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Rule sufficient_travel_time for GYM for RL."
    version = "0.1.0"

    default_config = {}
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def evalute_normal_single_worker_n_job(self, env, job=None):  # worker = None,
        # return score, violated_rules (negative values)
        # return self.weight * 1
        # Now check if this new job can fit into existing

        score = 1
        overall_message = "Job ({}) requires skill ({}), workers: {}. ".format(
            job.job_code, job.requested_skills, job.scheduled_worker_codes
        )
        metrics_detail = {"status_code": "OK"}

        for worker_code in job.scheduled_worker_codes:
            worker = env.workers_dict[worker_code]

            # TODO check skill_keys match as set, which should be faster.
            worker_skill_key_set = set(worker.skills.keys())

            for skill_key in job.requested_skills:
                if skill_key not in worker_skill_key_set:
                    overall_message += "Skill key({}) is not found in worker!".format(skill_key)
                    score = -1
                    metrics_detail = {"missing_key": skill_key}
                    break
                for skill in job.requested_skills[skill_key]:
                    if skill not in worker.skills[skill_key]:
                        overall_message += "({}={}) is not found in worker {}!".format(
                            skill_key, skill, worker_code
                        )
                        score = -1
                        metrics_detail = {"missing_value": {skill_key: skill}}
                        break

        score_res = ActionEvaluationScore(
            score=score,
            score_type=self.title,
            message=overall_message,
            metrics_detail=metrics_detail,
        )
        return score_res
