import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util


from dispatch.plugins.bases.kandbox_planner import KandboxRulePlugin
from dispatch.plugins.kandbox_planner.env.env_models import (
    ActionDict,
    LocationTuple,
    Worker, 
    ActionEvaluationScore,
)
from dispatch.plugins.kandbox_planner.env.env_enums import (
    EnvRunModeType,
    JobPlanningStatus,
)

import copy
class KandboxRulePluginPickDropGroup(KandboxRulePlugin):
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

    title = "Pick Drop Grouping"
    slug = "kandbox_rule_pick_drop_group"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "check for pick drop Group in same order"
    version = "0.1.0"

    default_config = {
        "check_preceding_job": False,
        "check_order_code_type": True,

    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "check_preceding_job": {
                "type": "boolean",
                "default": False,
                "code": "check_preceding_job",
            },
            "check_order_code_type": {
                "type": "boolean",
                "default": True,
                "code": "check_order_code_type",
            }
        },
    }

    def __init__(self, weight=None, config=None):
        self.config = copy.deepcopy(self.default_config)
        if config:
            self.config.update(config) 


    def evalute_normal_single_worker_n_job(self, env, job=None):  # worker = None,
        # return score, violated_rules (negative values)
        # return self.weight * 1
        # Now check if this new job can fit into existing

        if self.config["check_order_code_type"]:
            order_type = job.flex_form_data.get('order_type',None)
            if order_type is None: 
                overall_message =  "Job ({}) have no order type".format(  job.job_code   )
                return ActionEvaluationScore(
                                    score=0,
                                    score_type=self.title,
                                    message=overall_message,
                                    metrics_detail={"status_code": "OK"},
                                )
            elif order_type in [ 'pickUp', "dropOff"]: 
                order_code = job.flex_form_data.get('order_code','-')
                for _j in env.jobs_dict.values():
                    if _j.job_code == job.job_code:
                        continue
                    if _j.flex_form_data.get('order_code','-') == order_code:
                        if  _j.planning_status == JobPlanningStatus.IN_PLANNING:
                            if _j.scheduled_worker_codes[0] != job.scheduled_worker_codes[0]:
                                score = 0
                                overall_message =  "Job ({}) to Worker({}) is differnt from the pair job {} on worker {}".format( 
                                    job.job_code,
                                    job.scheduled_worker_codes[0],
                                    _j.job_code,
                                    _j.scheduled_worker_codes[0],
                                       )
                                return ActionEvaluationScore(
                                    score=-1,
                                    score_type=self.title,
                                    message=overall_message,
                                    metrics_detail={"status_code": "ERROR"},
                                )
                        else:
                            return ActionEvaluationScore(
                                    score=0,
                                    score_type=self.title,
                                    message="Job ({}) has unplanned job {}".format(  job.job_code,_j.job_code,   ),
                                    metrics_detail={"status_code": "OK"},
                                )
                return ActionEvaluationScore(
                                    score=1,
                                    score_type=self.title,
                                    message="Job ({}) has no pair or same worker inplanning ".format(  job.job_code ),
                                    metrics_detail={"status_code": "OK"},
                                )




        score_res = ActionEvaluationScore(
            score=-1,
            score_type=self.title,
            message="Wrong configuration",
            metrics_detail={"status_code": "ERROR"},
        )
        return score_res
