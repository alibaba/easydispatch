from dataclasses import dataclass
# from pandas import wide_to_long
import torch
import numpy as np
from itertools import cycle, islice
from dispatch.config import ADDR_DIM, ALLOWED_MAXIMUM_MINUTES, NEGATIVE_MIN_VALUE
from dispatch.contrib.training.pomo.pick_drop_tsp.pick_drop_tsp_env import PickDropTSPEnv 
from dispatch.contrib.training.pomo.pick_drop_tsp.pick_drop_tsp_model import PickDropTSPModel
from dispatch.contrib.training.pomo.pick_drop_tsp_with_start.pick_drop_tsp_with_start_env import PickDropWithStartTSPEnv
from dispatch.contrib.training.pomo.pick_drop_tsp_with_start.pick_drop_tsp_with_start_model import PickDropWithStartTSPModel 
from dispatch.plugins.kandbox_planner.util.kandbox_util import decode_solution

@dataclass
class Reset_State:
    worker_size: int = 0
    job_size: int = 0
    tsp_pomo_size: int = 0

    worker_loc_idx: torch.Tensor = None
    # shape: (batch, worker_size, 1)
    job_loc_idx: torch.Tensor = None
    # shape: (batch, job_size, 1)
    loc_xy: torch.Tensor = None
    # shape: (batch, worker_size+job_size, loc_dim)
    allowed_maximum_minutes: int = ALLOWED_MAXIMUM_MINUTES
    allowed_minutes_importance: int = 0.1
    loc_dim: int = 3

    # worker_attr: torch.Tensor = None # shape: (batch, worker_size, loc_dim)
    # node_attr: torch.Tensor = None # shape: (batch, job, 2)
    BATCH_IDX: torch.Tensor = None
    POMO_IDX: torch.Tensor = None
    allowed_maximum_minutes: int = ALLOWED_MAXIMUM_MINUTES
    allowed_minutes_importance: int = 0.1



@dataclass
class Step_State:
    reset_state: Reset_State = None
    # Solution 和 pre_idx等里面的idx都是对应step_state.reset_state.job_loc_idx 里面的真正的loc_idx, 而不是对于job_loc_idx的指针。
    # 可以直接用solution里面的值从loc_xy里面gather真正的地址。
    solution: torch.Tensor = None
    solution_worker_idx: torch.Tensor = None
    solution_pre_idx: torch.Tensor = None
    solution_job_curr_seq: torch.Tensor = None
    prev_best_solution: torch.Tensor = None
    prev_best_obj: torch.Tensor = None
    prev_best_step: torch.Tensor = None
    # solution_job_next_seq: torch.Tensor = None

    BATCH_POMO_IDX_2D: torch.Tensor = None
    worker_size: int = 0
    job_size: int = 0
    worker_job_size: int = 0
    worker_job_size_plus1: int = 0
    batch_size: int = 0
    pomo_size: int = 0
    batch_pomo_size: int = 0
    max_job_in_worker_size: int = 0
    max_n2s_swap_step_count: int = 5
    allow_changing_worker_flag: bool = False


    job2slot_n2s_step: int = 0
    job2slot_tsp_step: int = 0
    tsp_pre_forward_done: int = 0
    job2slot_current_job_i: int = None
    tsp_selected_count:int = 0

    # shape: (batch, pomo, worker, max_job)
    # Deprecated. 2023-01-05 19:29:20. I will track only locations. not job indexes.
    # scheduled_job_idx: torch.Tensor = None

    # Job2Slot Dynamic
    ####################################

    # This one is for job2slot before the TSP, following sequence of:
    # pick_1, drop_1, pick_2,drop_2,....
    # shape: (batch, pomo, worker, max_job)
    worker_selected_loc_idx: torch.Tensor = None
    # This one is the location sequence after the TSP:
    # Could be pick_1,pick_2,drop_2, drop_1,....
    # shape: (batch, pomo, worker, max_job)
    worker_loc_idx_after_tsp: torch.Tensor = None
    # all_worker_locs_to_dispatch: torch.Tensor = None

    # shape: (batch, pomo, worker, max_job)
    worker_selected_loc_length: torch.Tensor = None

    enabled_slot_map: torch.Tensor = None
    # ninf_mask: torch.Tensor = None
    # enable_ninf_mask: bool = True



    # TSP Static
    ####################################
    tsp_next_job_mask: torch.Tensor = None
    tsp_next_job_index: torch.Tensor = None

    # TSP Dynamic
    ####################################
    tsp_selected_count:int = None
    tsp_current_loc = None
    # shape: (batch, pomo)
    tsp_selected_loc_idx = None
    tsp_starting_loc_idx = None
    # shape: (batch, pomo, 0~problem)



def step_remove_nodes(
    step_state: Step_State,
    action:  torch.Tensor, 
) -> torch.Tensor:
    # The selected job candidate to insert, pick and drop. Drop = pick + job_size
    pair_pick = action[:, 1].view(step_state.batch_pomo_size, 1)
    # pair_drop = pair_pick + step_state.job_size

    solution = step_state.solution #.clone()  # if solution=[2,0,1], means 0->2->1->0. # [:, :step_state.worker_job_size]
    # Assigned worker index should remain same
    # selected_worker_idx = step_state.solution_worker_idx.gather(1, target_first)


    # Erase first/pick from the link
    pre_pick = step_state.solution_pre_idx.gather(1, pair_pick)
    post_pick = solution.gather(1, pair_pick)

    step_state.solution_pre_idx.scatter_(1, post_pick, pre_pick)
    solution.scatter_(1, pre_pick, post_pick)  # second -> pair_drop
    solution.scatter_(1, pair_pick, step_state.worker_job_size)  # reset this job pointing to end

def step_insert_nodes(
    step_state: Step_State,
    action:  torch.Tensor, 
) -> torch.Tensor:
    # The selected job candidate to insert, pick and drop. Drop = pick + job_size
    pair_pick = action[:, 1].view(step_state.batch_pomo_size, 1)
    # pair_drop = pair_pick + step_state.job_size

    target_first = action[:, 2].view(step_state.batch_pomo_size, 1)
    # target_second = action[:, 4].view(step_state.batch_pomo_size, 1)
    
    # I work on step state solution directly.
    solution = step_state.solution
    # 2023-12-16 18:54:20, does not seem to be right. Weird. Disabled.
    # if (solution[0,action[:, 1]] == pair_pick[:,0]).any():
    #     print("CAN_NOT_SELECT_REMOVED_POSITION")
    #     assert False, "CAN_NOT_SELECT_REMOVED_POSITION"

    selected_worker_idx = step_state.solution_worker_idx.gather(1, target_first)

    step_state.worker_selected_loc_length[
        step_state.BATCH_POMO_IDX_2D, selected_worker_idx
    ] = step_state.worker_selected_loc_length[
        step_state.BATCH_POMO_IDX_2D, selected_worker_idx
    ] + 1

    post_first = solution.gather(1, target_first)
    solution.scatter_(1, target_first, pair_pick)  # first -> pair_pick
    step_state.solution_pre_idx.scatter_(1, pair_pick, target_first)

    solution.scatter_(1, pair_pick, post_first)
    step_state.solution_pre_idx.scatter_(1, post_first, pair_pick)

    step_state.solution_worker_idx.scatter_(1, pair_pick, selected_worker_idx)

    
    return solution



class SingleJob2SlotN2SEnv:
    def __init__(self, env_params, model_params):

        # Const @INIT
        ####################################
        self.env_params = env_params
        self.model_params = model_params

        self.worker_size = env_params['worker_size']
        self.pomo_size = env_params['pomo_size']
        self.tsp_pomo_size = self.worker_size * self.pomo_size

        self.job_size = int(env_params['job_size'])
        self.loc_size = env_params['worker_size'] + env_params['job_size']
        self.max_job_in_worker_size = env_params['max_job_in_worker_size']
        assert self.max_job_in_worker_size % 2 == 0, "max_job_in_worker_size must be even"
        self.nbr_original_job_in_worker = int(self.max_job_in_worker_size / 2)
        # self.batch_size = 1

        # self.FLAG__use_saved_jobs = False
        # self.saved_worker_xy = None
        # self.saved_loc_xy = None
        # self.saved_node_demand = None
        # self.saved_index = None 

        # Const @Load_Problem
        ####################################
        # self.batch_size = None
        self.BATCH_IDX = None
        self.POMO_IDX = None
        # IDX.shape: (batch, pomo)


        # Dynamic-1
        ####################################

        # Dynamic-2
        ####################################


        MAX_NBR_JOB_IN_WORKER = env_params['max_job_in_worker_size'] # 10
        # MAX_FLOAT = 1e25

        # cycled_idx is used to create repeatted patten for observation.
        cycled_idx = [[0 for _ in range(MAX_NBR_JOB_IN_WORKER)]]*2
        # To get jobs with trailing worker_location.
        pad_idx = [[0 for _ in range(MAX_NBR_JOB_IN_WORKER)]]

        # Serve as mask for regular FSM(1 job) and masks for (pick drop)
        pad_mask = [[float('-inf') for _ in range(MAX_NBR_JOB_IN_WORKER + 1)]]
        # Next job index.
        next_job_list = [[MAX_NBR_JOB_IN_WORKER for _ in range(MAX_NBR_JOB_IN_WORKER)]]

        # Used for masking not used job position in TSP at cumsum-time-limit phase
        time_cumsum_idx = [[0 for _ in range(MAX_NBR_JOB_IN_WORKER)]]

        # pick_drop_mask = [[float('-inf') for _ in range(10)]]
        for i in range(1,MAX_NBR_JOB_IN_WORKER + 1): # self.max_job_in_worker_size
            if i>1:
                repeat_i = list(islice(cycle(
                    list(range(1,i))
                ), MAX_NBR_JOB_IN_WORKER - 2 )) # self.max_job_in_worker_size
                cycled_idx.append([0] + repeat_i + [0]) 

            pad_idx.append(list(range(i)) + [0 for _ in range(MAX_NBR_JOB_IN_WORKER-i)]) # i-1
            time_cumsum_idx.append(  [1 for _ in range(i)] + [0 for _ in range(MAX_NBR_JOB_IN_WORKER-i)]) 

            _pd_mask = [float("-inf")] + [0 for _ in range(i-1)] + [-pi*NEGATIVE_MIN_VALUE for pi in range(i,MAX_NBR_JOB_IN_WORKER+1)]
            for pi in range(1,min(i,MAX_NBR_JOB_IN_WORKER-1),2):
                _pd_mask[pi+1]=-pi*NEGATIVE_MIN_VALUE
            pad_mask.append(_pd_mask)


            _next_list = [MAX_NBR_JOB_IN_WORKER for _ in range(MAX_NBR_JOB_IN_WORKER)]
            for pi in range(1,min(i,MAX_NBR_JOB_IN_WORKER-1),2):
                _next_list[pi:pi+2]=[pi+1, MAX_NBR_JOB_IN_WORKER] 
            next_job_list.append(_next_list)

        tile_indexer_np = np.array(cycled_idx)
        pad_indexer_np = np.array(pad_idx)
        pad_mask_np = np.array(pad_mask)
        next_job_np = np.array(next_job_list)
        time_cumsum_np = np.array(time_cumsum_idx)
        # print(pad_indexer_np)


        # Indexer : from length -> tiled indexes
        self.tile_indexer = torch.tensor(tile_indexer_np) 
        self.pad_indexer = torch.tensor(pad_indexer_np) 
        self.pad_masker = torch.tensor(pad_mask_np).float()
        self.next_job_indexer = torch.tensor(next_job_np).long()
        self.time_cumsum_masker = torch.tensor(time_cumsum_np).float()
        
        
        # states to return
        ####################################
        self.step_state = Step_State()
        self.step_state.reset_state = Reset_State()
        self.step_state.reset_state.tsp_pomo_size = self.pomo_size*self.worker_size

    def load_jobs(self, 
        loc_xy = None, 
        dist_matrix= None,
        worker_loc_idx = None,
        job_loc_idx = None,
        next_job_idx = None,
        next_job_mask = None,
        aug_factor=1, 
        ):
        
        self.batch_size, self.pomo_size, self.worker_size = worker_loc_idx.size()
        self.step_state.batch_size, self.step_state.pomo_size, self.step_state.worker_size = worker_loc_idx.size()
        self.step_state.reset_state.job_size = self.step_state.job_size = self.job_size = job_loc_idx.size(2)

        self.step_state.worker_job_size = self.step_state.job_size + self.step_state.worker_size
        self.step_state.worker_job_size_plus1 = self.step_state.worker_job_size+1
        self.step_state.max_job_in_worker_size = self.env_params['max_job_in_worker_size']
        self.step_state.batch_pomo_size = self.step_state.batch_size * self.step_state.pomo_size

        self.step_state.reset_state.tsp_pomo_size = self.tsp_pomo_size = self.worker_size * self.pomo_size
        self.step_state.reset_state.worker_size = self.worker_size


        self.dist_matrix = dist_matrix


        self.BATCH_IDX = torch.arange(self.batch_size)[:, None,None]#.expand(self.batch_size, self.pomo_size)
        self.POMO_IDX = torch.arange(self.pomo_size)[None, :,None]#.expand(self.batch_size, self.pomo_size)
        self.step_state.BATCH_POMO_IDX_2D = torch.arange(self.step_state.batch_pomo_size)[:,None]#.expand(self.batch_size, self.pomo_size)


        self.step_state.reset_state.BATCH_IDX = self.BATCH_IDX
        self.step_state.reset_state.POMO_IDX = self.POMO_IDX 



        # 4-dimensional Index for jobs
        self.I4D_Batch = torch.arange(self.batch_size)[:,None,None,None]
        self.I4D_Pomo = torch.arange(self.pomo_size)[None,:,None,None]
        self.I4D_TSP_Pomo = torch.arange(self.tsp_pomo_size)[None,:,None,None]
        self.I4D_Worker = torch.arange(self.worker_size)[None,None,:,None]
        # self.I4D_Job = torch.arange(self. ? )[:,None,None,None]


        self.step_state.reset_state.loc_xy = loc_xy
        # self.step_state.reset_state.loc_dim = loc_xy.size(2)
        self.loc_size = loc_xy.size(1)
        self.step_state.reset_state.worker_loc_idx = worker_loc_idx
        self.step_state.reset_state.job_loc_idx = job_loc_idx


        self.step_state.solution = torch.zeros((self.step_state.batch_pomo_size, self.step_state.worker_job_size_plus1), dtype=torch.long) + self.step_state.worker_job_size

        self.step_state.solution_worker_idx = torch.cat([
            worker_loc_idx.view(self.step_state.batch_pomo_size, self.step_state.reset_state.worker_size), 
            (-1000 - torch.arange(self.step_state.reset_state.job_size + 1)).long().view( # *2
                1, self.step_state.reset_state.job_size + 1).repeat( self.step_state.batch_pomo_size,1 ),   # *2
            ],
            dim=-1)

        self.step_state.solution_job_curr_seq = torch.zeros(self.step_state.solution_worker_idx.size(), dtype=torch.long)

        self.step_state.solution_pre_idx = torch.cat([
            worker_loc_idx.view(self.step_state.batch_pomo_size, self.step_state.reset_state.worker_size), 
            (self.step_state.worker_size + torch.arange(self.step_state.reset_state.job_size + 1)).long().view( # *2
                1, self.step_state.reset_state.job_size + 1).repeat( self.step_state.batch_pomo_size,1 ),   # *2
            ],
            dim=-1)

        self.step_state.worker_selected_loc_length = torch.ones(
            (self.step_state.batch_pomo_size, self.worker_size), 
            dtype=torch.int64)


        self.step_state.job2slot_n2s_step = 0
        self.step_state.tsp_pre_forward_done = 0
        self.job2slot_current_job_i = None
        self.tsp_selected_count = 0

    def reset(self):

        with torch.no_grad():
            self.step_state.job2slot_current_job_i = 0 # self.worker_size  # 
            self.step_state.job2slot_n2s_step = 0
            self.step_state.tsp_pre_forward_done = 0
            self.step_state.allow_changing_worker_flag = self.env_params["allow_changing_worker_flag"]
            self.job2slot_current_job_i = None
            self.tsp_selected_count = 0


            # shape: (batch, pomo)
            done = self.finished = (self.step_state.job2slot_current_job_i >= self.job_size)
            reward = None
            return self.step_state, reward, done


    def set_state_to_length(
            self, worker_loc_length, 
            enabled_slot_map = None,
            solution = None, 
            solution_pre_idx = None,
            solution_worker_idx = None,
            job2slot_current_job_i = 0, 
            max_job_in_worker_size = 16,
            job2slot_n2s_step = 0):


        with torch.no_grad():
            self.step_state.solution = solution
            self.step_state.solution_pre_idx = solution_pre_idx
            self.step_state.solution_worker_idx = solution_worker_idx

            self.step_state.worker_selected_loc_length = worker_loc_length
            self.step_state.enabled_slot_map = enabled_slot_map
            self.step_state.max_job_in_worker_size = max_job_in_worker_size
            if job2slot_n2s_step == 0:
                self.step_state.job2slot_n2s_step = 0
            else:
                # here job2slot_current_job_i should be ignored.
                self.pre_swap()
                self.step_state.job2slot_n2s_step = 1
            self.step_state.job2slot_current_job_i = job2slot_current_job_i



            # 更新Tiled selected job idx.
            ####################################


            # shape: (batch, pomo)
            done = False
            reward = None
            return self.step_state, reward, done

    def pre_step(self): 

        reward = None
        done = False 

        return self.step_state, reward, done

    def step(self, selected):
        # worker_selected_loc_idx shape: (batch, pomo, worker, max_job)
        # worker_selected_loc_length shape: (batch, pomo, worker)
        with torch.no_grad():
            if self.step_state.job2slot_n2s_step == 0:
                return self.step_job2slot(selected=selected)
            else: # if self.step_state.job2slot_n2s_step == 1:
                return self.step_swap(selected=selected)
            # else:
            #     assert False, f"wrong value job2slot_n2s_step = {self.step_state.job2slot_n2s_step}"


    def pre_swap(self, ):
        travel_distances = self.get_tsp_travel_distance_by_matrix()

        self.step_state.prev_best_obj = travel_distances.view(self.step_state.batch_pomo_size,1,).repeat(1,2,)
        self.step_state.prev_best_solution = self.step_state.solution.view(
            self.step_state.batch_pomo_size, self.step_state.worker_job_size_plus1,1,).repeat(1,1,2,) 
        self.step_state.prev_best_step = torch.ones((self.step_state.batch_pomo_size,2,), dtype=torch.int64)

        self.step_state.job2slot_n2s_step = 1


    def step_job2slot(self, selected):
        # 1 - 更新 solution
        ####################################
        step_insert_nodes(step_state=self.step_state, action=selected)
        self.step_state.job2slot_current_job_i=self.step_state.job2slot_current_job_i+1  

        reward = 0
        done = self.step_state.job2slot_current_job_i >= self.job_size # self.worker_size + 
        if done:
            done = False
            self.pre_swap()

        # leave it to TSP
        return self.step_state, reward, done

    def step_swap(self, selected):
        # print("before_step_remove_nodes", self.step_state.solution, selected, decode_solution(self.step_state.solution[0],worker_length=self.step_state.reset_state.worker_loc_idx.size(2)))
        step_remove_nodes(step_state=self.step_state, action=selected)
        # print("after_step_remove_nodes", self.step_state.solution, selected, decode_solution(self.step_state.solution[0],worker_length=self.step_state.reset_state.worker_loc_idx.size(2)))
        step_insert_nodes(step_state=self.step_state, action=selected)
        # print("after_insert_nodes", self.step_state.solution, decode_solution(self.step_state.solution[0],worker_length=self.step_state.reset_state.worker_loc_idx.size(2)))




        self.step_state.job2slot_n2s_step = self.step_state.job2slot_n2s_step+1        
        travel_distances = self.get_tsp_travel_distance_by_matrix()
 
        best_n_new_objs = torch.cat((
            travel_distances[:, None], 
            self.step_state.prev_best_obj[:, -1, None]
            ), -1)
        now_best_objective, min_indices = torch.min(
            best_n_new_objs, -1 # 
        )

        self.step_state.prev_best_obj = torch.cat([
            travel_distances[:, None],
            now_best_objective[:,None],
        ], dim=-1) 


        best_n_new_solutions = torch.cat([
            self.step_state.solution[:,:,None], 
            self.step_state.prev_best_solution[:, :, 1:2]], dim=-1)
        BATCH_IDX = torch.arange(self.step_state.batch_pomo_size)[:, None].expand(self.step_state.batch_pomo_size, self.step_state.worker_job_size_plus1)
        GRAPH_IDX = torch.arange(self.step_state.worker_job_size_plus1)[None, :].expand(self.step_state.batch_pomo_size, self.step_state.worker_job_size_plus1)
        MIN_IDX = min_indices[:, None].repeat(1, self.step_state.worker_job_size_plus1)
        now_best_solution = best_n_new_solutions[BATCH_IDX, GRAPH_IDX, MIN_IDX]
 
        self.step_state.prev_best_solution = torch.cat([
            self.step_state.solution[:,:,None],
            now_best_solution[:,:,None]
        ], dim=-1) 

        now_steps = torch.zeros(( self.step_state.batch_pomo_size,1,), dtype=torch.int64) + self.step_state.job2slot_n2s_step
        best_n_new_solution_steps =  torch.cat([
            now_steps, 
            self.step_state.prev_best_step[:,  1:2]], dim=-1)
        STEP_MIN_IDX = min_indices[:, None] # .repeat(1, self.step_state.batch_pomo_size)
        now_best_solution_step = best_n_new_solution_steps[
            torch.arange(self.step_state.batch_pomo_size)[:,None], STEP_MIN_IDX]
        self.step_state.prev_best_step = torch.cat([
            now_steps,
            now_best_solution_step,
        ], dim=-1) 

        ####################################
        done = (self.step_state.job2slot_n2s_step >= self.step_state.max_n2s_swap_step_count)
        if done and (not self.env_params["serving_only_n_no_reward"]):
            # travel_distances is the last objective/travel
            reward = 0-now_best_objective
        else:
            reward = 0
        # rolled_seq = ordered_seq.roll(dims=3, shifts=-1)
        # segment_lengths = ((ordered_seq-rolled_seq)**2).sum(4).sqrt()
        # travel_distances = segment_lengths.sum((2,3,))

        return self.step_state, reward, done

     

    def get_tsp_travel_distance_by_matrix(self,):
        dist_mat_plus1 = torch.cat([
            self.dist_matrix,
            torch.zeros(self.step_state.batch_size, self.step_state.worker_job_size, 1)
        ], dim=-1)
        dist_mat_plus1_2d = torch.cat([
            dist_mat_plus1,
            torch.zeros(self.step_state.batch_size, 1, self.step_state.worker_job_size+1)
        ], dim=1)

        dist_mat_plus1_2d_padded = dist_mat_plus1_2d.unsqueeze(1).repeat(
            1,self.step_state.pomo_size,1, 1
        ).view(self.step_state.batch_pomo_size, self.step_state.worker_job_size_plus1 * self.step_state.worker_job_size_plus1,)
        
        head_idx = torch.arange(self.step_state.worker_job_size_plus1).view(
            1,self.step_state.worker_job_size_plus1).repeat(self.step_state.batch_pomo_size, 1) 
        # tail_idx = self.step_state.solution
        node2node_linear_index = head_idx * self.step_state.worker_job_size_plus1 + self.step_state.solution

        node2node_dist = dist_mat_plus1_2d_padded[
            torch.arange(self.step_state.batch_pomo_size)[:, None,],
            node2node_linear_index
        ]

        travel_distances = node2node_dist.sum(dim=-1) 

        total_missed_minutes = 0
        if False and self.step_state.tsp_time_cumsum_mask is not None and ADDR_DIM > 2:
            # Now I calculate the time limit penalty (cumsum of minutes as arrival)
            dist_cumsum = torch.cumsum(dist, dim=2)
            dist_cumsum = dist_cumsum.roll(dims=2, shifts=1)
            dist_cumsum[:,:,0] = 0
            dist_cumsum = dist_cumsum * self.step_state.tsp_time_cumsum_mask
            
            allowed_cumsum = self.step_state.reset_state.loc_xy[:,:,2] [
                torch.arange(self.batch_size)[:,None,None],
                ordered_nodes
            ] * self.step_state.reset_state.allowed_maximum_minutes

            missed_minutes = dist_cumsum - allowed_cumsum
            missed_minutes[missed_minutes < 0] = 0
            total_missed_minutes = missed_minutes.view(
                self.batch_size,self.pomo_size,-1
            ).sum(2)*self.step_state.reset_state.allowed_minutes_importance * 2 # TODO, temp improve importance.

        return travel_distances + total_missed_minutes
