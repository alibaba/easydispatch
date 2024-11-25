from logging import getLogger
from dispatch.config import ADDR_DIM, MAP_SCALE
from dispatch.contrib.training.pomo.dataset.kandbox_dataset import KandboxDataset
# from dispatch.contrib.training.pomo.job2slot.Job2SlotEnv import Job2SlotEnv as Env
# from dispatch.contrib.training.pomo.job2slot.Job2SlotModel import Job2SlotModel as Model

# from dispatch.contrib.training.pomo.utils.utils import *
from dispatch.contrib.training.pomo.pomo_params import dataset_params, trainer_params

import pandas as pd
import numpy as np
import torch
import random
import os
import time


# def get_addr_list(batch_size, random_state):
def consume_cpu(steps = 1000_0000):
    return
    a=21
    # print(idx.start, idx.step, idx.start)
    for i in range(steps):
        a=a*a % 1000000 
# import json

class OSRMSampleCachedDataset(KandboxDataset):
  def __init__(self, 
    manual_seed = None, env_config = None, pomo_size = 8, 
    dataset_name = "london",
    osrm_url = ("http://192.168.9.251:5001",),
    random_sample_seed = True,
    worker_size = 8,
    job_size = 21,
    # worker_cache_size = 80,
    # job_cache_size = 210,
    use_distance_matrix_cache = True,
    max_dm_count = 16*32,
    ):
    super(OSRMSampleCachedDataset, self,).__init__(
        pomo_size, worker_size, job_size, osrm_url,        
    )

    # a_seed = (os.getpid() * int(time.time())) % 1_000_000 
    # random.seed(a_seed)
    # np.random.seed(a_seed)
    # self.random_seed = random.randint(1000,20000) 
    self.dataset_name = dataset_name

    self.worker_cache_size = dataset_params[self.dataset_name]["worker_cache_size"]
    self.job_cache_size =dataset_params[self.dataset_name] ["job_cache_size"]

    self.worker_size = worker_size
    # self.job_size = int(( episode_loc_size - worker_size ) / 2)
    self.job_size = job_size
    self.episode_loc_size = self.worker_size + (self.job_size*2)
    self.pomo_size = pomo_size

    self.random_sample_seed = random_sample_seed

    self.dmc = None
    self.use_distance_matrix_cache = use_distance_matrix_cache
    self.dm_refresh_count = 0
    self.dm_query_count = 0
    self.original_max_dm_count = max_dm_count

    self.dm_count = self.original_max_dm_count + 100  # Refresh cache immediately
    self.max_dm_count = random.randint(int(self.original_max_dm_count /3), self.original_max_dm_count)


    self.geo_longitude_max = dataset_params[self.dataset_name]["geo_longitude_max"]
    self.geo_longitude_min = dataset_params[self.dataset_name]["geo_longitude_min"]
    self.geo_latitude_max  = dataset_params[self.dataset_name]["geo_latitude_max"]
    self.geo_latitude_min  = dataset_params[self.dataset_name]["geo_latitude_min"]

    if dataset_params[self.dataset_name]["location_type"] == "double":
        self.worker_df = pd.read_csv(
            dataset_params[dataset_name]["worker_file_path"],
            header=0,
            sep=",",
            encoding="utf_8",
        ) 

    if dataset_name == "london":
        df = pd.read_csv(
            dataset_params[dataset_name]["file_path"],
            header=0,
            sep="|",
            encoding="utf_8",
        )
        self.gps_df = df.sample(frac=1).reset_index(drop=True)

        self.gps_df["Address"].fillna("N/A", inplace=True)
        self.gps_df["Post_Code"].fillna("N/A", inplace=True)
    elif dataset_name == "ganzhou":
        self.gps_df = pd.read_csv(
            dataset_params[dataset_name]["file_path"],
            header=0,
            sep=",",
            encoding="utf_8",
        ) 
        self.gps_df = self.gps_df[self.gps_df["start_x"]>self.geo_longitude_min]
        self.gps_df = self.gps_df[self.gps_df["start_x"]<self.geo_longitude_max]
        self.gps_df = self.gps_df[self.gps_df["start_y"]>self.geo_latitude_min]
        self.gps_df = self.gps_df[self.gps_df["start_y"]<self.geo_latitude_max]

        self.gps_df = self.gps_df[self.gps_df["end_x"]>self.geo_longitude_min]
        self.gps_df = self.gps_df[self.gps_df["end_x"]<self.geo_longitude_max]
        self.gps_df = self.gps_df[self.gps_df["end_y"]>self.geo_latitude_min]
        self.gps_df = self.gps_df[self.gps_df["end_y"]<self.geo_latitude_max]
        # self.gps_df["duration"] = self.gps_df["end_seconds"] - self.gps_df["start_seconds"]


    elif dataset_name == "ganzhou_loc_only":
        df = pd.read_csv(
            # "/home/dispatch/ganzhou_202105/job_log_20000.csv",
            "/home/dispatch/ganzhou_202105/job_log.csv",
            header=0,
            sep=",",
            encoding="utf_8",
        )

        from_df = df[["start_x","start_y"]]
        from_df.columns = ["long","lat"]
        to_df = df[["end_x","end_y"]]
        to_df.columns = ["long","lat"]
        self.gps_df = pd.concat([from_df, to_df])

        self.gps_df = self.gps_df[self.gps_df["long"]>self.geo_longitude_min]
        self.gps_df = self.gps_df[self.gps_df["long"]<self.geo_longitude_max]
        self.gps_df = self.gps_df[self.gps_df["lat"]>self.geo_latitude_min]
        self.gps_df = self.gps_df[self.gps_df["lat"]<self.geo_latitude_max]
    else: #  dataset_name in ["setagaya", "setagaya_double", "riyadh_double", "dubai_double", "singapore"] : 
        self.gps_df = pd.read_csv(
            dataset_params[dataset_name]["file_path"],
            header=0,
            sep=",",
            encoding="utf_8",
        )  
    # else:
        # print(f"unknow type: {dataset_name}, finished init")
        # return

    if "end_seconds" in self.gps_df.columns:
        self.gps_df["duration"] = self.gps_df["end_seconds"] - self.gps_df["start_seconds"]
    else:
        self.gps_df["duration"] = 100
        self.gps_df["end_seconds"] = 1000
        self.gps_df["start_seconds"] = 1
    if "end_x" not in self.gps_df.columns:
        self.gps_df["end_x"] = self.gps_df["long"]
        self.gps_df["end_y"] = self.gps_df["lat"]
    # HaversineTravelTime1
    # OSRMTravelTime1

    # print(self.router.get_travel_minutes_2locations([-83.21477, 35.375], [-80.63446, 35.06158]))
    print(f"Loaded {self.gps_df.count().max()} jobs from {dataset_name} dataset, file: {dataset_params[dataset_name]['file_path']}, refresh interval {self.max_dm_count}")


  def _refresh_distance_matrix_cache(self,idx):
    # print(f"data {idx}")
    # consume_cpu(steps = 1_000_0000)

    self.dm_count += 1
    if self.dm_count < self.max_dm_count: 
        return
    else:
        pid = os.getpid()

        a_seed = (pid * idx * int(time.time())) % 1_000_000
        # a_seed = (self.dm_count * idx ) % 1_000_000
        random.seed(a_seed)
        np.random.seed(a_seed)
        self.random_seed = a_seed

        # w_info = torch.utils.data.get_worker_info()
        # print(f"Refresh by loader pid: {pid}, self.random_seed = {self.random_seed}, tseed: {w_info.seed} dataset: {self.dataset_name}, refresh interval {self.max_dm_count}, refreshed {self.dm_refresh_count} times")

        # Now refresh

        if self.episode_loc_size > self.gps_df.count().max():
            raise ValueError(f"Not enough training data. {self.gps_df.count().max()}")
            self.curr_df = self.gps_df

        # 2022-12-23 05:57:19 self.dataset_name in ['ganzhou']
        # This means pick-drop dataset.
        if dataset_params[self.dataset_name]["location_type"] ==  "double" :
            selected_worker_df = self.worker_df.sample(
                n=(self.worker_cache_size),
                random_state = self.random_seed)
            self.curr_worker_df = selected_worker_df[["start_x","start_y"]] # [0:self.worker_cache_size]
            addr_list_worker_n_start = self.curr_worker_df.values.tolist()


            self.curr_df = self.gps_df.sample(
                n=(self.job_cache_size),
                random_state = self.random_seed).reset_index()
            # random_start_minutes = pd.Series(np.random.randint(0,100,size=(self.job_cache_size)))
            # self.curr_df["deadline_minutes"] = random_start_minutes + (self.curr_df["duration"]/60)

            self.curr_job_df = self.curr_df[["start_x","start_y","end_x","end_y"]] # [self.worker_cache_size:]
            addr_list_job_start = self.curr_job_df[["start_x","start_y"]].values.tolist()
            addr_list_job_end = self.curr_job_df[["end_x","end_y"]].values.tolist()
            self.curr_addr_list = addr_list_worker_n_start + addr_list_job_start + addr_list_job_end
            

        else:
            self.curr_df = self.gps_df.sample(
                n=(self.job_cache_size * 2 + self.worker_cache_size),
                random_state = self.random_seed)
            self.curr_addr_list = self.curr_df[["end_x","end_y"]].values.tolist()

        self.curr_addr_array = np.array(self.curr_addr_list )
        matrix_list = self.router.get_travel_minutes_matrix(self.curr_addr_list)
        self.distance_matrix_cache_array = np.array( matrix_list )
        self.dm_count = 0
        self.dm_refresh_count+=1
        self.max_dm_count = random.randint(int(self.original_max_dm_count /3), self.original_max_dm_count)
        # print(f"_refresh_distance_matrix_cache: pid = {pid}, seed = {a_seed}, refreshing {self.dm_refresh_count} times, total query = {self.dm_query_count}, next max = {self.max_dm_count}")

        self.curr_addr_list_t = torch.tensor(self.curr_addr_array, device=self.DATASET_DEVICE)
        self.distance_matrix_cache_t = torch.tensor(self.distance_matrix_cache_array, device=self.DATASET_DEVICE)

  def __getitem__(self,idx):

    self._refresh_distance_matrix_cache(idx)

    if self.random_sample_seed:
        # random_seed = random.randint(1,100) * (idx + random.randint(1,1000))
        # self.curr_worker_cache_idx = torch.randperm(self.worker_size*10)[:self.worker_size]
        # self.curr_job_cache_idx = torch.randperm(self.job_size*10)[:self.job_size] + (self.worker_size*10)
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
        addr_list = self.curr_addr_array[self.curr_job_cache_idx,:]

        # addr = np.array(addr_list )
        matrix_np = self.distance_matrix_cache_array[curr_job_cache_idx_x, curr_job_cache_idx_y] 
        matrix = torch.tensor(matrix_np, device=self.DATASET_DEVICE)
    else:
        assert False, "Must sample data"
        addr_list = self.curr_addr_list
        # addr = np.array(addr_list )
        # matrix = np.array(matrix_list )
        matrix = torch.tensor(matrix_list, device=self.DATASET_DEVICE)

    addr = torch.tensor(addr_list, device=self.DATASET_DEVICE)

    addr[:,0] = (addr[:,0] - self.geo_longitude_min) * 2
    addr[:,1] = (addr[:,1] - self.geo_latitude_min) * 2

    if ADDR_DIM > 2:
        # I will attached this as the 3rd dimension of addr.
        end_minutes_1 =  torch.rand(( self.job_size,1), device=self.DATASET_DEVICE) 
        pick_drop_ind_1 = torch.zeros(( self.worker_size+self.job_size,1), device=self.DATASET_DEVICE) 
        pick_drop_ind_2 = torch.ones((self.job_size,1), device=self.DATASET_DEVICE) 
        # np.random.randint(0,100,size=(self.job_cache_size))
        job_end_minutes = torch.cat( (
            torch.zeros(self.worker_size, 1, device=self.DATASET_DEVICE) +1,
                end_minutes_1,
                end_minutes_1 + 0.4,
            ), dim = 0
        ).float()#[None,:,:].repeat(batch_size,1,1) 

        pick_drop_ind = torch.cat( (pick_drop_ind_1,pick_drop_ind_2), dim = 0).float() 

        addr =  torch.cat( (addr, job_end_minutes, pick_drop_ind), dim = 1).float()


    worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask = self.create_worker_job_batch4pickdrop() 
    self.dm_query_count += 1
    return addr, matrix, worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask


class ENUSampleDataset(KandboxDataset):
    # mean = [0, 0]
    # cov = [[0.75, 0], [0, 0.75]]  # diagonal covariance 
    # minute_scale = MAP_SCALE / 700 # 700 Meters per Minute
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
        addr = torch.tensor(self.addr_np, device=self.DATASET_DEVICE).float()
        # Recover orginal 10KM scale and calculate the distance.
        matrix = torch.cdist(addr*self.minute_scale,addr*self.minute_scale, p=2)

        # I will attach the 3rd dimension of addr as allowed_time.
        end_minutes_1 =  torch.rand(( self.job_size,1), device=self.DATASET_DEVICE) 
        # np.random.randint(0,100,size=(self.job_cache_size))
        job_end_minutes = torch.cat( (
            torch.zeros(self.worker_size, 1, device=self.DATASET_DEVICE) +1,
                end_minutes_1,
                end_minutes_1 + 0.4,
            ), dim = 0
        ).float()#[None,:,:].repeat(batch_size,1,1) 

        pick_drop_ind_1 = torch.zeros(( self.worker_size+self.job_size,1), device=self.DATASET_DEVICE) 
        pick_drop_ind_2 = torch.ones((self.job_size,1), device=self.DATASET_DEVICE) 
        pick_drop_ind = torch.cat( (pick_drop_ind_1,pick_drop_ind_2), dim = 0).float() 

        addr =  torch.cat( (addr, job_end_minutes, pick_drop_ind), dim = 1).float()


        worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask = self.create_worker_job_batch4pickdrop() 

        return addr, matrix, worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask


class ENUUniformDataset(KandboxDataset):
    # minute_scale = MAP_SCALE / 700 # 700 Meters per Minute
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
        super(ENUUniformDataset, self,).__init__(
            pomo_size, worker_size, job_size, osrm_url,        
        )
        self.dataset_name = dataset_name  
        self.worker_size = worker_size 
        self.job_size = job_size
        self.episode_loc_size = self.worker_size + (self.job_size*2)
        self.pomo_size = pomo_size
        self.geo_longitude_min = self.geo_latitude_min = 0


    def __getitem__(self,idx): 

        worker_loc = torch.FloatTensor(self.worker_size, 2).uniform_(0, 1).to(self.DATASET_DEVICE)
        pick_loc = torch.FloatTensor(self.job_size, 2, ).uniform_(0, 1).to(self.DATASET_DEVICE)
        drop_loc = torch.FloatTensor(self.job_size, 2, ).uniform_(0, 1).to(self.DATASET_DEVICE)  

        self.addr_np = torch.cat(
            (worker_loc, pick_loc,drop_loc), dim=0
        )
        addr = self.addr_np
        # Recover orginal 10KM scale and calculate the distance.
        matrix = torch.cdist(addr*self.minute_scale,addr*self.minute_scale, p=2)

        if ADDR_DIM > 2:
            # I will attach the 3rd, 4th dimension of addr as pickdrop_flag, allowed_time.
            end_minutes_1 =  torch.rand(( self.job_size,1), device=self.DATASET_DEVICE) 
            pick_drop_ind_1 = torch.zeros(( self.worker_size+self.job_size,1), device=self.DATASET_DEVICE) 
            pick_drop_ind_2 = torch.ones((self.job_size,1), device=self.DATASET_DEVICE) 
            # np.random.randint(0,100,size=(self.job_cache_size))
            job_end_minutes = torch.cat( (
                torch.zeros(self.worker_size, 1, device=self.DATASET_DEVICE) +1,
                    end_minutes_1,
                    end_minutes_1 + 0.4,
                ), dim = 0
            ).float()#[None,:,:].repeat(batch_size,1,1) 

            pick_drop_ind = torch.cat( (pick_drop_ind_1,pick_drop_ind_2), dim = 0).float() 

            addr =  torch.cat( (addr, job_end_minutes, pick_drop_ind), dim = 1).float()


        worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask = self.create_worker_job_batch4pickdrop() 

        return addr, matrix, worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask



class OSRMRandomLocationSampleCachedDataset(OSRMSampleCachedDataset):
    
    def __init__(self, 
        manual_seed = None, env_config = None, pomo_size = 8, 
        dataset_name = "london",
        osrm_url = ("http://192.168.9.251:5001",),
        random_sample_seed = True,
        worker_size = 8,
        job_size = 21,
        # worker_cache_size = 80,
        # job_cache_size = 210,
        use_distance_matrix_cache = True,
        max_dm_count = 16*32,
        ):
        super().__init__(manual_seed , env_config  , pomo_size  , 
        dataset_name ,
        osrm_url ,
        random_sample_seed ,
        worker_size ,
        job_size , 
        use_distance_matrix_cache ,
        max_dm_count ,) 
        
        self.worker_df = pd.read_csv(
            dataset_params[dataset_name]["worker_file_path"],
            header=0,
            sep=",",
            encoding="utf_8",
        ) 
        self.worker_longlat_np = self.worker_df[["longitude_mean", "latitude_mean"]].values
        self.worker_longlat_prob_list = self.worker_df["loc_count"].values
        self.worker_longlat_prob_list = self.worker_longlat_prob_list / self.worker_longlat_prob_list.sum()

        self.job_df = pd.read_csv(
            dataset_params[dataset_name]["file_path"],
            header=0,
            sep=",",
            encoding="utf_8",
        ) 
        self.job_longlat_np = self.job_df[["longitude_mean", "latitude_mean"]].values
        self.job_longlat_prob_list = self.job_df["loc_count"].values
        self.job_longlat_prob_list = self.job_longlat_prob_list / self.job_longlat_prob_list.sum()

        # HaversineTravelTime1
        # OSRMTravelTime1
        self.router = the_router_class(
            osrm_url = osrm_url, 
            travel_mode = "car", # foot, car, bike
            travel_speed=19,
            min_minutes = 0.1,
            # enable_home_travel = True
            )
        # print(self.router.get_travel_minutes_2locations([-83.21477, 35.375], [-80.63446, 35.06158]))
        print(f"Loaded {self.job_df.count().max()} rows from {dataset_name} dataset, file: {dataset_params[dataset_name]['file_path']}, refresh interval {self.max_dm_count}")




    def __len__(self):
        return 100_000_000
    
    def _refresh_distance_matrix_cache(self,idx):
        # print(f"data {idx}")
        # consume_cpu(steps = 1_000_0000)

        self.dm_count += 1
        if self.dm_count < self.max_dm_count: 
            return

        pid = os.getpid()

        a_seed = (pid * idx * int(time.time())) % 1_000_000
        # a_seed = (self.dm_count * idx ) % 1_000_000
        random.seed(a_seed)
        np.random.seed(a_seed)
        self.random_seed = a_seed

        # Now refresh
        worker_idx_list = np.random.choice(
            a=len(self.worker_longlat_prob_list), 
            size=self.worker_cache_size, 
            p=self.worker_longlat_prob_list)
        
        addr_list_worker_n_start = []
        for idx_i in worker_idx_list:
            addr_list_worker_n_start.append(self.worker_longlat_np[idx_i].tolist())


        pick_idx_list = np.random.choice(
            a=len(self.worker_longlat_prob_list), 
            size=self.job_cache_size, 
            p=self.worker_longlat_prob_list)
        
        addr_list_job_start = []
        for idx_i in pick_idx_list:
            addr_list_job_start.append(self.worker_longlat_np[idx_i].tolist())

        drop_idx_list = np.random.choice(
            a=len(self.job_longlat_prob_list), 
            size=self.job_cache_size, 
            p=self.job_longlat_prob_list)
        
        addr_list_job_end = []
        for idx_i in drop_idx_list:
            addr_list_job_end.append(self.job_longlat_np[idx_i].tolist())

        self.curr_addr_list = addr_list_worker_n_start + addr_list_job_start + addr_list_job_end
        
        
        self.curr_addr_array = np.array(self.curr_addr_list )
        matrix_list = self.router.get_travel_minutes_matrix(self.curr_addr_list, return_type = "duration")
        self.distance_matrix_cache_array = np.array( matrix_list )
        self.dm_count = 0
        self.dm_refresh_count+=1
        self.max_dm_count = random.randint(int(self.original_max_dm_count /3), self.original_max_dm_count)

        # print(f"_refresh_distance_matrix_cache: pid = {pid}, seed = {a_seed}, refreshing {self.dm_refresh_count} times, total query = {self.dm_query_count}, next max = {self.max_dm_count}")
        self.curr_addr_list_t = torch.tensor(self.curr_addr_array, device=self.DATASET_DEVICE)
        self.distance_matrix_cache_t = torch.tensor(self.distance_matrix_cache_array, device=self.DATASET_DEVICE)
