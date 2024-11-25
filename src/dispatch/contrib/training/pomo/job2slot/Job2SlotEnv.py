
from dataclasses import dataclass
import torch
import numpy as np
from itertools import cycle, islice


from dispatch.contrib.training.pomo.TSP.TSPEnv import TSPEnv 
from dispatch.contrib.training.pomo.TSP.TSPModel import TSPModel 

from dispatch.contrib.training.pomo.job2slot.Job2SlotProblemDef import get_random_jobs, augment_xy_data_by_8_fold


def get_random_indexes_from_jobs(loc_xy, batch_size, pomo_size, worker_size, job_size):

    # TODO, 2022-02-25 16:50:02, verify if permutate worker location index should help. 
    # I do only job permutation, and No worker permutation for now. 
    worker_loc_idx = torch.arange(worker_size).repeat(batch_size,pomo_size,1)

    # shape: (batch, job_size, 1)
    # job_loc_idx = torch.arange(job_size).repeat(batch_size,1) + worker_size
    _rand_perm = torch.rand((pomo_size,job_size)).argsort() + worker_size

    job_loc_idx = _rand_perm[None,:,:].repeat(batch_size,1,1)


    return worker_loc_idx, job_loc_idx



@dataclass
class Reset_State:
    worker_loc_idx: torch.Tensor = None
    # shape: (batch, worker_size, 1)
    job_loc_idx: torch.Tensor = None
    # shape: (batch, job_size, 1)
    loc_xy: torch.Tensor = None
    # shape: (batch, worker_size+job_size, 2)

    # worker_attr: torch.Tensor = None
    # # shape: (batch, worker_size, 2)
    # node_attr: torch.Tensor = None
    # # shape: (batch, job, 2)
    BATCH_IDX: torch.Tensor = None
    POMO_IDX: torch.Tensor = None


@dataclass
class Step_State:

    # shape: (batch, pomo, worker, max_job)
    worker_selected_loc_idx: torch.Tensor = None

    # TODO: 2022-10-24 13:02:40 Should I have this seperated？
    # worker_selected_job_idx: torch.Tensor = None

    # shape: (batch, pomo, worker, max_job)
    worker_selected_loc_length: torch.Tensor = None
    worker_loc_idx_after_tsp: torch.Tensor = None

    # shape: (batch, pomo, worker, max_job)
    ninf_mask: torch.Tensor = None

    current_job_idx: int = None
    reset_state: Reset_State = None
    job2slot_tsp_step = 0
    tsp_pre_forward_done = 0

class Job2SlotEnv:
    def __init__(self, env_params, model_params):

        # Const @INIT
        ####################################
        self.env_params = env_params
        self.model_params = model_params
        
        self.worker_size = env_params['worker_size']
        self.job_size = env_params['job_size']
        self.max_job_in_worker_size = env_params['max_job_in_worker_size']
        self.pomo_size = env_params['pomo_size']

        self.FLAG__use_saved_jobs = False
        self.saved_worker_xy = None
        self.saved_loc_xy = None
        self.saved_node_demand = None
        self.saved_index = None

        # TSP Env
        self.tsp_env_params = dict(env_params)
        self.tsp_env_params.update({
            'problem_size': env_params['max_job_in_worker_size'],
            'pomo_size': 1,
            'serving_only_n_no_reward': True,
        }) 
        self.tsp_model_params = dict(model_params)
        self.tsp_model_params.update({
            'eval_type': 'argmax', 
        })
        self.tsp_env = TSPEnv(env_params = self.tsp_env_params)

        self.tsp_model = TSPModel(self.tsp_model_params)
        # Load a pretrained TSP model as sub-model of Job2Slot
        file_name = self.env_params['tsp_model_path']
        checkpoint = torch.load(file_name, map_location=self.env_params["device"])
        self.tsp_model.load_state_dict(checkpoint['model_state_dict'])

        self.tsp_model.eval()
        print(f"Loaded inner TSP model for Job2SlotEnv from: {file_name}")
        

        # Const @Load_Problem
        ####################################
        self.batch_size = None
        self.BATCH_IDX = None
        self.POMO_IDX = None
        # IDX.shape: (batch, pomo)


        # Dynamic-1
        ####################################

        # Dynamic-2
        ####################################


        cycled_idx = [[0 for _ in range(self.max_job_in_worker_size)]]
        pad_idx = [[0 for _ in range(self.max_job_in_worker_size)]]
        pad_mask = [[float('-inf') for _ in range(self.max_job_in_worker_size)]]
        for i in range(1,self.max_job_in_worker_size+1): # 11
            repeat_i = list(islice(cycle(
                list(range(i))
            ), self.max_job_in_worker_size )) #10, self.max_job_in_worker_size
            cycled_idx.append(repeat_i) 

            pad_idx.append(list(range(i)) + [0 for _ in range(self.max_job_in_worker_size-i)])
            pad_mask.append([0 for _ in range(i)] + [-pi*1e10 for pi in range(i,self.max_job_in_worker_size)])

        tile_indexer_np = np.array(cycled_idx)
        pad_indexer_np = np.array(pad_idx)
        pad_mask_np = np.array(pad_mask)

        # Indexer : from length -> tiled indexes
        self.tile_indexer = torch.tensor(tile_indexer_np) 
        self.pad_indexer = torch.tensor(pad_indexer_np) 
        self.pad_masker = torch.tensor(pad_mask_np).float()
        
        
        # states to return
        ####################################
        self.step_state = Step_State()
        self.step_state.reset_state = Reset_State()

    def use_saved_jobs(self, filename, device):
        self.FLAG__use_saved_jobs = True

        loaded_dict = torch.load(filename, map_location=device)
        self.saved_worker_xy = loaded_dict['worker_xy']
        self.saved_loc_xy = loaded_dict['loc_xy']
        self.saved_node_demand = loaded_dict['node_demand']
        self.saved_index = 0

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
            loc_xy, worker_loc_idx, job_loc_idx = get_random_jobs(batch_size, self.pomo_size, self.worker_size, self.job_size)
            self.dist_matrix = torch.cdist(loc_xy, loc_xy, p=2)
        else:
            self.batch_size = batch_size = loc_xy.size(0)
            # worker_loc_idx, job_loc_idx = get_random_indexes_from_jobs(
            #     loc_xy, 
            #     batch_size, self.pomo_size, self.worker_size, self.job_size)
            
            self.dist_matrix = dist_matrix
    
        if self.FLAG__use_saved_jobs:
            worker_xy = self.saved_worker_xy[self.saved_index:self.saved_index+batch_size]
            loc_xy = self.saved_loc_xy[self.saved_index:self.saved_index+batch_size]
            node_demand = self.saved_node_demand[self.saved_index:self.saved_index+batch_size]
            self.saved_index += batch_size

        if aug_factor > 1:
            raise NotImplementedError
            if aug_factor == 8:
                self.batch_size = self.batch_size * 8
                worker_xy = augment_xy_data_by_8_fold(worker_xy)
                loc_xy = augment_xy_data_by_8_fold(loc_xy)
                node_demand = node_demand.repeat(8, 1)
            else:
                raise NotImplementedError

        self.loc_size = loc_xy.size(1)
        self.worker_size = worker_loc_idx.size(2)
        self.BATCH_IDX = torch.arange(self.batch_size)[:, None].expand(self.batch_size, self.pomo_size)
        self.POMO_IDX = torch.arange(self.pomo_size)[None, :].expand(self.batch_size, self.pomo_size)

        # 4-dimensional Index for jobs
        self.I4D_Batch = torch.arange(self.batch_size)[:,None,None,None]
        self.I4D_Pomo = torch.arange(self.pomo_size)[None,:,None,None]
        self.I4D_Worker = torch.arange(self.worker_size)[None,None,:,None]
        # self.I4D_Job = torch.arange(self. ? )[:,None,None,None]

        self.step_state.reset_state.BATCH_IDX = self.BATCH_IDX
        self.step_state.reset_state.POMO_IDX = self.POMO_IDX

        self.step_state.reset_state.loc_xy = loc_xy
        self.step_state.reset_state.worker_loc_idx = worker_loc_idx
        self.step_state.reset_state.job_loc_idx = job_loc_idx


    def reset(self):

        # 这是分配过程中的Visited，不是最后TSP的visited。
        # shape: (batch, pomo, self.job_size+1) # Worker location is the last one
        # self.current_job_idx = torch.zeros(size=(self.batch_size, self.pomo_size, 1)) + self.worker_size 

        self.step_state.current_job_idx = 0 # self.worker_size 
        self.step_state.ninf_mask = torch.zeros(size=(self.batch_size, self.pomo_size, self.worker_size))

        # shape: (batch, pomo)
        self.finished = (self.step_state.current_job_idx >= self.worker_size + self.job_size)

        # from pre_step
        self.step_state.worker_selected_loc_idx = self.step_state.reset_state.worker_loc_idx.clone()[:,:,:,None].repeat(
            1,1,1,self.max_job_in_worker_size
        )
        # shape: (batch, pomo, 0~)
        self.step_state.worker_selected_loc_length = torch.ones(
            (self.batch_size, self.pomo_size, self.worker_size), 
            dtype=torch.int64)
        # self.worker_selected_job_mask = torch.zeros((self.batch_size, self.pomo_size, self.worker_size, 0), dtype=torch.bool)


        reward = None
        done = False
        return self.step_state, reward, done

    def pre_step(self): 
        # self.step_state.worker_selected_loc_idx = torch.arange(0,self.worker_size)[None, None,:,None].repeat(
        #     self.batch_size, self.pomo_size,  
        #     1, self.max_job_in_worker_size
        # )

        reward = None
        done = False
        # self.step_state.current_job_idx = 0 # self.worker_size 
        # ninf_mask

        return self.step_state, reward, done


    def set_state_to_length(self, worker_loc_length, worker_selected_loc, enable_ninf_mask = None):

        with torch.no_grad():
            self.step_state.current_job_idx = 0 # self.worker_size 
            self.step_state.worker_selected_loc_length = worker_loc_length
            self.step_state.worker_selected_loc_idx = worker_selected_loc

            # 更新Tiled selected job idx.
            ####################################
            # 2.1. Convert worker_selected_loc_idx to tiled.
            self._calc_tiled_worker_selected_loc_idx()

            # self._calc_all_worker_locs_to_dispatch()

            # shape: (batch, pomo)
            
            reward = None
            self.step_state.ninf_mask = torch.zeros(size=(self.batch_size, self.pomo_size, self.worker_size))
            self.finished = done = False


            return self.step_state, reward, done

    def step(self, selected):
        # selected.shape: (batch, pomo, worker), containing bool value
        ## 

        # # shape: (batch, pomo, worker, max_job)
        # worker_selected_loc_idx: torch.Tensor = None
        # # shape: (batch, pomo, worker, max_job)
        # worker_selected_loc_length: torch.Tensor = None
        # # shape: (batch, pomo, worker, max_job)
        # ninf_mask: torch.Tensor = None

        # Do those steps:
        # 1. 更新idx，length
        # 2. 更新.step_state.ninf_mask

        # Dynamic-1 - 更新idx，length
        ####################################

        selected_worker_length = self.step_state.worker_selected_loc_length[
                self.BATCH_IDX, self.POMO_IDX, selected
            ].long()


        # selected_worker_idx = self.step_state.worker_selected_loc_idx[
        #     self.BATCH_IDX, self.POMO_IDX, selected, selected_worker_length
        #     ]

        current_job_loc_idx = self.step_state.reset_state.job_loc_idx[
            self.BATCH_IDX, self.POMO_IDX, self.step_state.current_job_idx]
        
        self.step_state.worker_selected_loc_idx[
            self.BATCH_IDX, self.POMO_IDX, selected, selected_worker_length
            ] = current_job_loc_idx

        self.step_state.worker_selected_loc_length[
                self.BATCH_IDX, self.POMO_IDX, selected
            ] = self.step_state.worker_selected_loc_length[
                self.BATCH_IDX, self.POMO_IDX, selected
            ] + 1
        
        self._calc_tiled_worker_selected_loc_idx()

        self.step_state.current_job_idx += 1
        
        # 2. 更新Tiled selected job idx.

        # 3. 更新.step_state.ninf_mask
        ####################################
        is_worker_full = self.step_state.worker_selected_loc_length >= self.max_job_in_worker_size
        self.step_state.ninf_mask[is_worker_full] = float('-inf')

        # returning values
        done = self.step_state.current_job_idx >=self.job_size
        if done:
            # reward = -self._get_travel_distance()  # note the minus sign!
            reward = 0-self._get_travel_distance_after_tsp()
        else:
            reward = None

        return self.step_state, reward, done

    def _calc_tiled_worker_selected_loc_idx(self):
        flatted_indexer_picker = self.step_state.worker_selected_loc_length.view(
            self.batch_size*self.pomo_size*self.worker_size
        ) 
        worker_job_gather_idx = self.tile_indexer[flatted_indexer_picker, :].view(
            self.batch_size,self.pomo_size,self.worker_size, self.max_job_in_worker_size)
        # bi=torch.arange(self.batch_size)
        new_worker_jobs = self.step_state.worker_selected_loc_idx[
            torch.arange(self.batch_size)[:,None,None,None], torch.arange(self.pomo_size)[None,:,None,None], 
            torch.arange(self.worker_size)[None,None,:,None], worker_job_gather_idx
            ]
        self.step_state.worker_selected_loc_idx = new_worker_jobs
        
    def _get_travel_distance(self):
        # TODO: TSP inside. 2022-02-27 22:32:07
        gathering_index = self.pad_indexer[self.step_state.worker_selected_loc_length.view(
            self.batch_size*self.pomo_size*self.worker_size 
            ),:].view(self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size)

        # shape: (batch, pomo, self.worker_size, self.max_job_in_worker_size)
        gathered_job_indexes = self.step_state.worker_selected_loc_idx[
                self.I4D_Batch, self.I4D_Pomo, self.I4D_Worker, gathering_index
            ][:,:,:,:, None].expand(-1, -1, -1,-1, 2) # add the last X,Y (long/lat) index

        all_xy = self.step_state.reset_state.loc_xy[:, None, None, :, :].expand(-1, self.pomo_size, self.worker_size, -1, -1)
        ordered_seq = all_xy.gather(dim=3, index=gathered_job_indexes)
        # shape: (batch, pomo, self.worker_size, self.max_job_in_worker_size, 2)

        rolled_seq = ordered_seq.roll(dims=3, shifts=-1)
        segment_lengths = ((ordered_seq-rolled_seq)**2).sum(4).sqrt()
        # shape: (batch, pomo, selected_list_length)

        travel_distances = segment_lengths.sum((2,3,))
        # shape: (batch, pomo)
        return travel_distances

    def _get_travel_distance_after_tsp(self):
        # TODO: TSP inside. 2022-02-27 22:32:07

        gathering_index = self.pad_indexer[self.step_state.worker_selected_loc_length.view(
            self.batch_size*self.pomo_size*self.worker_size 
            ),:].view(self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size)

        tsp_pad_mask_index = self.pad_masker[self.step_state.worker_selected_loc_length.view(
            self.batch_size*self.pomo_size*self.worker_size 
            ),:][:,None,:]

        # self.pad_masker

        # shape: (batch, pomo, self.worker_size, self.max_job_in_worker_size)
        tsp_gathered_job_indexes = self.step_state.worker_selected_loc_idx[
                self.I4D_Batch, self.I4D_Pomo, self.I4D_Worker, gathering_index
            ] # add the last X,Y (long/lat) index

        all_xy = self.step_state.reset_state.loc_xy[:, None, None, :, :].expand(-1, self.pomo_size, self.worker_size, -1, -1)
        ordered_jobs = all_xy.gather(
            dim=3, 
            index=tsp_gathered_job_indexes[:,:,:,:, None].expand(-1, -1, -1,-1, 2))
        # shape: (batch, pomo, self.woker_size, self.max_job_in_worker_size, 2)

        # save it for outside debugger
        # self.tsp_gathered_job_indexes = tsp_gathered_job_indexes
        travel_distances = self.solve_tsp_problem(ordered_jobs, tsp_pad_mask_index, tsp_gathered_job_indexes)
        # rolled_seq = ordered_seq.roll(dims=3, shifts=-1)
        # segment_lengths = ((ordered_seq-rolled_seq)**2).sum(4).sqrt()
        # travel_distances = segment_lengths.sum((2,3,))

        # Now I save the re-arranged job sequence in each worker from TSP ENV.
        self.step_state.worker_loc_idx_after_tsp = self.step_state.worker_selected_loc_idx[
            self.I4D_Batch, self.I4D_Pomo, self.I4D_Worker,
            self.tsp_env.selected_node_list.view(
                self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size
            )  
        ]

        return travel_distances


    def solve_tsp_problem(self, ordered_jobs, tsp_pad_mask_index, tsp_gathered_job_indexes):
        
        with torch.no_grad():
            tsp_batch_size = self.batch_size*self.pomo_size*self.worker_size
            self.tsp_env.problems = ordered_jobs.view(
                tsp_batch_size, self.max_job_in_worker_size, 2)

            self.tsp_env.batch_size = tsp_batch_size
            self.tsp_env.BATCH_IDX = torch.arange(tsp_batch_size)[:, None].expand(
                tsp_batch_size, self.tsp_env_params["pomo_size"])
            self.tsp_env.POMO_IDX = torch.arange(self.tsp_env_params["pomo_size"])[None, :].expand(
                tsp_batch_size, self.tsp_env_params["pomo_size"])

            step_state, _, done = self.tsp_env.reset()
            self.tsp_model.pad_mask = tsp_pad_mask_index

            # self.tsp_env.step_state.ninf_mask = self.tsp_env.step_state.ninf_mask + \


            self.tsp_model.pre_forward(step_state.reset_state)
            # state, reward, done = self.tsp_env.pre_step()

            while not done:
                selected, prob, probs = self.tsp_model(step_state)
                # shape: (batch, pomo*worker)
                step_state, reward, done = self.tsp_env.step(selected)
            # return self.get_tsp_travel_distance()

            return self.get_tsp_travel_distance_by_matrix(tsp_gathered_job_indexes)
    
    def get_tsp_travel_distance(self):
        # ,tsp_segments
        tsp_travel_distances = self.tsp_env._get_travel_distance()
        travel_distances = tsp_travel_distances.view(
            self.batch_size,self.pomo_size,self.worker_size
            ).sum(2)
        return travel_distances

    def get_tsp_travel_distance_by_matrix(self,tsp_gathered_job_indexes):

        ordered_seq = self.tsp_env.selected_node_list.view(
            self.batch_size, self.pomo_size,self.worker_size, self.max_job_in_worker_size,
        ) 
        ordered_nodes = self.ordered_nodes = tsp_gathered_job_indexes.gather(dim=3,index=ordered_seq)

        rolled_seq = ordered_seq.roll(dims=3, shifts=-1)
        rolled_nodes = self.rolled_nodes = tsp_gathered_job_indexes.gather(dim=3,index=rolled_seq)

        linear_index = ordered_nodes.view(
            self.batch_size, self.pomo_size*self.worker_size*self.max_job_in_worker_size
        ) * self.loc_size + rolled_nodes.view(
            self.batch_size, self.pomo_size*self.worker_size*self.max_job_in_worker_size
        )

        dist = self.dist_matrix.view(self.batch_size, self.loc_size**2)[ # (self.worker_size+self.job_size)
            torch.arange(self.batch_size)[:, None,],
            linear_index
        ] 

        # dist = self.dist_matrix[
        #     torch.arange(self.batch_size)[:, None, None,],
        #     ordered_seq.view(self.batch_size, self.pomo_size*self.worker_size*self.max_job_in_worker_size
        #     )[:, None, :,],
        #     rolled_seq.view(self.batch_size, self.pomo_size*self.worker_size*self.max_job_in_worker_size
        #     )[:,:, None, ]
        # ] 
        # print(dist.view(
        #     self.batch_size,self.pomo_size,self.worker_size,self.max_job_in_worker_size
        #     ) )
        travel_distances = dist.view(
            self.batch_size,self.pomo_size,self.worker_size*self.max_job_in_worker_size
            ).sum(2)
        return travel_distances
