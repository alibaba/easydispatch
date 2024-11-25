from torch.utils.data import Dataset
import random

import torch
from torch.utils.data import Dataset
from dispatch.plugins.kandbox_planner.travel_time_plugin import OSRMTravelTime1, HaversineTravelTime1
from dispatch.contrib.training.pomo.pomo_params import dataset_params, trainer_params, dataset_name


router_class_dict = {
    "OSRMTravelTime1":OSRMTravelTime1,   
    "HaversineTravelTime1":HaversineTravelTime1,
}
the_router_class = router_class_dict[trainer_params["router_class"]]

class KandboxDataset(Dataset):
    mean = [0, 0]
    cov = [[0.5, 0], [0, 0.5]]  # diagonal covariance 
    minute_scale = 1 # 700 Meters per Minute

    uniform_min = -0.5
    uniform_max = 0.5


    def __init__(
        self, 
        pomo_size = 8, 
        worker_size = 8,
        job_size = 21,
        osrm_url = ("http://192.168.9.251:5001",),
        ):
        self.dataset_name = dataset_name
        self.geo_longitude_max = dataset_params[self.dataset_name]["geo_longitude_max"]
        self.geo_longitude_min = dataset_params[self.dataset_name]["geo_longitude_min"]
        self.geo_latitude_max  = dataset_params[self.dataset_name]["geo_latitude_max"]
        self.geo_latitude_min  = dataset_params[self.dataset_name]["geo_latitude_min"]
        self.worker_cache_size = dataset_params[self.dataset_name]["worker_cache_size"]
        self.job_cache_size =dataset_params[self.dataset_name] ["job_cache_size"]

        self.worker_size = worker_size
        self.job_size = job_size
        self.episode_loc_size = self.worker_size + (self.job_size*2)
        self.pomo_size = pomo_size

        self.worker_loc_size = self.worker_size
        self.job_loc_size = self.job_size*2

        self.router = the_router_class(
            osrm_url = osrm_url, 
            travel_mode = "car", # foot, car, bike
            travel_speed=19,
            min_minutes = 0.1,
            # enable_home_travel = True
            )
        self.DATASET_DEVICE = torch.Tensor(1, 2).device
        print("initialized device at :", self.DATASET_DEVICE)
        
    def __len__(self):
        return 100_000_000
    
    def _refresh_distance_matrix_cache(self,idx):
        raise NotImplementedError("Not implemented, pls use sub-class of KandboxDataset") 
    def __getitem__(self,idx):
        raise NotImplementedError("Not implemented, pls use sub-class of KandboxDataset") 
        
    def create_worker_job_batch4pickdrop( self,):

        worker_loc_idx = torch.arange(self.worker_size, device=self.DATASET_DEVICE).view(1,self.worker_size).repeat(self.pomo_size, 1)

        rand_pick_indices = torch.argsort(torch.rand((
            self.pomo_size, self.job_size), device=self.DATASET_DEVICE), dim=-1) + self.worker_size
        rand_drop_indices = rand_pick_indices + self.job_size
        job_loc_idx = torch.cat((rand_pick_indices[:,:,None],rand_drop_indices[:,:,None]), dim = -1).long()


        # This matrix tracks relatinship: Pick-->Drop for each paired job
        next_job_idx = torch.cat( (
            torch.zeros(self.pomo_size, self.worker_size, device=self.DATASET_DEVICE) + (self.job_size*2) + self.worker_size,
            (torch.arange(self.job_size, device=self.DATASET_DEVICE))[None,:].repeat(self.pomo_size,1) + self.job_size + self.worker_size,
            torch.zeros(self.pomo_size, self.job_size, device=self.DATASET_DEVICE) + (self.job_size*2) + self.worker_size,
            ), dim = 1
        ).long()#[None,:,:].repeat(batch_size,1,1) 

        # This matrix tracks mask: Job-->(1 as valid for select or 0, not -inf) for each paired job
        # one extra job position for void masking setting .
        next_job_mask = torch.cat( (
            torch.zeros(self.pomo_size, self.worker_size + self.job_size, device=self.DATASET_DEVICE) ,  # + 1
            torch.zeros(self.pomo_size, self.job_size + 1, device=self.DATASET_DEVICE) + float("-inf"),  # + 0
            ), dim = 1
        )# [None,:,:].repeat(batch_size,1,1) 


        return worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask

    def create_worker_job_batch4single( self,):

        rand_worker_indices = torch.argsort(
            torch.rand((self.pomo_size, self.worker_loc_size), device=self.DATASET_DEVICE), dim=-1)
        rand_job_indices = torch.argsort(torch.rand((
            self.pomo_size, self.job_loc_size), device=self.DATASET_DEVICE), dim=-1)
        
        # This should remain same. No picking
        worker_loc_idx = rand_worker_indices[:,0:self.worker_loc_size]# .view(self.pomo_size*self.worker_loc_size)

        job_loc_idx = rand_job_indices[:,0:self.job_loc_size] + self.worker_loc_size# .view(self.pomo_size*self.worker_loc_size)

        # This matrix tracks relatinship: Pick-->Drop for each paired job
        next_job_idx = torch.zeros(
            self.pomo_size, self.worker_loc_size+ self.job_loc_size + 1, device=self.DATASET_DEVICE
        ).long() +( self.job_loc_size + self.worker_loc_size )

        # This matrix tracks mask: Job-->(1 as valid for select or 0, not -inf) for each paired job
        # one extra job position for void masking setting .
        next_job_mask = torch.cat( (
            torch.zeros(self.pomo_size, self.worker_loc_size + self.job_loc_size, device=self.DATASET_DEVICE) ,  # + 1
            torch.zeros(self.pomo_size, 1, device=self.DATASET_DEVICE) + float("-inf"),  # + 0
            ), dim = 1
        )# [None,:,:].repeat(batch_size,1,1) 


        return worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask

