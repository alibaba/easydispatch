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

from dispatch.plugins.kandbox_planner.env.env_enums import LocationType
from dispatch.plugins.kandbox_planner.env.env_models import JobLocationBase


class ClusterCVRPPlanner(KandboxBatchOptimizerPlugin):

    title = "VRP and Cluster Planner"
    slug = "kandbox_cluster_cvrp_planner"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan/kandbox_dispatch"
    description = "This is a Batch Optimizer, using Gaussian Mixture for clustering and then ortools for vrp inside each cluster."
    version = "0.1.0"
    default_config = {"log_search_progress": True, "max_exec_seconds": 60}
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, config=None):
        self.config = config or self.default_config.copy()

    def _get_travel_time_2locations(self, loc1, loc2):
        new_time = self.env.travel_router.get_travel_minutes_2locations(
            [loc1[0], loc1[1]],
            [loc2[0], loc2[1]],
        )
        if new_time > 200:
            print([loc1[0], loc1[1]], [loc2[0], loc2[1]], (new_time), "Error, too long")
        # print("travel: ", new_time)
        return int(new_time / 1)

    def dispatch_jobs(self, env, rl_agent=None):
        # Real batch, rl_agent is skilpped.
        #
        assert env.config["nbr_of_days_planning_window"] == 1, "I can do all workers for one day only."
        if len(env.jobs) < 1:
            print("it is empty, nothing to dispatch!")
            return
        self.env = env

        # 20, 150 failed for 8 hours.
        slot_keys = list(self.env.slot_server.time_slot_dict.keys())  # [0:12]
        self.worker_slots_all = [self.env.slot_server.time_slot_dict[key] for key in slot_keys]

        # env.jobs = env.jobs [0:200]
        begin_time = datetime.now()
        print(f"Started dispatching at time: {begin_time}")

        jobs_locs = [
            [w.job_code, w.location.geo_longitude, w.location.geo_latitude] for w in env.jobs
        ]
        jobs_df = pd.DataFrame.from_records(jobs_locs)
        jobs_df.columns = ['job_code', 'longitude', "latitude"]

        mclusterer = GaussianMixture(n_components=len(
            slot_keys), tol=0.01, random_state=66, verbose=1)
        jobs_df['cluster_id'] = mclusterer.fit_predict(jobs_df[['longitude', "latitude"]].values)
        cluster_count = jobs_df['cluster_id'].max() + 1
        print("{} clusters".format(cluster_count))

        avg_long = sum([j.location.geo_longitude for j in self.env.jobs]) / len(self.env.jobs)
        avg_lat = sum([j.location.geo_latitude for j in self.env.jobs]) / len(self.env.jobs)
        # DEPOT_AVG_JOB_LOCATION = JobLocationBase(
        #     geo_longitude=avg_long,
        #     geo_latitude=avg_lat,
        #     location_type=LocationType.HOME,
        #     location_code="depot",
        # )

        # depot_list = []
        # for cluster_i in range(cluster_count):
        #     depot_list.append(["depot", avg_long, avg_lat, cluster_i])
        # depot_df = pd.DataFrame.from_records(depot_list)
        # depot_df.columns = ['job_code', 'longitude', "latitude", "cluster_id"]

        # clustered_jobs_df = pd.concat([depot_df, jobs_df], ignore_index=True)

        for cluster_i in range(cluster_count):

            cluster_df = jobs_df[jobs_df["cluster_id"] == cluster_i].copy()
            cluster_df.set_index("job_code")
            self.cluster_list = [("depot", avg_long, avg_lat, cluster_i)] + \
                [tuple(j) for j in cluster_df.to_records(index=False)]

            self.worker_slots = [self.worker_slots_all[cluster_i]]
            self.dispatch_jobs_1_cluster()

        total_time = datetime.now() - begin_time
        print(
            f"Done. nbr workers: {len(self.worker_slots_all)}, nbr jobs: {len(self.cluster_list)}, Total Elapsed: {total_time}"
        )
        print(
            f"Travel Router: hit rate= {round(self.env.travel_router.redis_router_hit / self.env.travel_router.all_hit,4)}, routing api = {self.env.travel_router.routing_router_hit}, all count = {self.env.travel_router.all_hit}."
        )

    def dispatch_jobs_1_cluster(self):
        cluster_begin_time = datetime.now()
        # Create and register a transit callback.

        def distance_callback(from_index, to_index):
            # Convert from routing variable Index to distance matrix NodeIndex.
            from_node = manager.IndexToNode(from_index)  # - 1
            to_node = manager.IndexToNode(to_index)  # - 1

            if from_node == to_node:
                return 0
            return self._get_travel_time_2locations(
                self.cluster_list[from_node][1:3], self.cluster_list[to_node][1:3]
            )
        self.distance_callback_func = distance_callback
        # Create the routing index manager.
        manager = pywrapcp.RoutingIndexManager(len(self.cluster_list), 1, 0)

        # Create Routing Model.
        routing = pywrapcp.RoutingModel(manager)

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)

        # Define cost of each arc.
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Add Distance constraint.
        dimension_name = "Distance"
        routing.AddDimension(
            transit_callback_index,
            0,  # no slack
            600,  # vehicle maximum travel distance
            True,  # start cumul to zero
            dimension_name,
        )
        distance_dimension = routing.GetDimensionOrDie(dimension_name)
        distance_dimension.SetGlobalSpanCostCoefficient(100)

        # Setting first solution heuristic.
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
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
            self.save_solution(manager, routing, solution)

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
                route_distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
            plan_output += "{}\n".format(manager.IndexToNode(index))
            plan_output += "Distance of the route: {}m\n".format(route_distance)
            print(plan_output)
            max_route_distance = max(route_distance, max_route_distance)
        print("Maximum of the route distances: {}m".format(max_route_distance))

    def save_solution(self, manager, routing, solution):
        """Prints solution on console."""
        max_route_distance = 0
        for vehicle_id in range(len(self.worker_slots)):
            index = routing.Start(vehicle_id)
            # First one should be depot
            previous_index = index
            index = solution.Value(routing.NextVar(index))
            plan_output = "Route for vehicle {}:\n".format(vehicle_id)
            route_distance = 0
            # worker/vehicle starts at 0
            scheduled_worker_codes = [self.worker_slots[vehicle_id].worker_id]

            next_start_minutes = self.worker_slots[vehicle_id].start_minutes
            prev_location = self.worker_slots[vehicle_id].end_location

            while not routing.IsEnd(index):
                plan_output += " {} -> ".format(manager.IndexToNode(index))
                # job starts at 0
                job_code = self.cluster_list[index][0]  # - 1
                job = self.env.jobs_dict[job_code]
                one_job_action_dict = ActionDict(
                    job_code=job.job_code,
                    scheduled_worker_codes=scheduled_worker_codes,
                    scheduled_start_minutes=next_start_minutes,
                    scheduled_duration_minutes=job.requested_duration_minutes,
                    action_type=ActionType.FLOATING,
                    is_forced_action=False,
                )
                internal_result_info = self.env.mutate_update_job_by_action_dict(
                    a_dict=one_job_action_dict, post_changes_flag=True
                )
                if internal_result_info.status_code != ActionScoringResultType.OK:
                    print(
                        f"{one_job_action_dict.job_code}: Failed to commit change, error: {str(internal_result_info)} ")
                else:
                    print(f"job({one_job_action_dict.job_code}) is planned successfully ...")

                db_job = job_service.get_by_code(
                    db_session=self.env.kp_data_adapter.db_session, code=job.job_code)
                db_worker = worker_service.get_by_code(
                    db_session=self.env.kp_data_adapter.db_session, code=scheduled_worker_codes[0])

                db_job.requested_primary_worker = db_worker

                self.env.kp_data_adapter.db_session.add(db_job)
                self.env.kp_data_adapter.db_session.commit()

                print(
                    f"job({job.job_code}) is updated to new requested_primary_worker = {scheduled_worker_codes[0]} ")

                travel_time = self._get_travel_time_2locations(
                    prev_location, job.location
                )

                route_distance = routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
                next_start_minutes += job.requested_duration_minutes + route_distance

                prev_location = job.location
                previous_index = index
                index = solution.Value(routing.NextVar(index))

            # plan_output += "{}\n".format(manager.IndexToNode(index))
            # plan_output += "Distance of the route: {}m\n".format(route_distance)
            # print(plan_output)
            # max_route_distance = max(route_distance, max_route_distance)
        # print("Maximum of the route distances: {}m".format(max_route_distance))


if __name__ == "__main__":
    from pprint import pprint

    opti = Opti1DayPlanner(max_exec_seconds=config.KANDBOX_OPTI1DAY_EXEC_SECONDS)  # 0*60*24
    ss = config.KANDBOX_TEST_OPTI1DAY_START_DAY
    ee = config.KANDBOX_TEST_OPTI1DAY_END_DAY
    opti.env.purge_planner_job_status(planner_code=opti.planner_code, start_date=ss, end_date=ee)
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
