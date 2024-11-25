# Cited from https://developers.google.com/optimization/routing/penalties#complete-programs

from datetime import datetime, timedelta
import pandas as pd
import numpy as np
# from sklearn.mixture import GaussianMixture

# from ortools.sat.python import cp_model
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

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
from dispatch.item import service as item_service
# from dispatch.job.models import JobPlanningInfoUpdate

# from dispatch.plugins.kandbox_planner.env.env_enums import LocationType
# from dispatch.plugins.kandbox_planner.env.env_models import JobLocationBase

from k_means_constrained import KMeansConstrained
# from size_constrained_clustering import  minmax 
# by default it is euclidean distance, but can select others
from sklearn.metrics.pairwise import haversine_distances
import logging
log = logging.getLogger("opti1_cvrp_configurable_planner")

from typing import List, Dict, Any, Optional
import pydantic 

# (j.geo_longitude, j.geo_latitude, j.code, all_job_index, c_weight, c_volume, 1, c_time_window))
from dispatch.plugins.kandbox_planner.env.env_models import  OptiJobLoc

class ConfigurableCVRPPlanner(KandboxBatchOptimizerPlugin):

    title = "Configurable TW-C-VRP Planner"
    slug = "opti1_cvrp_configurable_planner"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan/kandbox_dispatch"
    description = "This is a Batch Optimizer. Configurable C-VRP Planner"
    version = "0.1.0"
    default_config = {
        "load_init_stock": 0,
        "log_search_progress": False,
        "max_exec_seconds": 10, 
        "enable_weight_constraint": 1,
        "enable_volume_constraint": 0,
        "enable_location_group_constraint":0,
        "enable_time_window_constraint": 1,
        "run_pickup_job_dispatching":True,
        "plan_all_to_beginning_no_travel": False,
        "travel_minutes_scale_factor":1,
        "enable_fix_planned_constraint":1,
        "weight_constraint_code":"weight" # order_count
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "max_exec_seconds": {
                "type": "number",
                "code": "Maximum Seconds of Execution",
                "description": "How many seconds the algorithm is allowed to run for optimizing",
            },
            "enable_location_group_constraint": {
                "type": "number", 
                "description": "enable_location_group_constraint, 1 means yes",
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
                "description": "enable_return2home_constraint, 1 means yes",
            },
            "weight_constraint_code": {
                "type": "string", 
                "description": "This affects timing, N=Normal, FS=Fixed Schedule.",
                "default": "weight",
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


    def _get_travel_time_2locations(self, loc1, loc2):
        new_time = self.env.travel_router.get_travel_minutes_2locations(
            [loc1[0], loc1[1]],
            [loc2[0], loc2[1]],
        )
        if new_time > 200:
            log.warning([loc1[0], loc1[1]], [loc2[0], loc2[1]], (new_time),
                  "Error, too long")
        # print("travel: ", new_time)
        return int(new_time / 1)
 
    def dispatch_jobs(self, env:ConfigurableDispatchEnv, db_session, rl_agent=None, batch_request=None):
        # Real batch, rl_agent is skilpped.
        #
        assert int(env.config[
            "nbr_of_days_planning_window"]) == 1, "I can do all workers for one day only."
        self.env = env 

        worker_slots_all = self.env.get_working_slot_list( 
            active_only = False
            )
        if len(worker_slots_all) < 1:
            log.info(f"dispatch_jobs: No active worker slots are found, quitting at {datetime.now()}")
            return False

        if int(self.config.get("enable_location_group_constraint", 0)) == 1 or int(self.config.get("enable_fix_planned_constraint", 0)) == 1:
            self.location_group2worker_index = {}
            self.worker_code2index = {}
            lg2worker_code = location_group_service.get_query_all_with_worker_code(
                    db_session = db_session)
            wc2lg = {v:k for k,v in lg2worker_code.items()}
            for si, s in enumerate(worker_slots_all):
                self.worker_code2index[s.worker_code] = si
                if s.worker_code in wc2lg:
                    lg_code = wc2lg[s.worker_code]
                    self.location_group2worker_index[lg_code] = si
            log.info(f"enable_location_group_constraint or enable_fix_planned_constraint is true, with lg={lg2worker_code}, lg2work_index: {self.location_group2worker_index}, self.worker_code2index = {self.worker_code2index}")


        begin_time = datetime.now()
        log.info(f"Started dispatching at time: {begin_time}, with config: {self.config}")

        # GENERATOR_START_DATE = datetime.strptime(
        #     self.env.config["env_start_datetime"], config.KANDBOX_DATETIME_FORMAT_ISO
        # )
        # GENERATOR_END_DATE = GENERATOR_START_DATE + timedelta(
        #     days=int(self.env.config["nbr_of_days_planning_window"])
        # )
        # day_jobs = job_service.get_jobs_worker_days( 
        #             db_session=db_session,
        #             start_datetime = GENERATOR_START_DATE, 
        #             end_datetime = GENERATOR_END_DATE,
        #             worker_code = None,
        #             include_unplanned = True,
        #             include_inplanning = True,
        #         )
        day_jobs = self.env.get_env_batch_opti_jobs(db_session)
        
        team = db_session.query(Team).filter(Team.id == self.env.team_id).one_or_none()
        if not team:
            raise ValueError(f"team not found,id: {self.team_id} ")
        all_job_list = [None]

        jobs_locs = [
            OptiJobLoc(
                geo_longitude = team.geo_longitude,
                geo_latitude = team.geo_latitude,
                node_type = "depot",
                orig_index = 0,
                code = "depot",
                c_weight = 0,
                c_volume = 0,
                c_time_window =[],
                fixed_worker_index = None
                # flex_form_data={}
            )
        ]
        # all_job_list = []
        all_job_index=1
        for ji, j in enumerate(day_jobs):
            if j.planning_status in (JobPlanningStatus.UNPLANNED, JobPlanningStatus.IN_PLANNING, JobPlanningStatus.PLANNED,  ):
                # 标记
                # c_weight = int(j.flex_form_data.get("weight", 1)) # *1.5 
                c_weight = int(j.flex_form_data.get(self.config.get("weight_constraint_code", "weight"), 1)) # *1.5 
                c_volume = int(j.flex_form_data.get(self.config.get("volume_constraint_code", "volume"), 1)) # *1.5
                # c_time_window = from_time_window_str_to_list( j.flex_form_data.get("time_window_list", "")) # *1.5
                c_time_window = env.from_time_window_flex_form_to_list( j.flex_form_data) # *1.5
                fixed_worker_index = None
                if int(self.config.get("enable_location_group_constraint", 0)) == 1:
                    lg_code = j.flex_form_data.get('location_group_code', None)
                    if lg_code:
                        if lg_code in self.location_group2worker_index:
                            fixed_worker_index = self.location_group2worker_index[lg_code]
                        else:
                            log.warning(f"{lg_code} is not found from location_group2worker_index.")
                if j.planning_status == JobPlanningStatus.PLANNED:
                    if int(self.config.get("enable_fix_planned_constraint", 0)) == 1:
                        fixed_worker_index = self.worker_code2index[j.scheduled_primary_worker_code]
                    else:
                        log.warning(f"job: {j.code} is planned, but enable_fix_planned_constraint is not enabled. Job Skipped")
                        # continue


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
                        flex_form_data= j.flex_form_data
                    )
                )
                all_job_list.append(j)
                all_job_index +=1

        for si, s in enumerate(worker_slots_all):
            if round(s.start_longitude,5) != round(team.geo_longitude,5
            ) or round(s.start_latitude,5) != round(team.geo_latitude,5):
                c_time_window = [[
                    s.start_minutes - self.env.get_env_start_minutes(),
                    s.end_minutes - self.env.get_env_start_minutes()
                ]]
                jobs_locs.append(
                    OptiJobLoc(
                        geo_longitude = s.end_longitude,
                        geo_latitude = s.end_latitude,
                        node_type = "slot",
                        orig_index = si,
                        code = s.slot_code,
                        c_weight = 0,
                        c_volume = 0,
                        c_time_window = c_time_window,
                        fixed_worker_index = None,
                        # flex_form_data= j.flex_form_data
                    )
                )

        if len(jobs_locs) < 2:
            log.info(f"No jobs are found. Dispatching terminated.")
            return
        # jobs_df = pd.DataFrame.from_records(jobs_locs)
        # jobs_df.columns = ['job_code', 'longitude', "latitude", "all_job_index", "c_weight", "c_volume", "c_minutes", "c_time_window"]

        # commit previous trx-s.
        db_session.commit()
        res = self.dispatch_jobs_cvrp(
            jobs_locs = jobs_locs, 
            worker_slots_all = worker_slots_all,
            db_job_list = day_jobs,
            db_session = db_session,
        )

        total_time = datetime.now() - begin_time
        log.info(
            f"Done. nbr workers: {len(worker_slots_all)}, nbr jobs: {len(all_job_list)}, Total Elapsed: {total_time}"
        )

        # print(
        #     f"Travel Router: hit rate= {round(self.env.travel_router.redis_router_hit / self.env.travel_router.all_hit,4)}, routing api = {self.env.travel_router.routing_router_hit}, all count = {self.env.travel_router.all_hit}."
        # )
        return True

    def dispatch_jobs_cvrp(self, jobs_locs: List[OptiJobLoc], worker_slots_all, db_job_list, db_session):
        # c_num_vehicles = 
        max_vehicle_minutes = 0
        c_vehicle_minutes = []
        c_vehicle_weights = []
        c_vehicle_volumes = []
        for s in worker_slots_all:
            in_day_start = s.start_minutes - self.env.get_env_start_minutes()#  % 1440
            in_day_end = s.end_minutes - s.start_minutes + in_day_start

            c_vehicle_minutes.append((in_day_start, in_day_end))
            if in_day_end > max_vehicle_minutes:
                max_vehicle_minutes = in_day_end
            c_vehicle_weights.append(
                int(s.capacity_weight) #  // 2
            )
            c_vehicle_volumes.append(
                int(s.capacity_volume) #  // 2
            )

        log.info("Opti1_Dispatching_Started: with {} seconds limit, job count: {}, slot minute: {}, weight: {}, volume: {}, worker_code: {}, job_locs: {} ".format(
            int(self.config["max_exec_seconds"]),
            len(jobs_locs),
            c_vehicle_minutes, c_vehicle_weights, c_vehicle_volumes,
            [s.slot_code for s in worker_slots_all],
            [(s.geo_longitude, s.geo_latitude, s.code, s.c_time_window, s.c_weight, s.c_volume) for s in jobs_locs]
            ))
        # w_l = [s[4] for s in jobs_locs]
        # v_l = [s[5] for s in jobs_locs]
        # log.info("Job Summary: weight: {}, volume: {}. \n {} \n {} ".format(
        #             sum(w_l), sum(v_l), w_l, v_l ))

        # cluster_begin_time = datetime.now()
        manager = pywrapcp.RoutingIndexManager(
            len(jobs_locs), 
            len(worker_slots_all), 
            0)
        routing = pywrapcp.RoutingModel(manager)
        long_lat_list = [(j.geo_longitude, j.geo_latitude) for j in jobs_locs]
        dist_mat_np = (self.env.get_travel_router().get_travel_minutes_matrix(long_lat_list, return_type="duration") 
                       * float(self.config.get("travel_minutes_scale_factor",1)) )
        dist_mat = dist_mat_np.astype(int).tolist()
        log.info(f"distance matrix statistics: (max = {dist_mat_np.max()}, min = {dist_mat_np.min()}, sum = {round(dist_mat_np.sum(),2)}, mean = {round(dist_mat_np.mean(),2)}, median = {round(np.median(dist_mat_np),2)})")
        for d1 in range(len(long_lat_list)):
            if jobs_locs[d1].node_type != "slot":
                continue
            # for d2 in range(len(long_lat_list)): 
            # 这里把worker virutal job到depot到距离变成0
            dist_mat[d1][0] = 0
            # for d2 in range(1,len(long_lat_list)): 
            #     if d2 >= d1:
            #         break
            #     dist_mat[d1][d2] = 9999
        def distance_callback(from_index, to_index):
            # Convert from routing variable Index to distance matrix NodeIndex.
            from_node = manager.IndexToNode(from_index)  # - 1
            to_node = manager.IndexToNode(to_index)  # - 1
            return int(dist_mat[from_node][to_node])
            if from_node == to_node:
                return 0
            return self._get_travel_time_2locations(
                jobs_locs[from_node][1:3],
                jobs_locs[to_node][1:3]) + jobs_locs[to_node][6]

        transit_callback_index = routing.RegisterTransitCallback(
            distance_callback)
        # Define cost of each arc.
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Wierd, if I add this, no solution or destroys others. 2023-06-11 21:41:43
        # minute_callback_index = routing.RegisterUnaryTransitCallback(
        #     distance_callback)
        # routing.AddDimensionWithVehicleCapacity(
        #     minute_callback_index,
        #     0,  # null capacity slack
        #     c_vehicle_minutes, # 320, # c_vehicle_minutes,  # vehicle maximum weight capacities
        #     True,  # start cumul to zero
        #     'Minute_Capacity')
        # distance_dimension = routing.GetDimensionOrDie('Minute_Capacity')
        # distance_dimension.SetGlobalSpanCostCoefficient(100)

        if int(self.config.get("enable_time_window_constraint", 0)) == 1:
            print("time window constraint is enabled: enable_time_window_constraint=",int(self.config.get("enable_time_window_constraint", 0)))
            # Add Time Windows constraint.
            time = 'Time'
            routing.AddDimension(
                transit_callback_index,
                30,  # allow waiting time
                max_vehicle_minutes,  # maximum time per vehicle
                False,  # Don't force start cumul to zero.
                time)
            time_dimension = routing.GetDimensionOrDie(time)
            # Add time window constraints for each location except depot.
            for location_idx, job in enumerate(jobs_locs):
                if location_idx == 0:
                    continue
                index = manager.NodeToIndex(location_idx)
                time_window = job.c_time_window # [7]
                try:
                    if len(time_window) > 0:
                        # TODO, 如何考虑多个window？
                        time_dimension.CumulVar(index).SetRange(time_window[0][0], time_window[0][1])
                except:
                    print("Exception: CP Solver fail")
            # Add time window constraints for each vehicle start node.
            depot_idx = 0
            for vehicle_id in range(len(worker_slots_all)):
                index = routing.Start(vehicle_id)
                time_dimension.CumulVar(index).SetRange(
                    c_vehicle_minutes[vehicle_id][0],
                    c_vehicle_minutes[vehicle_id][1],
                    )
                route_end_index = routing.End(vehicle_id)
                time_dimension.CumulVar(route_end_index).SetRange(
                    c_vehicle_minutes[vehicle_id][0],
                    c_vehicle_minutes[vehicle_id][1],
                    )
                if int(self.config.get("enable_return2home_constraint", 1)) == 1:
                    for ji, j in enumerate(jobs_locs):
                        if j.node_type == "slot" and j.orig_index == vehicle_id:
                            slot_node_index = manager.NodeToIndex(ji)
                            routing.solver().Add(vehicle_id == routing.VehicleVar(slot_node_index))            
                            routing.solver().Add(routing.NextVar(slot_node_index) == route_end_index)          
                            log.info(f"added virtual return2home constraint: vehicle_id = {vehicle_id}, slot_node_index = {slot_node_index} --> route_end_index = {route_end_index}, virtual job_i = {ji}, code = {j.code}, time_window: {c_vehicle_minutes[vehicle_id]}")  
                            # time_dimension.CumulVar(slot_node_index).SetRange(
                            #     c_vehicle_minutes[vehicle_id][1] - 5,
                            #     c_vehicle_minutes[vehicle_id][1] - 0,
                            #     )

        if int(self.config.get("enable_location_group_constraint", 0)) == 1:
            for ji, j in enumerate(jobs_locs):
                if j.node_type == "job" and j.fixed_worker_index is not None:
                    # vehicle_index = routing.End(j.fixed_worker_index)
                    target_job_index = manager.NodeToIndex(ji)
                    routing.solver().Add(j.fixed_worker_index == routing.VehicleVar(target_job_index))    
                    ## TODO, verify work timewindow.        
                    print(f"added location_group constraint: target_job_index = {target_job_index} --> vehicle = {j.fixed_worker_index},  job = {j.code},  job_i = {ji}, slot = {worker_slots_all[j.fixed_worker_index].slot_code}, job time window: { j.c_time_window}, worker_time_window: {c_vehicle_minutes[vehicle_id]}")  
                    # time_dimension.CumulVar(slot_node_index).SetRange(
                    #     c_vehicle_minutes[vehicle_id][1] - 5,
                    #     c_vehicle_minutes[vehicle_id][1] - 0,
                    #     )

        if int(self.config.get("enable_weight_constraint", 0)) == 1:
            print("weight_constraint is enabled: enable_weight_constraint=",int(self.config.get("enable_weight_constraint", 0)), self.config.get("weight_constraint_code", "weight"))
            # #Add Capacity constraint.
            def weight_callback(from_index):
                from_node = manager.IndexToNode(from_index)
                return int(jobs_locs[from_node].c_weight) # [4]
            weight_callback_index = routing.RegisterUnaryTransitCallback(
                weight_callback)
            routing.AddDimensionWithVehicleCapacity(
                weight_callback_index,
                0,  # null capacity slack
                c_vehicle_weights,  # vehicle maximum weight capacities
                True,  # start cumul to zero
                'Weight_Capacity')

        if int(self.config.get("enable_volume_constraint", 0)) == 1:
            print("volume_constraint is enabled: enable_volume_constraint=",int(self.config.get("enable_time_window_constraint", 0)))
            # #Add Capacity constraint.
            def volume_callback(from_index):
                from_node = manager.IndexToNode(from_index)
                return int(jobs_locs[from_node].c_volume) # [5]
            volume_callback_index = routing.RegisterUnaryTransitCallback(
                volume_callback)
            routing.AddDimensionWithVehicleCapacity(
                volume_callback_index,
                0,  # null capacity slack
                c_vehicle_volumes,  # vehicle maximum volume capacities
                True,  # start cumul to zero
                'Volume_Capacity')
    
        # Setting first solution heuristic.
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.AUTOMATIC) # PATH_CHEAPEST_ARC
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        search_parameters.log_search = self.config["log_search_progress"] # True
        search_parameters.time_limit.FromSeconds(int(self.config["max_exec_seconds"])) 



        # Solve the problem.
        solution = routing.SolveWithParameters(search_parameters)


        # Print solution on console.
        if solution:
            print(f'Solver status: {routing.status()}, Objective: {solution.ObjectiveValue()}') 
            self.print_solution(manager, routing, solution, worker_slots_all, jobs_locs, dist_mat)
            self.save_solution(manager, routing, solution, worker_slots_all, jobs_locs, dist_mat, 
                               db_job_list = db_job_list, db_session=db_session)

        else:
            log.warning("Batch_Dispatching_Failed.")

    def print_solution(self, manager, routing, solution, worker_slots_all, jobs_locs, dist_mat):
        """Prints solution on console."""
        
        max_route_distance = 0
        # volume_dimension = routing.GetDimensionOrDie('Volume_Capacity')
        time_dimension = routing.GetDimensionOrDie("Time")
        weight_dimension = routing.GetDimensionOrDie("Weight_Capacity")
        
        jobs_lens = []
        for vehicle_id in range(len(worker_slots_all)):
            index = routing.Start(vehicle_id)
            plan_output = "Route for vehicle {}, min:{}, max: {}:\n".format(vehicle_id, solution.Min(time_dimension.CumulVar(index)), solution.Max(time_dimension.CumulVar(index)))
            route_distance = 0
            r_minute = r_weight = r_volume = 0
            jobs_lens.append(0)
            while not routing.IsEnd(index):
                prev_node = manager.IndexToNode(index)
                previous_index = index
                index = solution.Value(routing.NextVar(index))
                curr_minutes = time_dimension.CumulVar(index)
                curr_weight = weight_dimension.CumulVar(index)
                curr_node = manager.IndexToNode(index)
                route_distance += routing.GetArcCostForVehicle(
                    previous_index, index, vehicle_id)
                r_minute += dist_mat[prev_node][curr_node] 
                r_weight += jobs_locs[prev_node].c_weight # [4]
                r_volume += jobs_locs[prev_node].c_volume # [5]
                plan_output += ":{}(curr_minutes: {}, from zero minute: {}, weight: {}, volume: {}) -> ".format(
                    # prev_node, 
                    (prev_node, jobs_locs[prev_node].code), # [2]
                    # curr_minutes, 
                    (solution.Min(curr_minutes), solution.Max(curr_minutes)),
                    r_minute, 
                    # r_weight, 
                    (solution.Min(curr_weight), solution.Max(curr_weight)),
                    r_volume )
                jobs_lens[-1] += 1

            plan_output += "{}\n".format(manager.IndexToNode(index))
            plan_output += "Route stats: {}, slot capacity: {}\n".format(
                (route_distance, r_minute, r_weight, r_volume), 
                (worker_slots_all[vehicle_id].capacity_weight, worker_slots_all[vehicle_id].capacity_volume, ))
            print(plan_output)
            max_route_distance = max(route_distance, max_route_distance)
        print("Maximum of the route distances: {}, length = {}".format(max_route_distance, jobs_lens))

    def save_solution(self, 
            manager, routing, solution, 
            worker_slots_all, jobs_locs, dist_mat, 
            db_job_list, db_session, item_price_dict = {}
        ):
        # return
        total_item_value = 0
        time_dimension = routing.GetDimensionOrDie("Time")
        for vehicle_id in range(len(worker_slots_all)):
            _slot = worker_slots_all[vehicle_id]
            # worker_code = _slot.worker_code
            _assigned_jobs = []
            _required_items = {}
            # First one (previous_index) should be depot 
            previous_index = routing.Start(vehicle_id)
            # Start from second job
            index = solution.Value(routing.NextVar(previous_index))
            next_start_minutes = max(
                _slot.start_minutes,
                self.env.get_env_planning_horizon_start_minutes(),
            )
            r_minute = r_weight = r_volume = 0
            # prev_location = self.worker_slots[vehicle_id].end_location 

            while not routing.IsEnd(index):
                # plan_output += " {} -> ".format(manager.IndexToNode(index))
                # job starts at 0
                if index < 1:
                    continue
                prev_node = manager.IndexToNode(previous_index)
                curr_node = manager.IndexToNode(index)
                curr_minutes_variable = time_dimension.CumulVar(index)
                curr_minutes = solution.Min(curr_minutes_variable) + self.env.get_env_start_minutes()
                if jobs_locs[curr_node].node_type != "job":
                    previous_index = index
                    index = solution.Value(routing.NextVar(index))
                    continue
                db_job = db_job_list[curr_node-1] # first one was depot
                requested_items = db_job.flex_form_data.get("accum_items", "")
                if len(requested_items) > 2:
                    for item_str in requested_items.split(config.SEPERATOR_FLEX_0):
                        try:
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

                travel_time = dist_mat[prev_node][curr_node]
                r_minute += dist_mat[prev_node][curr_node] 
                r_weight += jobs_locs[prev_node].c_weight # [4]
                r_volume += jobs_locs[prev_node].c_volume # [5]

                previous_index = index
                index = solution.Value(routing.NextVar(index))

                if total_item_value > 3000:
                    log.warning(f"Worker slot {_slot.slot_code} reached limit of 3000, skipping an assigned job: {db_job.code}")
                    break
                job_in_slot = self.env.env_encode_single_job_db(db_job)
                job_in_slot.scheduled_start_minutes = curr_minutes # next_start_minutes + travel_time
                job_in_slot.prev_travel = travel_time
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



if __name__ == "__main__":
    from pprint import pprint

    opti = Opti1DayPlanner(
        max_exec_seconds=config.KANDBOX_OPTI1DAY_EXEC_SECONDS)  # 0*60*24
    ss = config.KANDBOX_TEST_OPTI1DAY_START_DAY
    ee = config.KANDBOX_TEST_OPTI1DAY_END_DAY
    opti.env.purge_planner_job_status(planner_code=opti.planner_code,
                                      start_date=ss,
                                      end_date=ee)
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
