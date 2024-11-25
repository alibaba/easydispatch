from dataclasses import dataclass
# from pandas import wide_to_long
import torch
import numpy as np
from itertools import cycle, islice
from dispatch.config import ALLOWED_MAXIMUM_MINUTES
from dispatch.contrib.training.pomo.pick_drop_tsp.pick_drop_tsp_env import PickDropTSPEnv 
from dispatch.contrib.training.pomo.pick_drop_tsp.pick_drop_tsp_model import PickDropTSPModel
from dispatch.contrib.training.pomo.pick_drop_tsp_with_start.pick_drop_tsp_with_start_env import PickDropWithStartTSPEnv
from dispatch.contrib.training.pomo.pick_drop_tsp_with_start.pick_drop_tsp_with_start_model import PickDropWithStartTSPModel 

@dataclass
class Reset_State:
    worker_size: int = 0
    job_size: int = 0
    worker_loc_idx: torch.Tensor = None
    # shape: (batch, worker_size, 1)
    job_loc_idx: torch.Tensor = None
    # shape: (batch, job_size, 1)
    loc_xy: torch.Tensor = None
    # shape: (batch, worker_size+job_size, loc_dim)

    # worker_attr: torch.Tensor = None
    # # shape: (batch, worker_size, loc_dim)
    # node_attr: torch.Tensor = None
    # # shape: (batch, job, 2)
    BATCH_IDX: torch.Tensor = None
    POMO_IDX: torch.Tensor = None
    loc_dim: int = 3
    allowed_maximum_minutes: int = ALLOWED_MAXIMUM_MINUTES
    allowed_minutes_importance: int = 0.1



@dataclass
class Step_State:

    # shape: (batch, pomo, worker, max_job)
    scheduled_job_idx: torch.Tensor = None

    # This one is before the TSP, following sequence of:
    # pick_1, drop_1, pick_2,drop_2,....
    # shape: (batch, pomo, worker, max_job)
    worker_selected_loc_idx: torch.Tensor = None

    # This one is the location sequence after the TSP:
    # Could be pick_1,pick_2,drop_2, drop_1,....
    # shape: (batch, pomo, worker, max_job)
    worker_loc_idx_after_tsp: torch.Tensor = None
    all_worker_locs_to_dispatch: torch.Tensor = None

    # shape: (batch, pomo, worker, max_job)
    worker_selected_loc_length: torch.Tensor = None

    # shape: (batch, pomo, worker, max_job)
    ninf_mask: torch.Tensor = None

    current_job_idx: int = None

    reset_state: Reset_State = None


class PickDropJob2SlotEnv:
    def __init__(self, env_params, model_params):

        # Const @INIT
        ####################################
        self.env_params = env_params
        self.model_params = model_params
        
        self.worker_size = env_params['worker_size']
        self.num_pairs = int(env_params['job_size'] / 2)
        self.loc_size = env_params['worker_size'] + env_params['job_size']
        self.max_job_in_worker_size = env_params['max_job_in_worker_size']
        assert self.max_job_in_worker_size % 2 == 0, "max_job_in_worker_size must be even"
        self.nbr_original_job_in_worker = int(self.max_job_in_worker_size / 2)
        self.pomo_size = env_params['pomo_size']
        # self.batch_size = 1

        self.FLAG__use_saved_jobs = False
        self.saved_worker_xy = None
        self.saved_loc_xy = None
        self.saved_node_demand = None
        self.saved_index = None

        # TSP Env
        self.tsp_env_params = dict(env_params)
        self.tsp_env_params.update({
            'problem_size': env_params['max_job_in_worker_size'],
            'pomo_size': 1, # self.worker_size * self.pomo_size, #1,
            'serving_only_n_no_reward': True,
        }) 
        self.tsp_model_params = dict(model_params)
        self.tsp_model_params.update({
            'eval_type': 'argmax', 
        })

        # self.tsp_env = PickDropTSPEnv(env_params = self.tsp_env_params)
        # self.tsp_model = PickDropTSPModel(self.tsp_model_params)
        self.tsp_env = PickDropWithStartTSPEnv(env_params = self.tsp_env_params)
        self.tsp_model = PickDropWithStartTSPModel(self.tsp_model_params)

        # Load a pretrained TSP model as sub-model of Job2Slot
        file_name = self.env_params['tsp_model_path']
        checkpoint = torch.load(file_name, map_location=self.env_params["device"])
        self.tsp_model.load_state_dict(checkpoint['model_state_dict'])

        self.tsp_model.eval()
        print(f"Loaded inner TSP model for PickDropJob2SlotEnv from: {file_name}")
        

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

            _pd_mask = [float("-inf")] + [0 for _ in range(i-1)] + [-pi*1e10 for pi in range(i,MAX_NBR_JOB_IN_WORKER+1)]
            for pi in range(1,min(i,9),2):
                _pd_mask[pi+1]=-pi*1e20
            pad_mask.append(_pd_mask)


            _next_list = [MAX_NBR_JOB_IN_WORKER for _ in range(MAX_NBR_JOB_IN_WORKER)]
            for pi in range(1,min(i,9),2):
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
    def use_saved_jobs(self, filename, device):
        self.FLAG__use_saved_jobs = True

        loaded_dict = torch.load(filename, map_location=device)
        self.saved_worker_xy = loaded_dict['worker_xy']
        self.saved_loc_xy = loaded_dict['loc_xy']
        self.saved_node_demand = loaded_dict['node_demand']
        self.saved_index = 0

    def load_jobs(self, 
        loc_xy = None, 
        dist_matrix= None,
        worker_loc_idx = None,
        job_loc_idx = None,
        next_job_idx = None,
        next_job_mask = None,
        aug_factor=1, 
        ):
        
        self.batch_size = batch_size = loc_xy.size(0)

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


        self.BATCH_IDX = torch.arange(self.batch_size)[:, None].expand(self.batch_size, self.pomo_size)
        self.POMO_IDX = torch.arange(self.pomo_size)[None, :].expand(self.batch_size, self.pomo_size)
        self.step_state.reset_state.BATCH_IDX = self.BATCH_IDX
        self.step_state.reset_state.POMO_IDX = self.POMO_IDX

        self.step_state.reset_state.worker_size = self.worker_size = worker_loc_idx.size(2)
        self.step_state.reset_state.job_size = self.num_pairs = job_loc_idx.size(2)


        # 4-dimensional Index for jobs
        self.I4D_Batch = torch.arange(self.batch_size)[:,None,None,None]
        self.I4D_Pomo = torch.arange(self.pomo_size)[None,:,None,None]
        self.I4D_Worker = torch.arange(self.worker_size)[None,None,:,None]
        # self.I4D_Job = torch.arange(self. ? )[:,None,None,None]


        self.step_state.reset_state.loc_xy = loc_xy
        self.step_state.reset_state.loc_dim = loc_xy.size(2)
        self.loc_size = loc_xy.size(1)
        self.step_state.reset_state.worker_loc_idx = worker_loc_idx
        self.step_state.reset_state.job_loc_idx = job_loc_idx
        
        # self.step_state.reset_state.next_job_idx = next_job_idx


    def reset(self):

        # 这是分配过程中的Visited，不是最后TSP的visited。
        # shape: (batch, pomo, self.num_pairs+1) # Worker location is the last one
        # self.current_job_idx = torch.zeros(size=(self.batch_size, self.pomo_size, 1)) + self.worker_size 
        with torch.no_grad():
            self.step_state.current_job_idx = 0 # self.worker_size  # 
            self.step_state.ninf_mask = torch.zeros(size=(self.batch_size, self.pomo_size, self.worker_size))

            self.step_state.scheduled_job_idx = self.step_state.reset_state.worker_loc_idx.clone()[:,:,:,None].repeat(
                1,1,1, self.nbr_original_job_in_worker + 1
            )

            # self.step_state.worker_selected_loc_idx = torch.arange(0,self.worker_size)[None, None,:,None].repeat(
            #     self.batch_size, self.pomo_size,  
            #     1, self.max_job_in_worker_size
            # )
            self.step_state.worker_selected_loc_idx = self.step_state.reset_state.worker_loc_idx.clone()[:,:,:,None].repeat(
                1,1,1, self.max_job_in_worker_size
            )
            # shape: (batch, pomo, 0~)
            self.step_state.worker_selected_loc_length = torch.ones(
                (self.batch_size, self.pomo_size, self.worker_size), 
                dtype=torch.int64)
            self._calc_all_worker_locs_to_dispatch()
            # self.worker_selected_job_mask = torch.zeros((self.batch_size, self.pomo_size, self.worker_size, 0), dtype=torch.bool)

            # shape: (batch, pomo)
            done = self.finished = (self.step_state.current_job_idx >= self.num_pairs)
            reward = None
            return self.step_state, reward, done


    def set_state_to_length(self, worker_loc_length, worker_selected_loc):

        # 这是分配过程中的Visited，不是最后TSP的visited。
        # shape: (batch, pomo, self.num_pairs+1) # Worker location is the last one
        # self.current_job_idx = torch.zeros(size=(self.batch_size, self.pomo_size, 1)) + self.worker_size 
        with torch.no_grad():
            self.step_state.current_job_idx = 0 # self.worker_size  # 
            self.step_state.ninf_mask = torch.zeros(size=(self.batch_size, self.pomo_size, self.worker_size))


            self.step_state.worker_selected_loc_length = worker_loc_length
            self.step_state.worker_selected_loc_idx = worker_selected_loc
            # 更新Tiled selected job idx.
            ####################################
            # 2.1. Convert worker_selected_loc_idx to tiled.
            self._calc_tiled_worker_selected_loc_idx()

            self._calc_all_worker_locs_to_dispatch()

            # shape: (batch, pomo)
            done = False
            reward = None
            return self.step_state, reward, done

    def pre_step(self): 

        reward = None
        done = False
        # self.step_state.current_job_idx = 0 # self.worker_size 
        # ninf_mask

        return self.step_state, reward, done

    def step(self, selected):
        # worker_selected_loc_idx shape: (batch, pomo, worker, max_job)
        # worker_selected_loc_length shape: (batch, pomo, worker)
        # ninf_mask: torch.Tensor = None
        with torch.no_grad():
            # Do those
            # 1. 更新idx，length
            # 2. convert to tiled idx
            # 3. 更新.step_state.ninf_mask

            # 1 - 更新 scheduled_job_idx, loc_idx, length
            ####################################

            selected_worker_length = self.step_state.worker_selected_loc_length[
                    self.BATCH_IDX, self.POMO_IDX, selected
                ] .long()
            curr_job_i = self.step_state.current_job_idx 

            # 2022-03-22 01:54:35: scheduled_job_idx is job idx and worker_selected_loc_idx is loc idx.
            selected_worker_original_job_length = (((selected_worker_length - 1) / 2) + 1).long()
            self.step_state.scheduled_job_idx[
                self.BATCH_IDX, self.POMO_IDX, selected, selected_worker_original_job_length
                ] = curr_job_i + self.worker_size

            self.step_state.worker_selected_loc_idx[
                self.BATCH_IDX, self.POMO_IDX, selected, selected_worker_length 
                ] = self.step_state.reset_state.job_loc_idx[:,:,curr_job_i,0]

            self.step_state.worker_selected_loc_idx[
                self.BATCH_IDX, self.POMO_IDX, selected, selected_worker_length+1
                ] = self.step_state.reset_state.job_loc_idx[:,:,curr_job_i,1]

            self.step_state.worker_selected_loc_length[
                    self.BATCH_IDX, self.POMO_IDX, selected
                ] = self.step_state.worker_selected_loc_length[
                    self.BATCH_IDX, self.POMO_IDX, selected
                ] + 2

            # 2. 更新Tiled selected job idx.
            ####################################
            # 2.1. Convert worker_selected_loc_idx to tiled.
            self._calc_tiled_worker_selected_loc_idx()
            self.step_state.current_job_idx += 1

            # 3. 更新.step_state.ninf_mask
            ####################################
            is_worker_full = self.step_state.worker_selected_loc_length >= (self.max_job_in_worker_size - 1)
            self.step_state.ninf_mask[is_worker_full] = float('-inf')

            # 4. Final, returning reward 
            ####################################
            reward = 0
            done = self.step_state.current_job_idx >= self.num_pairs # self.worker_size + 
            if done or self.env_params["solve_tsp_in_each_step"]:
                # reward = -self._get_travel_distance()  # note the minus sign!
                # 2022-12-25 10:51:47, this was for converting batch,pomo,worker all into batch
                reward = 0-self._get_travel_distance_after_tsp()
                # reward = 0-self._get_travel_distance_after_pomo_worker_tsp() #, 2022-12-25 10:51:47, this was for converting pomo,worker into pomo, but faied.
            else:
                self._calc_all_worker_locs_to_dispatch()

            return self.step_state, reward, done

    def _calc_tiled_worker_selected_loc_idx(self):
            flatted_indexer_picker = self.step_state.worker_selected_loc_length.view(
                self.batch_size*self.pomo_size*self.worker_size
            )

            worker_job_gather_idx = self.tile_indexer[flatted_indexer_picker, :].view(
                self.batch_size,self.pomo_size,self.worker_size, self.max_job_in_worker_size)
            
            new_worker_jobs = self.step_state.worker_selected_loc_idx[
                torch.arange(self.batch_size)[:,None,None,None], torch.arange(self.pomo_size)[None,:,None,None], 
                torch.arange(self.worker_size)[None,None,:,None], worker_job_gather_idx
                ]
            self.step_state.worker_selected_loc_idx = new_worker_jobs

            # 2.2 convert scheduled_job_idx to tiled.
            # worker_original_job_length = (((self.step_state.worker_selected_loc_length - 1) / 2) + 1).long()
            # flatted_indexer_picker = worker_original_job_length.view(
            #     self.batch_size*self.pomo_size*self.worker_size
            # )
            # worker_orig_job_gather_idx = self.tile_indexer[flatted_indexer_picker, :].view(
            #     self.batch_size,self.pomo_size,self.worker_size, self.max_job_in_worker_size)[:,:,:,0:self.nbr_original_job_in_worker+1]
            # new_jobs = self.step_state.scheduled_job_idx[
            #     torch.arange(self.batch_size)[:,None,None,None], torch.arange(self.pomo_size)[None,:,None,None], 
            #     torch.arange(self.worker_size)[None,None,:,None], worker_orig_job_gather_idx
            #     ]
            # self.step_state.scheduled_job_idx = new_jobs

            
    def _calc_all_worker_locs_to_dispatch(self):
        batch_size, pomo_size, worker_size,max_job_in_worker_size = self.step_state.worker_selected_loc_idx.size()

        worker_loc_index = self.step_state.worker_selected_loc_idx[:,:,:,0:max_job_in_worker_size].view(
            batch_size*pomo_size,
            worker_size*max_job_in_worker_size, 
        )

        curr_job_i = self.step_state.current_job_idx  

        wt = self.step_state.reset_state.job_loc_idx[:,:,curr_job_i
            ].repeat(
            1,1, int(max_job_in_worker_size/2)
        ).view(batch_size*pomo_size, max_job_in_worker_size)

        self.new_job_as_worker_t = torch.cat((wt[:,0:1], wt[:,2:10], wt[:,0:1]),dim = 1)

        temp1 =  torch.cat((worker_loc_index, self.new_job_as_worker_t),dim = 1)

        all_worker_loc_indice =temp1.view(
            batch_size,
            pomo_size * (worker_size + 1) * max_job_in_worker_size, 
        )
        all_worker_locs = self.step_state.reset_state.loc_xy.gather(
            dim=1, index=all_worker_loc_indice[:,:,None].expand(-1,-1,self.step_state.reset_state.loc_dim)
        ).view(
            batch_size,pomo_size,
            (worker_size + 1)  , #TODO,  Why + 1, 2022-12-25 03:22:21
            max_job_in_worker_size*self.step_state.reset_state.loc_dim # Here every 10-job-path for each worker is one vector to be transformed.
        )
        self.step_state.all_worker_locs_to_dispatch = all_worker_locs

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


    def _get_travel_distance_after_pomo_worker_tsp(self):
        # 2022-12-25 10:52:14, I will use POMO+Worker as POMO, batch as batch
        # The problem on this approach is that it does not deduct last trip (back to depot) correctly, since the inside TSP env does not know length

        flat_length = self.step_state.worker_selected_loc_length.view(
            self.batch_size*self.pomo_size*self.worker_size 
            )

        tsp_next_job_index = self.next_job_indexer[flat_length,:].view(
            self.batch_size, self.pomo_size*self.worker_size, self.max_job_in_worker_size)

        tsp_pad_mask = self.pad_masker[flat_length,:].view(
            self.batch_size, self.pomo_size*self.worker_size, self.max_job_in_worker_size+1)

        tsp_time_cumsum_mask = self.time_cumsum_masker[flat_length,:].view(
            self.batch_size, self.pomo_size*self.worker_size, self.max_job_in_worker_size)

        # self.pad_masker

        gathering_index = self.pad_indexer[flat_length,:].view(
            self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size)
        # shape: (batch, pomo, self.worker_size, self.max_job_in_worker_size)
        tsp_gathered_job_indexes = self.step_state.worker_selected_loc_idx[
                self.I4D_Batch, self.I4D_Pomo, self.I4D_Worker, gathering_index
            ].view(self.batch_size, self.pomo_size*self.worker_size, self.max_job_in_worker_size) # add the last X,Y (long/lat) index

        # all_xy = self.step_state.reset_state.loc_xy[:, None, None, :, :].expand(-1, self.pomo_size, self.worker_size, -1, -1)
        # ordered_jobs = all_xy.gather(
        #     dim=3, 
        #     index=tsp_gathered_job_indexes[:,:,:,:, None].expand(-1, -1, -1,-1, self.step_state.reset_state.loc_dim))
        # shape: (batch, pomo, self.woker_size, self.max_job_in_worker_size, loc_dim)

        # save it for outside debugger
        # self.tsp_gathered_job_indexes = tsp_gathered_job_indexes
        # solve_tsp_problem

        with torch.no_grad():
            tsp_batch_size = self.batch_size
            tsp_batch_size = self.pomo_size * self.worker_size
            # self.tsp_env.batch_size = tsp_batch_size
            # _job_loc_idx = torch.arange(self.max_job_in_worker_size)[None,None, :].repeat(tsp_batch_size,1, 1)
            self.tsp_env.load_jobs(
                loc_xy = self.step_state.reset_state.loc_xy,
                dist_matrix=self.dist_matrix,
                worker_loc_idx=None,
                job_loc_idx=tsp_gathered_job_indexes,
                next_job_idx=tsp_next_job_index, #.view(tsp_batch_size,1, self.max_job_in_worker_size),
                next_job_mask=tsp_pad_mask, #.view(tsp_batch_size,1, self.max_job_in_worker_size+1),
            )

            # self.tsp_env.BATCH_IDX = torch.arange(tsp_batch_size)[:, None].expand(
            #     tsp_batch_size, self.tsp_env_params["pomo_size"])
            # self.tsp_env.POMO_IDX = torch.arange(self.tsp_env_params["pomo_size"])[None, :].expand(
            #     tsp_batch_size, self.tsp_env_params["pomo_size"])

            step_state, _, _ = self.tsp_env.reset()
            # self.tsp_model.pad_mask = tsp_pad_mask

            # self.tsp_env.step_state.ninf_mask = self.tsp_env.step_state.ninf_mask + \


            self.tsp_model.pre_forward(step_state.reset_state)
            state, reward, done = self.tsp_env.pre_step()

            while not done:
                selected, prob, probs = self.tsp_model(state)
                # shape: (batch, pomo*worker)
                state, reward, done = self.tsp_env.step(selected)

            # print(f"loc_xy = {self.step_state.reset_state.loc_xy [0].tolist()}") 
            # return self.get_tsp_travel_distance()
            # return self.get_tsp_travel_distance_by_matrix(tsp_gathered_job_indexes)



        
        # travel_distances = reward.view(self.batch_size,self.pomo_size,self.worker_size*1)
        travel_distances1 = self.get_tsp_travel_distance_by_matrix(
            tsp_gathered_job_indexes.view(self.batch_size, self.pomo_size,self.worker_size, self.max_job_in_worker_size),
            tsp_time_cumsum_mask.view(self.batch_size, self.pomo_size,self.worker_size, self.max_job_in_worker_size)
            )

        # Now I save the re-arranged job sequence in each worker from TSP ENV.
        self.step_state.worker_loc_idx_after_tsp = self.step_state.worker_selected_loc_idx[
            self.I4D_Batch, self.I4D_Pomo, self.I4D_Worker,
            self.tsp_env.selected_node_list.view(
                self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size
            )  
        ]
        # rolled_seq = ordered_seq.roll(dims=3, shifts=-1)
        # segment_lengths = ((ordered_seq-rolled_seq)**2).sum(4).sqrt()
        # travel_distances = segment_lengths.sum((2,3,))

        return travel_distances1



    def _get_travel_distance_after_tsp(self):
        # TODO: TSP inside. 2022-02-27 22:32:07

        flat_length = self.step_state.worker_selected_loc_length.view(
            self.batch_size*self.pomo_size*self.worker_size 
            )

        tsp_next_job_index = self.next_job_indexer[flat_length,:].view(
            self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size)

        gathering_index = self.pad_indexer[flat_length,:].view(
            self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size)

        tsp_pad_mask = self.pad_masker[flat_length,:].view(
            self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size+1)

        # self.pad_masker
        tsp_time_cumsum_mask = self.time_cumsum_masker[flat_length,:].view(
            self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size)

        # shape: (batch, pomo, self.worker_size, self.max_job_in_worker_size)
        tsp_gathered_job_indexes = self.step_state.worker_selected_loc_idx[
                self.I4D_Batch, self.I4D_Pomo, self.I4D_Worker, gathering_index
            ] # add the last X,Y (long/lat) index

        all_xy = self.step_state.reset_state.loc_xy[:, None, None, :, :].expand(-1, self.pomo_size, self.worker_size, -1, -1)
        ordered_jobs = all_xy.gather(
            dim=3, 
            index=tsp_gathered_job_indexes[:,:,:,:, None].expand(-1, -1, -1,-1, self.step_state.reset_state.loc_dim))
        # shape: (batch, pomo, self.woker_size, self.max_job_in_worker_size, loc_dim)

        # save it for outside debugger
        # self.tsp_gathered_job_indexes = tsp_gathered_job_indexes
        self.solve_tsp_problem(
            ordered_jobs, tsp_pad_mask, tsp_next_job_index
            )

        travel_distances = self.get_tsp_travel_distance_by_matrix(tsp_gathered_job_indexes, tsp_time_cumsum_mask)

        # Now I save the re-arranged job sequence in each worker from TSP ENV.
        self.step_state.worker_loc_idx_after_tsp = self.step_state.worker_selected_loc_idx[
            self.I4D_Batch, self.I4D_Pomo, self.I4D_Worker,
            self.tsp_env.selected_node_list.view(
                self.batch_size, self.pomo_size, self.worker_size, self.max_job_in_worker_size
            )  
        ]
        # rolled_seq = ordered_seq.roll(dims=3, shifts=-1)
        # segment_lengths = ((ordered_seq-rolled_seq)**2).sum(4).sqrt()
        # travel_distances = segment_lengths.sum((2,3,))

        return travel_distances


    def solve_tsp_problem(self, ordered_jobs, tsp_pad_mask, tsp_next_job_index): # , nbr_initial_fixed = 1
        
        with torch.no_grad():
            batch_size,pomo_size,worker_size, max_job_in_worker_size, _ = ordered_jobs.size()
            tsp_batch_size = batch_size* pomo_size* worker_size
            # self.tsp_env.batch_size = tsp_batch_size
            _job_loc_idx = torch.arange(self.max_job_in_worker_size)[None,None, :].repeat(tsp_batch_size,1, 1)
            self.tsp_env.load_jobs(
                loc_xy = ordered_jobs.view(tsp_batch_size, self.max_job_in_worker_size, self.step_state.reset_state.loc_dim),
                dist_matrix=None,
                worker_loc_idx=None,
                job_loc_idx=_job_loc_idx,
                next_job_idx=tsp_next_job_index.view(tsp_batch_size,1, self.max_job_in_worker_size),
                next_job_mask=tsp_pad_mask.view(tsp_batch_size,1, self.max_job_in_worker_size+1),
            )

            # self.tsp_env.BATCH_IDX = torch.arange(tsp_batch_size)[:, None].expand(
            #     tsp_batch_size, self.tsp_env_params["pomo_size"])
            # self.tsp_env.POMO_IDX = torch.arange(self.tsp_env_params["pomo_size"])[None, :].expand(
            #     tsp_batch_size, self.tsp_env_params["pomo_size"])

            step_state, _, _ = self.tsp_env.reset()
            # self.tsp_model.pad_mask = tsp_pad_mask

            # self.tsp_env.step_state.ninf_mask = self.tsp_env.step_state.ninf_mask + \


            self.tsp_model.pre_forward(step_state.reset_state)
            state, reward, done = self.tsp_env.pre_step()

            while not done:
                selected, prob, probs = self.tsp_model(state)
                # shape: (batch, pomo*worker)
                state, reward, done = self.tsp_env.step(selected)

            # print(f"loc_xy = {self.step_state.reset_state.loc_xy [0].tolist()}") 
            # return self.get_tsp_travel_distance()
            # return self.get_tsp_travel_distance_by_matrix(tsp_gathered_job_indexes)

        return True
    
    def get_tsp_travel_distance(self):
        # ,tsp_segments
        tsp_travel_distances = self.tsp_env._get_travel_distance()
        travel_distances = tsp_travel_distances.view(
            self.batch_size,self.pomo_size,self.worker_size
            ).sum(2)
        return travel_distances

    def get_tsp_travel_distance_by_matrix(self,tsp_gathered_job_indexes, tsp_time_cumsum_mask):
        # self.tsp_env.dist_matrix is None, and can not calculate distance.
        # other_dist = self.tsp_env._get_travel_distance_by_matrix()

        ordered_seq = self.tsp_env.selected_node_list.view(
            self.batch_size, self.pomo_size,self.worker_size, self.max_job_in_worker_size,
        ) 
        ordered_nodes = self.ordered_nodes = tsp_gathered_job_indexes.gather(dim=3,index=ordered_seq)

        rolled_seq = ordered_seq.roll(dims=3, shifts=-1)
        rolled_nodes = self.rolled_nodes = tsp_gathered_job_indexes.gather(dim=3,index=rolled_seq)

        linear_index = ordered_nodes.view(
            self.batch_size, self.pomo_size*self.worker_size*self.max_job_in_worker_size
        ) * (self.loc_size) + rolled_nodes.view(
            self.batch_size, self.pomo_size*self.worker_size*self.max_job_in_worker_size
        )

        dist = self.dist_matrix.view(self.batch_size, self.loc_size**2)[
            torch.arange(self.batch_size)[:, None,],
            linear_index
        ].view(self.batch_size,self.pomo_size,self.worker_size, self.max_job_in_worker_size)

        # I will then calculate last trip from Tail to Head, and deduct this trip from overall TSP travel.
        head_seq = ordered_nodes[:,:,:,0].view(
            self.batch_size, self.pomo_size,self.worker_size,1
        ) 
        tail_seq = ordered_nodes.gather(dim=3,index=(self.step_state.worker_selected_loc_length-1)[:,:,:,None])

        tail2head_linear_index = tail_seq.view(
            self.batch_size, self.pomo_size*self.worker_size 
        ) * (self.loc_size) + head_seq.view(
            self.batch_size, self.pomo_size*self.worker_size 
        )
        tail2head_dist = self.dist_matrix.view(self.batch_size, self.loc_size**2)[
            torch.arange(self.batch_size)[:, None,],
            tail2head_linear_index
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
        all_dist = torch.cat((
            dist,
            (0-tail2head_dist).view(self.batch_size,self.pomo_size,self.worker_size, 1),
        ), dim = 3
        )

        travel_distances = all_dist.view(
            self.batch_size,self.pomo_size,-1
        ).sum(2)
        # worker_i = 3
        # print(f"jobs = locs = loc_xy = {self.tsp_env.step_state.reset_state.loc_xy [worker_i].tolist()}") 
        # print(f"next_jobs = {self.tsp_env.next_job_idx[worker_i,0].tolist()}") 
        # print(f"solution = {self.tsp_env.selected_node_list[worker_i,0].tolist()}") 
        if tsp_time_cumsum_mask is not None:
            # Now I calculate the time limit penalty (cumsum of minutes as arrival)
            dist_cumsum = torch.cumsum(dist, dim=3)
            dist_cumsum = dist_cumsum.roll(dims=3, shifts=1)
            dist_cumsum[:,:,:,0] = 0
            dist_cumsum = dist_cumsum * tsp_time_cumsum_mask
            
            allowed_cumsum = self.step_state.reset_state.loc_xy[:,:,2] [
                torch.arange(self.batch_size)[:,None,None,None],
                ordered_nodes
            ] * self.step_state.reset_state.allowed_maximum_minutes

            missed_minutes = dist_cumsum - allowed_cumsum
            missed_minutes[missed_minutes < 0] = 0
            total_missed_minutes = missed_minutes.view(
                self.batch_size,self.pomo_size,-1
            ).sum(2)*self.step_state.reset_state.allowed_minutes_importance * 2 # TODO, temp improve importance.

        else:
            total_missed_minutes = 0
        return travel_distances + total_missed_minutes
