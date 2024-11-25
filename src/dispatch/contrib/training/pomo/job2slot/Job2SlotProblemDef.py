
import torch
import numpy as np


def get_random_jobs(batch_size, pomo_size, worker_size, job_size):

    loc_xy = torch.rand(size=(batch_size, worker_size+job_size, 2))
    # TODO, 2022-02-25 16:50:02, verify if permutate worker location index should help. 
    # No permutate for now. 
    worker_loc_idx = torch.arange(worker_size).repeat(batch_size,pomo_size,1)

    # shape: (batch, job_size, 1)
    # job_loc_idx = torch.arange(job_size).repeat(batch_size,1) + worker_size
    _rand_perm = torch.rand((pomo_size,job_size)).argsort() + worker_size

    job_loc_idx = _rand_perm[None,:,:].repeat(batch_size,1,1)


    return loc_xy, worker_loc_idx, job_loc_idx


def augment_xy_data_by_8_fold(xy_data):
    # xy_data.shape: (batch, N, 2)

    x = xy_data[:, :, [0]]
    y = xy_data[:, :, [1]]
    # x,y shape: (batch, N, 1)

    dat1 = torch.cat((x, y), dim=2)
    dat2 = torch.cat((1 - x, y), dim=2)
    dat3 = torch.cat((x, 1 - y), dim=2)
    dat4 = torch.cat((1 - x, 1 - y), dim=2)
    dat5 = torch.cat((y, x), dim=2)
    dat6 = torch.cat((1 - y, x), dim=2)
    dat7 = torch.cat((y, 1 - x), dim=2)
    dat8 = torch.cat((1 - y, 1 - x), dim=2)

    aug_xy_data = torch.cat((dat1, dat2, dat3, dat4, dat5, dat6, dat7, dat8), dim=0)
    # shape: (8*batch, N, 2)

    return aug_xy_data