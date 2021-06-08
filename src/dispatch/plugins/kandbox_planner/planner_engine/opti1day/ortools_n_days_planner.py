from datetime import datetime, timedelta
import pandas as pd


from ortools.sat.python import cp_model

import collections


from pprint import pprint

import sys

from dispatch import config
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util


from dispatch.plugins.kandbox_planner.travel_time_plugin import HaversineTravelTime as TravelTime
from dispatch.plugins.bases.kandbox_planner import KandboxBatchOptimizerPlugin

from dispatch.plugins.kandbox_planner.env.env_enums import (
    JobScheduleType,
    JobPlanningStatus,
    ActionType,
    ActionScoringResultType,
    JobType,
)

from dispatch.plugins.kandbox_planner.env.env_models import ActionDict
import copy
from dispatch.job import service as job_service
from dispatch.worker import service as worker_service
from dispatch.job.models import JobPlanningInfoUpdate

import logging

log = logging.getLogger(__name__)


class OrtoolsNDaysPlanner(KandboxBatchOptimizerPlugin):

    title = "Kandbox Plugin - Batch Optimizer - for n days"
    slug = "kandbox_ortools_n_days_optimizer"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Kandbox Plugin - Batch Optimizer - for n days"
    version = "0.1.0"
    default_config = {"log_search_progress": True, "max_exec_seconds": 10}
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, config=None):
        self.config = config or self.default_config

    def _get_travel_time_2locations(self, loc1, loc2):
        new_time = self.kandbox_env.travel_router.get_travel_minutes_2locations(
            [loc1[0], loc1[1]],
            [loc2[0], loc2[1]],
        )
        if new_time > 200:
            print([loc1[0], loc1[1]], [loc2[0], loc2[1]], (new_time), "Error, too long")
        # print("travel: ", new_time)
        return int(new_time / 1)

    def dispatch_jobs(self, env):
        # , start_date="20191101", end_date="20191230"
        self.kandbox_env = env
        GENERATOR_START_DATE = datetime.strptime(
            self.kandbox_env.config["env_start_day"], config.KANDBOX_DATE_FORMAT
        )
        GENERATOR_END_DATE = GENERATOR_START_DATE + timedelta(
            days=self.kandbox_env.config["nbr_of_days_planning_window"]
        )
        current_date = GENERATOR_START_DATE
        print("current_start_day", current_date, "GENERATOR_END_DATE", GENERATOR_END_DATE)

        slot_keys = list(self.kandbox_env.slot_server.time_slot_dict.keys())
        worker_slots = [self.kandbox_env.slot_server.time_slot_dict[key] for key in slot_keys]
        # TODO, do it per day

        jobs_orig = []
        for j in self.kandbox_env.jobs:
            if j.planning_status in (JobPlanningStatus.UNPLANNED, JobPlanningStatus.IN_PLANNING):
                jobs_orig.append(j)
        if len(jobs_orig) < 1:
            print("it is empty, nothing to dispatch!")
            return

        current_shifts = jobs_orig

        print(
            {
                "loaded day": GENERATOR_START_DATE,
                "job count": len(current_shifts),
                "worker_slots count": len(worker_slots),
            }
        )

        worker_day = self.dispatch_jobs_to_slots(
            jobs=current_shifts, worker_slots=worker_slots
        )  # [0:20]  [:70]

        if len(worker_day) < 1:
            print("no data returned from dispataching!")
            return

        # pprint(worker_day)

        job_list = []
        for w_i in range(len(worker_day)):
            # worker_day is the dispatched result, now we save it into DB.
            pre_job_code = "__HOME"
            for task in worker_day[w_i][:-1]:
                task_id = task[0]  # + 1
                worker_code = worker_slots[w_i].worker_id

                # updated_order =  {} # latest_order_dict[id]
                job_list.append(
                    {
                        "job_code": current_shifts[task_id].job_code,
                        "job_schedule_type": current_shifts[task_id].job_schedule_type,
                        "planning_status": JobPlanningStatus.IN_PLANNING,
                        "scheduled_primary_worker_id": worker_code,
                        "scheduled_start_minutes": task[1] + worker_slots[w_i].start_minutes,
                        "scheduled_duration_minutes": current_shifts[
                            task_id
                        ].requested_duration_minutes,
                        "scheduled_travel_minutes_before": task[2],
                        "scheduled_travel_prev_code": pre_job_code,
                        "geo_longitude": current_shifts[task_id].location[0],
                        "geo_latitude": current_shifts[task_id].location[1],
                        "conflict_level": 0,
                        "scheduled_secondary_worker_ids": "[]",
                        "scheduled_share_status": "N",
                        "error_message": "",
                    }
                )
                pre_job_code = current_shifts[task_id].job_code
        """
        import pprint

        pprint.pprint(job_list)
        return
        """
        # TODO: No needs of 2 rounds.
        # fmt:off
        self.kandbox_env.kp_data_adapter.reload_data_from_db()
        for job in job_list:
            one_job_action_dict = ActionDict(
                is_forced_action=False,
                job_code=job["job_code"],
                # I assume that only in-planning jobs can appear here...
                action_type=ActionType.FLOATING,
                scheduled_worker_codes=[job["scheduled_primary_worker_id"]],
                scheduled_start_minutes=job["scheduled_start_minutes"],
                scheduled_duration_minutes=job["scheduled_duration_minutes"],
            )
            internal_result_info = self.kandbox_env.mutate_update_job_by_action_dict(
                a_dict=one_job_action_dict, post_changes_flag=False
            )
            if internal_result_info.status_code != ActionScoringResultType.OK:
                print(
                    f"{one_job_action_dict.job_code}: Failed to commit change, error: {str(internal_result_info)} ")

            job_to_update = JobPlanningInfoUpdate(
                code=job["job_code"],
                planning_status=job["planning_status"],
                scheduled_start_datetime=self.kandbox_env.env_decode_from_minutes_to_datetime(
                    job["scheduled_start_minutes"]),
                scheduled_duration_minutes=job["scheduled_duration_minutes"],
                scheduled_primary_worker_code=job["scheduled_primary_worker_id"],
            )
            job_service.update_planning_info(
                db_session=self.kandbox_env.kp_data_adapter.db_session, job_in=job_to_update)

            print(f"job({job_to_update.code}) is updated with new planning info")

        # fmt:on

    def dispatch_jobs_to_slots(self, worker_slots={}, jobs=[]):
        """Assign jobs to worker_slots."""
        num_slots = len(worker_slots)
        num_jobs = len(jobs)

        # All durations are in minutes.
        # max_onsite_time = 10*60 #  660 # 108  # 8 hours. / 5 *num_slots This is per worker.
        # max_shift_time = 4*60  # 60*10
        min_lunch_break_minutes = 30
        min_delay_between_jobs = 2  # 2
        # extra_time = 5
        # min_working_time = 390  # 6.5 hours

        # worker_start_time = 1+ 0*60 # 8:00
        # worker_end_time = 24*60
        # total_worker_minutes = ( worker_end_time - worker_start_time ) * num_slots

        MAX_TRAVEL_MINUTE = 600  # 2 * 24 * 60  # 24 hours in one day.

        # MIN_START_MINUTE = min([slot.start_minutes for slot in worker_slots])
        # MAX_START_MINUTE = max([slot.end_minutes for slot in worker_slots])

        # START_TIME_BASE = MIN_START_MINUTE
        MIN_START_MINUTE = 0
        MAX_START_MINUTE = 400  # MAX_START_MINUTE - START_TIME_BASE

        # Computed statistics.
        all_jobs_total_working_time = sum(
            [jobs[j].requested_duration_minutes for j in range(1, num_jobs)]
        )

        random_total_travel_time = sum(
            [
                self._get_travel_time_2locations(jobs[shift - 1].location, jobs[shift].location)
                for shift in range(1, num_jobs)
            ]
        )

        print("num worker_slots: ", num_slots, ", num_jobs: ", num_jobs)
        # print('worker_start_time: ', worker_start_time ,'worker_end_time: ', worker_end_time  )
        print("all_jobs_total_working_time: ", all_jobs_total_working_time)
        print("random_total_travel_time: ", random_total_travel_time)
        # print("total worker_slots time:", sum([1]))
        # We are going to build a flow from a the start of the day to the end
        # of the day.
        #
        # Along the path, we will accumulate travel time

        model = cp_model.CpModel()

        # Per node info

        incoming_literals = collections.defaultdict(list)
        outgoing_literals = collections.defaultdict(list)
        outgoing_other_job_index = []

        # emp_job_literals [job] = [worker_n_lit, ....]
        workers_assigned2_job_literals = collections.defaultdict(list)
        travel_time_per_emp_sum_dict = {}  # TODO

        # incoming_sink_literals = []
        # outgoing_source_literals = []

        # new_start_time = []
        # Create all the shift variables before iterating on the transitions
        # between these shifts.
        total_travel_until_emp = {}

        shift_start_time_dict = {}
        travel_time_until_job = {}
        source_lit_dict = {}
        sink_lit_dict = {}
        total_travel_until_emp[-1] = model.NewIntVar(
            0, 0, "total_travel until emp {}".format("init")
        )

        for ei in range(num_slots):
            source_lit_dict[ei] = {}
            sink_lit_dict[ei] = {}
            travel_time_per_emp_sum_dict[ei] = model.NewIntVar(
                0, MAX_TRAVEL_MINUTE, "total_travel time for emp {}".format(ei)
            )
            total_travel_until_emp[ei] = model.NewIntVar(
                0, MAX_TRAVEL_MINUTE * (ei + 1), "total_travel for emp {}".format(ei)
            )

            # To chain and  accumulate all travel times for each employee
            model.Add(
                total_travel_until_emp[ei] ==
                total_travel_until_emp[ei - 1] + travel_time_per_emp_sum_dict[ei]
            )
        # total traval (travel_time_final_total) is the last one
        travel_time_final_total = model.NewIntVar(
            0, num_slots * int(MAX_TRAVEL_MINUTE * 1), "total_travel for  - {}".format("all")
        )
        model.Add(travel_time_final_total == total_travel_until_emp[num_slots - 1])

        # Not sure why sum() does not work!!! sum(travel_time_per_emp_sum_dict)
        """
        model.Add(travel_time_final_total == travel_time_per_emp_sum_dict[0] + travel_time_per_emp_sum_dict[1] \
                + travel_time_per_emp_sum_dict[2] + travel_time_per_emp_sum_dict[3]     \
                + travel_time_per_emp_sum_dict[4] + travel_time_per_emp_sum_dict[5]     \
                )
        """

        # other_start_time_dict = {}

        for shift in range(num_jobs):
            #
            if jobs[shift].job_schedule_type != JobScheduleType.NORMAL:
                shift_start_time_dict[shift] = model.NewIntVar(
                    jobs[shift].requested_start_min_minutes,
                    jobs[shift].requested_start_max_minutes,
                    "start_time_shift_%i" % shift,
                )
            else:
                shift_start_time_dict[shift] = model.NewIntVar(
                    MIN_START_MINUTE, MAX_START_MINUTE, "start_time_shift_%i" % shift
                )

            # if jobs[shift]['job_schedule_type'] == 'FS':
            #    model.Add( shift_start_time_dict[shift] ==  jobs[shift]['requested_start_minutes'] )

            travel_time_until_job[shift] = model.NewIntVar(
                1, MAX_TRAVEL_MINUTE, "travel_time_until_shift_%i" % shift
            )
            outgoing_other_job_index.append([])
            for ei in range(num_slots):

                source_lit_dict[ei][shift] = model.NewBoolVar(
                    "from emp {} source to job {}".format(ei, shift)
                )
                # Arc from source worker to this job
                incoming_literals[shift].append(source_lit_dict[ei][shift])

                # If this job[shift] is first job for worker[ei], travel time on this job is from home to job.
                model.Add(
                    travel_time_until_job[shift] ==
                    self._get_travel_time_2locations(
                        worker_slots[ei].start_location, jobs[shift].location
                    )
                ).OnlyEnforceIf(source_lit_dict[ei][shift])

                sink_lit_dict[ei][shift] = model.NewBoolVar(
                    "from  job {} sink to emp {} ".format(shift, ei)
                )
                # Arc from job to sinking_worker.
                outgoing_literals[shift].append(sink_lit_dict[ei][shift])
                outgoing_other_job_index[shift].append("worker_{}".format(ei))

                # If this job[shift] is the last job for worker[ei], travel_time_per_emp_sum_dict (total) is the travel time on this job is from job to home.
                model.Add(
                    travel_time_per_emp_sum_dict[ei] ==
                    travel_time_until_job[shift] +
                    self._get_travel_time_2locations(
                        worker_slots[ei].end_location, jobs[shift].location
                    )
                ).OnlyEnforceIf(sink_lit_dict[ei][shift])

                model.Add(
                    shift_start_time_dict[shift] <=
                    int(
                        worker_slots[ei].end_minutes -
                        worker_slots[ei].start_minutes -  # Monday
                        jobs[shift].requested_duration_minutes +
                        self._get_travel_time_2locations(
                            worker_slots[ei].end_location, jobs[shift].location
                        )
                    )
                ).OnlyEnforceIf(sink_lit_dict[ei][shift])

                emp_on_job_lit = model.NewBoolVar("path Emp {} on job {}".format(ei, shift))
                # # ordered by worker_index
                workers_assigned2_job_literals[shift].append(emp_on_job_lit)

                # # job must obey Start time for worker, if assigned to this worker
                # # TODO, only 1 day for now, [0]
                # model.Add(
                #     shift_start_time_dict[shift] >= worker_slots[ei].start_minutes
                # ).OnlyEnforceIf(emp_on_job_lit)
                # #
                # # job must obey end time for worker, if assigned to this worker
                # model.Add(
                #     shift_start_time_dict[shift]
                #     <= int(
                #         worker_slots[ei].end_minutes  # Monday
                #         - jobs[shift].requested_duration_minutes
                #     )
                # ).OnlyEnforceIf(emp_on_job_lit)

                # If source or sink, it is on this emp.
                model.Add(emp_on_job_lit == 1).OnlyEnforceIf(sink_lit_dict[ei][shift])
                model.Add(emp_on_job_lit == 1).OnlyEnforceIf(source_lit_dict[ei][shift])

                if (jobs[shift].job_code in config.DEBUGGING_JOB_CODE_SET) and (
                    worker_slots[ei].worker_id == "Tom"
                ):
                    log.debug(f"debug {jobs[shift].job_code}")
                if (worker_slots[ei].worker_id,) not in jobs[shift].searching_worker_candidates:
                    model.Add(source_lit_dict[ei][shift] == 0)
                    model.Add(sink_lit_dict[ei][shift] == 0)
                    model.Add(emp_on_job_lit == 0)

        for shift in range(num_jobs):

            duration = jobs[shift].requested_duration_minutes

            for ei in range(num_slots):
                pass
                # outgoing_source_literals.append(source_lit_dict[ei][shift])

                # Arc from source to shift.
                # incoming_sink_literals.append(sink_lit_dict[ei][shift])

            for other in range(num_jobs):
                if shift == other:
                    continue
                other_duration = jobs[other].requested_duration_minutes
                lit = model.NewBoolVar("job path from %i to %i" % (shift, other))

                # constraint for start time by duan 2019-10-09 16:58:42  #### + jobs[shift]['requested_duration_minutes'] + min_delay_between_shifts
                # fmt: off
                model.Add(
                    shift_start_time_dict[shift] + int(jobs[shift].requested_duration_minutes) + min_delay_between_jobs +
                    self._get_travel_time_2locations(jobs[shift].location, jobs[other].location) <
                    shift_start_time_dict[other]
                ).OnlyEnforceIf(
                    lit
                )
                # fmt: on

                # Increase travel time
                model.Add(
                    travel_time_until_job[other] ==
                    travel_time_until_job[shift] +
                    self._get_travel_time_2locations(jobs[shift].location, jobs[other].location)
                ).OnlyEnforceIf(lit)

                # Make sure that for one flow path, all jobs belong to one worker 2020-01-07 12:59:21
                for ei in range(num_slots):
                    model.Add(
                        workers_assigned2_job_literals[other][ei] ==
                        workers_assigned2_job_literals[shift][ei]
                    ).OnlyEnforceIf(lit)

                # Add arc
                outgoing_literals[shift].append(lit)
                outgoing_other_job_index[shift].append("job_{}".format(other))
                incoming_literals[other].append(lit)

        # Create dag constraint.
        for shift in range(num_jobs):
            model.Add(sum(outgoing_literals[shift]) == 1)
            model.Add(sum(incoming_literals[shift]) == 1)

        # <= 1 makes it possible to leave some worker_slots idle.
        for ei in range(num_slots):
            emp_lits = []
            for ii in range(num_jobs):
                emp_lits.append(source_lit_dict[ei][ii])
            model.Add(sum(emp_lits) == 1)

        for ei in range(num_slots):
            emp_lits = []
            for ii in range(num_jobs):
                emp_lits.append(sink_lit_dict[ei][ii])
            model.Add(sum(emp_lits) == 1)

        model.Minimize(travel_time_final_total)

        # Solve model.
        solver = cp_model.CpSolver()
        solver.parameters.log_search_progress = self.config["log_search_progress"]
        # solver.parameters.num_search_workers = 4
        # https://developers.google.com/optimization/cp/cp_tasks
        solver.parameters.max_time_in_seconds = self.config["max_exec_seconds"]  # two minutes
        status = solver.Solve(model)

        if status == cp_model.INFEASIBLE:
            print(
                "SufficientAssumptionsForInfeasibility = "
                f"{solver.SufficientAssumptionsForInfeasibility()}"
            )
            return []

        if status != cp_model.OPTIMAL and status != cp_model.FEASIBLE:  #
            print("Status = %s, failed." % solver.StatusName(status))
            return []

        optimal_travel_time = int(solver.ObjectiveValue())
        print("optimal_travel_time =", optimal_travel_time)

        all_following_tasks = {}
        emp_following_tasks = {}
        """
        for ei in range(num_slots):
            print("w_{}_{}: {}, hasta {}".format(
                ei,
                worker_slots[ei]['worker_code'],
                solver.Value( travel_time_per_emp_sum_dict[ei]),
                solver.Value( total_travel_until_emp[ei])
                )
            )
        for ei in range(num_jobs):
            print("j_{} : {},  travel {}, start: {}".format(
                ei,
                jobs[ei]['requested_duration_minutes'],
                solver.Value(travel_time_until_job[ei] ) ,
                solver.Value( shift_start_time_dict [ei])
                )
            )
        """
        for shift in range(num_jobs):
            if shift == 7:
                pass
                # print("pause")
            for ii in range(len(outgoing_literals[shift])):
                if solver.Value(outgoing_literals[shift][ii]) == 1:
                    # print(
                    #     "job_",
                    #     shift,
                    #     f"({jobs[shift].job_code})--> ",
                    #     outgoing_other_job_index[shift][ii],
                    # )
                    # TODO make it a list for multiple worker_slots on same job
                    # 0 means this is a job, 1 is ending at worker
                    all_following_tasks[shift] = outgoing_other_job_index[shift][ii].split("_")
            for ei in range(num_slots):
                if solver.Value(source_lit_dict[ei][shift]) == 1:
                    # print("worker:", ei, f"({worker_slots[ei].worker_id})--> job_", shift)
                    emp_following_tasks[ei] = ["job", shift]

        # j_file.write('')
        to_print_json_list = []
        for _ in range(num_slots):
            to_print_json_list.append([])
        for ei in emp_following_tasks.keys():
            my_next_node = emp_following_tasks[ei]
            prev_node = my_next_node
            while my_next_node[0] == "job":
                shift = int(my_next_node[1])
                to_print_json_list[ei].append(
                    [
                        shift,
                        solver.Value(shift_start_time_dict[shift]),
                        self._get_travel_time_2locations(
                            jobs[int(prev_node[1])].location, jobs[shift].location
                        ),
                        jobs[shift].requested_duration_minutes,
                    ]
                )
                prev_node = my_next_node
                my_next_node = all_following_tasks[shift]
            to_print_json_list[ei].append(
                [
                    -1,
                    -2,
                    self._get_travel_time_2locations(
                        worker_slots[ei].start_location, jobs[shift].location
                    ),
                    -4,
                ]
            )

        """
        print(to_print_json_list)

        """
        for ei in range(num_slots):
            print(
                "worker:",
                ei,
                f"({worker_slots[ei].worker_id}) --> ",
                [
                    (
                        to_print_json_list[ei][si][0],
                        f"({jobs[ to_print_json_list[ei][si][0] ].job_code})",
                        to_print_json_list[ei][si][1],
                    )
                    for si in range(len(to_print_json_list[ei]) - 1)
                ],
            )

        return to_print_json_list


if __name__ == "__main__":

    opti = OrtoolsNDaysPlanner(max_exec_seconds=config.KANDBOX_OPTI1DAY_EXEC_SECONDS)  # 0*60*24
    ss = config.KANDBOX_TEST_OPTI1DAY_START_DAY
    ee = config.KANDBOX_TEST_OPTI1DAY_END_DAY
    opti.kandbox_env.purge_planner_job_status(
        planner_code=opti.planner_code, start_date=ss, end_date=ee
    )
    res = opti.dispatch_jobs(start_date=ss, end_date=ee)
    # pprint(res)

    exit(0)

    # from dispatch.plugins.kandbox_planner.travel_time_plugin  import  TaxicabTravelTime as TravelTime
    """
    opti = OrtoolsNDaysPlanner( max_exec_seconds = 20)
    from dispatch.plugins.kandbox_planner.travel_time_plugin  import  TaxicabTravelTime
    opti.travel_router = TaxicabTravelTime()
    # [index, type = 'FS', location = '7:12', start_time: 110, end_time = 60 (not used), duration = 32]
    _SHIFTS =  [
    [0, 'FS', '7:12', 510, 60, 32],   [1, 'N', '8:3', 26, 68, 22],   [2, 'N', '06:4', 66, 121, 25],
    [3, 'FS', '15:5', 660, 72, 12],    [4, 'N', '11:4', 133, 189, 16], [5, 'N', '13:2', 2, 19, 17],
    [906, 'FS', '20:5', 731, 131, 34],   [7, 'N', '21:7', 8, 30, 52],   [8, 'FS', '3:45', 850, 190, 60],
    [9, 'N', '5:49', 38, 80, 22],   [10, 'FS', '14:54', 743, 90, 37],  [11, 'N', '13:60', 169, 169, 25],
    [12, 'FS', '19:55', 678, 215, 37], [13, 'N', '20:59', 196, 234, 38],[14, 'N', '20:48', 235, 248, 13]
    ]
    _EMP = ['3:4', '12:5', '21:4','4:55', '12:50', '21:50' ]

    jobs = [ {
            'job_index':wi,
            'job_code':'j_{}'.format(_SHIFTS[wi][0]),
            'job_schedule_type': 'NONE_',
            'requested_start_minutes':_SHIFTS[wi][3],
            'requested_duration_minutes':int(_SHIFTS[wi][5]),
            'mandatory_minutes_minmax_flag' : 1 if _SHIFTS[wi][1] == 'FS' else 0,
            'requested_start_min_minutes' : _SHIFTS[wi][3],
            'requested_start_max_minutes' : _SHIFTS[wi][3],
            'geo_longitude': float(_SHIFTS[wi][2].split(':')[0]),
            'geo_latitude': float(_SHIFTS[wi][2].split(':')[1]),
            'requested_worker_index':-1, # TODO
        } for wi in  range(len(_SHIFTS))]


    people = ('Tom', 'Mike', 'Harry', 'Slim', 'Jim','Duan')
    worker_list = [[wi, people[wi], _EMP[wi] ]  for wi in  range(len(people))]

    worker_slots = [ {
            'worker_index':wi,
            'worker_code':people[wi],
            'geo_longitude': float(_EMP[wi].split(':')[0]),
            'geo_latitude': float(_EMP[wi].split(':')[1]),
            'working_minutes':[[8*60, 18*60] ],
            'lunch_break_minutes': 30,
        } for wi in  range(len(people))]
    # pprint(jobs)
    # exit(0)

    to_print_json_list = opti.dispatch_jobs_to_slots(jobs = jobs, worker_slots= worker_slots )
    pprint(to_print_json_list)
        """
