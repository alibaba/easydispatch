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


class Opti1DayPlanner(KandboxBatchOptimizerPlugin):

    title = "Kandbox Plugin - Batch Optimizer - opti1day"
    slug = "kandbox_opti1day"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Batch Optimizer - opti1day."
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

    def dispatch_jobs(self, env, rl_agent=None):
        # Real batch, rl_agent is skilpped.
        self.kandbox_env = env
        GENERATOR_START_DATE = datetime.strptime(
            self.kandbox_env.config["env_start_day"], config.KANDBOX_DATE_FORMAT
        )
        GENERATOR_END_DATE = GENERATOR_START_DATE + timedelta(
            days=self.kandbox_env.config["nbr_of_days_planning_window"]
        )
        current_date = GENERATOR_START_DATE

        # day_seq = int(self.kandbox_env.env_encode_from_datetime_to_minutes( self.kandbox_env.data_start_datetime) / 1440) - 1

        while current_date < GENERATOR_END_DATE:
            """
            visit_cust  = self.kandbox_env.load_job_status_df(
                planner_code = config.ORIGINAL_PLANNER,
                start_date = start_date,
                end_date = end_date
                )
            """
            print("current_start_day", current_date, "GENERATOR_END_DATE", GENERATOR_END_DATE)
            current_start_day = datetime.strftime(current_date, config.KANDBOX_DATE_FORMAT)

            day_seq = int(self.kandbox_env.env_encode_from_datetime_to_minutes(current_date) / 1440)

            # purge job status for this planner and this day.

            workers = self.kandbox_env.workers  # start_day=current_start_day
            # TODO, do it per day

            jobs_orig = []
            for j in self.kandbox_env.jobs:
                if (j.requested_start_minutes >= day_seq * 1440) and (
                    j.requested_start_minutes < (day_seq + 1) * 1440
                ):
                    jobs_orig.append(j)
            if len(jobs_orig) < 1:
                print("it is empty, nothing to dispatch!")
                return

            current_shifts = jobs_orig
            current_workers = workers  # .T.to_dict().values()

            print(
                {
                    "loaded day": current_date,
                    "job count": len(current_shifts),
                    "current_workers count": len(current_workers),
                }
            )

            worker_day = self.dispatch_jobs_1day(
                jobs=current_shifts[0:53], workers=current_workers
            )  # [0:20]  [:70]
            # worker_day is the dispatched result, now we save it into DB.

            if len(worker_day) < 1:
                print("no data returned from opti1day! I will move on to next day!")
                current_date = current_date + timedelta(days=1)
                continue
            # pprint(worker_day)
            job_list = []
            for w_i in range(len(worker_day)):
                pre_job_code = "__HOME"
                for task in worker_day[w_i][:-1]:
                    task_id = task[0]  # + 1
                    worker_code = current_workers[w_i].worker_code

                    # updated_order =  {} # latest_order_dict[id]
                    job_list.append(
                        {
                            "job_code": current_shifts[task_id].job_code,
                            "job_schedule_type": current_shifts[task_id].job_schedule_type,
                            "planning_status": JobPlanningStatus.IN_PLANNING,
                            "scheduled_primary_worker_id": worker_code,
                            "scheduled_start_day": datetime.strftime(
                                current_date, config.KANDBOX_DATE_FORMAT
                            ),
                            "requested_start_day": datetime.strftime(
                                current_date, config.KANDBOX_DATE_FORMAT
                            ),
                            "scheduled_start_minutes": task[1] + (day_seq * 1440),
                            "scheduled_duration_minutes": current_shifts[
                                task_id
                            ].requested_duration_minutes,
                            "scheduled_travel_minutes_before": task[2],
                            "scheduled_travel_prev_code": pre_job_code,
                            # "location_code": current_shifts[task_id]["location_code"],
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
                # self.kandbox_env.jobs_dict[job["job_code"]] .planning_status = job["planning_status"]
                # self.kandbox_env.jobs_dict[job["job_code"]] .scheduled_worker_codes = job ["scheduled_primary_worker_id"] + job ["scheduled_secondary_worker_ids"]
                # self.kandbox_env.jobs_dict[job["job_code"]] .scheduled_start_minutes = job["scheduled_start_minutes"]
                # self.kandbox_env.jobs_dict[job["job_code"]].is_changed = True

                # Duration does not change
                # self.kandbox_env.jobs_dict[job.job_code] .scheduled_start_minutes = job.["scheduled_start_minutes"] \
                #      + 24*60* date_util.days_between_2_day_string(start_day=self.kandbox_env.config["data_start_day"], end_day=job["scheduled_start_day"])

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

                # job_to_create = copy.deepcopy(self.kandbox_env.kp_data_adapter.jobs_db_dict[job["job_code"]])
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

                # self.kandbox_env.kp_data_adapter.db_session.add(db_job)
                # self.kandbox_env.kp_data_adapter.db_session.commit()
                # job_to_create= copy.deepcopy(job_orig)

                print(f"job({job_to_update.code}) is updated with new planning info")

            # fmt:on

            # self.kandbox_env.commit_changed_jobs()

            current_date = current_date + timedelta(days=1)

    def calc_travel_minutes_before_after_df(self, df):

        visit_cust_I = (
            df[df.planning_status != JobPlanningStatus.UNPLANNED]
            .sort_values(
                ["scheduled_primary_worker_id", "scheduled_start_day", "scheduled_start_minutes"],
                ascending=True,
            )
            .copy()
        )

        visit_cust_I[
            [
                "prev_job_code",
                "prev_geo_longitude",
                "prev_geo_latitude",
                "prev_start_day",
                "prev_start_minute",
                "prev_duration_minutes",
                "prev_worker_code",
                "prev_location_code",
            ]
        ] = (
            visit_cust_I[
                [
                    "job_code",
                    "geo_longitude",
                    "geo_latitude",
                    "scheduled_start_day",
                    "scheduled_start_minutes",
                    "scheduled_duration_minutes",
                    "scheduled_primary_worker_id",
                    "location_code",
                ]
            ]
            .shift(periods=1, fill_value=999999)
            .apply(lambda x: x, axis=1, result_type="expand")
        )

        visit_cust_I[["next_start_day", "next_worker_code"]] = (
            visit_cust_I[["scheduled_start_day", "scheduled_primary_worker_id"]]
            .shift(periods=-1, fill_value=999999)
            .apply(lambda x: x, axis=1, result_type="expand")
        )

        visit_cust_U = (
            df[df.planning_status == JobPlanningStatus.UNPLANNED]
            .sort_values(
                ["scheduled_primary_worker_id", "scheduled_start_day", "scheduled_start_minutes"],
                ascending=True,
            )
            .copy()
        )
        visit_cust_U[
            [
                "prev_job_code",
                "prev_geo_longitude",
                "prev_geo_latitude",
                "prev_start_day",
                "prev_start_minute",
                "prev_duration_minutes",
                "prev_worker_code",
                "prev_location_code",
                "next_start_day",
                "next_worker_code",
            ]
        ] = visit_cust_U.apply(
            lambda x: ["_NONE", 0, 0, 0, 0, 0, "_NO_WORKER", "_NO_LOC", 0, "_NO_WORKER"],
            axis=1,
            result_type="expand",
        )

        visit_cust = pd.concat([visit_cust_I, visit_cust_U])

        visit_cust[
            [
                "scheduled_travel_minutes_before",
                "scheduled_travel_minutes_after",
                "scheduled_travel_prev_code",
                "scheduled_travel_next_code",
            ]
        ] = visit_cust.apply(
            lambda x: self.calc_travel_minutes_before_after(x), axis=1, result_type="expand"
        )

        visit_cust[
            [
                "scheduled_travel_minutes_before",
                "scheduled_travel_minutes_after",
                "scheduled_travel_prev_code",
                "scheduled_travel_next_code",
            ]
        ] = visit_cust.apply(
            lambda x: self.calc_travel_minutes_before_after(x), axis=1, result_type="expand"
        )

        return visit_cust

    def calc_travel_minutes_before_after_func(self, x):
        from_home = False
        to_home = False

        if x.scheduled_primary_worker_id != x["prev_worker_code"]:
            from_home = True
        if x["scheduled_start_day"] != x["prev_start_day"]:
            from_home = True

        if x.scheduled_primary_worker_id != x["next_worker_code"]:
            to_home = True
        if x["scheduled_start_day"] != x["next_start_day"]:
            to_home = True

        # if x['location_code'] != x['prev_location_code']:
        #    return fromjob, 0
        try:
            home_travel_time = self.kandbox_env.travel_router.get_travel_minutes_2locations(
                [float(x.location[0]), float(x.location[1])],
                [float(x["w_geo_longitude"]), float(x["w_geo_latitude"])],
            )
            prev_job_travel_time = self.kandbox_env.travel_router.get_travel_minutes_2locations(
                [float(x.location[0]), float(x.location[1])],
                [float(x["prev_geo_longitude"]), float(x["prev_geo_latitude"])],
            )
        except:
            home_travel_time = 5
            prev_job_travel_time = 5  # minimum travel time #TODO
        # print(from_home, to_home, prev_job_travel_time, home_travel_time)

        if from_home & to_home:
            return home_travel_time, home_travel_time, "__HOME", "__HOME"
        if to_home:
            return prev_job_travel_time, home_travel_time, x["prev_job_code"], "__HOME"
        if from_home:
            return home_travel_time, 0, "__HOME", "__NONE"
        # From = false, to=false
        return prev_job_travel_time, 0, x["prev_job_code"], "__NONE"

    def dispatch_jobs_1day(self, workers=[], jobs=[]):
        """Assign jobs to workers."""
        num_workers = len(workers)
        num_jobs = len(jobs)

        # All durations are in minutes.
        # max_onsite_time = 10*60 #  660 # 108  # 8 hours. / 5 *num_workers This is per worker.
        # max_shift_time = 4*60  # 60*10
        min_lunch_break_minutes = 30
        min_delay_between_jobs = 2  # 2
        # extra_time = 5
        # min_working_time = 390  # 6.5 hours

        # worker_start_time = 1+ 0*60 # 8:00
        # worker_end_time = 24*60
        # total_worker_minutes = ( worker_end_time - worker_start_time ) * num_workers

        MAX_MINUTE = 24 * 60  # 24 hours in one day.

        # Num workers
        # model.NewIntVar(min_num_workers, min_num_workers * 5, 'num_workers')
        # Computed data.
        all_jobs_total_working_time = sum(
            [jobs[j].requested_duration_minutes for j in range(1, num_jobs)]
        )

        random_total_travel_time = sum(
            [
                self._get_travel_time_2locations(jobs[shift - 1].location, jobs[shift].location)
                for shift in range(1, num_jobs)
            ]
        )

        print("num workers: ", num_workers, ", num_jobs: ", num_jobs)
        # print('worker_start_time: ', worker_start_time ,'worker_end_time: ', worker_end_time  )
        print("all_jobs_total_working_time: ", all_jobs_total_working_time)
        print("random_total_travel_time: ", random_total_travel_time)
        print("total workers time:", sum([1]))
        # We are going to build a flow from a the start of the day to the end
        # of the day.
        #
        # Along the path, we will accumulate travel time

        model = cp_model.CpModel()

        # Per node info

        incoming_literals = collections.defaultdict(list)
        outgoing_literals = collections.defaultdict(list)
        outgoing_other_job_index = []

        workers_assigned2_job_literals = collections.defaultdict(
            list
        )  # emp_job_literals [job] = [worker_n_lit, ....]
        travel_time_per_emp_sum_dict = {}  # TODO

        # incoming_sink_literals = []
        # outgoing_source_literals = []

        # new_start_time = []
        # Duan
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

        for ei in range(num_workers):
            source_lit_dict[ei] = {}
            sink_lit_dict[ei] = {}
            travel_time_per_emp_sum_dict[ei] = model.NewIntVar(
                0, MAX_MINUTE, "total_travel time for emp {}".format(ei)
            )
            total_travel_until_emp[ei] = model.NewIntVar(
                0, MAX_MINUTE * (ei + 1), "total_travel for emp {}".format(ei)
            )

            # To chain and  accumulate all travel times for each employee
            model.Add(
                total_travel_until_emp[ei] ==
                total_travel_until_emp[ei - 1] + travel_time_per_emp_sum_dict[ei]
            )
        # total traval (travel_time_final_total) is the last one
        travel_time_final_total = model.NewIntVar(
            0, num_workers * int(MAX_MINUTE * 1), "total_travel for  - {}".format("all")
        )
        model.Add(travel_time_final_total == total_travel_until_emp[num_workers - 1])

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
                    1, MAX_MINUTE, "start_time_shift_%i" % shift
                )

            # if jobs[shift]['job_schedule_type'] == 'FS':
            #    model.Add( shift_start_time_dict[shift] ==  jobs[shift]['requested_start_minutes'] )

            travel_time_until_job[shift] = model.NewIntVar(
                1, MAX_MINUTE, "travel_time_until_shift_%i" % shift
            )
            outgoing_other_job_index.append([])
            for ei in range(num_workers):

                source_lit_dict[ei][shift] = model.NewBoolVar(
                    "from emp {} source to job {}".format(ei, shift)
                )
                # Arc from source worker to this job
                incoming_literals[shift].append(source_lit_dict[ei][shift])

                # If this job[shift] is first job for worker[ei], travel time on this job is from home to job.
                model.Add(
                    travel_time_until_job[shift] ==
                    self._get_travel_time_2locations(
                        workers[ei].weekly_start_gps[0], jobs[shift].location
                    )
                    # workers[ei], jobs[shift]
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
                        workers[ei].weekly_start_gps[0], jobs[shift].location
                    )
                ).OnlyEnforceIf(
                    sink_lit_dict[ei][shift]
                )  # from sink_

                emp_on_job_lit = model.NewBoolVar("path Emp {} on job {}".format(ei, shift))
                workers_assigned2_job_literals[shift].append(
                    emp_on_job_lit
                )  # ordered by worker_index

                # job must obey Start time for worker, if assigned to this worker
                # TODO, only 1 day for now, [0]
                model.Add(
                    shift_start_time_dict[shift] >= workers[ei].weekly_working_slots[1][0]  # Monday
                ).OnlyEnforceIf(emp_on_job_lit)
                #
                # job must obey end time for worker, if assigned to this worker
                model.Add(
                    shift_start_time_dict[shift] <=
                    int(
                        workers[ei].weekly_working_slots[1][1] -  # Monday
                        jobs[shift].requested_duration_minutes
                    )
                ).OnlyEnforceIf(emp_on_job_lit)

                model.Add(emp_on_job_lit == 1).OnlyEnforceIf(sink_lit_dict[ei][shift])  # from sink_
                model.Add(emp_on_job_lit == 1).OnlyEnforceIf(
                    source_lit_dict[ei][shift]
                )  # from sink_

        for shift in range(num_jobs):

            duration = jobs[shift].requested_duration_minutes

            for ei in range(num_workers):
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
                    shift_start_time_dict[shift] + int(jobs[shift].requested_duration_minutes) + min_delay_between_jobs + self._get_travel_time_2locations(jobs[shift].location, jobs[other].location) <
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
                for ei in range(num_workers):
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

        # model.Add(sum(incoming_sink_literals) == num_workers)
        # model.Add(sum(outgoing_source_literals) == num_workers)

        # <= 1 makes it possible to leave some workers idle.
        for ei in range(num_workers):
            emp_lits = []
            for ii in range(num_jobs):
                emp_lits.append(source_lit_dict[ei][ii])
            model.Add(sum(emp_lits) == 1)

        for ei in range(num_workers):
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

        if status != cp_model.OPTIMAL and status != cp_model.FEASIBLE:  #
            print("not FEASIBLE, failed!")
            return []

        print("Status = %s" % solver.StatusName(status))
        optimal_travel_time = int(solver.ObjectiveValue())
        print("optimal_travel_time =", optimal_travel_time)
        # s_printer = OneSolutionPrinter(__variables,solver)
        # return s_printer.print_solution()
        # return optimal_num_workers
        all_following_tasks = {}
        emp_following_tasks = {}
        """
        for ei in range(num_workers):
            print("w_{}_{}: {}, hasta {}".format(
                ei,
                workers[ei]['worker_code'],
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
                    # print('job:', shift, '-->', outgoing_other_job_index[shift]  [ii])
                    # TODO make it a list for multiple workers on same job
                    # 0 means this is a job, 1 is ending at worker
                    all_following_tasks[shift] = outgoing_other_job_index[shift][ii].split("_")
            for ei in range(num_workers):
                if solver.Value(source_lit_dict[ei][shift]) == 1:
                    # print('start:', shift, '<--', ei)
                    emp_following_tasks[ei] = ["job", shift]

        # j_file.write('')
        to_print_json_list = []
        for _ in range(num_workers):
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
                            jobs[int(prev_node[1])].location, jobs[shift].location),
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
                        workers[ei].weekly_start_gps[0], jobs[shift].location
                    ),
                    -4,
                ]
            )

        """
        print(to_print_json_list)

        """

        return to_print_json_list


if __name__ == "__main__":

    opti = Opti1DayPlanner(max_exec_seconds=config.KANDBOX_OPTI1DAY_EXEC_SECONDS)  # 0*60*24
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
    opti = Opti1DayPlanner( max_exec_seconds = 20)
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

    workers = [ {
            'worker_index':wi,
            'worker_code':people[wi],
            'geo_longitude': float(_EMP[wi].split(':')[0]),
            'geo_latitude': float(_EMP[wi].split(':')[1]),
            'working_minutes':[[8*60, 18*60] ],
            'lunch_break_minutes': 30,
        } for wi in  range(len(people))]
    # pprint(jobs)
    # exit(0)

    to_print_json_list = opti.dispatch_jobs_1day(jobs = jobs, workers= workers )
    pprint(to_print_json_list)
        """
