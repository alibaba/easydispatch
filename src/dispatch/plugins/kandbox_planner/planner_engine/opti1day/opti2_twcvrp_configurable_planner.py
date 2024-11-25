# batch optimizer based on vroom,  using pyvroom library

from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import vroom
import math

from dispatch import config
from dispatch.plugins.kandbox_planner.env.configurable_dispatch_env import ConfigurableDispatchEnv
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
from dispatch.location_group import service as location_group_service

from dispatch.plugins.kandbox_planner.env.env_models import ActionDict, JobInSlot
import copy
from dispatch.job import service as job_service
from dispatch.plugins.kandbox_planner.util.kandbox_util import from_time_window_str_to_list 
from dispatch.team.models import Team
from dispatch.job.models import Job
# from dispatch.item import service as item_service
# from dispatch.job.models import JobPlanningInfoUpdate

# from dispatch.plugins.kandbox_planner.env.env_enums import LocationType
# from dispatch.plugins.kandbox_planner.env.env_models import JobLocationBase

# from k_means_constrained import KMeansConstrained
# from size_constrained_clustering import  minmax 
# by default it is euclidean distance, but can select others
# from sklearn.metrics.pairwise import haversine_distances
import logging
log = logging.getLogger("opti2_twcvrp_configurable_planner")

from typing import List, Dict, Any, Optional
import pydantic 

MAX_INT = int(np.iinfo(np.intp).max / 10)
from dispatch.plugins.kandbox_planner.env.env_models import  OptiJobLoc, OptiContext

# (j.geo_longitude, j.geo_latitude, j.code, all_job_index, c_weight, c_volume, 1, c_time_window))

class ConfigurableVRoomTWCVRPPlanner(KandboxBatchOptimizerPlugin):

    title = "Configurable TW-C-VRP Planner"
    slug = "opti2_twcvrp_configurable_planner"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan/kandbox_dispatch"
    description = "This is a Batch Optimizer. Configurable C-VRP Planner"
    version = "0.1.0"
    default_config = {
        "load_init_stock": 0,
        "log_search_progress": False,
        # "max_exec_seconds": 10, 
        "enable_max_order_constraint": 0,
        "enable_weight_constraint": 1,
        "enable_volume_constraint": 0,
        "enable_location_group_constraint":0,
        "enable_time_window_constraint": 1,
        "enable_return2home_constraint":0,
        "enable_start_from_home_constraint":1,
        "enable_fix_planned_constraint":1,
        "enable_always_start_from_depot":0,
        "enable_always_return2depot":0,
        "run_pickup_job_dispatching":True,
        "plan_all_to_beginning_no_travel": False,
        "travel_minutes_scale_factor":1,
        "volume_constraint_code":"volume",
        "weight_constraint_code":"weight" # order_count
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "weight_constraint_code": {
                "type": "string",
                "default": "weight", 
                "description": "weight_constraint_code"
            },
            "enable_location_group_constraint": {
                "type": "number", 
                "description": "enable_location_group_constraint, 1 means yes",
            },
            "enable_max_order_constraint": {
                "type": "number", 
                "description": "enable_max_order_constraint, 1 means yes",
            },
            "enable_weight_constraint": {
                "type": "number", 
                "description": "enable_weight_constraint, 1 means yes",
            },
            "enable_volume_constraint": {
                "type": "number",
                "description": "enable_volume_constraint, 1 means yes",
            },
            "enable_time_window_constraint": {
                "type": "number",
                "description": "enable_time_window_constraint, 1 means yes",
            },
            "enable_return2home_constraint": {
                "type": "number",
                "description": "enable_return2home_constraint, 1 means yes"
            },
            "enable_always_start_from_depot": {
                "type": "number",
                "description": "enable_always_start_from_depot, 1 means yes"
            },
            "enable_always_return2depot": {
                "type": "number",
                "description": "enable_always_return2depot, 1 means yes"
            },
            "travel_minutes_scale_factor": {
                "type": "number",
                "default": "1.0",
                "description": "travel_minutes_scale_factor, this can scale up or down routing time.",
            },
        },
    }

    def __init__(self, config=None):
        self.config = self.default_config.copy()
        if config is not None:
            self.config.update(config)

        self.location_group2worker_index = {}
        self.worker_code2index = {}


    def dispatch_jobs(self, env:ConfigurableDispatchEnv, db_session, rl_agent=None, batch_request=None):
        # Real batch, rl_agent is skilpped.
        #
        if  env.nbr_minutes_planning_windows_duration > 1440:
            log.error("I can plan all workers for one day only.")
            return
        self.env = env 

        worker_slots_all = self.env.get_working_slot_list(active_only = False)
        if len(worker_slots_all) < 1:
            log.info(f"dispatch_jobs: No active worker slots are found, quitting at {datetime.now()}")
            return False
        enable_time_window_constraint =  str(self.config.get("enable_time_window_constraint", "0"))  == "1"

        self.location_group2worker_index = {}
        self.worker_code2index = {}
        if int(self.config.get("enable_location_group_constraint", 0)) == 1 or int(self.config.get("enable_fix_planned_constraint", 0)) == 1:
            lg2worker_code = location_group_service.get_query_all_with_worker_code(
                    db_session = db_session)
            # wc2lg = {v:k for k,v in lg2worker_code.items()}
            for si, s in enumerate(worker_slots_all):
                self.worker_code2index[s.worker_code] = si
                # if s.worker_code in wc2lg:
                #     lg_code = wc2lg[s.worker_code]
                #     self.location_group2worker_index[lg_code] = si
            for lg_code in lg2worker_code.keys():
                self.location_group2worker_index[lg_code] = self.worker_code2index[lg2worker_code[lg_code]]

            log.info(f"enable_location_group_constraint or enable_fix_planned_constraint is true, with lg={lg2worker_code}, lg2work_index: {self.location_group2worker_index}, self.worker_code2index = {self.worker_code2index}")

        begin_time = datetime.now()
        log.info(f"Started dispatching at time: {begin_time}, with config: {self.config}")

        # opti_start_datetime = env.env_decode_from_minutes_to_datetime(
        #     env.get_env_planning_horizon_start_minutes() 
        #     ) 
        # opti_end_datetime = env.env_decode_from_minutes_to_datetime(
        #     env.get_env_planning_horizon_end_minutes()
        # )
        # day_jobs = job_service.get_jobs_worker_days( 
        #             db_session=db_session,
        #             start_datetime = opti_start_datetime, 
        #             end_datetime = opti_end_datetime,
        #             worker_code = None,
        #             include_unplanned = True,
        #             include_inplanning = True,
        #             nbr_minutes_backward_unplanned_jobs = env.nbr_minutes_backward_unplanned_jobs # N个小时之内的,当前时间的前N个小时 
        #         )
        day_jobs = env.get_env_batch_opti_jobs(db_session)
        
        team = db_session.query(Team).filter(Team.id == self.env.team_id).one_or_none()
        if not team:
            raise ValueError(f"team not found,id: {self.team_id} ")
        all_job_list = [None]
        ctx = OptiContext()

        jobs_locs = [
            OptiJobLoc(
                geo_longitude = team.geo_longitude,
                geo_latitude = team.geo_latitude,
                node_type = "depot",
                orig_index = 0,
                code = "depot",
                c_weight = 0,
                c_volume = 0,
                c_time_window = [],
                skills = None,
                fixed_worker_index = None
                # flex_form_data={}
            )
        ]
        # all_job_list = []
        all_job_index=1
        for ji, j in enumerate(day_jobs):
            if j.planning_status not in (JobPlanningStatus.UNPLANNED, JobPlanningStatus.IN_PLANNING, JobPlanningStatus.PLANNED):
                continue 
            
            
            # c_weight = int(j.flex_form_data.get(self.config.get("weight_constraint_code", "weight"), 1)) # *1.5 
            # c_volume = int(j.flex_form_data.get(self.config.get("volume_constraint_code", "volume"), 1)) # *1.5
            c_weight = math.ceil(float(j.flex_form_data.get(self.config.get("weight_constraint_code", "weight"), 1)))
            c_volume = math.ceil(float(j.flex_form_data.get(self.config.get("volume_constraint_code", "volume"), 1)))
            
            # c_time_window = from_time_window_str_to_list( j.flex_form_data.get("time_window_list", "")) # *1.5
            if enable_time_window_constraint:
                c_time_window = env.from_time_window_flex_form_to_list(j.flex_form_data) # *1.5
            else:
                c_time_window = []
            fixed_worker_index = None
            if j.planning_status == JobPlanningStatus.PLANNED:
                if str(self.config.get("enable_fix_planned_constraint", "0")) == "1":
                    fixed_worker_index = self.worker_code2index[j.scheduled_primary_worker_code]
                else:
                    log.warning(f"job: {j.code} is planned, but enable_fix_planned_constraint is not enabled. Job Skipped")
                    # continue
            if j.planning_status == JobPlanningStatus.IN_PLANNING:
                if str(j.flex_form_data.get("allow_in_planning2others", "0")) == "0":
                    fixed_worker_index = self.worker_code2index[j.scheduled_primary_worker_code]
                else:
                    log.warning(f"job: {j.code} is planned, but enable_fix_planned_constraint is not enabled. Job Skipped")
                    # continue

            if int(self.config.get("enable_location_group_constraint", 0)) == 1:
                lg_code = j.flex_form_data.get('location_group_code', None)
                if lg_code:
                    if lg_code in self.location_group2worker_index:
                        if fixed_worker_index is not None:
                            if self.location_group2worker_index[lg_code] != fixed_worker_index:
                                log.error(f"location group {lg_code} specifying different worker {self.location_group2worker_index[lg_code]} than planned {fixed_worker_index}.")
                        else:
                            fixed_worker_index = self.location_group2worker_index[lg_code]
                    else:
                        log.warning(f"{lg_code} is not found from location_group2worker_index.")
            skills = None
            if int(self.config.get("enable_skills", 0)) == 1:
                skill_code_str = j.flex_form_data.get('skills', "")
                if len(skill_code_str) > 0:
                    skills = ctx.convert_skills(skill_code_str.split(config.SEPERATOR_FLEX_0)) 



            jobs_locs.append(
                OptiJobLoc(
                    geo_longitude = j.geo_longitude,
                    geo_latitude = j.geo_latitude,
                    node_type = "job",
                    orig_index = ji,
                    code = j.code,
                    c_weight = c_weight,
                    c_volume = c_volume,
                    c_time_window = c_time_window,
                    fixed_worker_index = fixed_worker_index,
                    requested_duration_minutes = j.requested_duration_minutes if j.requested_duration_minutes is not None else 1,
                    skills = skills,
                    flex_form_data= j.flex_form_data
                )
            )
            all_job_list.append(j)
            all_job_index +=1
        if str(self.config.get("enable_return2home_constraint", "1")) == "1" or (
            str(self.config.get("enable_start_from_home_constraint", "1")) == "1"  
           ):
            for si, s in enumerate(worker_slots_all):
                if round(s.start_longitude,5) != round(team.geo_longitude,5
                ) or round(s.start_latitude,5) != round(team.geo_latitude,5):
                    if enable_time_window_constraint:
                        c_time_window = [[
                            s.start_minutes - self.env.get_env_start_minutes(),
                            s.end_minutes - self.env.get_env_start_minutes()
                        ]]
                    else:
                        c_time_window = []
                    jobs_locs.append(
                        OptiJobLoc(
                            geo_longitude = s.start_longitude, # end_longitude,
                            geo_latitude = s.start_latitude, # end_latitude,
                            node_type = "slot",
                            orig_index = si,
                            code = s.slot_code,
                            c_weight = 0,
                            c_volume = 0,
                            c_time_window = c_time_window,
                            fixed_worker_index = None,
                            requested_duration_minutes = 1,
                            # flex_form_data= j.flex_form_data
                            skills = None,
                        )
                    )
                    ctx.worker_loc_idx[s.slot_code] = len(jobs_locs) - 1

        if len(jobs_locs) < 2:
            log.info("No jobs are found. Dispatching terminated.")
            return
        # jobs_df = pd.DataFrame.from_records(jobs_locs)
        # jobs_df.columns = ['job_code', 'longitude', "latitude", "all_job_index", "c_weight", "c_volume", "c_minutes", "c_time_window"]

        # commit previous trx-s.
        db_session.commit()
        self.dispatch_jobs_cvrp(
            jobs_locs = jobs_locs, 
            worker_slots_all = worker_slots_all,
            db_job_list = day_jobs,
            db_session = db_session,
            ctx = ctx,
        )

        total_time = datetime.now() - begin_time
        log.info(
            f"Done. nbr workers: {len(worker_slots_all)}, nbr jobs: {len(all_job_list)}, Total Elapsed: {total_time}"
        )
        return True

        # print(
        #     f"Travel Router: hit rate= {round(self.env.travel_router.redis_router_hit / self.env.travel_router.all_hit,4)}, routing api = {self.env.travel_router.routing_router_hit}, all count = {self.env.travel_router.all_hit}."
        # )

    def dispatch_jobs_cvrp(self, jobs_locs: List[OptiJobLoc], worker_slots_all, db_job_list, db_session, ctx):
        # c_num_vehicles = 
        max_vehicle_minutes = 0
        c_vehicle_minutes = []
        c_vehicle_weights = []
        c_vehicle_volumes = [] 

        opti_model = vroom.Input()
        long_lat_list = [(j.geo_longitude, j.geo_latitude) for j in jobs_locs]
        dist_mat_np = self.env.get_travel_router().get_travel_minutes_matrix(
            long_lat_list, return_type="duration"
            ) * float(self.config.get("travel_minutes_scale_factor",1))
        dist_mat = dist_mat_np.astype(int).tolist()
        log.info(f"distance matrix statistics: (max = {dist_mat_np.max()}, min = {dist_mat_np.min()}, sum = {round(dist_mat_np.sum(),2)}, mean = {round(dist_mat_np.mean(),2)}, median = {round(np.median(dist_mat_np),2)})")

        opti_model.set_durations_matrix(
            profile="car",
            matrix_input=dist_mat,
        )
        vehicle_list = []
        _env_day_start_minutes = self.env.get_env_start_minutes_rounded()
        horizon = self.env.get_env_planning_horizon_start_minutes() - _env_day_start_minutes
        for si,s in enumerate(worker_slots_all):
            in_day_start = s.start_minutes - _env_day_start_minutes
            in_day_end = s.end_minutes - _env_day_start_minutes
            if in_day_end <= horizon:
                continue
            if in_day_start < horizon:
                in_day_start = horizon

            c_vehicle_minutes.append((in_day_start, in_day_end))
            if in_day_end > max_vehicle_minutes:
                max_vehicle_minutes = in_day_end
            c_vehicle_weights.append(
                int(s.capacity_weight) #  // 2
            )

            c_vehicle_volumes.append(
                int(s.capacity_volume) #  // 2
            )

            vehicle_capacity=[MAX_INT, MAX_INT]
            vehicle_max_nbr_order = MAX_INT
            if int(self.config.get("enable_max_travel_time", 1)) == 1:
                max_travel_time = int(self.config.get("max_travel_time_minutes", 360)) 
            else:
                max_travel_time = None

            if int(self.config.get("enable_weight_constraint", 0)) == 1:
                vehicle_capacity[0] = int(s.capacity_weight)

            if int(self.config.get("enable_volume_constraint", 0)) == 1:
                vehicle_capacity[1] = int(s.capacity_volume)

            if int(self.config.get("enable_max_order_constraint", 0)) == 1:
                vehicle_max_nbr_order = int(s.max_nbr_order)

            start_idx = 0
            return_idx = None
            
            if str(self.config.get("enable_return2home_constraint", "1")) == "1":
                if s.slot_code in ctx.worker_loc_idx:
                    return_idx = ctx.worker_loc_idx[s.slot_code]
                    log.info(f"Added virtual return2home constraint: vehicle_id = {10000+si}, slot_node_index = {s.slot_code} --> s.slot_code = {s.slot_code}, virtual return_idx = {return_idx}")  
            elif str(self.config.get("enable_always_return2depot", "0")) == "1":
                return_idx = 0

            if str(self.config.get("enable_always_start_from_depot", "0")) == "1":
                start_idx = 0
            elif str(self.config.get("enable_start_from_home_constraint", "0")) == "1":
                if s.slot_code in ctx.worker_loc_idx:
                    start_idx = ctx.worker_loc_idx[s.slot_code]
                    log.info(f"Added virtual start_from_worker_loc constraint: vehicle_id = {10000+si}, slot_node_index = {s.slot_code} --> s.slot_code = {s.slot_code}, virtual return_idx = {return_idx}")  

            skills = None
            if str(self.config.get("enable_skills", "0")) == "1":
                skills = ctx.convert_skills(list(s.skills) + [f"_slot_:{s.slot_code}"]) 
                # skills = set(sorted(skills))

            vehicle_list.append(vroom.Vehicle(
                10000+si, 
                start=start_idx, 
                end=return_idx, # return_idx,
                skills = skills, # {si}, #  self.worker_code2index[s.worker_code]
                capacity=vehicle_capacity,
                max_tasks=vehicle_max_nbr_order,
                max_travel_time = max_travel_time,
                time_window=[in_day_start, in_day_end]
            ))

        opti_model.add_vehicle(vehicle_list)

        log.info("Opti2_Dispatching_Started: with {} slots, {} jobs, slot minute: {}, weight: {}, volume: {}, worker_code: {}, job_locs: {} ".format(
            len(worker_slots_all),
            len(jobs_locs),
            c_vehicle_minutes, c_vehicle_weights, c_vehicle_volumes,
            [s.slot_code for s in worker_slots_all],
            [(s.geo_longitude, s.geo_latitude, s.code, s.c_time_window, s.c_weight, s.c_volume) for s in jobs_locs]
            ))

        # cluster_begin_time = datetime.now()
        
        clients = []
        for idx in range(1, len(jobs_locs) ):
            job = jobs_locs[idx]
            job_delivery=[1, 1]
            if int(self.config.get("enable_weight_constraint", 0)) == 1:
                job_delivery[0] = int(job.c_weight)

            if int(self.config.get("enable_volume_constraint", 0)) == 1:
                job_delivery[1] = int(job.c_volume)
            # job_skills = None
            # if job.fixed_worker_index is not None:
            #     job_skills = {job.fixed_worker_index}

            j = vroom.Job(
                id=idx, location=idx,
                delivery=job_delivery,
                service=job.requested_duration_minutes, 
                skills = job.skills,
                time_windows=job.c_time_window
            )

            clients.append(j)
        opti_model.add_job(clients)
             
        solution = opti_model.solve(exploration_level=5, nb_threads=config.VROOM_SOLVER_NB_THREADS)
        log.info(f"VRoom Dispatching result: solution.summary.cost = {solution.summary.cost}, violations = {solution.summary.violations._types}, waiting_time = {solution.summary.waiting_time}, unassigned = {solution.summary.unassigned}") 
        # return
        # Print solution on console.
        if solution:
            # print(f'Solver status: {routing.status()}, Objective: {solution.ObjectiveValue()}') 
            self.save_solution(solution, worker_slots_all, jobs_locs, dist_mat, 
                               db_job_list = db_job_list, db_session=db_session)

        else:
            log.warning("Batch_Dispatching_Failed.")

    def save_solution(self, solution, 
            worker_slots_all, jobs_locs, dist_mat, 
            db_job_list, db_session, item_price_dict = {}
        ):
        # return
        total_item_value = 0
        for vehicle_id in range(len(worker_slots_all)):
            _slot = worker_slots_all[vehicle_id]
            # worker_code = _slot.worker_code
            _assigned_jobs = []
            _required_items = {}
            # First one (previous_index) should be depot 
            previous_index = 0
            previous_duration = 0
            # Start from second job
            _env_day_start_minutes = self.env.get_env_start_minutes_rounded() 
            r_minute = r_weight = r_volume = 0
            # prev_location = self.worker_slots[vehicle_id].end_location 
            for index, job_row in solution.routes[solution.routes["vehicle_id"] == 10000 + vehicle_id].iterrows():
                if index < 1 or job_row.type != "job": # == "start":
                    previous_index = job_row.location_index
                    continue
                curr_minutes = job_row.arrival + job_row.waiting_time + _env_day_start_minutes
                _job_loc = jobs_locs[job_row.location_index]
                if _job_loc.node_type != "job":
                    previous_index = job_row.location_index
                    print(f"Skipped: location = {job_row.location_index}, job node_type == {_job_loc.node_type}. one of the last. ")
                    continue
                db_job = db_job_list[job_row.location_index - 1] # first of job_locs is depot
                requested_items = db_job.flex_form_data.get("accum_items", "")
                if len(requested_items) > 2:

                    try:
                        for item_str in requested_items.split(config.SEPERATOR_FLEX_0):
                            ic, iqty = item_str.split(":")[-2:]
                            if ic not in item_price_dict:
                                log.warning(f"item ({ic}) not found in item table, requested by job ({db_job.code})")
                            if ic in _required_items:
                                _required_items[ic] += float(iqty)
                            else:
                                _required_items[ic] = float(iqty)
                            total_item_value += item_price_dict[ic] * float(iqty)
                    except Exception as e:
                        print(f"error {str(e)}")

                previous_index = job_row.location_index

                if total_item_value > 3000:
                    log.warning(f"Worker slot {_slot.slot_code} reached limit of 3000, skipping an assigned job: {db_job.code}")
                    break
                job_in_slot = self.env.env_encode_single_job_db(db_job)
                job_in_slot.scheduled_start_minutes = curr_minutes # next_start_minutes + travel_time
                job_in_slot.prev_travel = job_row.duration - previous_duration
                previous_duration = job_row.duration
                _assigned_jobs.append(job_in_slot)
                next_start_minutes = job_in_slot.scheduled_start_minutes + job_in_slot.scheduled_duration_minutes


            _slot.assigned_jobs = _assigned_jobs
            init_load_items = copy.deepcopy(_required_items)
            init_load_total_value = total_item_value
            _free_items = {k:0 for k in init_load_items.keys()}
            for len_ratio in (0.1, 0.3, 0.5, 1):
                if str(self.config.get("load_init_stock", 1)) != 1:
                    break
                for len_i in range(int(len_ratio*len(self.job_item_value_stats))):
                    item = self.job_item_value_stats[len_i][0]
                    if item in init_load_items:
                        init_load_items[item] += 1
                        _free_items[item] += 1
                    else:
                        init_load_items[item] = 1
                        _free_items[item] = 1

                    init_load_total_value += item_price_dict[item]
                    if init_load_total_value > 3000:
                        break
                if init_load_total_value > 3000:
                    break


            _slot.accum_items = init_load_items
            _slot.free_items = _free_items
            _slot.accum_items.update({
                "_volume_":_slot.capacity_volume,
                "_weight_":_slot.capacity_weight,
            })
            _slot.free_items.update({
                "_volume_": _slot.capacity_volume - r_volume,
                "_weight_": _slot.capacity_weight - r_weight,
            })

            _slot.job_change_count += 1 # len(_assigned_jobs)
            self.env.add_single_working_time_slot(slot = _slot)

            for _slot_job in _assigned_jobs:
                self.env.commit_changed_job2db(
                    db_session=db_session,
                    job=_slot_job,
                    worker_code=_slot.worker_code)



