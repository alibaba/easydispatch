
from collections import OrderedDict
from operator import truediv
import torch 
from logging import getLogger
from dispatch.contrib.training.pomo.single_job2slot_n2s.single_job2slot_n2s_env import decode_solution
from dispatch.contrib.training.pomo.utils.utils import create_logger 

import vroom

from dispatch.contrib.training.pomo.job2slot.Job2SlotEnv import Job2SlotEnv 
from dispatch.contrib.training.pomo.job2slot.Job2SlotModel import Job2SlotModel 

from dispatch.contrib.training.pomo.TSP.TSPEnv import TSPEnv 
from dispatch.contrib.training.pomo.TSP.TSPModel import TSPModel 

from dispatch.contrib.training.pomo.pick_drop_tsp.pick_drop_tsp_env import PickDropTSPEnv 
from dispatch.contrib.training.pomo.pick_drop_tsp.pick_drop_tsp_model import PickDropTSPModel 

from dispatch.contrib.training.pomo.pick_drop_job2slot.pick_drop_job2slot_env import PickDropJob2SlotEnv 
from dispatch.contrib.training.pomo.pick_drop_job2slot.pick_drop_job2slot_model import PickDropJob2SlotModel 

from dispatch.contrib.training.pomo.job2slot_input_data_trainer import Job2SlotInputDataTrainer  

from dispatch.contrib.training.pomo.pomo_params import ( 
    env_params, model_params, optimizer_params, logger_params,  data_basedir)
device = torch.device('cpu')


from dispatch.contrib.training.pomo.pomo_params import tester_params as trainer_params 


from torch.optim import Adam as Optimizer
from torch.optim.lr_scheduler import MultiStepLR as Scheduler

from dispatch.contrib.training.pomo.utils.utils import *
# from dispatch.contrib.training.pomo.job2slot.job2slot_pickdrop_sampled_osrm_dataset import (
#     OSRMSampleDataset, EuclideanBoxDataset
# )
from torch.utils.data import DataLoader, Dataset, BatchSampler, RandomSampler


class Job2SlotInputDataTester(Job2SlotInputDataTrainer):
    def __init__(self,
                 env_params,
                 model_params,
                 optimizer_params,
                 trainer_params,
                 gpu_id,
                 ): 
        super(Job2SlotInputDataTester, self,).__init__(
            env_params,
            model_params,
            optimizer_params,
            trainer_params,
            gpu_id,      
        )
        if self.model_params['model_load']:
            checkpoint_fullname = self.model_params["job2slot_model_path"]
            checkpoint = torch.load(checkpoint_fullname, map_location=device)
            old_model_dict = checkpoint['model_state_dict']
            if "module.encoder.layers.0.Wq.weight" in old_model_dict:
                model_dict = OrderedDict()
                for k,v in old_model_dict.items():
                    model_dict[k[7:]] = v
            else:
                model_dict = old_model_dict

            self.model.load_state_dict(model_dict)
            self.start_epoch = 1 + checkpoint['epoch']
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            print('Target: {}, Model is reloaded from file: {}'.format(
                self.trainer_params["training_target"], checkpoint_fullname
            ))
        else:
            print('Target: {}, Model is initialized ...'.format(
                self.trainer_params["training_target"] 
            ))


    def run(self):
        self.time_estimator.reset()
        

        score_AM = AverageMeter() 

        num_train_episodes = self.trainer_params['train_episodes']
        episode = 0
        loop_cnt = 0 
        ## =====================================================================
        for batch in enumerate(self.dataloader):
            # loc_xy = torch.stack(
            #     [self.dataset[b_i][0] for b_i in batch_indices]
            # )
            # dist_matrix = torch.stack(
            #     [self.dataset[b_i][1] for b_i in batch_indices]
            # )
            loc_xy = batch[1][0].to(device)
            dist_matrix = batch[1][1].to(device)

            remaining = num_train_episodes - episode
            # batch_size = min(self.trainer_params['train_batch_size'], remaining)

            avg_score, batch_size,_  = self._train_one_batch(loc_xy, dist_matrix)
            # batch_size = avg_score.size(0)
            score_AM.update(avg_score) 

            episode += 1


            if episode >= num_train_episodes:
                break
            # Log Once, for each epoch
            self.logger.info('Epoch {:3d}: Score: {:.4f} '
                         .format( episode,
                                 score_AM.avg, ))

            all_done = (episode >= num_train_episodes)

            if all_done:
                self.logger.info(" *** Test Done *** ")
                self.logger.info(" NO-AUG SCORE: {:.4f} ".format(score_AM.avg)) 

    def _train_one_batch(self, 
        loc_xy, 
        dist_matrix,
        worker_loc_idx = None,
        job_loc_idx = None,
        next_job_idx = None,
        next_job_mask = None,
        ):
        self.batch_size, self.pomo_size, self.worker_size = worker_loc_idx.size()
        batch_size = loc_xy.size(0)
        # Prep
        ###############################################

        # Ready
        ###############################################
        self.model.eval()
        with torch.no_grad():

            self.env.load_jobs(
                loc_xy = loc_xy, 
                dist_matrix= dist_matrix,
                worker_loc_idx = worker_loc_idx,
                job_loc_idx = job_loc_idx,
                next_job_idx = next_job_idx,
                next_job_mask = next_job_mask,
                aug_factor=1, 
            )
            step_state, reward, done = self.env.reset()
            

            self.model.pre_forward(step_state.reset_state)

            # POMO Rollout
            ###############################################
            # step_state, reward, done = self.env.pre_step()
            log_prob_list = []
            while not done:
                if step_state.job2slot_tsp_step == 1 and step_state.tsp_pre_forward_done == 0:
                    self.model.pre_tsp_forward(step_state)
                    step_state.tsp_pre_forward_done = 1


                selected, prob, _probs = self.model(step_state)
                # shape: (batch, pomo)
                step_state, reward, done = self.env.step(selected)

                log_prob = prob.log()
                if step_state.tsp_pre_forward_done == 1:
                    log_prob = log_prob.reshape(self.batch_size, self.pomo_size, self.worker_size).sum(dim=2)
                log_prob_list.append(log_prob)





        # get best results from pomo
        # shape: (augmentation, batch)
        score_mean = -reward.float().mean()  # negative sign to make positive value 


        return round(score_mean.item(), 4), reward,log_prob_list


def decode_ortools_vrp_plan(solution, manager, routing, sub_jobs, loc_idx, dist_matrix, num_slots = 8):
    ortools_loc_idx =[[] for i in range(num_slots)]
    ortools_tsp_idx =[[] for i in range(num_slots)]
    ortools_loc_length =[0 for i in range(num_slots)]
    total_route_distance = 0
    seq_dimension = routing.GetDimensionOrDie('jobseq') 
    plan_output ='Ortools Objective: {} Minutes, Route:'.format(solution.ObjectiveValue())
    for slot_i  in range(num_slots):
        prev_index = routing.Start(slot_i) 
        plan_output += f"\n({slot_i},{solution.Value(seq_dimension.CumulVar(prev_index))})>"
        ortools_tsp_idx[slot_i].append(manager.IndexToNode(prev_index))
        dm_prev_index = dm_index = slot_i
        if routing.IsEnd(prev_index):
            continue 
        current_start = 0
        route_distance = 0
        job_list =[]
        job_seq = 0

        while not routing.IsEnd(prev_index):
            job_seq +=1
            index = solution.Value(routing.NextVar(prev_index))
            job_node_i = manager.IndexToNode(index)
            ortools_tsp_idx[slot_i].append(job_node_i)
            jobseq = solution.Value(seq_dimension.CumulVar(job_node_i))
            dm_index = sub_jobs[job_node_i][6]

            ortools_loc_idx[slot_i].append(dm_index)
            plan_output += '('.format(job_seq,job_node_i) # {}:{}:
            j_code = sub_jobs[job_node_i][4]
            if j_code.split("-")[-1] == "Start":
                # prev_loc = sub_jobs[job_node_i][0:2]
                prev_index = index
                plan_output += f'S_{job_node_i},{jobseq})>'
                continue
            if j_code == "depot":
                prev_index = index
                # print("Error depot")
                continue
            # loc_idx[slot_i][job_seq - 1] = job_node_i - 1
            job_list.append(j_code) 
            route_distance_arc = routing.GetArcCostForVehicle(prev_index, index, slot_i) 

            route_distance = dist_matrix[dm_prev_index, dm_index]
            # print(f"{job_node_i} --> {dm_index}, distance {(route_distance_arc, prev_index, index, slot_i)} vs {(route_distance,dm_prev_index, dm_index)} ")
            current_start += route_distance
            total_route_distance += route_distance
            _action_dict = [ ] 
            plan_output += f'{j_code},{jobseq})>' #  travel {route_distance}, job

            # prev_loc = curr_job.location
            prev_index = index 
            dm_prev_index = dm_index

        ortools_loc_length[slot_i] = job_seq - 1
    plan_output += '\nTotally {} mins, job_lengths = {}'.format(total_route_distance,ortools_loc_length)

    print(plan_output) 
    return total_route_distance, ortools_tsp_idx, ortools_loc_length, ortools_loc_idx
    



def decode_ortools_tsp_plan(solution, manager, routing, sub_jobs, loc_idx, dist_matrix, num_slots = 1):
    total_route_distance = 0
    plan_output ='Ortools Objective: {} Minutes, Route:'.format(solution.ObjectiveValue())
    for slot_i  in range(num_slots):
        plan_output += f"\nslot ({slot_i}): "
        prev_index = routing.Start(slot_i) 
        dm_prev_index = dm_index = slot_i
        if routing.IsEnd(prev_index):
            continue 
        current_start = 0
        route_distance = 0
        route_distance_list = []
        job_list =[]
        job_seq = 0

        tsp_idx = [ ]

        while not routing.IsEnd(prev_index):
            job_seq +=1
            index = solution.Value(routing.NextVar(prev_index))
            job_node_i = manager.IndexToNode(index)
            plan_output += ' ({}:{}:'.format(job_seq,job_node_i)
            j_code = sub_jobs[job_node_i][4]
            tsp_idx.append(index - 1)
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
            route_distance_arc = routing.GetArcCostForVehicle(prev_index, index, slot_i)
            # if job_node_i % 2 == 0:
            #     dm_index = 8 + math.floor ((job_node_i - 8) / 2) + 21 - 1
            # else:
            #     dm_index = 8 + math.floor ((job_node_i - 8) / 2)
            dm_index = job_node_i - 1

            route_distance = dist_matrix[
                loc_idx[dm_prev_index], 
                loc_idx[dm_index],   
            ]
            # print(' ({}:{} --> {}-{} distance {}:'.format(job_seq,prev_index, index, job_node_i, route_distance))
            # print(f"{job_node_i} --> {dm_index}, distance {(route_distance_arc, prev_index, index, slot_i)} vs {(route_distance,dm_prev_index, dm_index)} ")
            current_start += route_distance
            route_distance_list.append(route_distance)
            total_route_distance += route_distance
            _action_dict = [ ] 
            plan_output += f' {j_code}, travel {route_distance}) -> ' 

            # prev_loc = curr_job.location
            prev_index = index 
            dm_prev_index = dm_index

    plan_output += '\nTotally {} mins'.format(total_route_distance)

    ortools_total = total_route_distance
    # print(plan_output) 
    return total_route_distance, tsp_idx
##########################################################################################




def extract_tsp_data(tester, batch_i, worker_i):
    loc_xy = tester.env.step_state.reset_state.loc_xy
    loc_xy.size()
    loc_gps_x = (loc_xy[batch_i,:,0:1]/2) + tester.dataset.geo_longitude_min 
    loc_gps_y = (loc_xy[batch_i,:,1:2]/2) + tester.dataset.geo_latitude_min  
    loc_gps_xy= torch.cat((loc_gps_x, loc_gps_y),dim = 1).tolist()

    loc_idx = tester.env.step_state.reset_state.job_loc_idx[batch_i,worker_i].tolist() 
    # tsp_idx = tester.env.step_state.selected_node_list[batch_i,worker_i].tolist()

    tsp_selected_loc_idx = tester.env.step_state.tsp_selected_loc_idx[batch_i,worker_i].tolist()
    dist_matrix = tester.env.dist_matrix[batch_i]
    return loc_xy,loc_gps_xy, loc_idx, tsp_selected_loc_idx, dist_matrix

# loc_gps_xy= torch.cat((loc_gps_x, loc_gps_y),dim = 1).tolist()

def transform_sub_jobs(loc_gps_xy,loc_idx, num_slots = 1):
    start_xy = loc_gps_xy[loc_idx[0]]
    sub_jobs = [(start_xy[0], start_xy[1], 0.2,None, 'depot', None )] 

    # Extract all inplanning jobs in all slots
    slot_i = 0
    worker_loc = [start_xy[0], start_xy[1]]  + [1 , None, f"{slot_i}=Start", slot_i]
    sub_jobs.append(worker_loc)

    job_count = (len(loc_gps_xy) - 1) // 2 #  5
    for ji in range(0, job_count):
        
        pick_idx = ji + 1
        pick_code=f"job-{pick_idx}-pick" 
        
        _loc = loc_gps_xy[loc_idx[pick_idx]]  + [1 , None, pick_code, None]
        sub_jobs.append(_loc)

    for ji in range(0, job_count):
        
        pick_idx = ji + 1
        drop_idx = pick_idx + job_count 
        drop_code=f"{drop_idx}-{pick_idx}-drop"
        
        _loc = loc_gps_xy[loc_idx[drop_idx]]  + [1 , [num_slots + pick_idx ], drop_code, None]
        sub_jobs.append(_loc)
    return sub_jobs

def transform_sub_jobs_tsp_only(loc_gps_xy,loc_idx, num_slots = 1):
    start_xy = loc_gps_xy[loc_idx[0]]
    sub_jobs = [(start_xy[0], start_xy[1], 0.2,None, 'depot', None, 0 )] 

    # Extract all inplanning jobs in all slots
    slot_i = 0
    worker_loc = [start_xy[0], start_xy[1]]  + [1 , None, f"{slot_i}-Start", slot_i, 0]
    sub_jobs.append(worker_loc)

    job_count =  len(loc_gps_xy)  - 1
    for ji in range(0, job_count):
        
        pick_idx = ji + 1
        pick_code=f"job-{pick_idx}-pick" 
        
        _loc = loc_gps_xy[loc_idx[pick_idx]]  + [1 , None, pick_code, None, pick_idx]
        sub_jobs.append(_loc)

    return sub_jobs







# loc_idx = tester.env.job_loc_idx[batch_i,worker_i].tolist() 
def extract_n_transform_vrp_sub_jobs(tester, batch_i, pomo_i, num_slots = 8):
    batch_size, pomo_size, worker_size, job_in_worker_size = tester.env.step_state.worker_selected_loc_idx.size()
    assert num_slots == worker_size, "num_slots == worker_size"

    job_size = int(tester.env.env_params["job_size"]/2)
    loc_xy = tester.env.step_state.reset_state.loc_xy 
    loc_gps_x = (loc_xy[batch_i,:,0:1]/2) + tester.dataset.geo_longitude_min 
    loc_gps_y = (loc_xy[batch_i,:,1:2]/2) + tester.dataset.geo_latitude_min  
    loc_gps_xy= torch.cat((loc_gps_x, loc_gps_y),dim = 1).tolist()

    worker_loc_idx = tester.env.step_state.reset_state.worker_loc_idx[batch_i,pomo_i].cpu().tolist()
    job_loc_idx = tester.env.step_state.reset_state.job_loc_idx[batch_i,pomo_i].cpu().tolist() #.transpose(0,1).reshape(job_size*2)

    worker_locs = []
    job_locs = []

    for i in range(worker_size):
        worker_locs.append(loc_gps_xy[worker_loc_idx[i]])

    for i in range(job_size):
        job_locs.append(loc_gps_xy[job_loc_idx[i][0]])

    for i in range(job_size):
        job_locs.append(loc_gps_xy[job_loc_idx[i][1]])

    loc_idx = tester.env.step_state.tsp_selected_loc_idx[
        batch_i
        ].tolist() # ,pomo_i

    loc_length = tester.env.step_state.worker_selected_loc_length[
        batch_i,pomo_i
        ].tolist() 
    # tsp_idx = tester.env.tsp_env.selected_node_list.view(
    #     batch_size, pomo_size, worker_size, job_in_worker_size
    # )[batch_i,pomo_i].tolist()

    # obselete, fake it.
    tsp_idx = torch.arange(job_in_worker_size).view(1,job_in_worker_size).repeat(worker_size, 1)

    dist_matrix = tester.env.dist_matrix[batch_i].cpu().numpy()

    start_xy = [tester.dataset.geo_longitude_min+0.5, tester.dataset.geo_latitude_min+0.5]
    sub_jobs = [(start_xy[0], start_xy[1], 0.2, None, 'depot', None, 999)]
    

    # Extract all inplanning jobs in all slots
    for slot_i  in range(num_slots): 
        worker_loc = worker_locs[slot_i]  + [1 , None, f"{slot_i}-Start", slot_i, worker_loc_idx[slot_i] ]
        sub_jobs.append(worker_loc)
    
    for ji in range(0, job_size*2):        
        sub_jobs.append([])
    for ji in range(0, job_size):        
        pick_idx = ji 
        pick_code=f"job-{pick_idx}-pick" 
        
        _loc = job_locs[ pick_idx ]  + [1 , None, pick_code, None, job_loc_idx[pick_idx][0] ]
        sub_jobs[job_loc_idx[pick_idx][0]+1] = _loc

    for ji in range(0, job_size):
        
        pick_idx = ji 
        drop_idx = pick_idx + job_size 
        drop_code=f"{drop_idx}-{pick_idx}-drop"
        
        _loc = job_locs[ drop_idx]  + [0.2 , [job_loc_idx[pick_idx][0]], drop_code, None,  job_loc_idx[pick_idx][1] ]
        sub_jobs[job_loc_idx[pick_idx][1]+1] = _loc
    return sub_jobs, loc_xy, loc_gps_xy, loc_idx, tsp_idx, dist_matrix, loc_length


##########################################################################################
from dispatch.plugins.kandbox_planner.planner_engine.jobs_in_slots_ortools_routing import OrtoolsRoutingPlannerJobsInSlots

from dispatch.plugins.kandbox_planner.travel_time_plugin import  EuclideanTravelTime, OSRMTravelTime

travel_router = OSRMTravelTime( config = {
        "route_service_url" : "http://127.0.0.1:5002",
        "travel_mode" : "car", # foot, car, bike
        "travel_speed":18,
        # enable_home_travel = True
    })


planner = OrtoolsRoutingPlannerJobsInSlots(env=None, travel_router = travel_router)



def run_osrm_tsp_single(tester,return_batch_i, return_worker_i, num_slots = 1):

    num_batchs = tester.trainer_params["train_batch_size"]
    ortools_travels = [[] for i in range(num_batchs)]

    return_gps, return_loc_idx, return_pomo_tsp_idx, return_ortools_tsp_idx = None, None, None, None
    for batch_i in range(num_batchs):
        for worker_i in range(num_slots): 
            loc_xy,loc_gps_xy, loc_idx, tsp_idx, dist_matrix = extract_tsp_data(tester, batch_i, worker_i)
            # sub_jobs = transform_sub_jobs(loc_gps_xy,loc_idx, num_slots = 1) 
            sub_jobs = transform_sub_jobs_tsp_only(loc_gps_xy,loc_idx, num_slots = 1) 

            loc_list = [ x[0:2] for x in sub_jobs[1:] ]
            new_seq, start_distance = travel_router.solve_tsp(loc_list = loc_list)
            total_distance = sum(start_distance[0:-1])

            ortools_travels[batch_i].append(total_distance)

    return ortools_travels, return_gps, return_loc_idx, return_pomo_tsp_idx, return_ortools_tsp_idx





def run_ortools_tsp_pickdrop(tester,return_batch_i, return_worker_i, num_slots = 1):

    num_batchs = tester.trainer_params["train_batch_size"]
    ortools_travels = [[] for i in range(num_batchs)]

    return_gps, return_loc_idx, return_pomo_tsp_idx, return_ortools_tsp_idx = None, None, None, None
    for batch_i in range(num_batchs):
        for worker_i in range(num_slots): 
            loc_xy,loc_gps_xy, loc_idx, tsp_selected_loc_idx, dist_matrix = extract_tsp_data(tester, batch_i, worker_i)
            # sub_jobs = transform_sub_jobs(loc_gps_xy,loc_idx, num_slots = 1) 
            sub_jobs = transform_sub_jobs_tsp_only(loc_gps_xy,loc_idx, num_slots = 1) 

            loc_list = [ x[0:2] for x in sub_jobs[1:] ]
            dm1 = travel_router.get_travel_minutes_matrix( loc_list = loc_list)

            solution, manager, routing = planner.solve_ortools_pickdrop(
                sub_jobs, num_slots = num_slots, log_progress = False,
                distance_matrix = dm1,
                time_limit_seconds = 60*10)
            if solution is None:
                # print(f"Solution failed on ortools on batch_i.worker_i = {batch_i}.{worker_i}")
                raise ValueError(f"Solution failed on ortools on batch_i.worker_i = {batch_i}.{worker_i}")
                ortools_travels[batch_i].append(555)
                continue

            lll, ortools_tsp_idx = decode_ortools_tsp_plan(
                solution = solution, manager= manager, routing = routing,
                sub_jobs = sub_jobs,
                loc_idx = tester.env.step_state.reset_state.job_loc_idx[batch_i,worker_i].tolist(), 
                dist_matrix = tester.env.step_state.reset_state.dist_matrix[batch_i]
            )
            ortools_travels[batch_i].append(lll)
            if batch_i == return_batch_i and worker_i ==  return_worker_i:
                # print(f"Plotting POMO Result {batch_i} {worker_i}")
                return_gps = loc_gps_xy
                return_loc_idx = loc_idx
                return_pomo_tsp_idx = tsp_idx
                return_ortools_tsp_idx = ortools_tsp_idx

    return ortools_travels, return_gps, return_loc_idx, return_pomo_tsp_idx, return_ortools_tsp_idx



def run_ortools_vrp_pickdrop(tester,return_batch_i, return_pomo_i):
    num_slots = tester.env_params["worker_size"]
    num_batchs = tester.trainer_params["train_batch_size"]
    ortools_travels = [[] for i in range(num_batchs)]

    return_gps, return_pomo_loc_idx, return_pomo_tsp_idx, return_ortools_tsp_idx = None, None, None, None
    return_ortools_loc_idx = None
    for batch_i in range(num_batchs):
        # for pomo_i in range(tester.env_params["pomo_size"]): 
        # Only once since all Locs are same.
        pomo_i = return_pomo_i
        sub_jobs, loc_xy,loc_gps_xy, loc_idx, pomo_tsp_idx, dist_matrix, loc_length = \
            extract_n_transform_vrp_sub_jobs(tester, batch_i, pomo_i, num_slots=num_slots)

        solution, manager, routing = planner.solve_ortools_pickdrop(
            sub_jobs, num_slots = num_slots, log_progress = False,
            distance_matrix = dist_matrix,
            time_limit_seconds = 120, 
            max_job_in_worker_size=tester.env_params["max_job_in_worker_size"]
        )
        if solution is None:
            # print(f"Solution failed on ortools on batch_i.pomo_i = {batch_i}.{pomo_i}")
            raise ValueError(f"Solution failed on ortools on batch_i.pomo_i = {batch_i}.{pomo_i}")
            ortools_travels[batch_i].append(555)
            continue

        total_route_distance, ortools_tsp_idx, ortools_loc_length, ortools_loc_idx = decode_ortools_vrp_plan(
            solution = solution, manager= manager, routing = routing,
            sub_jobs = sub_jobs,
            loc_idx = None, 
            dist_matrix = dist_matrix, # tester.env.dist_matrix[batch_i]
            num_slots=num_slots, 
        )
        ortools_travels[batch_i].append(total_route_distance)
        if batch_i == return_batch_i and pomo_i ==  return_pomo_i:
            # print(f"Plotting POMO Result {batch_i} {pomo_i}") 
            return_gps = loc_gps_xy
            return_pomo_loc_idx = loc_idx
            return_pomo_loc_length = loc_length
            return_pomo_tsp_idx = pomo_tsp_idx
            return_ortools_tsp_idx = ortools_tsp_idx
            return_ortools_loc_length = ortools_loc_length
            return_ortools_loc_idx = ortools_loc_idx

    return ortools_travels, return_gps, return_pomo_loc_idx, return_pomo_tsp_idx, return_pomo_loc_length, \
        return_ortools_loc_idx, return_ortools_tsp_idx, return_ortools_loc_length


##########################################################################################
#  
def decode_vroom_vrp_plan(solution, vehicle_list, dist_matrix, loc_xy ):
    total_route_distance, opti_tsp_idx   = 0,0 
    worker_size = len(vehicle_list)
    worker_locs = [[loc_xy[ii]] for ii in range(worker_size)]
    worker_locs_i = [[ii] for ii in range(worker_size)]


    for vehicle_id in range(len(vehicle_list)):
        # First one (previous_index) should be depot 
        previous_index = vehicle_id
        # Start from second job 

        for index, job_row in solution.routes[solution.routes["vehicle_id"] == vehicle_id].iterrows():
            if index < 1: # == "start":
                previous_index = job_row.location_index
                continue
            curr_index = job_row.location_index
            curr_travel = dist_matrix[previous_index, curr_index]
            total_route_distance += curr_travel
            worker_locs[vehicle_id].append(loc_xy[curr_index])
            worker_locs_i[vehicle_id].append(curr_index)

            previous_index = curr_index
    return total_route_distance, opti_tsp_idx, worker_locs, worker_locs_i

def run_vroom_vrp_pickdrop(tester,return_batch_i, return_pomo_i):
    num_slots = tester.env_params["worker_size"]
    num_batchs = tester.trainer_params["train_batch_size"]
    opti_travels = [[] for i in range(num_batchs)]
    opti_model = vroom.Input()

    return_gps, return_pomo_loc_idx, return_pomo_tsp_idx, return_opti_tsp_idx = None, None, None, None
    return_opti_loc_idx = None
    for batch_i in range(num_batchs):
        # for pomo_i in range(tester.env_params["pomo_size"]): 
        # Only once since all Locs are same.
        pomo_i = return_pomo_i
        # sub_jobs, loc_xy,loc_gps_xy, loc_idx, pomo_tsp_idx, dist_matrix, loc_length = \
        #     extract_n_transform_vrp_sub_jobs(tester, batch_i, pomo_i, num_slots=num_slots)
        dist_matrix = tester.env.dist_matrix[batch_i].cpu().numpy()
        loc_xy = tester.env.step_state.reset_state.loc_xy[0].cpu().numpy()

        worker_loc_idx = tester.env.step_state.reset_state.worker_loc_idx[batch_i,pomo_i].cpu().tolist()
        job_loc_idx = tester.env.step_state.reset_state.job_loc_idx[batch_i,pomo_i].cpu().tolist()

        dist_mat = (dist_matrix*1000).astype(int).tolist()
        # print(f"distance matrix statistics: (max = {dist_matrix.max()}, min = {dist_matrix.min()}, sum = {round(dist_matrix.sum(),2)}, mean = {round(dist_matrix.mean(),2)}, median = {round(np.median(dist_matrix),2)})")
        opti_model.set_durations_matrix(
            profile="car",
            matrix_input=dist_mat,
        )
        vehicle_list=[]
        shipment_list = [ ]
        for ji,j in enumerate(worker_loc_idx):
            vehicle_list.append(vroom.Vehicle(
                id=ji, 
                start=ji, # ji == j
                # end=return_idx, # if end is omitted, the resulting route will stop at the last visited task, whose choice is determined by the optimization process
                # skills = {si}, #  self.worker_code2index[s.worker_code]
                # capacity=vehicle_capacity,
                max_tasks=6,
                # time_window=[in_day_start, in_day_end]
            ))
        opti_model.add_vehicle(vehicle_list)
        for ji,j_idx in enumerate(job_loc_idx): 
            pick_step = vroom.ShipmentStep(
                id=job_loc_idx[ji][0],
                location=job_loc_idx[ji][0],  
            )
            drop_step = vroom.ShipmentStep(
                id=job_loc_idx[ji][1],
                location=job_loc_idx[ji][1],  
            )
            opti_model.add_shipment(
                pickup = pick_step,
                delivery = drop_step,

            )
        
            # ship = vroom.Shipment(
            #     pickup = pick_step,
            #     delivery = drop_step,
            # )
            # shipment_list.append(ship)

        solution = opti_model.solve(exploration_level=5, nb_threads=6)
        # print(f"VRoom Dispatching result: solution.summary.cost = {solution.summary.cost}, violations = {solution.summary.violations._types}, waiting_time = {solution.summary.waiting_time}, unassigned = {solution.summary.unassigned}") 


        if solution is None:
            # print(f"Solution failed on opti on batch_i.pomo_i = {batch_i}.{pomo_i}")
            raise ValueError(f"Solution failed on vroom on batch_i.pomo_i = {batch_i}.{pomo_i}")
            opti_travels[batch_i].append(999555)
            continue

        total_route_distance, opti_tsp_idx, worker_locs, worker_locs_i = decode_vroom_vrp_plan(
            solution = solution, 
            # sub_jobs = sub_jobs,
            vehicle_list = vehicle_list, 
            dist_matrix = dist_matrix, # tester.env.dist_matrix[batch_i]
            loc_xy = loc_xy,
        )
        opti_travels[batch_i].append(total_route_distance)
        if batch_i == return_batch_i and pomo_i ==  return_pomo_i:
            # print(f"Plotting POMO Result {batch_i} {pomo_i}") 
            return_gps = 0 # loc_gps_xy
            return_pomo_loc_idx = 0 # loc_idx
            return_pomo_loc_length = 0 # loc_length
            return_pomo_tsp_idx = 0 # pomo_tsp_idx
            return_opti_tsp_idx = 0 # opti_tsp_idx
            return_opti_loc_length = 0 # opti_loc_length
            return_opti_loc_idx = 0 # opti_loc_idx

    return opti_travels, loc_xy, return_pomo_loc_idx, return_pomo_tsp_idx, return_pomo_loc_length, \
        return_opti_loc_idx, worker_locs, worker_locs_i



def run_vroom_vrp_single(tester,return_batch_i, return_pomo_i):
    num_slots = tester.env_params["worker_size"]
    num_batchs = tester.trainer_params["train_batch_size"]
    opti_travels = [[] for i in range(num_batchs)]
    opti_model = vroom.Input()

    return_gps, return_pomo_loc_idx, return_pomo_tsp_idx, return_opti_tsp_idx = None, None, None, None
    return_opti_loc_idx = None
    for batch_i in range(num_batchs):
        # for pomo_i in range(tester.env_params["pomo_size"]): 
        # Only once since all Locs are same.
        pomo_i = return_pomo_i
        # sub_jobs, loc_xy,loc_gps_xy, loc_idx, pomo_tsp_idx, dist_matrix, loc_length = \
        #     extract_n_transform_vrp_sub_jobs(tester, batch_i, pomo_i, num_slots=num_slots)
        dist_matrix = tester.env.dist_matrix[batch_i].cpu().numpy()
        loc_xy = tester.env.step_state.reset_state.loc_xy[0].cpu().numpy()

        worker_loc_idx = tester.env.step_state.reset_state.worker_loc_idx[batch_i,pomo_i].cpu().tolist()
        job_loc_idx = tester.env.step_state.reset_state.job_loc_idx[batch_i,pomo_i].cpu().tolist()

        dist_mat = (dist_matrix*1000).astype(int).tolist()
        # print(f"distance matrix statistics: (max = {dist_matrix.max()}, min = {dist_matrix.min()}, sum = {round(dist_matrix.sum(),2)}, mean = {round(dist_matrix.mean(),2)}, median = {round(np.median(dist_matrix),2)})")
        opti_model.set_durations_matrix(
            profile="car",
            matrix_input=dist_mat,
        )
        # print(decode_solution(tester.env.step_state.solution[0].tolist(), tester.env.step_state.reset_state.worker_loc_idx.size(2)))
        vehicle_list=[]
        shipment_list = [ ]
        for ji,j in enumerate(worker_loc_idx):
            vehicle_list.append(vroom.Vehicle(
                id=ji, 
                start=ji, # ji == j
                # end=return_idx, # if end is omitted, the resulting route will stop at the last visited task, whose choice is determined by the optimization process
                # skills = {si}, #  self.worker_code2index[s.worker_code]
                # capacity=vehicle_capacity,
                max_tasks=8,
                # time_window=[in_day_start, in_day_end]
            ))
        opti_model.add_vehicle(vehicle_list)
        for ji,j_idx in enumerate(job_loc_idx):  
            opti_model.add_job(vroom.Job(
                id=ji, location=ji,
                service=1, 
            ))

        solution = opti_model.solve(exploration_level=5, nb_threads=6)
        # print(f"VRoom Dispatching result: solution.summary.cost = {solution.summary.cost}, violations = {solution.summary.violations._types}, waiting_time = {solution.summary.waiting_time}, unassigned = {solution.summary.unassigned}") 


        if solution is None:
            # print(f"Solution failed on opti on batch_i.pomo_i = {batch_i}.{pomo_i}")
            raise ValueError(f"Solution failed on vroom on batch_i.pomo_i = {batch_i}.{pomo_i}")
            opti_travels[batch_i].append(999555)
            continue

        total_route_distance, opti_tsp_idx, worker_locs, worker_locs_i = decode_vroom_vrp_plan(
            solution = solution, 
            # sub_jobs = sub_jobs,
            vehicle_list = vehicle_list, 
            dist_matrix = dist_matrix, # tester.env.dist_matrix[batch_i]
            loc_xy = loc_xy,
        )
        opti_travels[batch_i].append(total_route_distance)
        if batch_i == return_batch_i and pomo_i ==  return_pomo_i:
            # print(f"Plotting POMO Result {batch_i} {pomo_i}") 
            return_gps = 0 # loc_gps_xy
            return_pomo_loc_idx = 0 # loc_idx
            return_pomo_loc_length = 0 # loc_length
            return_pomo_tsp_idx = 0 # pomo_tsp_idx
            return_opti_tsp_idx = 0 # opti_tsp_idx
            return_opti_loc_length = 0 # opti_loc_length
            return_opti_loc_idx = 0 # opti_loc_idx

    return opti_travels, loc_xy, return_pomo_loc_idx, return_pomo_tsp_idx, return_pomo_loc_length, \
        return_opti_loc_idx, worker_locs, worker_locs_i


def run_single_vroom_nns(tester,return_batch_i, return_pomo_i):
    # num_slots = tester.env_params["worker_size"]
    num_batchs = tester.trainer_params["train_batch_size"]
    opti_travels = [[] for i in range(num_batchs)]
    opti_nns_travels = [[] for i in range(num_batchs)]
    opti_model = vroom.Input()

    return_gps, return_pomo_loc_idx, return_pomo_tsp_idx, return_opti_tsp_idx = None, None, None, None
    return_opti_loc_idx = None
    for batch_i in range(num_batchs):
        # for pomo_i in range(tester.env_params["pomo_size"]): 
        # Only once since all Locs are same.
        pomo_i = return_pomo_i
        # sub_jobs, loc_xy,loc_gps_xy, loc_idx, pomo_tsp_idx, dist_matrix, loc_length = \
        #     extract_n_transform_vrp_sub_jobs(tester, batch_i, pomo_i, num_slots=num_slots)
        dist_matrix = tester.env.dist_matrix[batch_i].cpu().numpy()
        loc_xy = tester.env.step_state.reset_state.loc_xy[0].cpu().numpy()

        worker_loc_idx = tester.env.step_state.reset_state.worker_loc_idx[batch_i,pomo_i].cpu().tolist()
        job_loc_idx = tester.env.step_state.reset_state.job_loc_idx[batch_i,pomo_i].cpu().tolist()

        dist_mat = (dist_matrix*1000).astype(int).tolist()
        # print(f"distance matrix statistics: (max = {dist_matrix.max()}, min = {dist_matrix.min()}, sum = {round(dist_matrix.sum(),2)}, mean = {round(dist_matrix.mean(),2)}, median = {round(np.median(dist_matrix),2)})")
        opti_model.set_durations_matrix(
            profile="car",
            matrix_input=dist_mat,
        )
        # print(decode_solution(tester.env.step_state.solution[0].tolist(), tester.env.step_state.reset_state.worker_loc_idx.size(2)))
        vehicle_list=[]
        shipment_list = [ ]
        for ji,j in enumerate(worker_loc_idx):
            vehicle_list.append(vroom.Vehicle(
                id=worker_loc_idx[ji], 
                start=worker_loc_idx[ji], # ji == j
                # end=return_idx, # if end is omitted, the resulting route will stop at the last visited task, whose choice is determined by the optimization process
                # skills = {si}, #  self.worker_code2index[s.worker_code]
                # capacity=vehicle_capacity,
                max_tasks=8,
                # time_window=[in_day_start, in_day_end]
            ))
        opti_model.add_vehicle(vehicle_list)
        for ji,j_idx in enumerate(job_loc_idx):  
            opti_model.add_job(vroom.Job(
                id=job_loc_idx[ji], location=job_loc_idx[ji],
                service=1, 
            ))

        solution = opti_model.solve(exploration_level=5, nb_threads=6)
        # print(f"VRoom Dispatching result: solution.summary.cost = {solution.summary.cost}, violations = {solution.summary.violations._types}, waiting_time = {solution.summary.waiting_time}, unassigned = {solution.summary.unassigned}") 


        if solution is None:
            # print(f"Solution failed on opti on batch_i.pomo_i = {batch_i}.{pomo_i}")
            raise ValueError(f"Solution failed on vroom on batch_i.pomo_i = {batch_i}.{pomo_i}")
            opti_travels[batch_i].append(999555)
            continue

        total_route_distance, opti_tsp_idx, worker_locs, worker_locs_i = decode_vroom_vrp_plan(
            solution = solution, 
            # sub_jobs = sub_jobs,
            vehicle_list = vehicle_list, 
            dist_matrix = dist_matrix, # tester.env.dist_matrix[batch_i]
            loc_xy = loc_xy,
        )
        opti_travels[batch_i].append(total_route_distance)

        worker_job_size = tester.env.step_state.worker_job_size # one reserved for incoming job
        solution_list = [worker_job_size for _ in range(worker_job_size+1)]
        solution_pre_list = list(range(worker_job_size+1))
        loc2slot_idx_list = [
            -1 for _ in range(worker_job_size)
        ]
        worker_loc_lengths = [
            1
            for _ in  range(len(vehicle_list))
        ]
        for vehicle_id in range(len(vehicle_list)):
            # First one (previous_index) should be depot 
            slot_prev_i = vehicle_id
            # Start from second job 

            for index, job_row in solution.routes[solution.routes["vehicle_id"] == vehicle_id].iterrows():
                if index < 1: # == "start":
                    slot_prev_i = job_row.location_index
                    continue
                worker_loc_lengths[vehicle_id] += 1
                slot_curr_i = job_row.location_index
                solution_list[slot_prev_i] = slot_curr_i
                solution_pre_list[slot_curr_i] = slot_prev_i
                loc2slot_idx_list[slot_prev_i] = vehicle_id
                loc2slot_idx_list[slot_curr_i] = vehicle_id

                slot_prev_i = slot_curr_i

        # The same jobs are still there.
        # tester.env.load_jobs(
        #     loc_xy = loc_xy[None,:,:],
        #     dist_matrix= torch.tensor(dist_mat_np)[None,:,:],
        #     worker_loc_idx = torch.tensor(worker_locs)[None,None,:],
        #     job_loc_idx = torch.tensor(job_locs )[None,None,:],
        # )
        step_state, reward, done = tester.env.set_state_to_length(
            worker_loc_length = torch.tensor(worker_loc_lengths)[None,:],
            solution = torch.tensor(solution_list)[None,:],
            solution_pre_idx = torch.tensor(solution_pre_list)[None,:],
            solution_worker_idx = torch.tensor(loc2slot_idx_list)[None,:],
            job2slot_current_job_i = 0,
            max_job_in_worker_size = tester.env.step_state.max_job_in_worker_size,
            job2slot_n2s_step = 1
        )

        max_swap_count = 6500
        step_state.max_n2s_swap_step_count = max_swap_count # 65

        done = False
        for _ in range(max_swap_count+20): 
            selected, prob, _probs = tester.model(step_state)
            # shape: (batch, pomo)
            step_state, reward, done = tester.env.step(selected)
            if done:
                break

        worker_locs, worker_locs_i = None,None

        total_route_distance = 0 - reward.float().mean()  
            
        opti_nns_travels[batch_i].append(total_route_distance)
        if batch_i == return_batch_i and pomo_i ==  return_pomo_i:
            # print(f"Plotting POMO Result {batch_i} {pomo_i}") 
            return_gps = 0 # loc_gps_xy
            return_pomo_loc_idx = 0 # loc_idx
            return_pomo_loc_length = 0 # loc_length
            return_pomo_tsp_idx = 0 # pomo_tsp_idx
            return_opti_tsp_idx = 0 # opti_tsp_idx
            return_opti_loc_length = 0 # opti_loc_length
            return_opti_loc_idx = 0 # opti_loc_idx

    return opti_travels, loc_xy, opti_nns_travels, return_pomo_tsp_idx, return_pomo_loc_length, \
        return_opti_loc_idx, worker_locs, worker_locs_i


##########################################################################################
# main

def main(): 

    create_logger(**logger_params)  
    logger = getLogger(name='tester')


    # trainer_params.update({'osrm_url': ("http://192.168.9.251:5001","http://127.0.0.1:5001")})
    # http://192.168.9.251:5001 

    env_params.update({
        # 'job_size': 24 ,  # 32， 42,  
        # 'worker_size': 1,  # 6， 8, 
        'pomo_size': 1,  # 8, 64 # When training TSP_pick_drop, pomo_size == worker_size == 8.
        'problem_size': 20  + 1,  # 50, 20, 11,   33
    }) 
    model_params['model_load'] = True
    model_params["eval_type"] ="softmax" # 'argmax'
    # model_params["job2slot_model_path"] = "/home/dispatch/easydispatch/result/20220527_045521_train_job2slot_w8_j42/checkpoint-180.pt"
    # model_params["job2slot_model_path"] = "/home/dispatch/easydispatch/result/20220527_045521_train_job2slot_w8_j42/checkpoint-1920.pt"
    

    # model_params["job2slot_model_path"] = "/home/dispatch/easydispatch/result/20220608_175403_pick_drop_job2slot/checkpoint_80.pt"
    # model_params["job2slot_model_path"] = "/home/dispatch/easydispatch/result/20220608_175403_pick_drop_job2slot/checkpoint_4060.pt" 


    # model_params["job2slot_model_path"] = "/home/dispatch/easydispatch/result/20220622_195939_pick_drop_job2slot/checkpoint_680.pt" 
    # From first round, 680 is better than 900, about 1.16 vs 1.30
    # model_params["job2slot_model_path"] = "/home/dispatch/easydispatch/result/20220624_173557_pick_drop_job2slot/checkpoint_1800.pt" 
    # Second round, after performance boost -- 15 loops, 
    # checkpoint_600: Total Difference POMO vs Ortools: 1.0921,  1.2407,  1.1498
    # checkpoint_1800: after fixing job_length of ortools to limit < 10, 1.0957, 1.1993, 1.1235, 1.0649 --  1.1252 1.1494, WHY? 1800 is the best?
    # checkpoint_2300, 1.6574
    # checkpoint_2750:  1.4833  1.5221 1.3012



    # model_params["job2slot_model_path"] = "/home/dispatch/easydispatch/result/20220626_021204_pick_drop_job2slot/checkpoint_1920.pt" 
    # In 24,700 rows full dataset:
    # old: 1800: 1.1069  1.1411
    # new: 1020: 1.0891 1.0394 1.1412 0.9927
    # model_params["job2slot_model_path"] = "/data/easydispatch/etc/trained_models/pomo/pickdrop_job2slot_osrm_ganzhou/20220626_021204_pick_drop_job2slot_checkpoint_1920.pt" 
    # New, after fixing ortools distance, 1920: 1.0286 1.0302 1.0349 1.0414 1.0908 0.9751 1.0115
    # 2022-06-27 16:03:36 不明白为什么1920这个模型结果最好，有什么特征呢？也许是到后面的learning rate太大，容易横跳？
    
    # Those 2 are trained on 32 workers, about 1.4 times ORTOOLS
    # model_params["job2slot_model_path"] = "/home/dispatch/easydispatch/result/20220627_043705_pick_drop_job2slot/checkpoint_4750.pt" 
    # model_params["job2slot_model_path"] = "/home/dispatch/easydispatch/result/20220629_000842_pick_drop_job2slot/checkpoint_165.pt" 

    # Trained on 16 workers.
    # model_params["job2slot_model_path"] = "/home/dispatch/easydispatch/result/20220629_160208_pick_drop_job2slot/checkpoint_420.pt"  
    # model_params["job2slot_model_path"] = "/home/dispatch/easydispatch/result/20220629_160208_pick_drop_job2slot/checkpoint_705.pt"  
    # model_params["job2slot_model_path"] = "/data/easydispatch/etc/trained_models/pomo/pickdrop_osrm/20220629_160208_pick_drop_job2slot_checkpoint_755.pt"  
    # model_params["job2slot_model_path"] = "/home/dispatch/easydispatch/result/20220629_160208_pick_drop_job2slot/checkpoint_1035.pt"  
    # 32 workers: 1.2811, 1.2744,  1.2571 , 1.3025=100 (420) vs  1.3139, 1.2686 (705) vs  1.3216,  1.2964, 1.2816=100 (755) vs 1.2563,1.3356 (1035)  pomo avg_score = 1302.9512, ortools = 964.1941656516865, pct diff 1.3513, loop 8
    # 18 workers: 1.1567, 1.2011 (420)  vs 1.1288 vs  1.133, 1.1674 (1035)  pomo avg_score = 808.2075, ortools = 691.7508289897814, pct diff 1.1684, loop 20
    # 8 workers: 1.0229, 1.0981, 1.0264 (420) vs 1.0569  vs  1.0007, 0.9867,  1.0881, 1.0536 (1035) pomo avg_score = 412.1393, ortools = 413.5951641201973, pct diff 0.9965, loop 3
    # model_params["job2slot_model_path"] = "/home/dispatch/easydispatch/result/20220629_160208_pick_drop_job2slot/checkpoint_395.pt" 
    

    # 2022-07-04 20:17:44 start of online testing.
    # model_params["job2slot_model_path"] = "/data/easydispatch/etc/trained_models/pomo/training_logs/result/20220702_232239_pick_drop_job2slot/checkpoint_390.pt"  
    # model_params["job2slot_model_path"] = "/data/easydispatch/etc/trained_models/pomo/pickdrop_online_osrm_ganzhou/20220702_232239_pick_drop_job2slot_online_osrm_checkpoint_965.pt"  

    # 16 workers (epoch 390):  1.1634, 1.1696 (110 loops) 
    # 8 workers (epoch 390):  1.0309,  1.0542 (100 loops) 
    # 16 workers (epoch 535):  1.1626 (100 loops) 
    # 8 workers (epoch 535):  1.0438, 1.0613 (100 loops) 
    # 16 workers (epoch 965):  1.1549, 1.1409 (100 loops) 
    # 8 workers (epoch 965):  1.0617 (100 loops) 

    # testing online, 0711 result
    # model_params["job2slot_model_path"] = "/data/easydispatch/etc/trained_models/pomo/training_logs/result/20220711_231810_online_pick_drop_job2slot/checkpoint_1465.pt"  
    # 16 workers (epoch 500):  1.1354, 1.1496 (100 loops) 
    # 8 workers (epoch 500):  1.0444 (100 loops) 
    # 16 workers (epoch 545): 1.1608,  1.1642  (100 loops) 

    # 16 workers (epoch 790):, 1.1397 1.1698

    # 16 workers (epoch 845):, 1.1386
    # 16 workers (epoch 925):,  1.1432   1.1411

    # 
    # 2022-11-22 01:53:03 Use new singapore job2slot model
    # model_params["job2slot_model_path"] =  '/data/easydispatch/project/5gmax/trained_models/20221012_141254_online_job2slot_score_669_checkpoint_1960.pt'
    # dataset_name =  singapore 
    # 16 workers (epoch 1225), 1.1398, 1.163,  1.1357
    # 16 workers (epoch checkpoint_1465), 200 loops, 1.1304, 
    # --- '147 loops, Total POMO vs Ortools: 1.1306, min: 0.8539, max: 1.3406
    # ---   89 loops, Total POMO vs Ortools: 1.0949, min: 0.8527, max: 1.3226
    # 8 workers (epoch checkpoint_1465), 48 loops, Total POMO vs Ortools: 1.0359, min: 0.718, max: 1.2543


    # 2022-12-28 09:21:45 Testing new 
    # model_params["job2slot_model_path"] =  f"{data_basedir}/etc/trained_models/pomo/pickdrop_setagaya/20221226_181231_online_pick_drop_job2slot_checkpoint_1000_score_146.pt"
    # [2022-12-28 13:45:37] job2slot_input_data_tester.py(640) : worker 8, pomo avg_score = 181.2281, ortools = 234.91032767295837, pct diff 0.7715, loop 62
    # [2022-12-28 13:45:38] job2slot_input_data_tester.py(640) : worker 8, pomo avg_score = 184.9921, ortools = 270.47742462158203, pct diff 0.6839, loop 63
    # [2022-12-28 13:45:41] job2slot_input_data_tester.py(640) : worker 8, pomo avg_score = 136.1214, ortools = 249.0293647646904, pct diff 0.5466, loop 64
    # [2022-12-28 13:45:41] job2slot_input_data_tester.py(647) : 64 loops, Total POMO vs Ortools: 0.6129, min: 0.4411, max: 0.7939


    # 2023-01-07 17:05:51 Pruebado modelo de dimension 4, como long/lat/tiempo/recoger_dejar
    # model_params["job2slot_model_path"] =  f"{data_basedir}/result/20230107_060832_pickdrop_job2slot_tsp_2in1/checkpoint_260.pt"
    # dataset_name ='setagaya_double' #  "ganzhou", setagaya , singapore, london, setagaya_double
    # [2023-01-07 17:49:22] job2slot_input_data_tester.py(657) : Ortools Failed and skipped loop 1
    # [2023-01-07 17:49:25] job2slot_input_data_tester.py(664) : worker 8, pomo avg_score = 105.5537, ortools = 239.17492735385895, pct diff 0.4413, loop 2
    # [2023-01-07 17:49:26] job2slot_input_data_tester.py(657) : Ortools Failed and skipped loop 3
    # [2023-01-07 17:49:32] job2slot_input_data_tester.py(664) : worker 8, pomo avg_score = 111.92, ortools = 249.12156662344933, pct diff 0.4493, loop 4
    # [2023-01-07 17:49:37] job2slot_input_data_tester.py(664) : worker 8, pomo avg_score = 96.7077, ortools = 219.61888372898102, pct diff 0.4403, loop 5
    # [2023-01-07 17:49:42] job2slot_input_data_tester.py(664) : worker 8, pomo avg_score = 97.9507, ortools = 285.46542513370514, pct diff 0.3431, loop 6
    # [2023-01-07 17:49:46] job2slot_input_data_tester.py(664) : worker 8, pomo avg_score = 122.6984, ortools = 266.68234879663214, pct diff 0.4601, loop 7
    # [2023-01-07 17:49:48] job2slot_input_data_tester.py(664) : worker 8, pomo avg_score = 102.2629, ortools = 257.77107563614845, pct diff 0.3967, loop 8
    # [2023-01-07 17:49:48] job2slot_input_data_tester.py(671) : 6 loops, Total POMO vs Ortools: 0.4197, min: 0.3431, max: 0.4601

    # model_params["job2slot_model_path"] =  f"{data_basedir}/result/20230619_200550_tsp_checkpoint_320_score1105.pt"
    # This one was trained on 128 jobs. I will try less jobs.
    # [2023-06-20 14:33:08] job2slot_input_data_tester.py(706) : worker 1, pomo avg_score = 614.0259, ortools = 254.67984008789062, pct diff 2.411, loop 4
    # [2023-06-20 14:33:10] job2slot_input_data_tester.py(706) : worker 1, pomo avg_score = 827.8119, ortools = 314.4777526855469, pct diff 2.6323, loop 5
    # [2023-06-20 14:33:11] job2slot_input_data_tester.py(706) : worker 1, pomo avg_score = 741.6151, ortools = 367.82476806640625, pct diff 2.0162, loop 6
    # [2023-06-20 14:33:12] job2slot_input_data_tester.py(706) : worker 1, pomo avg_score = 552.928, ortools = 238.01768493652344, pct diff 2.3231, loop 7
    # [2023-06-20 14:33:13] job2slot_input_data_tester.py(706) : worker 1, pomo avg_score = 550.3663, ortools = 308.391845703125, pct diff 1.7846, loop 8
    # [2023-06-20 14:33:13] job2slot_input_data_tester.py(713) : 8 loops, Total POMO vs Ortools: 2.1315, min: 1.7375, max: 2.6323

    # model_params["job2slot_model_path"] =  f"{data_basedir}/result/20230622_004555_tsp_checkpoint_30_score549.pt"
    # This one was trained on 24 jobs. at episode 30
    # [2023-06-22 18:18:49] job2slot_input_data_tester.py(725) : worker 1, pomo avg_score = 438.334, ortools = 389.04486083984375, pct diff 1.1267, loop 3
    # [2023-06-22 18:18:51] job2slot_input_data_tester.py(725) : worker 1, pomo avg_score = 413.2662, ortools = 392.06976318359375, pct diff 1.0541, loop 4
    # [2023-06-22 18:18:52] job2slot_input_data_tester.py(725) : worker 1, pomo avg_score = 456.7982, ortools = 454.0931091308594, pct diff 1.006, loop 5
    # [2023-06-22 18:18:53] job2slot_input_data_tester.py(725) : worker 1, pomo avg_score = 443.2179, ortools = 413.67193603515625, pct diff 1.0714, loop 6
    # [2023-06-22 18:18:53] job2slot_input_data_tester.py(725) : worker 1, pomo avg_score = 374.8273, ortools = 294.1203308105469, pct diff 1.2744, loop 7
    # [2023-06-22 18:18:54] job2slot_input_data_tester.py(725) : worker 1, pomo avg_score = 405.0186, ortools = 375.8035888671875, pct diff 1.0777, loop 8
    # [2023-06-22 18:18:54] job2slot_input_data_tester.py(732) : 8 loops, Total POMO vs Ortools: 1.0931, min: 1.006, max: 1.2744
    # model_params["job2slot_model_path"] =  f"{data_basedir}/result/20230623_055633_tsp_checkpoint_1730_score234.pt" # result/20230622_004555_tsp_checkpoint_420_score534.pt"

    # This one was trained on 24 jobs. at episode 420， changed training to non roundtrip, duration.
    # [2023-06-25 02:01:17] job2slot_input_data_tester.py(765) : worker 1, pomo avg_score = 164.5217, osrm = 180.72999572753906, ortools = 170.5900115966797, pomo pct 0.9644, osrm pct 1.0594, loop 11
    # [2023-06-25 02:01:19] job2slot_input_data_tester.py(765) : worker 1, pomo avg_score = 174.555, osrm = 181.36000061035156, ortools = 178.2783203125, pomo pct 0.9791, osrm pct 1.0173, loop 12
    # [2023-06-25 02:01:21] job2slot_input_data_tester.py(765) : worker 1, pomo avg_score = 147.58, osrm = 134.77999877929688, ortools = 134.9350128173828, pomo pct 1.0937, osrm pct 0.9989, loop 13
    # [2023-06-25 02:01:30] job2slot_input_data_tester.py(765) : worker 1, pomo avg_score = 163.055, osrm = 181.74000549316406, ortools = 178.79000854492188, pomo pct 0.912, osrm pct 1.0165, loop 14
    # [2023-06-25 02:01:31] job2slot_input_data_tester.py(765) : worker 1, pomo avg_score = 149.5217, osrm = 164.38999938964844, ortools = 151.34832763671875, pomo pct 0.9879, osrm pct 1.0862, loop 15
    # [2023-06-25 02:01:33] job2slot_input_data_tester.py(765) : worker 1, pomo avg_score = 142.2183, osrm = 137.7899932861328, ortools = 138.57666015625, pomo pct 1.0263, osrm pct 0.9943, loop 16
    # [2023-06-25 02:01:36] job2slot_input_data_tester.py(765) : worker 1, pomo avg_score = 162.4183, osrm = 166.39999389648438, ortools = 164.66000366210938, pomo pct 0.9864, osrm pct 1.0106, loop 17
    # [2023-06-25 02:01:38] job2slot_input_data_tester.py(765) : worker 1, pomo avg_score = 169.7283, osrm = 180.8800048828125, ortools = 166.83834838867188, pomo pct 1.0173, osrm pct 1.0842, loop 18
    # [2023-06-25 02:01:38] job2slot_input_data_tester.py(773) : 18 loops, Total POMO vs Ortools: 0.9892, min: 0.912, max: 1.0937


    # model_params['job2slot_model_path'] = f"{data_basedir}/etc/trained_models/pomon2s/enu/20230908_045421_pickdrop_job2slot_tsp_2in1_checkpoint_3340_score6.pt"
    # [2023-09-09 21:29:53] job2slot_input_data_tester.py(883) : worker 4, pomo avg_score = 6.7422, osrm = 0, ortools = 6.184614825993776, pomo pct 1.0902, osrm pct 0.0, loop 1
    # [2023-09-09 21:29:53] job2slot_input_data_tester.py(883) : worker 4, pomo avg_score = 6.7793, osrm = 0, ortools = 5.582228947430849, pomo pct 1.2144, osrm pct 0.0, loop 2
    # [2023-09-09 21:29:53] job2slot_input_data_tester.py(883) : worker 4, pomo avg_score = 6.5026, osrm = 0, ortools = 6.369740083813667, pomo pct 1.0209, osrm pct 0.0, loop 3
    # [2023-09-09 21:29:53] job2slot_input_data_tester.py(891) : 3 loops, Total POMO vs Ortools: 1.1041, min: 1.0209, max: 1.2144

    # model_params['job2slot_model_path'] = f"{data_basedir}/etc/trained_models/pomon2s/enu/20230906_034936_pickdrop_pomo_n2s_checkpoint_1970_score6.pt"
    # [2023-09-09 21:58:03] job2slot_input_data_tester.py(892) : worker 4, pomo avg_score = 5.5146, osrm = 0, ortools = 5.193577937781811, pomo pct 1.0618, osrm pct 0.0, loop 1
    # [2023-09-09 21:58:04] job2slot_input_data_tester.py(892) : worker 4, pomo avg_score = 5.1655, osrm = 0, ortools = 5.925066381692886, pomo pct 0.8718, osrm pct 0.0, loop 2
    # [2023-09-09 21:58:04] job2slot_input_data_tester.py(892) : worker 4, pomo avg_score = 5.2366, osrm = 0, ortools = 5.36172092705965, pomo pct 0.9767, osrm pct 0.0, loop 3
    # [2023-09-09 21:58:04] job2slot_input_data_tester.py(892) : worker 4, pomo avg_score = 6.2514, osrm = 0, ortools = 6.080911595374346, pomo pct 1.028, osrm pct 0.0, loop 4
    # [2023-09-09 21:58:04] job2slot_input_data_tester.py(892) : worker 4, pomo avg_score = 5.6173, osrm = 0, ortools = 5.409230932593346, pomo pct 1.0385, osrm pct 0.0, loop 5
    # [2023-09-09 21:58:04] job2slot_input_data_tester.py(900) : 5 loops, Total POMO vs Ortools: 0.9934, min: 0.8718, max: 1.0618

    # [2023-10-22 22:11:03] job2slot_input_data_tester.py(898) : worker 4, pomo avg_score = 6.3231, osrm = 0, ortools = 6.513617247343063, pomo pct 0.9708, osrm pct 0.0, loop 28
    # [2023-10-22 22:11:04] job2slot_input_data_tester.py(898) : worker 4, pomo avg_score = 5.3753, osrm = 0, ortools = 4.877586379647255, pomo pct 1.102, osrm pct 0.0, loop 29
    # [2023-10-22 22:11:06] job2slot_input_data_tester.py(898) : worker 4, pomo avg_score = 6.4264, osrm = 0, ortools = 6.068095374852419, pomo pct 1.059, osrm pct 0.0, loop 30
    # [2023-10-22 22:11:08] job2slot_input_data_tester.py(898) : worker 4, pomo avg_score = 4.1499, osrm = 0, ortools = 4.407510485500097, pomo pct 0.9416, osrm pct 0.0, loop 31
    # [2023-10-22 22:11:10] job2slot_input_data_tester.py(898) : worker 4, pomo avg_score = 6.229, osrm = 0, ortools = 5.960803704336286, pomo pct 1.045, osrm pct 0.0, loop 32
    # [2023-10-22 22:11:30] job2slot_input_data_tester.py(898) : worker 4, pomo avg_score = 4.7609, osrm = 0, ortools = 4.861688565462828, pomo pct 0.9793, osrm pct 0.0, loop 33
    # [2023-10-22 22:11:30] job2slot_input_data_tester.py(906) : 33 loops, Total POMO vs vroom: 1.0779, min: 0.9254, max: 1.4454

    # model_params['job2slot_model_path'] = f"{data_basedir}/result/20230908_144215_pickdrop_pomo_n2s_checkpoint_12330_score5.pt"
    # model_params['job2slot_model_path'] = "/home/dispatch/git/trained_models/ed_model/pomo_n2s/enu/20230908_144215_pickdrop_pomo_n2s_checkpoint_11770_score5.pt"

    # [2023-10-22 22:14:46] job2slot_input_data_tester.py(908) : worker 4, pomo avg_score = 4.9032, osrm = 0, ortools = 4.5855458825826645, pomo pct 1.0693, osrm pct 0.0, loop 8
    # [2023-10-22 22:14:47] job2slot_input_data_tester.py(908) : worker 4, pomo avg_score = 5.8419, osrm = 0, ortools = 5.778708264231682, pomo pct 1.0109, osrm pct 0.0, loop 9
    # [2023-10-22 22:14:49] job2slot_input_data_tester.py(908) : worker 4, pomo avg_score = 7.0884, osrm = 0, ortools = 6.1753690131008625, pomo pct 1.1479, osrm pct 0.0, loop 10
    # [2023-10-22 22:14:49] job2slot_input_data_tester.py(916) : 10 loops, Total POMO vs vroom: 1.1203, min: 0.992, max: 1.3416



    # model_params['job2slot_model_path'] = "/home/dispatch/git/trained_models/ed_model/pomo_n2s/enu/20231128_001759_single_job2slot_n2s_checkpoint_800_score3_76.pt"
    # [2023-12-18 20:30:59] job2slot_input_data_tester.py(1164) : worker 4, pomo avg_score = 4.0257, osrm = 0, optimizer_score = 3.1111, vroom_nns_score = 3.1111, pomo pct 1.294, osrm pct 0.0,  vroom_nns pct 1.0, loop 60
    # [2023-12-18 20:30:59] job2slot_input_data_tester.py(1164) : worker 4, pomo avg_score = 3.7736, osrm = 0, optimizer_score = 3.108, vroom_nns_score = 3.108, pomo pct 1.2142, osrm pct 0.0,  vroom_nns pct 1.0, loop 61
    # [2023-12-18 20:30:59] job2slot_input_data_tester.py(1164) : worker 4, pomo avg_score = 3.5662, osrm = 0, optimizer_score = 2.6845, vroom_nns_score = 2.6845, pomo pct 1.3284, osrm pct 0.0,  vroom_nns pct 1.0, loop 62
    # [2023-12-18 20:30:59] job2slot_input_data_tester.py(1164) : worker 4, pomo avg_score = 3.8551, osrm = 0, optimizer_score = 3.2198, vroom_nns_score = 3.2198, pomo pct 1.1973, osrm pct 0.0,  vroom_nns pct 1.0, loop 63
    # [2023-12-18 20:31:00] job2slot_input_data_tester.py(1164) : worker 4, pomo avg_score = 3.0506, osrm = 0, optimizer_score = 2.8449, vroom_nns_score = 2.7983, pomo pct 1.0723, osrm pct 0.0,  vroom_nns pct 0.9836, loop 64
    # [2023-12-18 20:31:00] job2slot_input_data_tester.py(1173) : 64 loops, average pomo_n2s vs vroom: 1.1533, min: 0.9968, max: 1.3547
    # [2023-12-18 20:31:00] job2slot_input_data_tester.py(1175) : 64 loops, average vroom+pomo_n2s vs vroom: 0.998, min: 0.9398, max: 1.0

    # model_params['job2slot_model_path'] = "/home/dispatch/git/trained_models/ed_model/single/pomo_n2s/20231217_032508_single_job2slot_n2s_checkpoint_1570_score3_25_allow_changing_worker.pt"
    # 10 swaps
    # [2023-12-18 20:51:02] job2slot_input_data_tester.py(1173) : worker 4, pomo avg_score = 3.1663, osrm = 0, optimizer_score = 2.9617, vroom_nns_score = 2.9617, pomo pct 1.0691, osrm pct 0.0,  vroom_nns pct 1.0, loop 61
    # [2023-12-18 20:51:02] job2slot_input_data_tester.py(1173) : worker 4, pomo avg_score = 3.6386, osrm = 0, optimizer_score = 2.9916, vroom_nns_score = 2.9916, pomo pct 1.2163, osrm pct 0.0,  vroom_nns pct 1.0, loop 62
    # [2023-12-18 20:51:03] job2slot_input_data_tester.py(1173) : worker 4, pomo avg_score = 3.9612, osrm = 0, optimizer_score = 3.2163, vroom_nns_score = 3.1786, pomo pct 1.2316, osrm pct 0.0,  vroom_nns pct 0.9883, loop 63
    # [2023-12-18 20:51:03] job2slot_input_data_tester.py(1173) : worker 4, pomo avg_score = 3.2647, osrm = 0, optimizer_score = 3.0143, vroom_nns_score = 3.0143, pomo pct 1.0831, osrm pct 0.0,  vroom_nns pct 1.0, loop 64
    # [2023-12-18 20:51:03] job2slot_input_data_tester.py(1182) : 64 loops, average pomo_n2s vs vroom: 1.1028, min: 0.8938, max: 1.3735
    # [2023-12-18 20:51:03] job2slot_input_data_tester.py(1184) : 64 loops, average vroom+pomo_n2s vs vroom: 0.9971, min: 0.9594, max: 1.0
    # 65 swaps, 2023-12-19 00:14:48
    # [2023-12-18 20:58:13] job2slot_input_data_tester.py(1178) : worker 4, pomo avg_score = 3.0866, osrm = 0, optimizer_score = 2.669, vroom_nns_score = 2.669, pomo pct 1.1565, osrm pct 0.0,  vroom_nns pct 1.0, loop 61
    # [2023-12-18 20:58:14] job2slot_input_data_tester.py(1178) : worker 4, pomo avg_score = 3.0148, osrm = 0, optimizer_score = 3.0323, vroom_nns_score = 3.0323, pomo pct 0.9942, osrm pct 0.0,  vroom_nns pct 1.0, loop 62
    # [2023-12-18 20:58:15] job2slot_input_data_tester.py(1178) : worker 4, pomo avg_score = 3.4344, osrm = 0, optimizer_score = 3.3645, vroom_nns_score = 3.1569, pomo pct 1.0208, osrm pct 0.0,  vroom_nns pct 0.9383, loop 63
    # [2023-12-18 20:58:15] job2slot_input_data_tester.py(1178) : worker 4, pomo avg_score = 3.5621, osrm = 0, optimizer_score = 3.1528, vroom_nns_score = 3.1528, pomo pct 1.1298, osrm pct 0.0,  vroom_nns pct 1.0, loop 64
    # [2023-12-18 20:58:15] job2slot_input_data_tester.py(1187) : 64 loops, average pomo_n2s vs vroom: 1.0424, min: 0.9112, max: 1.2632
    # [2023-12-18 20:58:15] job2slot_input_data_tester.py(1189) : 64 loops, average vroom+pomo_n2s vs vroom: 0.991, min: 0.908, max: 1.0

    model_params['job2slot_model_path'] = "/home/dispatch/git/trained_models/ed_model/single/pomo_n2s/20231217_032508_single_job2slot_n2s_checkpoint_3190_score3_17.pt" # also allows changing worker.
    # [2023-12-22 10:46:45] job2slot_input_data_tester.py(1186) : worker 4, pomo avg_score = 2.7383, osrm = 0, optimizer_score = 2.8481, vroom_nns_score = 2.7278, pomo pct 0.9615, osrm pct 0.0,  vroom_nns pct 0.9578, loop 12
    # [2023-12-22 10:46:46] job2slot_input_data_tester.py(1186) : worker 4, pomo avg_score = 3.1156, osrm = 0, optimizer_score = 2.9675, vroom_nns_score = 2.9675, pomo pct 1.0499, osrm pct 0.0,  vroom_nns pct 1.0, loop 13
    # [2023-12-22 10:46:46] job2slot_input_data_tester.py(1186) : worker 4, pomo avg_score = 3.3279, osrm = 0, optimizer_score = 2.9946, vroom_nns_score = 2.7625, pomo pct 1.1113, osrm pct 0.0,  vroom_nns pct 0.9225, loop 14
    # [2023-12-22 10:46:46] job2slot_input_data_tester.py(1186) : worker 4, pomo avg_score = 2.5945, osrm = 0, optimizer_score = 2.5642, vroom_nns_score = 2.5642, pomo pct 1.0118, osrm pct 0.0,  vroom_nns pct 1.0, loop 15
    # [2023-12-22 10:46:47] job2slot_input_data_tester.py(1186) : worker 4, pomo avg_score = 3.0058, osrm = 0, optimizer_score = 2.7401, vroom_nns_score = 2.7401, pomo pct 1.097, osrm pct 0.0,  vroom_nns pct 1.0, loop 16
    # [2023-12-22 10:46:47] job2slot_input_data_tester.py(1195) : 16 loops, average pomo_n2s vs vroom: 1.0509, min: 0.958, max: 1.1113
    # [2023-12-22 10:46:47] job2slot_input_data_tester.py(1197) : 16 loops, average vroom+pomo_n2s vs vroom: 0.9864, min: 0.9225, max: 1.0

    #  2023-12-25 17:39:37， 用20job训练的模型在40个job的测试上，效果很不好。重新回到1，完全没有提升。
    # [2023-12-25 17:23:42] job2slot_input_data_tester.py(1192) : worker 8, pomo avg_score = 5.0711, osrm = 0, optimizer_score = 4.1695, vroom_nns_score = 4.1695, pomo pct 1.2163, osrm pct 0.0,  vroom_nns pct 1.0, loop 20
    # [2023-12-25 17:23:42] job2slot_input_data_tester.py(1192) : worker 8, pomo avg_score = 5.3275, osrm = 0, optimizer_score = 3.8313, vroom_nns_score = 3.8312, pomo pct 1.3905, osrm pct 0.0,  vroom_nns pct 1.0, loop 21
    # [2023-12-25 17:23:43] job2slot_input_data_tester.py(1192) : worker 8, pomo avg_score = 4.9426, osrm = 0, optimizer_score = 4.109, vroom_nns_score = 4.1089, pomo pct 1.2029, osrm pct 0.0,  vroom_nns pct 1.0, loop 22
    # [2023-12-25 17:23:44] job2slot_input_data_tester.py(1192) : worker 8, pomo avg_score = 4.6312, osrm = 0, optimizer_score = 3.7574, vroom_nns_score = 3.7574, pomo pct 1.2326, osrm pct 0.0,  vroom_nns pct 1.0, loop 23
    # [2023-12-25 17:23:45] job2slot_input_data_tester.py(1192) : worker 8, pomo avg_score = 5.0802, osrm = 0, optimizer_score = 4.4042, vroom_nns_score = 4.4042, pomo pct 1.1535, osrm pct 0.0,  vroom_nns pct 1.0, loop 24
    # [2023-12-25 17:23:45] job2slot_input_data_tester.py(1201) : 24 loops, average pomo_n2s vs vroom: 1.2428, min: 1.1219, max: 1.4093
    # [2023-12-25 17:23:45] job2slot_input_data_tester.py(1203) : 24 loops, average vroom+pomo_n2s vs vroom: 1.0, min: 0.9999, max: 1.0


    # model_params['job2slot_model_path'] = "/home/dispatch/git/ed_web/result/20231223_013325_single_job2slot_n2s_checkpoint_2220_score4_84_8workers_40jobs.pt" # also allows changing worker.
    # 用40jobs训练的模型效果稍微好一点。
    # [2023-12-25 18:15:17] job2slot_input_data_tester.py(1205) : worker 8, pomo avg_score = 4.0944, osrm = 0, optimizer_score = 3.7158, vroom_nns_score = 3.7156, pomo pct 1.1019, osrm pct 0.0,  vroom_nns pct 1.0, loop 5
    # [2023-12-25 18:15:18] job2slot_input_data_tester.py(1205) : worker 8, pomo avg_score = 5.4582, osrm = 0, optimizer_score = 4.5128, vroom_nns_score = 4.5006, pomo pct 1.2095, osrm pct 0.0,  vroom_nns pct 0.9973, loop 6
    # [2023-12-25 18:15:18] job2slot_input_data_tester.py(1205) : worker 8, pomo avg_score = 4.2004, osrm = 0, optimizer_score = 3.9106, vroom_nns_score = 3.9104, pomo pct 1.0741, osrm pct 0.0,  vroom_nns pct 1.0, loop 7
    # [2023-12-25 18:15:19] job2slot_input_data_tester.py(1205) : worker 8, pomo avg_score = 5.6796, osrm = 0, optimizer_score = 4.1351, vroom_nns_score = 4.1349, pomo pct 1.3735, osrm pct 0.0,  vroom_nns pct 1.0, loop 8
    # [2023-12-25 18:15:19] job2slot_input_data_tester.py(1214) : 8 loops, average pomo_n2s vs vroom: 1.1879, min: 1.0741, max: 1.3735
    # [2023-12-25 18:15:19] job2slot_input_data_tester.py(1216) : 8 loops, average vroom+pomo_n2s vs vroom: 0.9996, min: 0.9973, max: 1.0

    model_params['job2slot_model_path'] = "/home/dispatch/git/trained_models/20231228_202954_single_job2slot_n2s_checkpoint_2120_score4_60_40jobs_8workers.pt" # also allows changing worker.
    # 用4*A10 4个显卡训练的40jobs 模型效果稍微好一点。但是还是达不到期望。
    # [2024-01-05 15:29:45] job2slot_input_data_tester.py(1265) : worker 8, pomo avg_score = 4.7361, osrm = 0, optimizer_score = 4.3002, vroom_nns_score = 4.2723, pomo pct 1.1014, osrm pct 0.0,  vroom_nns pct 0.9935, loop 1
    # [2024-01-05 15:29:46] job2slot_input_data_tester.py(1265) : worker 8, pomo avg_score = 4.5058, osrm = 0, optimizer_score = 3.9706, vroom_nns_score = 3.8025, pomo pct 1.1348, osrm pct 0.0,  vroom_nns pct 0.9577, loop 2
    # [2024-01-05 15:29:46] job2slot_input_data_tester.py(1265) : worker 8, pomo avg_score = 4.1818, osrm = 0, optimizer_score = 3.8314, vroom_nns_score = 3.8314, pomo pct 1.0915, osrm pct 0.0,  vroom_nns pct 1.0, loop 3
    # [2024-01-05 15:29:47] job2slot_input_data_tester.py(1265) : worker 8, pomo avg_score = 4.2201, osrm = 0, optimizer_score = 4.0122, vroom_nns_score = 4.0122, pomo pct 1.0518, osrm pct 0.0,  vroom_nns pct 1.0, loop 4
    # [2024-01-05 15:29:48] job2slot_input_data_tester.py(1265) : worker 8, pomo avg_score = 4.1159, osrm = 0, optimizer_score = 3.9381, vroom_nns_score = 3.9377, pomo pct 1.0452, osrm pct 0.0,  vroom_nns pct 0.9999, loop 5
    # [2024-01-05 15:29:49] job2slot_input_data_tester.py(1265) : worker 8, pomo avg_score = 4.1156, osrm = 0, optimizer_score = 3.9908, vroom_nns_score = 3.9908, pomo pct 1.0313, osrm pct 0.0,  vroom_nns pct 1.0, loop 6
    # [2024-01-05 15:29:49] job2slot_input_data_tester.py(1265) : worker 8, pomo avg_score = 4.5184, osrm = 0, optimizer_score = 4.2375, vroom_nns_score = 4.2375, pomo pct 1.0663, osrm pct 0.0,  vroom_nns pct 1.0, loop 7
    # [2024-01-05 15:29:50] job2slot_input_data_tester.py(1265) : worker 8, pomo avg_score = 4.158, osrm = 0, optimizer_score = 3.9973, vroom_nns_score = 3.9973, pomo pct 1.0402, osrm pct 0.0,  vroom_nns pct 1.0, loop 8
    # [2024-01-05 15:29:50] job2slot_input_data_tester.py(1274) : 8 loops, average pomo_n2s vs vroom: 1.0704, min: 1.0313, max: 1.1348
    # [2024-01-05 15:29:50] job2slot_input_data_tester.py(1276) : 8 loops, average vroom+pomo_n2s vs vroom: 0.9939, min: 0.9577, max: 1.0

    # Job2SlotInputDataTester
    tester = trainer = Job2SlotInputDataTester(
        env_params=env_params,
        model_params=model_params,
        optimizer_params=optimizer_params,
        trainer_params=trainer_params,
        gpu_id = 0)

    # trainer.run()

    logger.info(f"""tester started: 
        env_params={env_params},
        model_params={model_params}, 
        trainer_params={trainer_params}""")

    loop_i = 0
    pomo_scores = []
    ortools_scores = []
    osrm_scores = []
    vroom_nns_scores = []
    ## =====================================================================
    for batch in enumerate(trainer.dataloader):
        loop_i +=1
        if loop_i > trainer_params["train_episodes"]:
            break
        # loc_xy = torch.stack(
        #     [self.dataset[b_i][0] for b_i in batch_indices]
        # )
        # dist_matrix = torch.stack(
        #     [self.dataset[b_i][1] for b_i in batch_indices]
        # )
        loc_xy = batch[1][0].to(device).float()
        dist_matrix = batch[1][1].to(device).float()
        if len(batch[1]) <= 2:
            worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask = trainer._create_loc_idx_data(loc_xy)
        else:
            assert len(batch[1]) == 6, "job loc index generated from dataset?"
            worker_loc_idx = batch[1][2].to(device).long()
            job_loc_idx = batch[1][3].to(device).long()
            next_job_idx = batch[1][4].to(device).long()
            next_job_mask = batch[1][5].to(device).float()
 

        pomo_avg_score, reward,_  = trainer._train_one_batch(
            loc_xy, dist_matrix,
            worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask)

        try: 
            opti_travels, return_gps, opti_nns_travels, return_pomo_tsp_idx, return_pomo_loc_length, \
                return_ortools_loc_idx, return_ortools_tsp_idx, return_ortools_loc_length = (
                run_single_vroom_nns(tester, return_batch_i = 0, return_pomo_i = 0)
            )


            # opti_travels, return_gps, return_pomo_loc_idx, return_pomo_tsp_idx, return_pomo_loc_length, \
            #     return_ortools_loc_idx, return_ortools_tsp_idx, return_ortools_loc_length = (
            #     run_vroom_vrp_single(tester, return_batch_i = 0, return_pomo_i = 0)
            # )

            # opti_travels, return_gps, return_pomo_loc_idx, return_pomo_tsp_idx, return_pomo_loc_length, \
            #     return_ortools_loc_idx, return_ortools_tsp_idx, return_ortools_loc_length = (
            #     run_vroom_vrp_pickdrop(tester, return_batch_i = 0, return_pomo_i = 0)
            # )
            # # opti_travels, return_gps, return_pomo_loc_idx, return_pomo_tsp_idx, return_pomo_loc_length, \
            # #     return_ortools_loc_idx, return_ortools_tsp_idx, return_ortools_loc_length = (
            # #     run_ortools_vrp_pickdrop(tester, return_batch_i = 0, return_pomo_i = 0)
            # # )
            # # opti_travels, return_gps, return_loc_idx, return_pomo_tsp_idx, return_ortools_tsp_idx = (
            # #     run_ortools_tsp_pickdrop(tester, return_batch_i = 0, return_worker_i = -100)
            # # )
        except ValueError as ee:
            logger.warning(f"Ortools Failed and skipped loop {loop_i}")
            continue
        ortools_travels = torch.tensor(opti_travels)
        ortools_avg = (ortools_travels.mean()).item()

        vroom_nns_travels = torch.tensor(opti_nns_travels)
        vroom_nns_avg = (vroom_nns_travels.mean()).item()


        # _osrm_travels, _, _,_, _ = (
        #         run_osrm_tsp_single(tester, return_batch_i = 0, return_worker_i = -100)
        #     )
        osrm_avg = 0 # torch.tensor(_osrm_travels).mean().item()
        osrm_scores.append(osrm_avg)
        


        pomo_scores.append(pomo_avg_score)
        ortools_scores.append(ortools_avg)
        vroom_nns_scores.append(vroom_nns_avg)
        logger.info("worker {}, pomo avg_score = {}, osrm = {}, optimizer_score = {}, vroom_nns_score = {}, pomo pct {}, osrm pct {},  vroom_nns pct {}, loop {}".format(
            env_params["worker_size"],
            round(pomo_avg_score, 4 ), round(osrm_avg, 4 ), round(ortools_avg, 4 ) , round(vroom_nns_avg, 4 ),
            round(pomo_avg_score / ortools_avg, 4 ),
            round(osrm_avg / ortools_avg, 4 ),  
            round(vroom_nns_avg / ortools_avg, 4 ), 
            loop_i))
    if len(pomo_scores) > 0:  # 
        ratios = list(map(truediv,pomo_scores, ortools_scores))
        logger.info(f"{len(pomo_scores)} loops, average pomo_n2s vs vroom: {round(sum(pomo_scores)/sum(ortools_scores), 4)}, min: {round(min(ratios),4)}, max: {round(max(ratios),4)}")
        ratios = list(map(truediv,vroom_nns_scores, ortools_scores))
        logger.info(f"{len(pomo_scores)} loops, average vroom+pomo_n2s vs vroom: {round(sum(vroom_nns_scores)/sum(ortools_scores), 4)}, min: {round(min(ratios),4)}, max: {round(max(ratios),4)}")

##########################################################################################

if __name__ == "__main__":
    main()

