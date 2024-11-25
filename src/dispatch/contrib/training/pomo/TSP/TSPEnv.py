
from dataclasses import dataclass
import torch

from dispatch.contrib.training.pomo.TSP.TSProblemDef import get_random_problems, augment_xy_data_by_8_fold


@dataclass
class Reset_State:
    problems: torch.Tensor
    loc_xy: torch.Tensor = None
    # shape: (batch, problem, 2)
    # dist_matrix: torch.Tensor


@dataclass
class Step_State:
    BATCH_IDX: torch.Tensor
    POMO_IDX: torch.Tensor
    # shape: (batch, pomo)
    current_node: torch.Tensor = None
    # shape: (batch, pomo)
    ninf_mask: torch.Tensor = None
    # shape: (batch, pomo, node)    
    reset_state: Reset_State = None
    job2slot_tsp_step = 0
    tsp_pre_forward_done = 0


class TSPEnv:
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
        self.problems = None
        # shape: (batch, node, node)
        self.dist_matrix = None

        # Dynamic
        ####################################
        self.selected_count = None
        self.current_node = None
        # shape: (batch, pomo)
        self.selected_node_list = None
        # shape: (batch, pomo, 0~problem)

    def load_problems(self, batch_size, aug_factor=1):
        self.batch_size = batch_size

        self.problems = get_random_problems(batch_size, self.problem_size)
        # problems.shape: (batch, problem, 2)
        if aug_factor > 1:
            if aug_factor == 8:
                self.batch_size = self.batch_size * 8
                self.problems = augment_xy_data_by_8_fold(self.problems)
                # shape: (8*batch, problem, 2)
            else:
                raise NotImplementedError

        self.BATCH_IDX = torch.arange(self.batch_size)[:, None].expand(self.batch_size, self.pomo_size)
        self.POMO_IDX = torch.arange(self.pomo_size)[None, :].expand(self.batch_size, self.pomo_size)

    def load_jobs(self,  
        batch_size = None, aug_factor=1, 
        loc_xy = None, dist_matrix= None,
        worker_loc_idx = None,
        job_loc_idx = None,
        next_job_idx = None,
        next_job_mask = None,
        ):


        if loc_xy is None:
            self.batch_size = batch_size
            return self.load_problems(batch_size=self.batch_size) 
        else:
            self.batch_size = batch_size = loc_xy.size(0)
            assert self.problem_size == loc_xy.size(1)
            
        self.dist_matrix = dist_matrix
        self.problems = loc_xy
        self.loc_xy = loc_xy
        self.job_loc_idx = torch.arange(self.problem_size)[None, :].expand(self.batch_size, self.pomo_size, self.problem_size)


        if aug_factor > 1:
            raise NotImplementedError
            if aug_factor == 8:
                self.batch_size = self.batch_size * 8
                worker_xy = augment_xy_data_by_8_fold(worker_xy)
                loc_xy = augment_xy_data_by_8_fold(loc_xy)
                node_demand = node_demand.repeat(8, 1)
            else:
                raise NotImplementedError


        self.BATCH_IDX = torch.arange(self.batch_size)[
            :, None].expand(self.batch_size, self.pomo_size)
        self.POMO_IDX = torch.arange(self.pomo_size)[
            None, :].expand(self.batch_size, self.pomo_size)

        # 4-dimensional Index for jobs
        self.I4D_Batch = torch.arange(self.batch_size)[:,None,None,None]
        self.I4D_Pomo = torch.arange(self.pomo_size)[None,:,None,None]

    
    def reset(self):
        self.selected_count = 0
        self.current_node = None
        # shape: (batch, pomo)
        self.selected_node_list = torch.zeros((self.batch_size, self.pomo_size, 0), dtype=torch.long)
        # shape: (batch, pomo, 0~problem)

        # CREATE STEP STATE
        self.step_state = Step_State(BATCH_IDX=self.BATCH_IDX, POMO_IDX=self.POMO_IDX)
        self.step_state.reset_state = Reset_State(
            self.problems,
            loc_xy = self.problems)
        self.step_state.ninf_mask = torch.zeros((self.batch_size, self.pomo_size, self.problem_size))
        # shape: (batch, pomo, problem)

        done = self.finished = (self.selected_count >= self.problem_size)
        reward = None
        return self.step_state, reward, done

    def pre_step(self):
        print("DO not USE pre_step, from tspenv")
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
        # shape: (batch, pomo)
        self.step_state.ninf_mask[self.BATCH_IDX, self.POMO_IDX, self.current_node] = float('-inf')
        # shape: (batch, pomo, node)

        # returning values
        done = (self.selected_count >= self.problem_size)
        if done:
            if self.env_params["serving_only_n_no_reward"]:
                reward = 0
            else:
                if self.dist_matrix is None:
                    reward = -self._get_travel_distance()  # note the minus sign!
                else:
                    reward = -self._get_travel_distance_by_matrix()
            
        else:
            reward = None

        return self.step_state, reward, done

    def _get_travel_distance(self):
        gathering_index = self.selected_node_list.unsqueeze(3).expand(self.batch_size, -1, self.problem_size, 2)
        # shape: (batch, pomo, problem, 2)
        seq_expanded = self.problems[:, None, :, :].expand(self.batch_size, self.pomo_size, self.problem_size, 2)

        ordered_seq = seq_expanded.gather(dim=2, index=gathering_index)
        # shape: (batch, pomo, problem, 2)

        rolled_seq = ordered_seq.roll(dims=2, shifts=-1)
        segment_lengths = ((ordered_seq-rolled_seq)**2).sum(3).sqrt()
        # shape: (batch, pomo, problem)

        travel_distances = segment_lengths.sum(2)
        # shape: (batch, pomo)
        return travel_distances # , segment_lengths


    def _get_travel_distance_by_matrix(self): 

        ordered_nodes = self.selected_node_list.view(
            self.batch_size, self.pomo_size,self.problem_size,
        ) 
        rolled_nodes = ordered_nodes.roll(dims=2, shifts=-1)


        linear_index = ordered_nodes.view(
            self.batch_size, self.pomo_size*self.problem_size 
        ) * self.problem_size + rolled_nodes.view(
            self.batch_size, self.pomo_size*self.problem_size 
        )

        dist = self.dist_matrix.view(self.batch_size, (self.problem_size)**2)[
            torch.arange(self.batch_size)[:, None,],
            linear_index
        ] 

        travel_distances = dist.view(
            self.batch_size,self.pomo_size,self.problem_size
            )[:,:,0:self.problem_size-1].sum(2)
        return travel_distances
