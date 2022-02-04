from dispatch.plugins.kandbox_planner.env.env_models import ActionDict, JobsInSlotsDispatchResult
from dispatch.plugins.kandbox_planner.env.env_enums import OptimizerSolutionStatus, ActionType
from datetime import datetime, timedelta
import pandas as pd


from ortools.sat.python import cp_model

import collections


from pprint import pprint

import sys

from dispatch import config
import dispatch.plugins.kandbox_planner.util.kandbox_date_util as date_util


from dispatch.plugins.kandbox_planner.planner_engine.jobs_in_slots_trait import JobsInSlotsPlannerTrait



import logging

from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp



log = logging.getLogger(__file__)


class OrtoolsRoutingPlannerJobsInSlots(JobsInSlotsPlannerTrait):  

    title = "Kandbox Plugin - internal - weighted nearest neighbour jobs in slots"
    slug = "kandbox_inner_planner_ortools_routing"
    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch"
    description = "Batch Optimizer - nearest_neighbour."
    version = "0.1.0"
    default_config = { }
    config_form_spec = {
        "type": "object",
        "properties": {},
    }

    def dispatch_jobs_in_slots(self, working_time_slots: list=[], last_job_count=1):
        """Assign jobs to workers.
        
        Note: THis works only for single worker, not shared.!
        """
        num_slots = len(working_time_slots)  # - 2
        num_workers = len(working_time_slots) - 2
        if num_workers < 1:
            num_workers = 1
        final_result = JobsInSlotsDispatchResult(
                status = OptimizerSolutionStatus.INFEASIBLE,
                changed_action_dict_by_job_code= {},
                all_assigned_job_codes=[],
                planned_job_sequence=[]
            ) 
        #     {
        #     "status": OptimizerSolutionStatus.INFEASIBLE,
        #     "changed_action_dict_by_job_code": {},
        #     "all_assigned_job_codes": [],
        #     "travel_minutes_difference": 0,
        # }
        if (num_slots < 1) or (
            len(working_time_slots[0].assigned_job_codes) > self.env.config["MAX_NBR_JOBS_IN_SLOT"]
        ):
            log.debug(f"Plan rejected, trying to plan {len(working_time_slots[0].assigned_job_codes)} jobs ...")
            return final_result





        slot = working_time_slots[0]
        horizon_start = self.env.get_env_planning_horizon_start_minutes()
        if horizon_start < slot.start_minutes:
            horizon_start = slot.start_minutes
        # orig_slot_job_codes = slot.assigned_job_codes[: 0 - last_job_count] 

        if len(slot.assigned_job_codes) < 3:
            if len(slot.assigned_job_codes) < 2:
                log.error("Not enough jobs to route")
            assert slot.assigned_job_codes[0].split("-")[-1]  == "pick", "first must be pick if only up to two jobs"
            solution_index = [0,1,2]
        else:
            pre_job = [None for _ in range(len(slot.assigned_job_codes))]
            for ji, jc in enumerate(slot.assigned_job_codes):
                if jc.split("-")[-1]  == "drop":
                    pick_code = jc[:-4]+"pick" # jc.split("-")[1] + "-pick"
                    if pick_code in slot.assigned_job_codes:
                        pre_job[ji] = [slot.assigned_job_codes.index(pick_code) + 1]

            locations = [
                self.env.jobs_dict[jc].location[0:2] + (0.2 if jc.split("-")[-1]  == "pick" else 1 , pre_job[ji])
                for ji, jc in enumerate(slot.assigned_job_codes)
            ]
            locations = [
                slot.start_location[0:2] + (1,None)
                ] +  locations
            
            solution_index = self.solve(locations)
            if solution_index is None:
                final_result.status = OptimizerSolutionStatus.INFEASIBLE
                return final_result 

        job_list = [slot.assigned_job_codes[i-1] for i in solution_index[1:]]
        final_result.status = OptimizerSolutionStatus.SUCCESS 

        # is_ok_end = True
        job_1_code = working_time_slots[0].assigned_job_codes[0-last_job_count]
        job_1 = self.env.jobs_dict[job_1_code]
        # I assume that job1 and job2 have same duration. 2021-07-06 07:16:06
        job_duration_minutes = self.env.get_encode_shared_duration_by_planning_efficiency_factor(
            requested_duration_minutes=job_1.requested_duration_minutes,
            nbr_workers=num_workers,
        )

        job_2_code = working_time_slots[0].assigned_job_codes[-1]
        job_2 = self.env.jobs_dict[job_2_code]


        prev_start_time = horizon_start
        if prev_start_time < slot.start_minutes:
            prev_start_time = slot.start_minutes
        
        prev_loc = slot.start_location
        

        all_worker_codes = [s.worker_id for s in working_time_slots]

        final_result.all_assigned_job_codes = [job_list]
        current_start = prev_start_time
        for job_i in list(range(0, len(job_list))):
            j_code = job_list[job_i]
            curr_job = self.env.jobs_dict[j_code]
            current_start +=  self.env.travel_router.get_travel_minutes_2locations(prev_loc, curr_job.location)
            _action_dict = ActionDict(
                is_forced_action=False,
                job_code=j_code,
                action_type=ActionType.FLOATING,
                scheduled_worker_codes=all_worker_codes,
                scheduled_start_minutes=current_start,
                scheduled_duration_minutes=curr_job.requested_duration_minutes,
            )
            final_result.changed_action_dict_by_job_code[j_code] = _action_dict
            prev_loc = curr_job.location
        # (len(job_list) > 2) and (job_list[0].split("-")[-1]  == "drop")
        return final_result

    def solve(self, locations):
        self.distance_matrix = self.env.travel_router.get_travel_minutes_matrix(locations)
        # Create the routing index manager.
        # 1 vehicle, 1 depot (==0)
        manager = pywrapcp.RoutingIndexManager(len(locations),1,0)
        # Create Routing Model.
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            """Returns the distance between the two nodes."""
            # Convert from routing variable Index to distance matrix NodeIndex.
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return self.distance_matrix [from_node][to_node]
        transit_callback_index = routing.RegisterTransitCallback(distance_callback)


        # routing.AddNodePrecedence(6,4,1)
        # Add pickup precedence.
        for loc_j, loc in enumerate(locations):
            if loc[3] is not None:
                for loc_i in  loc[3]:
                    routing.AddPickupAndDelivery(loc_i,loc_j)
        # routing.AddPickupAndDelivery(6,4)

        # Define cost of each arc.
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Setting first solution heuristic.
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)

        # Solve the problem.
        solution = routing.SolveWithParameters(search_parameters)
        index_list = []
        # Print solution on console.
        if solution: 
            
            index = routing.Start(0)
            plan_output ='Objective: {} Minutes, Route:'.format(solution.ObjectiveValue())
            route_distance = 0
            while not routing.IsEnd(index):
                plan_output += ' {} ->'.format(manager.IndexToNode(index))
                index_list.append(index)
                previous_index = index
                index = solution.Value(routing.NextVar(index))
                route_distance += routing.GetArcCostForVehicle(previous_index, index, 0)
                plan_output += ' ({}) '.format(route_distance/10)
            plan_output += ' {}. '.format(manager.IndexToNode(index))
            # index_list.append(index)
            plan_output += 'Totally {} mins'.format(route_distance)
            log.debug(plan_output)
            return index_list
            
        return None



if __name__ == "__main__":

    import pickle

    slots = pickle.load(open("/tmp/working_time_slots.p", "rb"))

    opti_slot = OrtoolsRoutingPlannerJobsInSlots()
    res = opti_slot.dispatch_jobs_in_slots(slots)
    print(res)
