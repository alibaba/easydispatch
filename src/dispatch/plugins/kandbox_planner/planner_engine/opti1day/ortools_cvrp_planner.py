# Cited from https://developers.google.com/optimization/routing/penalties#complete-programs

from datetime import datetime, timedelta
import pandas as pd


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


def print_solution(agent, manager, routing, solution):
    """Prints solution on console."""
    max_route_distance = 0
    for vehicle_id in range(len(agent.worker_slots)):
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


def save_solution(agent, manager, routing, solution):
    """Prints solution on console."""
    max_route_distance = 0
    for vehicle_id in range(len(agent.worker_slots)):
        index = routing.Start(vehicle_id)
        # First one should be depot
        previous_index = index
        index = solution.Value(routing.NextVar(index))
        plan_output = "Route for vehicle {}:\n".format(vehicle_id)
        route_distance = 0
        # worker/vehicle starts at 0
        scheduled_worker_codes = [agent.worker_slots[vehicle_id].worker_id]

        next_start_minutes = agent.worker_slots[vehicle_id].start_minutes
        prev_location = agent.worker_slots[vehicle_id].end_location

        while not routing.IsEnd(index):
            plan_output += " {} -> ".format(manager.IndexToNode(index))
            # job starts at 0
            job = agent.env.jobs[index - 1]
            one_job_action_dict = ActionDict(
                job_code=job.job_code,
                scheduled_worker_codes=scheduled_worker_codes,
                scheduled_start_minutes=next_start_minutes,
                scheduled_duration_minutes=job.requested_duration_minutes,
                action_type=ActionType.FLOATING,
                is_forced_action=False,
            )
            internal_result_info = agent.env.mutate_update_job_by_action_dict(
                a_dict=one_job_action_dict, post_changes_flag=True
            )
            if internal_result_info.status_code != ActionScoringResultType.OK:
                print(
                    f"{one_job_action_dict.job_code}: Failed to commit change, error: {str(internal_result_info)} ")
            else:
                print(f"job({one_job_action_dict.job_code}) is planned successfully ...")

            travel_time = agent._get_travel_time_2locations(
                prev_location, job.location
            )

            route_distance = routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
            next_start_minutes += job.requested_duration_minutes + route_distance

            prev_location = job.location
            previous_index = index
            index = solution.Value(routing.NextVar(index))


class OrtoolsCVRPPlanner(KandboxBatchOptimizerPlugin):

    title = "Kandbox Plugin - Batch Optimizer - ortools_cvrp_planner"
    slug = "kandbox_ortools_cvrp_planner"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan/kandbox_dispatch"
    description = "Batch Optimizer - opti1day."
    version = "0.1.0"
    default_config = {"log_search_progress": True, "max_exec_seconds": 10}
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

    def dispatch_jobs(self, env):
        # , start_date="20191101", end_date="20191230"
        assert env.config["nbr_of_days_planning_window"] == 1, "I can do all workers for one day only."
        if len(env.jobs) < 1:
            print("it is empty, nothing to dispatch!")
            return
        self.env = env

        # 20, 150 failed for 8 hours. with 100 limit
        # 100 w, 1000 jobs finished in 10 minutes with 300 travel limit
        slot_keys = list(self.env.slot_server.time_slot_dict.keys())  # [0:100] [0:5]
        self.worker_slots = [self.env.slot_server.time_slot_dict[key] for key in slot_keys]

        env.jobs = env.jobs  # [0:500] [0:50]
        begin_time = datetime.now()
        print(f"Started dispatching at time: {begin_time}")

        avg_long = sum([j.location.geo_longitude for j in self.env.jobs]) / len(self.env.jobs)
        avg_lat = sum([j.location.geo_latitude for j in self.env.jobs]) / len(self.env.jobs)
        DEPOT_AVG_JOB_LOCATION = JobLocationBase(
            geo_longitude=avg_long,
            geo_latitude=avg_lat,
            location_type=LocationType.HOME,
            location_code="depot",
        )
        self.job_locations = [DEPOT_AVG_JOB_LOCATION]

        for j in self.env.jobs:
            self.job_locations.append(j.location)

        # Create and register a transit callback.

        def distance_callback(from_index, to_index):
            # Convert from routing variable Index to distance matrix NodeIndex.
            from_node = manager.IndexToNode(from_index)  # - 1
            to_node = manager.IndexToNode(to_index)  # - 1

            if from_node == to_node:
                return 0
            return self._get_travel_time_2locations(
                self.job_locations[from_node], self.job_locations[to_node]
            )

        # Create the routing index manager.
        manager = pywrapcp.RoutingIndexManager(len(self.job_locations), len(self.worker_slots), 0)
        # routing_parameters = pywrapcp.DefaultRoutingModelParameters()
        # routing_parameters.solver_parameters.trace_propagation = True
        # routing_parameters.solver_parameters.trace_search = True
        # routing_parameters

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
            200,  # vehicle maximum travel distance
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
        search_parameters.time_limit.seconds = 60 * 3

        # Solve the problem.
        solution = routing.SolveWithParameters(search_parameters)

        total_time = datetime.now() - begin_time
        # Date: {begin_time},
        print(
            f"Algorithm Done. nbr workers: {len(self.worker_slots)}, nbr jobs: {len(self.job_locations)}, router cache hit = {round(self.env.travel_router.redis_router_hit / self.env.travel_router.all_hit,4)}, router count = {self.env.travel_router.all_hit},Elapsed: {total_time}"
        )

        # Print solution on console.
        if solution:
            print_solution(self, manager, routing, solution)
            save_solution(self, manager, routing, solution)

            total_time = datetime.now() - begin_time
            # Date: {begin_time},
            print(
                f"Done. nbr workers: {len(self.worker_slots)}, nbr jobs: {len(self.job_locations)}, Total Elapsed: {total_time}"
            )

        else:
            print("Failed")


if __name__ == "__main__":
    from pprint import pprint

    opti = Opti1DayPlanner(max_exec_seconds=config.KANDBOX_OPTI1DAY_EXEC_SECONDS)  # 0*60*24
    ss = config.KANDBOX_TEST_OPTI1DAY_START_DAY
    ee = config.KANDBOX_TEST_OPTI1DAY_END_DAY
    opti.env.purge_planner_job_status(planner_code=opti.planner_code, start_date=ss, end_date=ee)
    res = opti.dispatch_jobs(start_date=ss, end_date=ee)
    # pprint(res)

    exit(0)
