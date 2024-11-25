from logging import getLogger
from dispatch.config import ADDR_DIM


from dispatch.contrib.training.pomo.dataset.job2slot_pickdrop_sampled_cached_osrm_dataset import OSRMRandomLocationSampleCachedDataset, OSRMSampleCachedDataset

# from dispatch.contrib.training.pomo.utils.utils import *
# from dispatch.plugins.kandbox_planner.travel_time_plugin import OSRMTravelTime
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



class OSRMSampleCachedTSPWithStartDataset(OSRMSampleCachedDataset):

    def __getitem__(self,idx):
        self._refresh_distance_matrix_cache(idx)

        self.curr_worker_cache_idx = np.random.permutation(self.worker_cache_size)[0:self.worker_size]
        self.curr_job_cache_idx_pick = np.random.permutation(self.job_cache_size)[:self.job_size] + (self.worker_cache_size)

        self.curr_job_cache_idx_drop = self.curr_job_cache_idx_pick + self.job_cache_size
        # self.curr_job_cache_idx = torch.cat(
        self.curr_job_cache_idx = np.concatenate(
            (self.curr_worker_cache_idx,
            self.curr_job_cache_idx_pick,
            self.curr_job_cache_idx_drop),
            axis=0
        )
        curr_job_cache_idx_x = self.curr_job_cache_idx.view().reshape(self.episode_loc_size,1).repeat(
            repeats = self.episode_loc_size, axis = 1)
        curr_job_cache_idx_y = self.curr_job_cache_idx.view().reshape(1, self.episode_loc_size).repeat(
            repeats = self.episode_loc_size, axis = 0)

        # addr_list = self.curr_addr_list_t[self.curr_job_cache_idx,:]
        # addr = torch.tensor(addr_list, device="cpu")
        addr = self.curr_addr_list_t[self.curr_job_cache_idx,:]

        # matrix_np = self.distance_matrix_cache_t[curr_job_cache_idx_x, curr_job_cache_idx_y] 
        # matrix = torch.tensor(matrix_np, device="cpu")
        matrix = self.distance_matrix_cache_t[curr_job_cache_idx_x, curr_job_cache_idx_y] 



        addr[:,0] = (addr[:,0] - self.geo_longitude_min) * 2
        addr[:,1] = (addr[:,1] -self.geo_latitude_min) * 2

        worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask = self.create_worker_job_batch()  # , job_end_minutes
        if ADDR_DIM == 3:
            # I will attached this as the 3rd dimension of addr.
            end_minutes_1 =  torch.rand(( self.job_size,1), device="cpu") 
            # np.random.randint(0,100,size=(self.job_cache_size))
            job_end_minutes = torch.cat( (
                torch.zeros(self.worker_size, 1, device="cpu") +1,
                end_minutes_1,
                end_minutes_1 + 0.4,
                ), dim = 0
            ).float()#[None,:,:].repeat(batch_size,1,1) 

            addr =  torch.cat( (addr, job_end_minutes), dim = 1).float()

        return addr, matrix, worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask # , job_end_minutes



    def create_worker_job_batch( self,):
        pomo_size = self.worker_size 
        

        worker_loc_idx = torch.arange(pomo_size, device="cpu").view(pomo_size,1).long()
        # job_loc_idx_root = torch.arange(self.job_size, device="cpu").view(1,self.job_size).repeat(pomo_size,1)
        job_loc_idx_root = torch.argsort(torch.rand((pomo_size, self.job_size), device="cpu"), dim=-1) 

        all_loc_count = (self.job_size*2) + 1
        worker_job_count = 1 + self.job_size

        job_loc_idx = torch.cat((
            worker_loc_idx,
            job_loc_idx_root + pomo_size, 
            job_loc_idx_root + pomo_size + self.job_size , 
            ), dim = -1).long()


        # This matrix tracks relatinship: Pick-->Drop for each paired job
        next_job_idx = torch.cat( (
            torch.zeros(pomo_size, 1, device="cpu") + all_loc_count,
            (torch.arange(self.job_size, device="cpu"))[None,:].repeat(pomo_size,1) + worker_job_count,
            torch.zeros(pomo_size, self.job_size, device="cpu") + all_loc_count,
            ), dim = 1
        ).long()#[None,:,:].repeat(batch_size,1,1) 

        # This matrix tracks mask: Job-->(1 as valid for select or 0, not -inf) for each paired job
        # one extra job position for void masking setting .
        next_job_mask = torch.cat( (
            torch.zeros(pomo_size, 1, device="cpu") + float("-inf"),  # + 0
            torch.zeros(pomo_size, self.job_size, device="cpu") ,  # + 1
            torch.zeros(pomo_size, self.job_size + 1, device="cpu") + float("-inf"),  # + 0
            ), dim = 1
        )# [None,:,:].repeat(batch_size,1,1) 


        return worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask


class ENUTSPDataset(OSRMSampleCachedTSPWithStartDataset):
    # mean = [0, 0]
    # cov = [[0.75, 0], [0, 0.75]]  # diagonal covariance 
    minute_scale = 1 # MAP_SCALE / 700 # 700 Meters per Minute
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
        self.dataset_name = dataset_name  
        self.worker_size = worker_size 
        self.job_size = job_size
        self.episode_loc_size = self.worker_size + (self.job_size*2)
        self.pomo_size = pomo_size
        self.geo_longitude_min = self.geo_latitude_min = 0
    

    def __getitem__(self,idx): 

        # worker_loc = np.random.multivariate_normal(self.mean, self.cov, self.worker_size) 
        # pick_loc = np.random.multivariate_normal(self.mean, self.cov, self.job_size) 
        # drop_loc_1 = np.random.multivariate_normal(self.mean, self.cov, self.job_size)  
        # move_covariance = [[0.2, 0], [0, 0.2]]
        # x = np.random.multivariate_normal(self.mean, move_covariance, self.job_size * 5 + 20) 
        # move =[]
        # for i in range(x.shape[0]): 
        #     if abs(x[i][0]) +  abs(x[i][1]) < 0.1:
        #         continue
        #     if abs(x[i][0]) +  abs(x[i][1]) > 0.65:
        #         continue
        #     move.append(x[i].tolist())
        #     if len(move) >= self.job_size:
        #         break
        # move_np = np.array(move)
        # drop_loc = drop_loc_1 + move_np
        # self.addr_np = np.concatenate(
        #     (worker_loc, pick_loc,drop_loc),
        #     axis=0
        # )
        size = self.worker_size + (self.job_size * 2)
        addr = torch.FloatTensor(size, 2 ).uniform_(0, 1).to(self.DATASET_DEVICE)
        

        # addr = torch.tensor(self.addr_np, device="cpu").float()
        # Recover orginal 10KM scale and calculate the distance.
        matrix = torch.cdist(addr*self.minute_scale,addr*self.minute_scale, p=2)

        # I will attach the 3rd dimension of addr as allowed_time.
        end_minutes_1 =  torch.rand(( self.job_size,1), device="cpu") 
        pick_drop_ind_1 = torch.zeros(( self.worker_size+self.job_size,1), device="cpu") 
        pick_drop_ind_2 = torch.ones((self.job_size,1), device="cpu") 
        # np.random.randint(0,100,size=(self.job_cache_size))
        job_end_minutes = torch.cat( (
            torch.zeros(self.worker_size, 1, device="cpu") +1,
                end_minutes_1,
                end_minutes_1 + 0.4,
            ), dim = 0
        ).float()#[None,:,:].repeat(batch_size,1,1) 

        pick_drop_ind = torch.cat( (pick_drop_ind_1,pick_drop_ind_2), dim = 0).float() 
        if ADDR_DIM > 2:
            addr =  torch.cat( (addr, job_end_minutes), dim = 1).float() # pick_drop_ind

        worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask = self.create_worker_job_batch() 

        return addr, matrix, worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask


class OSRMRandomLocationSampleCachedTSPWithStartDataset(OSRMRandomLocationSampleCachedDataset):
    

    def __getitem__(self,idx):
        OSRMRandomLocationSampleCachedDataset._refresh_distance_matrix_cache(self,idx)

        self.curr_worker_cache_idx = np.random.permutation(self.worker_cache_size)[0:self.worker_size]
        self.curr_job_cache_idx_pick = np.random.permutation(self.job_cache_size)[:self.job_size] + (self.worker_cache_size)

        self.curr_job_cache_idx_drop = self.curr_job_cache_idx_pick + self.job_cache_size

        self.curr_job_cache_idx = np.concatenate(
            (self.curr_worker_cache_idx,
            self.curr_job_cache_idx_pick,
            self.curr_job_cache_idx_drop),
            axis=0
        )
        curr_job_cache_idx_x = self.curr_job_cache_idx.view().reshape(self.episode_loc_size,1).repeat(
            repeats = self.episode_loc_size, axis = 1)
        curr_job_cache_idx_y = self.curr_job_cache_idx.view().reshape(1, self.episode_loc_size).repeat(
            repeats = self.episode_loc_size, axis = 0)

        # addr_list = self.curr_addr_list_t[self.curr_job_cache_idx,:]
        # addr = torch.tensor(addr_list, device="cpu")
        addr = self.curr_addr_list_t[self.curr_job_cache_idx,:]

        # matrix_np = self.distance_matrix_cache_t[curr_job_cache_idx_x, curr_job_cache_idx_y] 
        # matrix = torch.tensor(matrix_np, device="cpu")
        matrix = self.distance_matrix_cache_t[curr_job_cache_idx_x, curr_job_cache_idx_y] 



        addr[:,0] = (addr[:,0] - self.geo_longitude_min) * 2
        addr[:,1] = (addr[:,1] -self.geo_latitude_min) * 2

        worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask = self.create_worker_job_batch()  # , job_end_minutes

        # I will attached this as the 3rd dimension of addr.
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

        return addr, matrix, worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask # , job_end_minutes



    def create_worker_job_batch( self,):
        pomo_size = self.worker_size 
        

        worker_loc_idx = torch.arange(pomo_size, device="cpu").view(pomo_size,1).long()
        # job_loc_idx_root = torch.arange(self.job_size, device="cpu").view(1,self.job_size).repeat(pomo_size,1)
        job_loc_idx_root = torch.argsort(torch.rand((pomo_size, self.job_size), device="cpu"), dim=-1) 

        all_loc_count = (self.job_size*2) + 1
        worker_job_count = 1 + self.job_size

        job_loc_idx = torch.cat((
            worker_loc_idx,
            job_loc_idx_root + pomo_size, 
            job_loc_idx_root + pomo_size + self.job_size , 
            ), dim = -1).long()


        # This matrix tracks relatinship: Pick-->Drop for each paired job
        next_job_idx = torch.cat( (
            torch.zeros(pomo_size, 1, device="cpu") + all_loc_count,
            (torch.arange(self.job_size, device="cpu"))[None,:].repeat(pomo_size,1) + worker_job_count,
            torch.zeros(pomo_size, self.job_size, device="cpu") + all_loc_count,
            ), dim = 1
        ).long()#[None,:,:].repeat(batch_size,1,1) 

        # This matrix tracks mask: Job-->(1 as valid for select or 0, not -inf) for each paired job
        # one extra job position for void masking setting .
        next_job_mask = torch.cat( (
            torch.zeros(pomo_size, 1, device="cpu") + float("-inf"),  # + 0
            torch.zeros(pomo_size, self.job_size, device="cpu") ,  # + 1
            torch.zeros(pomo_size, self.job_size + 1, device="cpu") + float("-inf"),  # + 0
            ), dim = 1
        )# [None,:,:].repeat(batch_size,1,1) 


        return worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask
