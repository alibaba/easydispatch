# Cited from https://developers.google.com/optimization/routing/penalties#complete-programs

from datetime import datetime, timedelta
import pandas as pd
from sklearn.mixture import GaussianMixture

from ortools.sat.python import cp_model
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

import collections

import sys

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

# from dispatch.plugins.kandbox_planner.env.env_models import ActionDict, JobInSlot
import copy
from dispatch.job import service as job_service
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
log = logging.getLogger("kandbox_cluster_cvrp_planner")


class ClusterCVRPPlanner(KandboxBatchOptimizerPlugin):

    title = "VRP and Cluster Planner"
    slug = "kandbox_cluster_cvrp_planner"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan/kandbox_dispatch"
    description = "This is a Batch Optimizer, using Gaussian Mixture or Minmax MaxFlowCut for clustering and then ortools for vrp inside each cluster."
    version = "0.1.0"
    default_config = {
        "log_search_progress": True,
        "max_exec_seconds": 60,
        "cluster_algorithm": "kmeans-constrained", # "minmax"  # "gmm"
        "tsp_algorithm": "osrm", # "ortools"  # "osrm"
    }
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, config=None):
        self.config = self.default_config.copy()
        if config is not None:
            self.config.update(config)

    def _get_travel_time_2locations(self, loc1, loc2):
        new_time = self.env.travel_router.get_travel_minutes_2locations(
            [loc1[0], loc1[1]],
            [loc2[0], loc2[1]],
        )
        # if new_time > 200:
        #     print([loc1[0], loc1[1]], [loc2[0], loc2[1]], (new_time), "Error_travel_time_too_long")
        # print("travel: ", new_time)
        return int(new_time / 1)

    def get_item_price_dict(self, db_session):
        # blocked this function for execution of 25 seconds, on empty set. 2022-12-28 05:38:48
        # 查询 job 关联worker的信息 
        worker_list = item_service.get_all(db_session=db_session)
        item_price_dict = {}
        for item in worker_list:
            if item.code:
                item_price_dict[item.code] = item.weight
        
        all_jobs = job_service.get_all(db_session=db_session)
        self.job_item_stats = {} 
        for job in all_jobs:
            if "accum_items" not in job.flex_form_data:
                continue
            requested_items = job.flex_form_data["accum_items"]
            if len(requested_items) <1:
                continue
            
            for ri in requested_items:
                if len(ri.split(":")) != 2:
                    continue
                name, qty = ri.split(":")
                if name not in item_price_dict:
                    print(f"item ({name}) not found in item table, but in job {job.code}")
                    continue
                if name in self.job_item_stats:
                    self.job_item_stats[name] += int(qty)
                else:
                    self.job_item_stats[name] = int(qty)

        _values = [(k,item_price_dict[k] * qty) for k,qty in self.job_item_stats.items()]
        self.job_item_value_stats = sorted(_values, key=lambda x: x[1], reverse=True)
        self.item_price_dict = item_price_dict
        return item_price_dict

    def dispatch_jobs(self, env:ConfigurableDispatchEnv, db_session, rl_agent=None, batch_request=None):
        # Real batch, rl_agent is skilpped.
        #
        assert int(env.config[
            "nbr_of_days_planning_window"]) == 1, "I can do all workers for one day only."
        self.env = env 
        item_price_dict =self.get_item_price_dict(db_session)
        # 20, 150 failed for 8 hours.

        worker_slots_all = self.env.get_working_slot_list( 
            active_only = False
            )
        if len(worker_slots_all) < 1:
            print(f"dispatch_jobs: No active worker slots are found, quitting at {datetime.now()}")
            return False

        begin_time = datetime.now()
        log.info(f"Started dispatching at time: {begin_time}, config={self.config}")

        GENERATOR_START_DATE = datetime.strptime(
            self.env.config["env_start_datetime"], config.KANDBOX_DATETIME_FORMAT_ISO
        )
        GENERATOR_END_DATE = GENERATOR_START_DATE + timedelta(
            days=int(self.env.config["nbr_of_days_planning_window"])
        )
        day_jobs = job_service.get_jobs_worker_days( 
                    db_session=db_session,
                    start_datetime = GENERATOR_START_DATE, 
                    end_datetime = GENERATOR_END_DATE,
                    worker_code = None,
                    include_unplanned = True,
                    include_inplanning = True,
                )
        
        jobs_locs = []
        all_job_list = []
        all_job_index=0
        for j in day_jobs:
            if j.planning_status in (JobPlanningStatus.UNPLANNED, JobPlanningStatus.IN_PLANNING):
                jobs_locs.append((j.code, j.geo_longitude, j.geo_latitude, all_job_index))
                all_job_list.append(j)
                all_job_index +=1
        if len(jobs_locs) < 1:
            print(f"No data found")
            return
        jobs_df = pd.DataFrame.from_records(jobs_locs)
        jobs_df.columns = ['job_code', 'longitude', "latitude", "all_job_index"]

        job_loc_matrix = jobs_df[['longitude', "latitude"]].values


        if self.config["cluster_algorithm"] == "kmeans-constrained":
            cluster_count = len(worker_slots_all)
            minmax_cluster_model = KMeansConstrained(
                n_clusters=cluster_count,
                size_min=max(1,int(job_loc_matrix.shape[0] * 0.8 / len(worker_slots_all))),
                size_max=max(3,int(job_loc_matrix.shape[0] * 1.6 / len(worker_slots_all))),
                random_state=0)
            # minmax_cluster_model.fit(job_loc_matrix)
            # centers = model.cluster_centers_
            # labels = model.labels_
            belongs_to = minmax_cluster_model.fit_predict(job_loc_matrix)
            jobs_df['cluster_id'] = belongs_to

            # cluster_count = # jobs_df['cluster_id'].max() + 1
        elif self.config["cluster_algorithm"] == "minmax":
            from size_constrained_clustering import  minmax
            minmax_cluster_model = minmax.MinMaxKMeansMinCostFlow(
                len(worker_slots_all),
                size_min=int(job_loc_matrix.shape[0] * 0.4 / len(worker_slots_all)),
                size_max=int(job_loc_matrix.shape[0] * 1.7 / len(worker_slots_all)))
            minmax_cluster_model.fit(job_loc_matrix)
            # centers = model.cluster_centers_
            # labels = model.labels_
            belongs_to = minmax_cluster_model.predict(job_loc_matrix)
            jobs_df['cluster_id'] = belongs_to

            cluster_count = jobs_df['cluster_id'].max() + 1
        elif self.config["cluster_algorithm"] == "gmm":
            mclusterer = GaussianMixture(n_components=len(worker_slots_all),
                                         tol=0.01,
                                         random_state=66,
                                         verbose=1)
            jobs_df['cluster_id'] = mclusterer.fit_predict()
            cluster_count = jobs_df['cluster_id'].max() + 1
        else:
            print("Wrong config cluster_algorithm=",
                  self.config["cluster_algorithm"])
            return

        print("{} clusters done at {}".format(cluster_count, datetime.now()))

        team = db_session.query(Team).filter(Team.id == self.env.team_id).one_or_none()
        if not team:
            raise ValueError(f"team not found,id: {self.team_id} ")

        avg_long = team.geo_longitude
        avg_lat = team.geo_latitude

        # avg_long = sum([j.location.geo_longitude
        #                 for j in self.env.jobs]) / len(self.env.jobs)
        # avg_lat = sum([j.location.geo_latitude
        #                for j in self.env.jobs]) / len(self.env.jobs)
        # DEPOT_AVG_JOB_LOCATION = JobLocationBase(
        #     geo_longitude=avg_long,
        #     geo_latitude=avg_lat,
        #     location_type=LocationType.HOME,
        #     code="depot",
        # )

        # depot_list = []
        # for cluster_i in range(cluster_count):
        #     depot_list.append(["depot", avg_long, avg_lat, cluster_i])
        # depot_df = pd.DataFrame.from_records(depot_list)
        # depot_df.columns = ['job_code', 'longitude', "latitude", "cluster_id"]

        # clustered_jobs_df = pd.concat([depot_df, jobs_df], ignore_index=True)

        for cluster_i in range(cluster_count):
            db_job_list = []
            cluster_df = jobs_df[jobs_df["cluster_id"] == cluster_i].copy()
            cluster_df.set_index("job_code")
            self.cluster_list = [("depot", avg_long, avg_lat, cluster_i)] + \
                [tuple(j) for j in cluster_df.to_records(index=False)]
            db_job_list = [
                Job(
                    code = "virtual",
                    geo_longitude = avg_long,
                    geo_latitude =  avg_lat,
                    scheduled_duration_minutes = 1,
                    tolerance_start_minutes = -1440*100,
                    tolerance_end_minutes = 1440*100,
                ) 
                ]
            for row_i, row in cluster_df.iterrows():
                db_job_list.append(all_job_list[row.all_job_index])

            self.worker_slots = [worker_slots_all[cluster_i]]
            print("Dispatching cluster {}, len={}, time = {}".format(
                cluster_i, len(self.cluster_list), datetime.now()))
            if self.config.get("tsp_algorithm","osrm") == "osrm":
                self.dispatch_jobs_1_cluster_osrm_tsp(db_job_list = db_job_list, db_session = db_session, item_price_dict = item_price_dict)
            else:
                self.dispatch_jobs_1_cluster_ortools(db_job_list = db_job_list, db_session = db_session, item_price_dict = item_price_dict)

        total_time = datetime.now() - begin_time
        print(
            f"Done. nbr workers: {len(worker_slots_all)}, nbr jobs: {len(self.cluster_list)}, Total Elapsed: {total_time}"
        )

        # print(
        #     f"Travel Router: hit rate= {round(self.env.travel_router.redis_router_hit / self.env.travel_router.all_hit,4)}, routing api = {self.env.travel_router.routing_router_hit}, all count = {self.env.travel_router.all_hit}."
        # )
    def dispatch_jobs_1_cluster_osrm_tsp(self, db_job_list, db_session, item_price_dict):
        cluster_begin_time = datetime.now()
        assigned_jobs = [ self.env.env_encode_single_job_db(j) for j in db_job_list]

        assigned_job_locs =  [
            (j.geo_longitude, j.geo_latitude) for j in assigned_jobs 
        ] 

        new_seq, start_distance = self.env.get_travel_router().solve_tsp(loc_list = assigned_job_locs )

        # Then generate jobs by this seq
        _assigned_new = assigned_jobs[0:1]
        # current_start = db_job_list[0].scheduled_start_minutes
        _slot = self.worker_slots[0]
        current_start = max(
                _slot.start_minutes,
                self.env.get_env_planning_horizon_start_minutes(),
            )

        for j_idx, ji in enumerate(new_seq):
            if j_idx < 1:
                continue
            job = assigned_jobs[ji]
            current_start += start_distance[j_idx] + job.scheduled_duration_minutes
            job.prev_travel = start_distance[j_idx]
            job.scheduled_start_minutes=current_start + start_distance[j_idx]
            _assigned_new.append(job)

        # worker_code = _slot.worker_code
        _assigned_jobs = []
        _required_items = {}

        _slot.assigned_jobs = _assigned_new
        init_load_items = copy.deepcopy(_required_items)
        init_load_total_value = 0
        _free_items = {k:0 for k in init_load_items.keys()}

        _slot.accum_items = init_load_items
        _slot.free_items = _free_items
        _slot.job_change_count += 1 # len(_assigned_jobs)
        self.env.add_single_working_time_slot(slot = _slot)

        for _slot_job in _assigned_jobs:
            self.env.commit_changed_job2db(
                db_session=db_session,
                job=_slot_job,
                worker_code=_slot.worker_code)



    def dispatch_jobs_1_cluster_ortools(self, db_job_list, db_session, item_price_dict):
        cluster_begin_time = datetime.now()

        # Create and register a transit callback.

        def distance_callback(from_index, to_index):
            # Convert from routing variable Index to distance matrix NodeIndex.
            from_node = manager.IndexToNode(from_index)  # - 1
            to_node = manager.IndexToNode(to_index)  # - 1

            if from_node == to_node:
                return 0
            return self._get_travel_time_2locations(
                self.cluster_list[from_node][1:3],
                self.cluster_list[to_node][1:3])

        self.distance_callback_func = distance_callback
        # Create the routing index manager.
        manager = pywrapcp.RoutingIndexManager(len(self.cluster_list), 1, 0)

        # Create Routing Model.
        routing = pywrapcp.RoutingModel(manager)

        transit_callback_index = routing.RegisterTransitCallback(
            distance_callback)

        # Define cost of each arc.
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Add Distance constraint.
        dimension_name = "Distance"
        routing.AddDimension(
            transit_callback_index,
            0,  # no slack
            900,  # vehicle maximum travel distance
            True,  # start cumul to zero
            dimension_name,
        )
        distance_dimension = routing.GetDimensionOrDie(dimension_name)
        distance_dimension.SetGlobalSpanCostCoefficient(100)

        # Setting first solution heuristic.
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
        search_parameters.log_search = True
        search_parameters.time_limit.seconds = self.config["max_exec_seconds"]

        # Solve the problem.
        solution = routing.SolveWithParameters(search_parameters)

        cluster_total_time = datetime.now() - cluster_begin_time
        print(
            f"Algorithm Done. nbr workers: {len(self.worker_slots)}, nbr jobs: {len(self.cluster_list)}, Elapsed: {cluster_total_time}"
        )

        # Print solution on console.
        if solution:
            self.print_solution(manager, routing, solution)
            self.save_solution(manager, routing, solution, db_job_list = db_job_list, db_session=db_session, item_price_dict = item_price_dict)

        else:
            print(f"Failed on cluster")

    def print_solution(self, manager, routing, solution):
        """Prints solution on console."""
        max_route_distance = 0
        for vehicle_id in range(len(self.worker_slots)):
            index = routing.Start(vehicle_id)
            plan_output = "Route for vehicle {}:\n".format(vehicle_id)
            route_distance = 0
            while not routing.IsEnd(index):
                plan_output += " {} -> ".format(manager.IndexToNode(index))
                previous_index = index
                index = solution.Value(routing.NextVar(index))
                route_distance += routing.GetArcCostForVehicle(
                    previous_index, index, vehicle_id)
            plan_output += "{}\n".format(manager.IndexToNode(index))
            plan_output += "Distance of the route: {}m\n".format(
                route_distance)
            print(plan_output)
            max_route_distance = max(route_distance, max_route_distance)
        print("Maximum of the route distances: {}m".format(max_route_distance))

    def save_solution(self, manager, routing, solution, db_job_list, db_session, item_price_dict):
        """Prints solution on console."""

        total_item_value = 0
        for vehicle_id in range(len(self.worker_slots)):
            _slot = self.worker_slots[vehicle_id]
            # worker_code = _slot.worker_code
            _assigned_jobs = []
            _required_items = {}

            # First one (previous_index) should be depot 
            previous_index = routing.Start(vehicle_id)
            # Start from second
            index = solution.Value(routing.NextVar(previous_index))
            plan_output = "Route for vehicle {}:\n".format(vehicle_id)
            route_distance = 0

            next_start_minutes = max(
                self.worker_slots[vehicle_id].start_minutes,
                self.env.get_env_planning_horizon_start_minutes(),
            )
            # prev_location = self.worker_slots[vehicle_id].end_location 

            while not routing.IsEnd(index):
                plan_output += " {} -> ".format(manager.IndexToNode(index))
                # job starts at 0
                if index < 1:
                    continue
                db_job = db_job_list[index]
                requested_items = db_job.flex_form_data.get("accum_items", "")
                if len(requested_items) < 3:
                    continue

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

                travel_time = routing.GetArcCostForVehicle(
                    previous_index, index, vehicle_id)
                previous_index = index
                index = solution.Value(routing.NextVar(index))

                if total_item_value > 3000:
                    log.warning(f"Worker slot {_slot.slot_code} reached limit of 3000, skipping an assigned job: {db_job.code}")
                    # break # if break, it skips next jobs even if next job does not require any item
                    continue
                job_in_slot = self.env.env_encode_single_job_db(db_job)
                job_in_slot.scheduled_start_minutes = next_start_minutes + travel_time
                job_in_slot.prev_travel = travel_time
                _assigned_jobs.append(job_in_slot)
                next_start_minutes = job_in_slot.scheduled_start_minutes + job_in_slot.scheduled_duration_minutes


            _slot.assigned_jobs = _assigned_jobs
            init_load_items = copy.deepcopy(_required_items)
            init_load_total_value = total_item_value
            _free_items = {k:0 for k in init_load_items.keys()}
            for len_ratio in (0.1, 0.3, 0.5, 1):
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
