
from dataclasses import dataclass
import torch
from dispatch.config import ADDR_DIM, ALLOWED_MAXIMUM_MINUTES
@dataclass
class Reset_State:
    loc_xy: torch.Tensor
    # shape: (batch, problem, 2)
    # dist_matrix: torch.Tensor
    job_loc_idx: torch.Tensor
    allowed_maximum_minutes: int = ALLOWED_MAXIMUM_MINUTES
    allowed_minutes_importance: int = 0.1
    loc_dim: int = 3

@dataclass
class Step_State:
    BATCH_IDX: torch.Tensor
    POMO_IDX: torch.Tensor
    # shape: (batch, pomo)
    current_node: torch.Tensor = None
    # shape: (batch, pomo)
    next_job_mask: torch.Tensor = None
    # shape: (batch, pomo, node)

    reset_state: Reset_State = None
    job2slot_tsp_step = 0
    tsp_pre_forward_done = 0
class PickDropWithStartTSPEnv:
    def __init__(self, env_params,  model_params = {}):

        # Const @INIT
        ####################################
        self.env_params = env_params
        self.problem_size = env_params['problem_size']
        self.pomo_size = env_params['pomo_size']

        self.model_params = model_params
        # Const @Load_Problem
        ####################################
        self.batch_size = None
        self.BATCH_IDX = None
        self.POMO_IDX = None
        # IDX.shape: (batch, pomo)
        self.loc_xy = None
        # self.loc_size  = 1
        # shape: (batch, node, node)

        # Dynamic
        ####################################
        self.selected_count = None
        self.current_node = None
        # shape: (batch, pomo)
        self.selected_node_list = None
        # shape: (batch, pomo, 0~problem)

    def load_jobs(self, 
        batch_size = None, aug_factor=1, 
        loc_xy = None, 
        dist_matrix= None,
        worker_loc_idx = None, # only for compatability of job2slot training
        job_loc_idx = None,
        next_job_idx = None,
        next_job_mask = None,
        ):
        
        if loc_xy is None:
            self.batch_size = batch_size
            raise NotImplemented("You must provide loc_xy, or fail.")
        else:
            self.batch_size = batch_size = loc_xy.size(0)
            assert self.problem_size == job_loc_idx.size(2), "Wrong dimensions, for TSP with start problem, problem_size is number of nodes (1 worker + N job_pair * 2) and pomo size are pseudo-workers"
            
        self.dist_matrix = dist_matrix
        self.loc_xy = loc_xy
        
        # This is TSP. POMO replaced worker.
        # self.worker_loc_idx = worker_loc_idx
        self.job_loc_idx = job_loc_idx
        self.next_job_idx = next_job_idx
        self.next_job_mask = next_job_mask

        self.BATCH_IDX = torch.arange(self.batch_size)[
            :, None].expand(self.batch_size, self.pomo_size)
        self.POMO_IDX = torch.arange(self.pomo_size)[
            None, :].expand(self.batch_size, self.pomo_size)

        # 4-dimensional Index for jobs
        self.I4D_Batch = torch.arange(self.batch_size)[:,None,None,None]
        self.I4D_Pomo = torch.arange(self.pomo_size)[None,:,None,None]

    
    def reset(self):
        # The first node is already selected.
        self.current_node = torch.zeros((self.batch_size, self.pomo_size), dtype=torch.long)
        self.selected_count = 1
        # shape: (batch, pomo, 1)
        self.selected_node_list = self.current_node[:,:,None]

        # CREATE STEP STATE
        self.step_state = Step_State(
            BATCH_IDX=self.BATCH_IDX, 
            POMO_IDX=self.POMO_IDX,
            current_node = self.current_node,
            next_job_mask = self.next_job_mask
            )
        # shape: (batch, pomo, problem)
        reward = None
        done = False

        self.step_state.reset_state = Reset_State(
            loc_xy = self.loc_xy,
            job_loc_idx = self.job_loc_idx
            )

        return self.step_state, reward, done


    def pre_step(self):
        reward = None
        done = False
        return self.step_state, reward, done

    def step(self, selected):
        # selected.shape: (batch, pomo)

        self.selected_count += 1
        self.current_node = selected
        # shape: (batch, pomo)
        self.selected_node_list = torch.cat((self.selected_node_list, self.current_node[:, :, None]), dim=2)
        # shape: (batch, pomo, 0~problem)

        # UPDATE STEP STATE
        self.step_state.current_node = self.current_node
        unblocked_job_idx = self.next_job_idx[self.BATCH_IDX, self.POMO_IDX, self.current_node]
        # shape: (batch, pomo, 1)
        self.step_state.next_job_mask[self.BATCH_IDX, self.POMO_IDX, unblocked_job_idx] = 0 # 1
        self.step_state.next_job_mask[self.BATCH_IDX, self.POMO_IDX, self.current_node] = float("-inf")# 0
        # shape: (batch, pomo, node)

        # returning values
        done = (self.selected_count >= self.problem_size)
        if done:
            if self.env_params["serving_only_n_no_reward"]:
                reward = 0
            else:
                # reward = -self._get_travel_distance_by_euclidean()  # note the minus sign!
                reward = -self._get_travel_distance_by_matrix()
            
        else:
            reward = None

        return self.step_state, reward, done

    def _get_travel_distance_by_euclidean(self):
        gathering_index = self.selected_node_list.unsqueeze(3).expand(self.batch_size, -1, self.problem_size, 2)
        # shape: (batch, pomo, problem, 2)
        seq_expanded = self.loc_xy[:, None, :, :].expand(self.batch_size, self.pomo_size, self.problem_size, 2)

        ordered_seq = seq_expanded.gather(dim=2, index=gathering_index)
        # shape: (batch, pomo, problem, 2)

        rolled_seq = ordered_seq.roll(dims=2, shifts=-1)
        segment_lengths = ((ordered_seq-rolled_seq)**2).sum(3).sqrt()
        # shape: (batch, pomo, problem)

        travel_distances = segment_lengths.sum(2)
        # shape: (batch, pomo)
        return travel_distances # , segment_lengths


    def _get_travel_distance_by_matrix(self): 
        loc_size = self.loc_xy.size(1)
        self.selected_loc_list = self.job_loc_idx[ 
            torch.arange(self.batch_size)[:,None,None],
            torch.arange(self.pomo_size)[None,:,None],
            self.selected_node_list
        ]

        ordered_nodes = self.selected_loc_list.view(
            self.batch_size, self.pomo_size,self.problem_size,
        ) 
        rolled_nodes = ordered_nodes.roll(dims=2, shifts=-1)
        # To remove last travel back to depot/starting point
        rolled_nodes[:,:,-1] = ordered_nodes[:,:,-1]


        linear_index = ordered_nodes.view(
            self.batch_size, self.pomo_size*(self.problem_size) 
        ) * loc_size + rolled_nodes.view(
            self.batch_size, self.pomo_size*(self.problem_size) 
        )

        # This solution has stride problem. maybe shape()?
        # linear_index = ordered_nodes[:,:,0:self.problem_size-1].view(
        #     self.batch_size, self.pomo_size*(self.problem_size-1) 
        # ) * self.problem_size + rolled_nodes[:,:,0:self.problem_size-1].view(
        #     self.batch_size, self.pomo_size*(self.problem_size-1) 
        # )

        dist = self.dist_matrix.view(self.batch_size, loc_size**2)[
            torch.arange(self.batch_size)[:, None,],
            linear_index
        ].view(
            self.batch_size,self.pomo_size,self.problem_size
        )

        travel_distances = dist.sum(2)
        if ADDR_DIM <= 2:
            return travel_distances
        else:
            # Now I calculate the time limit penalty (cumsum of minutes as arrival)
            dist_cumsum = torch.cumsum(dist, dim=2)
            dist_cumsum = dist_cumsum.roll(dims=2, shifts=1)
            dist_cumsum[:,:,0] = 0
            allowed_cumsum = self.loc_xy[:,:,2] [
                torch.arange(self.batch_size)[:,None,None],
                self.selected_loc_list
            ] * self.step_state.reset_state.allowed_maximum_minutes

            missed_minutes = dist_cumsum - allowed_cumsum
            missed_minutes[missed_minutes < 0] = 0
            total_missed_minutes = missed_minutes.sum(2)*self.step_state.reset_state.allowed_minutes_importance


            return travel_distances + total_missed_minutes

