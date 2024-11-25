import copy
from dispatch.plugins.kandbox_planner.env.env_models import ActionDict, JobsInSlotsDispatchResult
from dispatch.plugins.kandbox_planner.env.env_enums import JobType, OptimizerSolutionStatus, ActionType
from datetime import datetime, timedelta

import numpy as np

import math

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
        """ 
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
                log.debug("Not enough jobs to route")
            # assert slot.assigned_job_codes[0].split("-")[-1]  == "pick", "first must be pick if only up to two jobs"
            solution_index = list(range(len(slot.assigned_job_codes)+1))# [0,1,2]
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
        

        all_worker_codes = [s.worker_code for s in working_time_slots]

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
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)



        # routing.AddNodePrecedence(6,4,1)
        # Add pickup precedence.
        for loc_j, loc in enumerate(locations):
            if loc[3] is not None:
                for loc_i in  loc[3]:
                    routing.AddPickupAndDelivery(loc_i,loc_j)
        # routing.AddPickupAndDelivery(6,4)

        # Define cost of each arc.
        
        # Setting first solution heuristic.
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC)
        search_parameters.time_limit.seconds = 30
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


    def dispatch_jobs_to_slots(self, 
        working_time_slots: list=[], 
        unplanned_job_code_list=[],
        log_progress = False,
        print_result=False,
        ):
        """ 
        Note: THis works only for single worker, not shared.!
        """
        num_slots = len(working_time_slots)  
        final_result = JobsInSlotsDispatchResult(
                status = OptimizerSolutionStatus.INFEASIBLE,
                changed_action_dict_by_job_code= {},
                all_assigned_job_codes=[],
                planned_job_sequence=[]
        ) 

        if (num_slots < 1) or (
            len(unplanned_job_code_list) < 1
        ):
            log.debug(f"Plan rejected, no slots or no {len(unplanned_job_code_list)} jobs ...")
            return final_result


        sub_jobs = [[114.948, 25.828, 0.2,None, 'depot', None, -1]]
        # Extract all inplanning jobs in all slots
        for slot_i, slot in enumerate(working_time_slots):
            pre_job = [None for _ in range(len(slot.assigned_job_codes))]
            for ji, jc in enumerate(slot.assigned_job_codes):
                if jc.split("-")[-1]  == "drop":
                    pick_code = jc[:-4]+"pick" # jc.split("-")[1] + "-pick"
                    if pick_code in slot.assigned_job_codes:
                        pre_job[ji] = [slot.assigned_job_codes.index(pick_code) + 1 + len(sub_jobs)]

            locations = [
                list(self.env.jobs_dict[jc].location[0:2]) + [0.2 if jc.split("-")[-1]  == "pick" else 1 , pre_job[ji], jc, slot_i]
                for ji, jc in enumerate(slot.assigned_job_codes)
            ]
            locations = [
                list(slot.start_location[0:2]) + [1,None, f"{slot.worker_code}=Start", slot_i]
                ] +  locations
            
            sub_jobs += locations
        # collect all free , unplanned jobs 
        for ji, jc in enumerate(unplanned_job_code_list):

            job = self.env.jobs_dict[jc]
            if job.job_type == JobType.COMPOSITE:
                job_root = jc.split("-")[:-1]
                pick_job = self.env.jobs_dict["-".join(job_root+["pick"])]
                drop_job = self.env.jobs_dict["-".join(job_root+["drop"])]

                sub_jobs.append(list(pick_job.location[0:2]) + [
                    0.2,None, "-".join(job_root+["pick"]), None
                ])
                pick_index = len(sub_jobs) - 1
                sub_jobs.append(list(drop_job.location[0:2]) + [ 
                    1,[pick_index], "-".join(job_root+["drop"]), None
                ])
            else:
                sub_jobs.append(list(job.location[0:2]) + [
                    0.2,None, job.job_code, None
                ])
        sub_jobs[0].append(-1)
        loc_list = []
        for si in range(1,len(sub_jobs)):
            sub_jobs[si].append(si-1)
            loc_list.append(sub_jobs[si][0:2])

        distance_matrix = self.travel_router.get_travel_minutes_matrix(loc_list)
        # distance_matrix_cache_t = np.array( matrix_list )

        solution, manager, routing = self.solve_ortools_pickdrop(sub_jobs, num_slots, 
            log_progress = log_progress, 
            distance_matrix=distance_matrix
            )

        if solution is None:
            final_result.status = OptimizerSolutionStatus.INFEASIBLE
            return final_result 
        # else: 
        # good solution, continue to assemble result.
        final_result.status = OptimizerSolutionStatus.SUCCESS 
        total_route_distance = 0
        plan_output ='Objective: {} Minutes, Route:'.format(solution.ObjectiveValue())
        for slot_i, slot in enumerate(working_time_slots):
            plan_output += f"\nslot ({slot_i}): "
            prev_index = routing.Start(slot_i) 
            if routing.IsEnd(prev_index):
                continue
            # prev_loc = slot.start_location
            current_start = slot.start_minutes
            route_distance = 0
            job_list =[]
            job_seq = 0
            while not routing.IsEnd(prev_index):
                job_seq +=1
                index = solution.Value(routing.NextVar(prev_index))
                job_node_i = manager.IndexToNode(index)
                plan_output += ' ({}:{}:'.format(job_seq,job_node_i)
                j_code = sub_jobs[job_node_i][4]
                if j_code.split("-")[-1] == "Start":
                    # prev_loc = sub_jobs[job_node_i][0:2]
                    prev_index = index
                    plan_output += 'worker_start) --> ('
                    continue
                if j_code == "depot":
                    prev_index = index
                    # print("Error depot")
                    continue
                job_list.append(j_code)
                curr_job = self.env.jobs_dict[j_code]
                route_distance = routing.GetArcCostForVehicle(prev_index, index, slot_i)
                current_start += route_distance
                total_route_distance += route_distance
                _action_dict = ActionDict(
                    is_forced_action=False,
                    job_code=j_code,
                    action_type=ActionType.FLOATING,
                    scheduled_worker_codes=[slot.worker_code],
                    scheduled_start_minutes=current_start,
                    scheduled_duration_minutes=curr_job.requested_duration_minutes,
                )
                final_result.changed_action_dict_by_job_code[j_code] = _action_dict
                plan_output += f' {j_code}, travel {route_distance}) -> ' 
                if sub_jobs[job_node_i][5] is None:
                    if j_code.split("-")[-1] == "pick":
                        # First inplanning of free job, then add composite
                        _composite_action = copy.copy(_action_dict)
                        _composite_action.job_code = "-".join(j_code.split("-")[:-1]+["composite"])
                        final_result.changed_action_dict_by_job_code[_composite_action.job_code] = _composite_action


                # prev_loc = curr_job.location
                prev_index = index

            slot.assigned_job_codes = job_list
        plan_output += '\nTotally {} mins'.format(total_route_distance)
        if print_result:
            log.error(plan_output)
        return final_result
            

    def solve_ortools_pickdrop(self, sub_jobs, num_slots, 
        log_progress = False, distance_matrix = None,
        time_limit_seconds = 10, max_job_in_worker_size = 30, max_travel_minutes = 999999 ):
        if distance_matrix is not None:
            assert len(sub_jobs) == distance_matrix.shape[0]+1, "sub_jobs == distance_matrix.shape(0)+1"

        manager = pywrapcp.RoutingIndexManager(len(sub_jobs),num_slots,0)
        # Create Routing Model.
        routing = pywrapcp.RoutingModel(manager)
        node2loc_dict={}
        for ji, j in enumerate(sub_jobs):
            node2loc_dict[ji] = j[6]

        def distance_callback(from_index, to_index):
            """Returns the distance between the two nodes."""
            # Convert from routing variable Index to distance matrix NodeIndex.
            # print("from,to:", from_index, to_index)
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            if (from_node==0) or (to_node==0):
                return 0
            # print("from,", from_index, from_node,"to:", to_index, to_node)
            if distance_matrix is None:
                dist = self.travel_router.get_travel_minutes_2locations(
                    sub_jobs[from_node][0:2],
                    sub_jobs[to_node][0:2],
                )
                print("Pls use distance matrix")
            else:
                # dist = distance_matrix[from_node - 1, to_node - 1]
                dist = distance_matrix[node2loc_dict[from_node], node2loc_dict[to_node]]
            return math.ceil(dist)
        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Add Distance constraint.
        dimension_name = 'Distance'
        routing.AddDimension(
            transit_callback_index,
            0,  # no slack
            max_travel_minutes,  # vehicle maximum travel distance
            True,  # start cumul to zero
            dimension_name)
        distance_dimension = routing.GetDimensionOrDie(dimension_name)
        distance_dimension.SetGlobalSpanCostCoefficient(100)


        def sequence_callback(from_index, to_index):
            """Returns the sequence gap between the two nodes.""" 
            return 1
        seq_callback_index = routing.RegisterTransitCallback(sequence_callback)

        seq_dimension_name = 'jobseq'
        routing.AddDimension(
            seq_callback_index,
            0,  # no slack
            max_job_in_worker_size,  # vehicle maximum number of jobs
            True,  # start cumul to zero
            seq_dimension_name)
        seq_dimension = routing.GetDimensionOrDie(dimension_name) 


        # routing.AddNodePrecedence(6,4,1)
        # Add pickup precedence.
        for loc_j, loc in enumerate(sub_jobs):
            name_codes = loc[4].split("-")
            if len(name_codes) > 1:
                if name_codes[1] == "Start":
                    assert loc[5] is not None, "Starting node must belong to a vehicle at loc[5]"
                    routing.solver().Add(
                        routing.VehicleVar(manager.NodeToIndex(loc_j)) == loc[5]
                    )
                    routing.solver().Add(
                        distance_dimension.CumulVar(loc_j) == 0 # <= 100
                    )
                    routing.solver().Add(
                        seq_dimension.CumulVar(loc_j) == 0 # <= 100
                    )

                    

                    continue
                else:
                    # Must be a job node
                    assert len(name_codes) == 3, f"Error {name_codes}"
                    routing.solver().Add(
                        seq_dimension.CumulVar(loc_j) > 0 # <= 100
                    )
            else:
                # it is depot
                continue
            if loc[3] is not None:
                # This job has a preceding pick.
                for loc_i in  loc[3]:
                    routing.AddPickupAndDelivery(loc_i,loc_j)
                    routing.solver().Add(
                        routing.VehicleVar(manager.NodeToIndex(loc_i)) == routing.VehicleVar(manager.NodeToIndex(loc_j))
                    )
                    routing.solver().Add(
                        distance_dimension.CumulVar(loc_i) <=
                        distance_dimension.CumulVar(loc_j)
                    )
                    routing.solver().Add(
                        seq_dimension.CumulVar(loc_i) <
                        seq_dimension.CumulVar(loc_j)
                    )

            if loc[5] is not None:
                # already assigned to a worker
                routing.solver().Add(
                    routing.VehicleVar(manager.NodeToIndex(loc_j)) == loc[5]
                )

            # else:
            #     # Currently free. Then it will be a regular pick-drop pair.
            #     if loc[3] is not None:
            #         for loc_i in loc[3]:
            #             routing.solver().Add(
            #                 routing.VehicleVar(manager.NodeToIndex(loc_i)) == routing.VehicleVar(manager.NodeToIndex(loc_j))
            #             )

            #     routing.AddPickupAndDelivery(loc_i,loc_j)
        
        # Setting first solution heuristic.
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION)
        # search_parameters.local_search_metaheuristic = (routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
        search_parameters.time_limit.seconds = time_limit_seconds
        # Solve the problem.
        if log_progress:
            search_parameters.log_search = True
        solution = routing.SolveWithParameters(search_parameters)

        return solution, manager, routing

if __name__ == "__main__":

    # import pickle

    # slots = pickle.load(open("/tmp/working_time_slots.p", "rb"))

    # opti_slot = OrtoolsRoutingPlannerJobsInSlots()
    # res = opti_slot.dispatch_jobs_in_slots(slots)

    sub_jobs = [(114.90756225585938, 25.861677169799805, 0.2, None, 'depot', None), [114.90756225585938, 25.861677169799805, 1, None, '0=Start', 0], [114.90756225585938, 25.861677169799805, 1, None, 'job-1-pick', None], [114.94388580322266, 25.840124130249023, 1, None, 'job-2-pick', None], [114.90447235107422, 25.86334991455078, 1, None, 'job-3-pick', None], [114.92900848388672, 25.840490341186523, 1, None, 'job-4-pick', None], [114.9574966430664, 25.84896469116211, 1, None, 'job-5-pick', None], [114.92407989501953, 25.8885498046875, 1, [2], '6-1-drop', None], [114.95848083496094, 25.852882385253906, 1, [3], '7-2-drop', None], [114.89722442626953, 25.883434295654297, 1, [4], '8-3-drop', None], [114.91728210449219, 25.82912254333496, 1, [5], '9-4-drop', None], [114.95425415039062, 25.819541931152344, 1, [6], '10-5-drop', None]]

    from dispatch.plugins.kandbox_planner.travel_time_plugin import  EuclideanTravelTime, OSRMTravelTime
    import numpy as np
    travel_router = OSRMTravelTime(
            # osrm_url = "http://127.0.0.1:5000",
            osrm_url = "http://192.168.9.251:5001",
            travel_mode = "car", # foot, car, bike
            travel_speed=18,
            # enable_home_travel = True
            )
    dm1 = np.array(
        [[0.0, 0.0, 18.19, 6.83, 15.17, 20.71, 15.84, 19.97, 12.59, 16.49, 26.29],
        [0.0, 0.0, 18.19, 6.83, 15.17, 20.71, 15.84, 19.97, 12.59, 16.49, 26.29],
        [18.19, 18.19, 0.0, 24.98, 6.14, 7.76, 22.8, 9.14, 30.72, 11.29, 10.08],
        [6.83, 6.83, 24.98, 0.0, 21.0, 27.54, 22.67, 26.8, 9.45, 20.92, 33.07],
        [15.17, 15.17, 6.14, 21.0, 0.0, 12.96, 21.04, 13.06, 26.46, 7.03, 14.22],
        [20.71, 20.71, 7.76, 27.54, 12.96, 0.0, 24.69, 2.84, 33.31, 18.14, 13.06],
        [15.84, 15.84, 22.8, 22.67, 21.04, 24.69, 0.0, 23.95, 28.43, 25.95, 30.95],
        [19.97, 19.97, 9.14, 26.8, 13.06, 2.84, 23.95, 0.0, 32.57, 19.51, 14.61],
        [12.59, 12.59, 30.72, 9.45, 26.46, 33.31, 28.43, 32.57, 0.0, 26.37, 38.81],
        [16.49, 16.49, 11.29, 20.92, 7.03, 18.14, 25.95, 19.51, 26.37, 0.0, 17.72],
        [26.29, 26.29, 10.08, 33.07, 14.22, 13.06, 30.95, 14.61, 38.81, 17.72, 0.0]]
    )
    planner = OrtoolsRoutingPlannerJobsInSlots(env=None, travel_router = travel_router)
    solution, manager, routing = planner.solve_ortools_pickdrop(
        sub_jobs, num_slots = 1, log_progress = True,
        distance_matrix = dm1,
        time_limit_seconds = 130)

    print(solution)
