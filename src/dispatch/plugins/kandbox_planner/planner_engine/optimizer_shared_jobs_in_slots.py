from dispatch.plugins.kandbox_planner.env.env_models import ActionDict
from dispatch.plugins.kandbox_planner.env.env_enums import OptimizerSolutionStatus, ActionType
from datetime import datetime, timedelta
import pandas as pd


from ortools.sat.python import cp_model

import collections


from pprint import pprint

import sys

from dispatch import config
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util

from dispatch.plugins.kandbox_planner.travel_time_plugin import (
    MultiLayerCacheTravelTime as TravelTime,
)
from dispatch.plugins.bases.kandbox_planner import KandboxBatchOptimizerPlugin
import logging

log = logging.getLogger("OptimizerJobsInSlots")
# log = logging.getLogger(__name__)


class OptimizerJobsInSlots:

    title = "Kandbox Plugin - Batch Optimizer - opti1day"
    slug = "kandbox_opti1day"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Batch Optimizer - opti1day."
    version = "0.1.0"
    default_config = {"log_search_progress": False, "max_exec_time": 5}
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, env, config=None):
        self.env = env
        self.travel_router = env.travel_router  # TravelTime(travel_speed=25)
        self.config = config or self.default_config
        # self.kandbox_env = kandbox_env
        # self.kandbox_env.reset()
        # if max_exec_time is not None:
        #    self.max_exec_time = max_exec_time

    def _get_travel_time_from_location_to_job(self, location, job_code_2):
        # y_1,x_1= site1.split(':')
        # y_2,x_2= site2.split(':')
        site2 = self.env.jobs_dict[job_code_2]
        new_time = self.travel_router.get_travel_minutes_2locations(
            location,
            [site2.location.geo_longitude, site2.location.geo_latitude],
        )
        # try:
        #     print(f"{ location.geo_longitude,  location.geo_latitude}")
        # except:
        #     print("ok")
        if new_time > config.TRAVEL_MINUTES_WARNING_LEVEL:
            log.debug(
                f"JOB:{job_code_2}:LOCATION:{ location[0], location[1]}:very long travel time: {new_time} minutes. ")

            return config.TRAVEL_MINUTES_WARNING_RESULT

        return int(new_time / 1)

    def _get_travel_time_2_sites(self, job_code_1, job_code_2):
        # y_1,x_1= site1.split(':')
        # y_2,x_2= site2.split(':')
        site1 = self.env.jobs_dict[job_code_1]
        site2 = self.env.jobs_dict[job_code_2]

        new_time = self.travel_router.get_travel_minutes_2locations(
            [site1.location.geo_longitude, site1.location.geo_latitude],
            [site2.location.geo_longitude, site2.location.geo_latitude],
        )
        if new_time > config.TRAVEL_MINUTES_WARNING_LEVEL:
            log.debug(
                f"JOB:{job_code_1}:JOB:{job_code_2}: very long travel time: {new_time} minutes")
        return int(new_time / 1)

    def dispatch_jobs_in_slots(self, working_time_slots: list):
        """Assign jobs to workers."""
        num_slots = len(working_time_slots)

        # All durations are in minutes.
        all_start_minutes = [s.start_minutes - s.start_overtime_minutes for s in working_time_slots]
        all_end_minutes = [s.end_minutes + s.end_overtime_minutes for s in working_time_slots]

        # MAX_MINUTE = 24 * 60  # 24 hours in one day.
        SCHEDULED_WORKER_CODES = [s.worker_id for s in working_time_slots[:-2]]
        CURRENT_JOB_CODE = working_time_slots[-1].assigned_job_codes[0]

        all_job_durations = {
            CURRENT_JOB_CODE: self.env. get_encode_shared_duration_by_planning_efficiency_factor(
                self.env.jobs_dict[CURRENT_JOB_CODE].requested_duration_minutes,
                len(SCHEDULED_WORKER_CODES))
        }

        for a_slot in working_time_slots:
            for a_jc in a_slot.assigned_job_codes:
                if a_jc not in all_job_durations.keys():
                    if self.env.jobs_dict[a_jc].planning_status == 'U':
                        log.error(
                            f"dispatch_jobs_in_slots: self.env.jobs_dict[a_jc].planning_status == 'U', job_code = {a_jc}")
                    all_job_durations[a_jc] = self.env.jobs_dict[a_jc].scheduled_duration_minutes

        MIN_MINUTE = max(all_start_minutes)  # 24 hours in one day.
        MAX_MINUTE = min(all_end_minutes)  # 24 hours in one day.

        MAX_TRAVEL_MINUTES = MAX_MINUTE - MIN_MINUTE

        # TODO: Missing shared ===
        # model.NewIntVar(min_num_workers, min_num_workers * 5, 'num_slots')
        # Computed data.

        # We are going to build a flow from a the start of the day to the end
        # of the day.
        #
        # Along the path, we will accumulate travel time

        model = cp_model.CpModel()

        # Per node info

        #incoming_literals = collections.defaultdict(list)
        #outgoing_literals = collections.defaultdict(list)
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

        all_worker_codes_for_each_job_dict = {}
        all_jobs_in_slots = []
        for slot_i in range(num_slots):
            all_jobs_in_slots.append([
                self.env.jobs_dict[jc] for jc in working_time_slots[slot_i].assigned_job_codes
            ])
            for ajob in all_jobs_in_slots[slot_i]:
                if ajob.job_code not in all_worker_codes_for_each_job_dict.keys():
                    all_worker_codes_for_each_job_dict[ajob.job_code] = [
                        working_time_slots[slot_i].worker_id]
                else:
                    all_worker_codes_for_each_job_dict[ajob.job_code].append(
                        working_time_slots[slot_i].worker_id)

        for slot_i in range(num_slots):
            incoming_literals_per_slot = {}
            outgoing_literals_per_slot = {}
            shift_start_time_dict[slot_i] = {}
            source_lit_dict[slot_i] = {}
            sink_lit_dict[slot_i] = {}
            travel_time_per_emp_sum_dict[slot_i] = model.NewIntVar(
                0, MAX_TRAVEL_MINUTES, "total_travel time for emp {}".format(slot_i)
            )
            total_travel_until_emp[slot_i] = model.NewIntVar(
                0, MAX_TRAVEL_MINUTES * (slot_i + 1), "total_travel for emp {}".format(slot_i)
            )

            # To chain and  accumulate all travel times for each employee
            model.Add(
                total_travel_until_emp[slot_i] ==
                total_travel_until_emp[slot_i - 1] + travel_time_per_emp_sum_dict[slot_i]
            )
        # total traval (travel_time_final_total) is the last one
        travel_time_final_total = model.NewIntVar(
            0, num_slots * int(MAX_TRAVEL_MINUTES), "total_travel for  - {}".format("all")
        )
        model.Add(travel_time_final_total == total_travel_until_emp[num_slots - 1])

        # Not sure why sum() does not work!!! sum(travel_time_per_emp_sum_dict)
        """
        model.Add(travel_time_final_total == travel_time_per_emp_sum_dict[0] + travel_time_per_emp_sum_dict[1] \
                + travel_time_per_emp_sum_dict[2] + travel_time_per_emp_sum_dict[3]     \
                + travel_time_per_emp_sum_dict[4] + travel_time_per_emp_sum_dict[5]     \
                )
        """
        shared_job_lits = {}

        job_edge_dict = {}  # only for tracking

        # other_start_time_dict = {}
        for slot_i in range(num_slots):

            outgoing_other_job_index.append([])
            num_jobs = len(working_time_slots[slot_i].assigned_job_codes)
            incoming_literals_per_slot[slot_i] = collections.defaultdict(list)
            outgoing_literals_per_slot[slot_i] = collections.defaultdict(list)
            # fmt: off
            for shift in range(num_jobs):
                shift_start_time_dict[slot_i][shift] = model.NewIntVar(
                    MIN_MINUTE, MAX_MINUTE, "start_time_shift_%i" % shift)
                travel_time_until_job[shift] = model.NewIntVar(
                    0, MAX_TRAVEL_MINUTES, "travel_time_until_shift_%i" % shift)

                job_code = working_time_slots[slot_i].assigned_job_codes[shift]
                if job_code in shared_job_lits.keys():
                    for existing_lits in shared_job_lits[job_code]:
                        if existing_lits[0] == slot_i:
                            log.error(
                                f"Duplicated job ({job_code}) code in same slot({working_time_slots[slot_i]})")

                            res_dict = {"status": OptimizerSolutionStatus.INFEASIBLE}
                            return res_dict
                            # raise ValueError(f"Error, duplicated job ({job_code}) code in same slot")
                        # Not necessary for M*N
                        # model.Add( existing_lits[1] == shift_start_time_dict[slot_i][shift] )

                    # Link only the last slot_i literal to this new literal in new slot, for same job
                    last_lit = shared_job_lits[job_code][-1][1]
                    model.Add(last_lit == shift_start_time_dict[slot_i][shift])

                    shared_job_lits[job_code].append((slot_i, shift_start_time_dict[slot_i][shift]))
                else:
                    shared_job_lits[job_code] = [(slot_i, shift_start_time_dict[slot_i][shift])]

            for shift in range(num_jobs):
                #
                job_code = working_time_slots[slot_i].assigned_job_codes[shift]
                #
                # job_duration =  self.env. get_encode_shared_duration_by_planning_efficiency_factor (
                #     self.env.jobs_dict[job_code].requested_duration_minutes,
                #     NBR_OF_WORKERS)
                """
                if working_time_slots[slot_i].assigned_job_codes[shift]["mandatory_minutes_minmax_flag"] == 1:
                    shift_start_time_dict[slot_i][shift] = model.NewIntVar(
                        working_time_slots[slot_i].assigned_job_codes[shift]["requested_start_min_minutes"],
                        working_time_slots[slot_i].assigned_job_codes[shift]["requested_start_max_minutes"],
                        "start_time_shift_%i" % shift,
                    )
                else:
                """
                source_lit_dict[slot_i][shift] = model.NewBoolVar(
                    "Source Emp {} to job {}".format(slot_i, shift))
                # Arc from source worker to this job
                incoming_literals_per_slot[slot_i][shift].append(source_lit_dict[slot_i][shift])

                # If this job[shift] is first job for worker[slot_i], travel time on this job is from home to job.
                model.Add(
                    travel_time_until_job[shift] == self._get_travel_time_from_location_to_job(
                        working_time_slots[slot_i].start_location,
                        working_time_slots[slot_i].assigned_job_codes[shift]
                    )
                ).OnlyEnforceIf(source_lit_dict[slot_i][shift])

                sink_lit_dict[slot_i][shift] = model.NewBoolVar(
                    "Sink job {} to emp {} ".format(shift, slot_i)
                )
                # Arc from job to sinking_worker.
                outgoing_literals_per_slot[slot_i][shift].append(sink_lit_dict[slot_i][shift])

                this_job = self.env.jobs_dict[job_code]
                # If this job[shift] is the last job for worker[slot_i], travel_time_per_emp_sum_dict (total) is the travel time on this job is from job to home.
                model.Add(
                    travel_time_per_emp_sum_dict[slot_i] ==
                    travel_time_until_job[shift] +
                    self._get_travel_time_from_location_to_job(
                        working_time_slots[slot_i].end_location, working_time_slots[slot_i].assigned_job_codes[shift])
                ).OnlyEnforceIf(
                    sink_lit_dict[slot_i][shift]
                )  # from sink_

                # job must obey Start time for worker, if assigned to this worker
                # TODO, only 1 day for now, [0]
                try:
                    model.Add(
                        shift_start_time_dict[slot_i][shift] >= int(
                            working_time_slots[slot_i].start_minutes -
                            working_time_slots[slot_i].start_overtime_minutes +
                            self._get_travel_time_from_location_to_job(
                                working_time_slots[slot_i].start_location,
                                working_time_slots[slot_i].assigned_job_codes[shift]))
                    ).OnlyEnforceIf(source_lit_dict[slot_i][shift])
                except TypeError:
                    log.error(str('internal - int vs float?'))

                #
                # job must obey end time for worker, if assigned to this worker
                model.Add(
                    shift_start_time_dict[slot_i][shift] <= int(
                        working_time_slots[slot_i].end_minutes +
                        working_time_slots[slot_i].end_overtime_minutes -
                        all_job_durations[job_code] - self._get_travel_time_from_location_to_job(
                            working_time_slots[slot_i].end_location,
                            working_time_slots[slot_i].assigned_job_codes[shift]))
                ).OnlyEnforceIf(sink_lit_dict[slot_i][shift])

                for other in range(num_jobs):
                    if shift == other:
                        continue
                    other_job_code = working_time_slots[slot_i].assigned_job_codes[other]
                    other_duration = self.env.jobs_dict[other_job_code].requested_duration_minutes

                    lit = model.NewBoolVar("job path from %i to %i" % (shift, other))
                    job_edge_dict[(slot_i, shift, other)] = lit

                    # constraint for start time by duan 2019-10-09 16:58:42  #### + working_time_slots[slot_i].assigned_job_codes[shift]['requested_duration_minutes'] + min_delay_between_shifts

                    model.Add(
                        shift_start_time_dict[slot_i][shift] + int(all_job_durations[job_code]) + self._get_travel_time_2_sites(working_time_slots[slot_i].assigned_job_codes[shift], working_time_slots[slot_i].assigned_job_codes[other]) <
                        shift_start_time_dict[slot_i][other]
                    ).OnlyEnforceIf(
                        lit
                    )

                    # Increase travel time
                    model.Add(
                        travel_time_until_job[other] ==
                        travel_time_until_job[shift] +
                        self._get_travel_time_2_sites(
                            working_time_slots[slot_i].assigned_job_codes[shift], working_time_slots[slot_i].assigned_job_codes[other])
                    ).OnlyEnforceIf(lit)

                    # Add arc
                    outgoing_literals_per_slot[slot_i][shift].append(lit)
                    incoming_literals_per_slot[slot_i][other].append(lit)

            """
            model.Add(sum(  (  outgoing_literals_per_slot[slot_i][s_i] for s_i in range(num_jobs) )
                ) == 1)
            model.Add(sum( [incoming_literals_per_slot[slot_i][s_i] for s_i in range(num_jobs) ]
            ) == 1)
            """

        # fmt: on
        # Create dag constraint.
        for slot_i in range(num_slots):
            num_jobs = len(working_time_slots[slot_i].assigned_job_codes)
            model.Add(sum((
                sink_lit_dict[slot_i][s_i] for s_i in range(num_jobs)
            )) == 1)
            model.Add(sum((
                source_lit_dict[slot_i][s_i] for s_i in range(num_jobs)
            )) == 1)

            for shift in range(num_jobs):
                model.Add(sum((outgoing_literals_per_slot[slot_i][shift][s_i] for s_i in range(num_jobs))
                              ) == 1)
                model.Add(sum((incoming_literals_per_slot[slot_i][shift][s_i] for s_i in range(num_jobs))
                              ) == 1)

        """
        """
        # model.Add(sum(incoming_sink_literals) == num_slots)
        # model.Add(sum(outgoing_source_literals) == num_slots)

        model.Minimize(travel_time_final_total)

        # Solve model.
        solver = cp_model.CpSolver()
        solver.parameters.log_search_progress = self.config["log_search_progress"]
        # solver.parameters.num_search_workers = 4
        # https://developers.google.com/optimization/cp/cp_tasks
        solver.parameters.max_time_in_seconds = self.config["max_exec_time"]  # two minutes
        status = solver.Solve(model)

        if status != cp_model.OPTIMAL and status != cp_model.FEASIBLE:  #
            log.debug(f"Solver Status = {solver.StatusName(status)}, Not FEASIBLE, failed!")
            res_dict = {"status": OptimizerSolutionStatus.INFEASIBLE}
            return res_dict

        optimal_travel_time = int(solver.ObjectiveValue())
        log.debug(
            f"Solver Status = {solver.StatusName(status)}, optimal_travel_time = {optimal_travel_time} minutes")
        # s_printer = OneSolutionPrinter(__variables,solver)
        # return s_printer.print_solution()
        # return optimal_num_workers
        all_following_tasks = {}
        emp_following_tasks = {}
        """
        for slot_i in range(num_slots):
            print("w_{}_{}: {}, hasta {}".format(
                slot_i,
                workers[slot_i]['worker_code'],
                solver.Value( travel_time_per_emp_sum_dict[slot_i]),
                solver.Value( total_travel_until_emp[slot_i])
                )
            )
        for slot_i in range(num_jobs):
            print("j_{} : {},  travel {}, start: {}".format(
                slot_i,
                working_time_slots[slot_i].assigned_job_codes[slot_i]['requested_duration_minutes'],
                solver.Value(travel_time_until_job[slot_i] ) ,
                solver.Value( shift_start_time_dict[slot_i] [slot_i])
                )
            )
        """

        # j_file.write('')
        to_print_json_list = []
        final_result = {"status": OptimizerSolutionStatus.SUCCESS,
                        "changed_action_dict_by_job_code": {}, "not_changed_job_codes": []}
        for slot_i in range(num_slots):
            to_print_json_list.append([])
            num_jobs = len(working_time_slots[slot_i].assigned_job_codes)

            # for LI in range(num_jobs):
            #     for LJ in range(num_jobs):
            #         if LI != LJ:
            #             print(f"slot-i = {slot_i}, edge: {LI}-{LJ} == {solver.BooleanValue(job_edge_dict[(slot_i,LI,LJ)])}")
            # TODO , to align jobs to job_side, or beginning
            # TODO , add lunch break as objective.
            for shift in range(num_jobs):
                if all_jobs_in_slots[slot_i][shift].scheduled_start_minutes == solver.Value(shift_start_time_dict[slot_i][shift]):
                    changed_flag = False
                else:
                    changed_flag = True
                if changed_flag:
                    this_job_code = all_jobs_in_slots[slot_i][shift].job_code

                    one_job_action_dict = ActionDict(
                        is_forced_action=False,
                        job_code=this_job_code,
                        action_type=ActionType.JOB_FIXED,
                        # self._tmp_get_worker_code_list_by_id_n_ids(primary_id = )
                        scheduled_worker_codes=all_worker_codes_for_each_job_dict[this_job_code],
                        scheduled_start_minutes=solver.Value(shift_start_time_dict[slot_i][shift]),
                        scheduled_duration_minutes=all_jobs_in_slots[slot_i][shift].scheduled_duration_minutes,
                        # slot_code_list =
                    )
                    final_result["changed_action_dict_by_job_code"][all_jobs_in_slots[slot_i]
                                                                    [shift].job_code] = one_job_action_dict
                else:
                    final_result["not_changed_job_codes"].append(
                        all_jobs_in_slots[slot_i][shift].job_code)

                one_job_result = [
                    solver.Value(shift_start_time_dict[slot_i][shift]),
                    all_jobs_in_slots[slot_i][shift].job_code,
                    shift,
                    changed_flag
                ]
                to_print_json_list[slot_i].append(one_job_result)
                # final_result["changed_action_dict_by_job_code"][all_jobs_in_slots [slot_i][shift].job_code] = one_job_result
        res_slots = []
        for job_list in to_print_json_list:
            res_slots.append(sorted(
                job_list,
                key=lambda item: item[0],
                reverse=False,
            ))
        final_result["slots"] = res_slots
        log.debug(final_result)

        return final_result


if __name__ == "__main__":

    import pickle

    slots = pickle.load(open("/tmp/working_time_slots.p", "rb"))

    opti_slot = OptimizerJobsInSlots()
    res = opti_slot.dispatch_jobs_in_slots(slots)
    print(res)
