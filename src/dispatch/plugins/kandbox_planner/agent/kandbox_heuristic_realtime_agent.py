from dispatch.plugins.kandbox_planner.env.configurable_dispatch_env import ConfigurableDispatchEnv
from dispatch.plugins.kandbox_planner.env.env_enums import (
    OptimizerSolutionStatus,
    ActionType,
    JobPlanningStatus,
    ActionScoringResultType,
)
from dispatch.plugins.kandbox_planner.env.env_models import (
    EnvAction,
    JobInSlot,
    RecommendedAction,
    ActionDict,
    LocationTuple,
    Worker,
    # Job,
    # BaseJob,
    # Appointment,
    # Absence,
    ActionEvaluationScore,
    TimeSlotType,
    WorkingTimeSlot,
)
from dispatch.job import service as job_service
from dispatch.order import service as order_service

import random
import numpy as np
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util


from dispatch.plugins.bases.realtime_agent import KandboxAgentPlugin
from dispatch.location_group import service as location_group_service

"""
"""
import pandas as pd
from dispatch.config import APPOINTMENT_DEBUG_LIST, JOB_RECOMMENDATION_INTERVAL
import copy

from collections import namedtuple

from typing import List

import logging
log = logging.getLogger("kandbox_heuristic_realtime_agent")


class KandboxHeuristicRealtimeAgentPlugin(KandboxAgentPlugin):
    title = "Kandbox Plugin - Agent - Heuristic"
    slug = "kandbox_heuristic_realtime_agent"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "real time recommendation for job dispatching by predefined rules"
    version = "0.1.0"
    default_config = {
        "nbr_of_actions": 4,
        "try_location_group": True,
        "location_group_priority_number": 1_000_000,
        "location_group_file_path": "/home/dispatch/easydispatch/project/5gmax/location_group_loc_info_df.csv",
        "try_static_worker_codes": True,
        "static_worker_code_priority_number": 1_00_000,
        "static_worker_codes": "W14",
        "try_closest_workers": False,
        "trace_progress": True,
        "max_jobs_per_worker": 0,
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "nbr_of_actions": {
                "type": "number",
                "default": 5,
                "title": "nbr_of_actions",
            },
            "allow_changing_worker": {
                "type": "boolean",
                "default": False,
                "title": "allow_changing_worker",
            },
            "try_location_group": {
                "type": "boolean",
                "default": True,
                "title": "try_location_group",
            },
            "try_static_worker_codes": {
                "type": "boolean",
                "default": True,
                "title": "try_static_worker_codes",
            },
            "static_worker_codes": {
                "type": "string",
                "default": "W14",
                "description": "static_worker_codes", 
            }, 
    },
    }

    def __init__(self, config=None, env_config=None, env=None):
        self.config = copy.deepcopy(self.default_config)
        if config:
            self.config.update(config)

        self.env = env

        if self.config["try_location_group"] and (self.env is not None):
            self.location_group2worker_mapping = self.get_location_group2worker_mapping(
                env=self.env
            )

        else:
            self.location_group2worker_mapping = dict()

        self.use_naive_search_for_speed = False

    def load_model(self, env_config=None):
        pass

    def train_model_by_data(self, training_data=None, model_path=None):
        return

    def search_action_dict_on_slot(
        self,
        slot,
        curr_job, #: BaseJob,
        attempt_unplan_jobs=False,
        allow_overtime=False,
    ) -> List[RecommendedAction]:
        
        result_rec_list = []
        requested_start_minutes = self.env.env_encode_from_datetime_to_minutes(curr_job.requested_start_datetime) 


        if (slot.start_minutes > requested_start_minutes + curr_job.tolerance_end_minutes) or (
            slot.end_minutes < requested_start_minutes + curr_job.tolerance_start_minutes
        ):
            return result_rec_list 

        if (
            slot.end_minutes
            - slot.start_minutes
            + slot.start_overtime_minutes
            + slot.end_overtime_minutes
        ) < curr_job.scheduled_duration_minutes + 5:
            # This may screen out some apparently no fitting slots, without considering travel time.
            return result_rec_list 

        new_start_minutes = slot.start_minutes
        if (self.env.config["fixed_horizon_flag"] == "1"): #  and self.env.config["rolling_every_day"]
            _env_start = self.env.get_env_planning_horizon_start_minutes()
            if  slot.end_minutes <= _env_start:
                log.info(f"Skipped slot {slot.worker_id}-({slot.start_minutes}->{slot.end_minutes}), _env_start = {_env_start}")
                return result_rec_list 
            new_start_minutes = max(
                new_start_minutes,
                _env_start,
            )
        ji = 0
        for jc in slot.assigned_job_codes:
            if self.env.jobs_dict[jc].scheduled_start_minutes > new_start_minutes:
                # curr_jc = jc
                new_start_minutes = self.env.jobs_dict[jc].scheduled_start_minutes
                break
            ji += 1
        rec_i = 0
        next_interval_start = new_start_minutes - (new_start_minutes % 15) + 15
        next_interval_end = next_interval_start + JOB_RECOMMENDATION_INTERVAL
        while next_interval_end < slot.end_minutes:
            while (new_start_minutes < next_interval_end) and (
                next_interval_end < slot.end_minutes
            ):
                all_travel_difference = []
                all_job_i = []
                while (
                    ji < len(slot.assigned_job_codes) - 1
                ) and new_start_minutes < next_interval_end:
                    loc1 = self.env.jobs_dict[slot.assigned_job_codes[ji]].location
                    loc2 = self.env.jobs_dict[slot.assigned_job_codes[ji + 1]].location
                    triangle_diff = (
                        self.env.travel_router.get_travel_minutes_2locations(
                            loc1, curr_job.location
                        )
                        + self.env.travel_router.get_travel_minutes_2locations(
                            curr_job.location, loc2,
                        )
                        - self.env.travel_router.get_travel_minutes_2locations(loc1, loc2,)
                    )
                    all_travel_difference.append(triangle_diff)
                    all_job_i.append(ji)
                    new_start_minutes = self.env.jobs_dict[
                        slot.assigned_job_codes[ji + 1]
                    ].scheduled_start_minutes
                    ji += 1

                if len(all_travel_difference) > 0:
                    min_job_i_i = np.argmin(all_travel_difference)
                    min_diff = all_travel_difference[min_job_i_i]
                    job_i = all_job_i[min_job_i_i]
                    # Skip all very close jobs to avoid split them
                    if ji < len(slot.assigned_job_codes) - 2:
                        while job_i < len(slot.assigned_job_codes) - 2:
                            if (
                                self.env.travel_router.get_travel_minutes_2locations(
                                    self.env.jobs_dict[slot.assigned_job_codes[job_i]].location,
                                    self.env.jobs_dict[
                                        slot.assigned_job_codes[job_i + 1]
                                    ].location,
                                )
                                > 2
                            ):
                                break
                            job_i += 1
                        if job_i > ji:
                            ji = job_i
                            new_start_minutes = self.env.jobs_dict[
                                slot.assigned_job_codes[ji + 1]
                            ].scheduled_start_minutes
                    job_selected = self.env.jobs_dict[slot.assigned_job_codes[job_i]]
                    rec_start_minutes = (
                        job_selected.scheduled_start_minutes
                        + job_selected.scheduled_duration_minutes
                        + self.env.travel_router.get_travel_minutes_2locations(
                            job_selected.location, curr_job.location
                        )
                    )
                else:
                    rec_start_minutes = new_start_minutes
                    min_diff = 0

                a_rec = RecommendedAction(
                    job_code=curr_job.job_code,
                    # action_type=ActionType.JOB_FIXED,
                    # JobType = JOB, which can be acquired from self.jobs_dict[job_code]
                    scheduled_worker_codes=a_worker_code_list,
                    scheduled_start_minutes=rec_start_minutes,
                    scheduled_duration_minutes=max(curr_job.scheduled_duration_minutes,1),
                    score=round(min_diff, 2),
                    score_detail=[],
                    scoped_slot_code_list=[self.env.slot_server.get_time_slot_key(slot)],
                    job_plan_in_scoped_slots=[],
                    unplanned_job_codes=[],
                )

                result_rec_list.append(a_rec)
                log.info(
                    f"Found solution on slots {a_rec.scoped_slot_code_list} at time: {self.env.env_decode_from_minutes_to_datetime(rec_start_minutes)}"
                )
                new_start_minutes += JOB_RECOMMENDATION_INTERVAL
                new_start_minutes = max(
                    new_start_minutes,
                    rec_start_minutes + JOB_RECOMMENDATION_INTERVAL,
                    next_interval_end,
                )
                new_start_minutes = new_start_minutes - (new_start_minutes % 15) + 15
                next_interval_start = new_start_minutes
                next_interval_end = next_interval_start + JOB_RECOMMENDATION_INTERVAL

                while (
                    ji < len(slot.assigned_job_codes) - 1
                    and self.env.jobs_dict[slot.assigned_job_codes[ji]].scheduled_start_minutes
                    < new_start_minutes
                ):
                    log.info(f"skipped job {slot.assigned_job_codes[ji]}")
                    ji += 1

        # log.info(f"Partial solutions returned")
        return result_rec_list

    def search_action_dict_on_multiple_workers(
        self,
        a_worker_code_list: List[str],
        curr_job, # : BaseJob
        max_number_of_matching: int = 9,
        attempt_unplan_jobs=False,
        allow_overtime=False,
    ) -> List[RecommendedAction]:
        # if "job_gps" not in curr_job.keys():
        #    curr_job["job_gps"] = ([curr_job.location[0], curr_job.location[1]],)
        if curr_job.job_code in APPOINTMENT_DEBUG_LIST:
            log.info(
                f"appt={curr_job.job_code}, worker_codes:{a_worker_code_list} started searching..."
            )
        if (curr_job.requested_duration_minutes is None) or (
            curr_job.requested_duration_minutes < 1
        ):
            log.error(
                f"appt={curr_job.job_code}, requested_duration_minutes = {curr_job.requested_duration_minutes}, no recommendation is possible, quitting..."
            )
            return []
        scheduled_duration_minutes = self.env.get_encode_shared_duration_by_planning_efficiency_factor(
            requested_duration_minutes=curr_job.requested_duration_minutes,
            nbr_workers=len(a_worker_code_list),
        )
        # if len(a_worker_code_list) > 1:
        # else:
        #     scheduled_duration_minutes = curr_job.requested_duration_minutes

        curr_job.scheduled_duration_minutes = scheduled_duration_minutes
        # self.env.jobs_dict[
        #     curr_job.job_code
        # ].scheduled_duration_minutes = scheduled_duration_minutes

        result_slot = []
        time_slot_list = []

        original_travel_minutes_difference = 0
        if curr_job.planning_status != JobPlanningStatus.UNPLANNED:
            for worker_code in curr_job.scheduled_worker_codes:
                a_slot_group = self.env.slot_server.get_overlapped_slots(
                    worker_code=worker_code,
                    start_minutes=curr_job.scheduled_start_minutes,
                    end_minutes=curr_job.scheduled_start_minutes
                    + curr_job.scheduled_duration_minutes,
                )
                for a_slot in a_slot_group:
                    try:
                        original_travel_minutes_difference += self.calc_travel_minutes_difference_for_1_job(
                            env=self.env, a_slot=a_slot, curr_job=curr_job
                        )
                    except ValueError as err:
                        log.debug(
                            f"JOB:{curr_job.job_code}:ERROR:{err}, This job has lost the worker time slot, For now, no more recomemndations. and then I set original_travel_minutes_difference = 0"
                        )
                        original_travel_minutes_difference = 0
                        # For now, no more recomemndations , TODO @duan
                        # return []

        for curr_worker_code in a_worker_code_list:
            if curr_worker_code not in self.env.workers_dict.keys():
                log.error(
                    f"WORKER:{curr_worker_code}: Worker is requested to be searched but not found in env."
                )
                return []
            log.debug(
                f"Querying slots, worker_code={curr_worker_code}, start_minutes={self.env.env_decode_from_minutes_to_datetime(curr_job.requested_start_min_minutes)}, end_minutes={self.env.env_decode_from_minutes_to_datetime(curr_job.requested_start_max_minutes)}")
            curr_overlapped_slot_list = self.env.slot_server.get_overlapped_slots(
                worker_code=curr_worker_code,
                start_minutes=curr_job.requested_start_min_minutes,
                end_minutes=curr_job.requested_start_max_minutes,
            )
            curr_free_slot_list = []
            for slot in curr_overlapped_slot_list:

                log.debug(f"Checking slot: {self.env.slot_server.get_time_slot_key(slot)}")
                if slot.slot_type == TimeSlotType.FLOATING:
                    if allow_overtime:
                        # If attempt_unplan_jobs is set true, this is already secondary round.
                        # I will also consider the overtime minutes for each worker
                        #
                        new_overtime_minutes = self.env.get_worker_available_overtime_minutes(
                            slot.worker_code, day_seq=int(slot.start_minutes / 1440))
                        if slot.prev_slot_code is None:
                            slot.start_overtime_minutes += new_overtime_minutes
                        if slot.next_slot_code is None:
                            slot.end_overtime_minutes += new_overtime_minutes

                    if (
                        slot.end_minutes
                        - slot.start_minutes
                        + slot.start_overtime_minutes
                        + slot.end_overtime_minutes
                    ) > scheduled_duration_minutes:
                        # This may screen out some apparently no fitting slots, without considering travel time.

                        curr_free_slot_list.append(slot)
                        log.debug(
                            f"worker_codes:{a_worker_code_list}:worker:{curr_worker_code}: identified one free slot ({slot.start_minutes}->{slot.end_minutes})."
                        )

            if len(curr_free_slot_list) < 1:
                log.debug(
                    f"appt={curr_job.job_code}, worker_codes:{a_worker_code_list}:worker:{curr_worker_code}: Worker has no free slots left by tolerance ({curr_job.requested_start_min_minutes}->{curr_job.requested_start_max_minutes}) ({self.env.env_decode_from_minutes_to_datetime(curr_job.requested_start_min_minutes)}->{self.env.env_decode_from_minutes_to_datetime(curr_job.requested_start_max_minutes)})."
                )
                return []
            # if curr_job.job_code in APPOINTMENT_DEBUG_LIST:
            # log.debug(
            #     "All free slots identified: "
            #     + str(
            #         [
            #             f"worker_code = {w.worker_code}, start_minutes= {w.start_minutes}, end_minutes= {w.end_minutes}, assigned_job_codes= {w.assigned_job_codes}"
            #             for w in curr_free_slot_list
            #         ]
            #     )
            # )
            time_slot_list.append(sorted(curr_free_slot_list, key=lambda item: item.start_minutes,))

        if len(time_slot_list) < 1:
            log.warning("should not happend: len(time_slot_list) < 1")
            return []

        # This appends the customer avavailable slots to be the last timeslot list to screen against all work's timeslots.
        # I assume that customer does not like current time slot and remove it from available slot,
        # TODO, @duan, 2020-12-17 19:23:53 Why available_slots is on locaiton? different jobs may differ.

        orig_avail = copy.deepcopy(curr_job.available_slots)
        if len(orig_avail) < 1:
            log.info(
                f"appt={curr_job.job_code}, job_available_slots:{orig_avail}: No available slots per customer availability."
            )
            return []
        else:
            # if curr_job.job_code in APPOINTMENT_DEBUG_LIST:
            log.debug(
                f"appt={curr_job.job_code}, len(orig_avail) ={len(orig_avail)}: Found available slots per customer availability."
            )

        # This fake_appt_time_slot will used to host the slot intersection result, especially after customer availability
        fake_appt_time_slot = copy.deepcopy(orig_avail[0])
        fake_appt_time_slot.assigned_job_codes = [curr_job.job_code]

        # This is to exclude those available slots that overlap with current scheduling time.
        # Make sure that customer do not get same time slots (meaningless, from other technicians) as current one.
        net_cust_avail_slots = []
        slot_to_exclude = (
            curr_job.scheduled_start_minutes - 60,
            curr_job.scheduled_start_minutes + 90,
        )
        for ti in range(len(orig_avail)):
            slot_ti = (orig_avail[ti].start_minutes, orig_avail[ti].end_minutes)
            clip = date_util.clip_time_period(slot_ti, slot_to_exclude)
            if len(clip) < 1:
                net_cust_avail_slots.append(orig_avail[ti])
            else:
                if clip[0] > orig_avail[ti].start_minutes:
                    a_slot = copy.copy(orig_avail[ti])
                    a_slot.end_minutes = clip[0]
                    net_cust_avail_slots.append(a_slot)
                if clip[1] < orig_avail[ti].end_minutes:
                    a_slot = copy.copy(orig_avail[ti])
                    a_slot.start_minutes = clip[1]
                    net_cust_avail_slots.append(a_slot)

        # To include the customer available time slots in the search
        time_slot_list.append(net_cust_avail_slots)
        # = {net_cust_avail_slots}
        log.debug(f"Final net_cust_avail_slots len={len(net_cust_avail_slots)}")

        available_slot_groups = self.env.intersect_geo_time_slots(
            time_slot_list,
            curr_job,
            duration_minutes=scheduled_duration_minutes,
            max_number_of_matching=max_number_of_matching,
        )

        # if ( free_slot.start_minutes <= start_minutes - travel_minutes ) &  ( end_minutes <= free_slot[1]):
        # if len(available_slot_groups) < 1:
        # no hit in this day_i
        #    continue
        log.debug(
            f"after env.intersect_geo_time_slots, available_slot_groups len={len(available_slot_groups)}."
        )
        for avail_slot_group in available_slot_groups:
            scoped_slot_list = avail_slot_group[2]
            shared_time_slots_temp = []
            for sc_slot in scoped_slot_list[:-1]:
                try:
                    # TODO, merge this with first filtering. with overtime minutes processing 2021-01-01 10:18:06
                    sc = self.env.slot_server.get_time_slot_key(sc_slot)
                    temp_slot_ = self.env.slot_server.get_slot(
                        redis_handler=self.env.slot_server.r, slot_code=sc
                    )
                    temp_slot_.start_overtime_minutes = sc_slot.start_overtime_minutes
                    temp_slot_.end_overtime_minutes = sc_slot.end_overtime_minutes
                    shared_time_slots_temp.append(temp_slot_)
                except Exception as mse:
                    log.error(f"failed to read slot {str(sc)}, error {str(mse)}")
            if len(shared_time_slots_temp) < 1:
                # After checking redis, there is no valid slot in the list
                log.info(
                    f"appt={curr_job.job_code}, After checking redis, there is no valid slot in the list, No available slots."
                )
                continue

            shared_time_slots_temp.append(scoped_slot_list[-1])

            shared_time_slots = shared_time_slots_temp.copy()
            # shared_time_slots_optimized may be changed/mutated during optimization process. Deep copy it.
            shared_time_slots_optimized = copy.deepcopy(shared_time_slots)

            for one_working_slot in shared_time_slots_optimized:
                one_working_slot.assigned_job_codes = sorted(
                    one_working_slot.assigned_job_codes,
                    key=lambda x: self.env.jobs_dict[x].scheduled_start_minutes
                    if x in self.env.jobs_dict
                    else 0,
                )

                one_working_slot.assigned_job_codes.append(curr_job.job_code)

            # TODO, then append other related shared code slots... Right now only this one.

            # This is the last attached fake time slot according to availability search
            # TODO: WHy two availability?
            fake_appt_time_slot.start_minutes = avail_slot_group[0]
            fake_appt_time_slot.end_minutes = avail_slot_group[1]
            shared_time_slots_optimized.append(fake_appt_time_slot)

            if self.use_naive_search_for_speed:
                dispatch_jobs_in_slots_func = self.env.inner_slot_heur.dispatch_jobs_in_slots
            else:
                dispatch_jobs_in_slots_func = self.env.inner_slot_opti.dispatch_jobs_in_slots

            unplanned_job_codes = []
            # res = {"status":OptimizerSolutionStatus.INFEASIBLE}
            res = dispatch_jobs_in_slots_func(shared_time_slots_optimized)
            while attempt_unplan_jobs & (res.status != OptimizerSolutionStatus.SUCCESS):
                is_shrinked = False
                for ts in shared_time_slots_optimized:
                    if len(ts.assigned_job_codes) > 1:
                        j_i = len(ts.assigned_job_codes) - 2
                        while j_i >= 0:
                            job_code_to_unplan = ts.assigned_job_codes[j_i]
                            if self.env.jobs_dict[job_code_to_unplan].priority < curr_job.priority:
                                unplanned_job_codes.append(job_code_to_unplan)
                                ts.assigned_job_codes = (
                                    ts.assigned_job_codes[0:j_i] + ts.assigned_job_codes[j_i + 1 :]
                                )
                                is_shrinked = True

                                log.info(
                                    f"job={curr_job.job_code}, attempting search after unplanning job {job_code_to_unplan}, to {ts.assigned_job_codes}, priority { self.env.jobs_dict[job_code_to_unplan].priority , curr_job.priority} ..."
                                )
                                break
                            j_i -= 1
                    if is_shrinked:
                        # only unplan one job in each attempt
                        break
                if not is_shrinked:
                    # No job can be unplanned.
                    break
                res = dispatch_jobs_in_slots_func(shared_time_slots_optimized)
                if res.status == OptimizerSolutionStatus.SUCCESS:
                    break

            if res.status != OptimizerSolutionStatus.SUCCESS:
                log.info(f"appt={curr_job.job_code}, failed to find solution on slots: " + str(
                    [f"(worker_code = {w.worker_code}, start_datetime= {self.env.env_decode_from_minutes_to_datetime(w.start_minutes)}, end_datetime= {self.env.env_decode_from_minutes_to_datetime(w.end_minutes)}, assigned_job_codes= {w.assigned_job_codes}) " for w in shared_time_slots_optimized]))
                continue
            try:

                new_start_mintues = res.changed_action_dict_by_job_code[
                    curr_job.job_code
                ].scheduled_start_minutes
            except KeyError:
                log.error(
                    f"{curr_job.job_code} is not in changed_action_dict_by_job_code. I should have already excluded it from search."
                )
                continue

            new_action_dict = ActionDict(
                is_forced_action=False,
                job_code=curr_job.job_code,
                action_type=ActionType.JOB_FIXED,
                scheduled_worker_codes=a_worker_code_list,
                scheduled_start_minutes=new_start_mintues,
                scheduled_duration_minutes=curr_job.scheduled_duration_minutes,
            )
            rule_check_result = self.env._check_action_on_rule_set(
                a_dict=new_action_dict, unplanned_job_codes=unplanned_job_codes
            )
            # TODO, track Failed number
            if rule_check_result.status_code == ActionScoringResultType.ERROR:
                log.info(
                    f"Failed on rule set check after acquiring recommendation. Skipped. appt = {curr_job.job_code}, workers = {a_worker_code_list}, start = {new_start_mintues}, messages = {['{}---{}---{}'.format(m.score,m.score_type, m.message) for m in rule_check_result.messages]} "
                )

                continue
            # This may not be necessary , because I have executed optimize_slot and the slot contains only possible jobs
            #
            # cut_off_success_flag, message_dict = self.env.slot_server.cut_off_time_slots(
            #     action_dict=new_action_dict, probe_only=True
            # )
            # if not cut_off_success_flag:
            #     log.info(
            #         f"After rule set, failed on probing cutting off slots. appt = {curr_job.job_code}, workers = {a_worker_code_list}, start = {new_start_mintues}, messages = {str(message_dict)} "
            #     )
            #     continue

            log.info(
                f"appt = {curr_job.job_code}, workers = {a_worker_code_list}, start = {new_start_mintues}, The solution passed all rules."
            )

            #  Now I should trim the last time slot attached as customer availability
            scoped_slot_code_list_no_cust = [
                self.env.slot_server.get_time_slot_key(s)
                for s in scoped_slot_list[0 : len(a_worker_code_list)]
            ]
            # Here i should also assert that len(scoped_slot_code_list) == worker_lenth + 1

            new_travel_minutes_difference = 0
            for a_slot in shared_time_slots:
                (prev_travel, next_travel, inside_travel,) = self.env.get_travel_time_jobs_in_slot(
                    a_slot, a_slot.assigned_job_codes
                )
                new_travel_minutes_difference -= prev_travel + next_travel + sum(inside_travel)

            for a_slot in shared_time_slots_optimized:
                (prev_travel, next_travel, inside_travel,) = self.env.get_travel_time_jobs_in_slot(
                    a_slot, a_slot.assigned_job_codes
                )
                new_travel_minutes_difference += prev_travel + next_travel + sum(inside_travel)

            total_score = (
                (
                    self.env.config["scoring_factor_standard_travel_minutes"]
                    - new_travel_minutes_difference
                    + original_travel_minutes_difference
                )
                / self.env.config["scoring_factor_standard_travel_minutes"]
            ) - (len(unplanned_job_codes) * 0.5)

            if allow_overtime:
                total_score -= 2

            travel_message = f"original minutes difference:{original_travel_minutes_difference}, new minutes difference: {new_travel_minutes_difference}"
            metrics_detail = {
                "original_minutes_difference": original_travel_minutes_difference,
                "new_minutes_difference": new_travel_minutes_difference,
            }
            travel_score_obj = ActionEvaluationScore(
                score=total_score,
                score_type="travel_difference",
                message=travel_message,
                metrics_detail=metrics_detail,
            )
            # if curr_job.job_code == "04856415-b6ae-4aeb-9e6d-ff399f00de0d":
            #     log.debug("04856415-b6ae-4aeb-9e6d-ff399f00de0d")

            a_rec = RecommendedAction(
                job_code=curr_job.job_code,
                # action_type=ActionType.JOB_FIXED,
                # JobType = JOB, which can be acquired from self.jobs_dict[job_code]
                scheduled_worker_codes=a_worker_code_list,
                scheduled_start_minutes=new_start_mintues,
                scheduled_duration_minutes=max(curr_job.scheduled_duration_minutes,1),
                score=total_score,
                score_detail=[travel_score_obj],
                scoped_slot_code_list=scoped_slot_code_list_no_cust,
                job_plan_in_scoped_slots=res.planned_job_sequence[0 : len(a_worker_code_list)],
                unplanned_job_codes=unplanned_job_codes,
            )

            log.info(
                f"Found solution on slots {a_rec.scoped_slot_code_list} at time: {self.env.env_decode_from_minutes_to_datetime(new_start_mintues)}"
            )
            # TODO for @Xingtong, calculate KPI about recommendation

            result_slot.append(a_rec)
            if len(result_slot) >= max_number_of_matching:
                return result_slot
        # log.info(f"Partial solutions returned")
        return result_slot

    def calc_travel_minutes_difference_for_1_job(self, env=None, a_slot=None, curr_job=None):
        original_travel_minutes_difference = 0
        # This is temp fix 2020-11-29 20:15:13
        return original_travel_minutes_difference

        the_job_index = a_slot.assigned_job_codes.index(curr_job.job_code)
        if the_job_index >= len(a_slot.assigned_job_codes) - 1:
            next_location = a_slot.end_location
        else:
            next_location = env.jobs_dict[a_slot.assigned_job_codes[the_job_index + 1]].location

        if the_job_index < 1:
            prev_location = a_slot.start_location
        else:
            prev_location = env.jobs_dict[a_slot.assigned_job_codes[the_job_index - 1]].location

        original_travel_minutes_difference += (
            original_travel_minutes_difference
            + env.travel_router.get_travel_minutes_2locations(prev_location, next_location)
        )

        original_travel_minutes_difference -= (
            original_travel_minutes_difference
            + env.travel_router.get_travel_minutes_2locations(prev_location, curr_job.location)
        )

        original_travel_minutes_difference -= (
            original_travel_minutes_difference
            + env.travel_router.get_travel_minutes_2locations(next_location, curr_job.location)
        )
        return original_travel_minutes_difference

    def get_location_group2worker_mapping(self, env):
        # 查询 job 关联worker的信息
        return location_group_service.get_query_all_with_worker_code(db_session = env.kp_data_adapter.db_session)


    def get_workers_to_check(self, curr_job):

        # TODO @duan
        candidates = []

        try:
            
            if (curr_job.planning_status != JobPlanningStatus.UNPLANNED) and (not self.config.get("allow_changing_worker", False)):
                return [curr_job.scheduled_worker_codes]

            if self.config["try_location_group"]:
                lg_code = curr_job.flex_form_data.get("location_group_code", "__")
                if lg_code in self.location_group2worker_mapping:
                    aw_code = self.location_group2worker_mapping[lg_code]
                    if aw_code in self.env.workers_dict:  # keys()
                        candidates = candidates + [(aw_code,)]

            if self.config["try_static_worker_codes"]:
                static_worker_codes = self.config["static_worker_codes"].split(",")

                candidates = candidates + [(w,) for w in static_worker_codes]

            if len(candidates) < 1:
                return curr_job.searching_worker_candidates

        except Exception as e:
            print(e)
            return []
        return candidates
        """
        shared_worker_count = 1
        if curr_job.planning_status != JobPlanningStatus.UNPLANNED:
            shared_worker_count = len(curr_job.scheduled_worker_codes)

        # scheduled_duration_minutes = job.requested_duration_minutes
        if (curr_job.flex_form_data["ShareStatus"] == "M") and shared_worker_count <= 1:
            shared_worker_count = 2
        if (curr_job.flex_form_data["ShareStatus"] == "N") and shared_worker_count > 1:
            shared_worker_count = 1

        hist_job_workers_ranked = [
            [k, v]
            for k, v in sorted(
                curr_job.location.historical_serving_worker_distribution.items(),
                key=lambda item: item[1],
                reverse=True,
            )
            if curr_job.requested_primary_worker_code != k
        ]
        workers_to_check = []
        if shared_worker_count == 1:
            workers_to_check.append([curr_job.requested_primary_worker_code])
            for hist_worker_count in hist_job_workers_ranked:
                # print(hist_worker_count)
                curr_worker_code = [hist_worker_count[0]]  #
                workers_to_check.append(curr_worker_code)

        else:  # Primary must be default when shared.
            for hist_worker_count in hist_job_workers_ranked:
                # print(hist_worker_count) . There should not no limit on count
                curr_worker_code = [
                    curr_job.requested_primary_worker_code,
                    hist_worker_count[0],
                ]  #
                workers_to_check.append(curr_worker_code)

        return workers_to_check
        """

    def predict_action(self, env: ConfigurableDispatchEnv, todo_action: EnvAction, db_session = None): 
        curr_job = todo_action.jobs[0]
        env_job = env.env_encode_single_job_db(curr_job)
        nearby_slots, dist_list = env.get_nearby_slots(
            loc=[curr_job.geo_longitude, curr_job.geo_latitude, ],
            worker_blacklist = [],
            worker_whitelist = [],
            overwrite_max_orders_limit = False,
            area_code = curr_job.flex_form_data.get("area_code","A"),
            return_on_first_priority_worker = True,
            drop_off_location = None,
            order_info = curr_job.code,
            # min_free_items=env_job.requested_items,
        )
        # result_rec_list = []
        for si, slot in enumerate(nearby_slots):
            if len(slot.assigned_jobs) < 1:
                start_loc = [slot.start_longitude, slot.start_latitude, ]
                current_start = slot.start_minutes
            else:
                start_loc = [slot.assigned_jobs[0].geo_longitude, slot.assigned_jobs[0].geo_latitude, ]
                current_start = slot.assigned_jobs[0].scheduled_start_minutes + slot.assigned_jobs[0].scheduled_duration_minutes + 1

            if len(slot.assigned_jobs) < 2:
                env_job.prev_travel = env.get_travel_router().get_travel_minutes_2locations(
                    start_loc, (curr_job.geo_longitude, curr_job.geo_latitude) 
                )
                env_job.scheduled_start_minutes = current_start + env_job.prev_travel

                slot.available_free_minutes = slot.end_minutes - env_job.scheduled_start_minutes - env_job.scheduled_duration_minutes
                slot.assigned_jobs = slot.assigned_jobs + [env_job]
                todo_action.scheduled_slots = [slot]
                todo_action.action_type = ActionType.FLOATING
                return todo_action
            
            _assigned_new = env.solve_tsp_slot_assigned_jobs(assigned_jobs=slot.assigned_jobs + [env_job])
            slot.assigned_jobs = _assigned_new
            # print(f"_assigned_new = {_assigned_new}")
            slot.available_free_minutes = 0
            todo_action.scheduled_slots = [slot]
            todo_action.action_type = ActionType.FLOATING
            return todo_action
        else:
            todo_action.action_type = ActionType.TODO
            return todo_action

    def dispatch2slot(
        self,
        env: ConfigurableDispatchEnv, 
        env_jobs: List[JobInSlot],
        slots:List[WorkingTimeSlot],
        dist_list = None,
        dist_matrix = None

    ) -> List[dict]:
        if len(slots) < 1 or len(env_jobs) < 1:
            return []
        curr_job = env_jobs[0]

        result_rec_list = []
        for si, slot in enumerate(slots):

            if len(slot.assigned_jobs) < 1:
                rec_start_minutes = slot.start_minutes
                start_loc = [slot.start_longitude, slot.start_latitude, ]
            else:
                rec_start_minutes = slot.assigned_jobs[-1].scheduled_start_minutes + 5
                start_loc = [slot.assigned_jobs[-1].geo_longitude, slot.assigned_jobs[-1].geo_latitude, ]

            travel_minutes = env.haversine_travel_router.get_travel_minutes_2locations(
                            start_loc, [curr_job.geo_longitude, curr_job.geo_latitude, ]
                        )
            new_start = rec_start_minutes + (travel_minutes / 5)
            env_jobs[0].scheduled_start_minutes = new_start
            slot.assigned_jobs.append(env_jobs[0])

            # travel_minutes = dist_list[si] / 1000 
            
            solution = {
                "score": round(travel_minutes, 2),
                "slots": [slot],
                "start_minutes":rec_start_minutes,
                "dist":  round(travel_minutes, 2),
            }
            
            result_rec_list.append(solution)
            if len(result_rec_list) > self.config["nbr_of_actions"] : # 5
                break
        return sorted(result_rec_list, key=lambda a: a["score"], reverse=False)