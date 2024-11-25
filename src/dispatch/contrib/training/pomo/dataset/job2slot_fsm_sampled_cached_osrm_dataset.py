from logging import getLogger
from dispatch.config import ADDR_DIM
from dispatch.contrib.training.pomo.dataset.kandbox_dataset import KandboxDataset


from dispatch.contrib.training.pomo.dataset.job2slot_pickdrop_sampled_cached_osrm_dataset import OSRMSampleCachedDataset

# from dispatch.contrib.training.pomo.utils.utils import *
from dispatch.plugins.kandbox_planner.travel_time_plugin import OSRMTravelTime
# 
from torch.utils.data import DataLoader, Dataset
import pandas as pd
import numpy as np
import torch
import random

# def get_addr_list(batch_size, random_state):
def consume_cpu(steps = 1000_0000):
    return
    a=21
    # print(idx.start, idx.step, idx.start)
    for i in range(steps):
        a=a*a % 1000000 



class OSRMSampleCachedFSMDataset(OSRMSampleCachedDataset):

    def __init__(self, *args, **kwargs): 
        super(OSRMSampleCachedFSMDataset, self,).__init__(*args, **kwargs)
        self.worker_loc_size = self.worker_size
        self.job_loc_size = self.job_size*2
        # self.episode_loc_size

    def __getitem__(self,idx):
        self._refresh_distance_matrix_cache(idx)

        self.curr_worker_cache_idx = np.random.permutation(self.worker_cache_size)[0:self.worker_size]
        self.curr_job_cache_idx = np.random.permutation(self.job_cache_size)[:self.job_size] + (self.worker_cache_size)

        self.curr_job_cache_idx_drop = self.curr_job_cache_idx + self.job_cache_size
        # self.curr_job_cache_idx = torch.cat(
        self.curr_job_cache_idx = np.concatenate(
            (self.curr_worker_cache_idx,
            self.curr_job_cache_idx,
            self.curr_job_cache_idx_drop),
            axis=0
        )
        curr_job_cache_idx_x = self.curr_job_cache_idx.view().reshape(self.episode_loc_size,1).repeat(
            repeats = self.episode_loc_size, axis = 1)
        curr_job_cache_idx_y = self.curr_job_cache_idx.view().reshape(1, self.episode_loc_size).repeat(
            repeats = self.episode_loc_size, axis = 0)

        # addr = np.array(addr_list )
        matrix = (self.distance_matrix_cache_t[curr_job_cache_idx_x, curr_job_cache_idx_y]).clone().detach()
        # matrix = torch.tensor(matrix_np, device="cpu")

        # addr_list = self.curr_addr_list_t[self.curr_job_cache_idx,:]
        # addr = torch.tensor(addr_list, device="cpu")
        addr = self.curr_addr_list_t[self.curr_job_cache_idx,:].clone().detach()

        addr[:,0] = (addr[:,0] - self.geo_longitude_min) * 2
        addr[:,1] = (addr[:,1] - self.geo_latitude_min) * 2

        worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask = self.create_worker_job_batch4single() 
        return addr, matrix, worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask



class SingleENUUniformDataset(KandboxDataset):
    def __init__(self, 
        manual_seed = None, env_config = None, pomo_size = 8, 
        dataset_name = "london",
        osrm_url = ("http://192.168.9.251:5001",),
        random_sample_seed = True,
        worker_size = 8,
        job_size = 21, 
        use_distance_matrix_cache = True,
        max_dm_count = 16*32,
        ): 

        super(SingleENUUniformDataset, self,).__init__(
            pomo_size, worker_size, job_size, osrm_url,        
        )

        self.dataset_name = dataset_name  
        self.worker_size = worker_size 
        self.job_size = job_size
        self.episode_loc_size = self.worker_size + (self.job_size*2)
        self.pomo_size = pomo_size
        self.geo_longitude_min = self.geo_latitude_min = 0



    def __getitem__(self,idx): 

        addr, matrix = self.get_addr_dist_mat()
        if ADDR_DIM > 2:
            # I will attach the 3rd dimension of addr as allowed_time.
            end_minutes_1 =  torch.rand(( self.job_size,1), device="cpu") 
            # np.random.randint(0,100,size=(self.job_cache_size))
            job_end_minutes = torch.cat( (
                torch.zeros(self.worker_size, 1, device="cpu") +1,
                    end_minutes_1,
                    end_minutes_1 + 0.4,
                ), dim = 0
            ).float()#[None,:,:].repeat(batch_size,1,1) 

            pick_drop_ind_1 = torch.zeros(( self.worker_size+self.job_size,1), device="cpu") 
            pick_drop_ind_2 = torch.ones((self.job_size,1), device="cpu") 
            pick_drop_ind = torch.cat( (pick_drop_ind_1,pick_drop_ind_2), dim = 0).float() 

            addr =  torch.cat( (addr, job_end_minutes, pick_drop_ind), dim = 1).float()


        worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask = self.create_worker_job_batch4single() 

        return addr, matrix, worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask
    def get_addr_dist_mat(self,): 
        addr = torch.FloatTensor(self.worker_loc_size + self.job_loc_size, 2 ).uniform_(self.uniform_min, self.uniform_max).to(self.DATASET_DEVICE)
        # Recover orginal 10KM scale and calculate the distance.
        matrix = torch.cdist(addr*self.minute_scale,addr*self.minute_scale, p=2)
        return addr, matrix

class SingleENUSampledDataset(SingleENUUniformDataset):
    def get_addr_dist_mat(self,): 
        worker_loc = np.random.multivariate_normal(self.mean, self.cov, self.worker_size) 
        pick_loc = np.random.multivariate_normal(self.mean, self.cov, self.job_size) 
        drop_loc_1 = np.random.multivariate_normal(self.mean, self.cov, self.job_size) 

        move_covariance = [[0.2, 0], [0, 0.2]]
        x = np.random.multivariate_normal(self.mean, move_covariance, self.job_size * 5 + 20) 
        move =[]
        for i in range(x.shape[0]): 
            if abs(x[i][0]) +  abs(x[i][1]) < 0.1:
                continue
            if abs(x[i][0]) +  abs(x[i][1]) > 0.65:
                continue
            move.append(x[i].tolist())
            if len(move) >= self.job_size:
                break
        move_np = np.array(move)
        drop_loc = drop_loc_1 + move_np
        self.addr_np = np.concatenate(
            (worker_loc, pick_loc,drop_loc),
            axis=0
        )
        addr = torch.tensor(self.addr_np, device="cpu").float()
        # Recover orginal 10KM scale and calculate the distance.
        matrix = torch.cdist(addr*self.minute_scale,addr*self.minute_scale, p=2)
        return addr, matrix
