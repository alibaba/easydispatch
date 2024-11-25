
import torch
import torch.nn as nn
# torch.autograd.set_detect_anomaly(True)
import torch.multiprocessing as mp
from torch.utils.data.distributed import DistributedSampler
from torch.nn.parallel import DistributedDataParallel
from torch.distributed import init_process_group, destroy_process_group
import torch.distributed as dist
import os

from logging import getLogger
from dispatch.config import USE_DDP

from dispatch.contrib.training.pomo.job2slot.Job2SlotEnv import Job2SlotEnv 
from dispatch.contrib.training.pomo.job2slot.Job2SlotModel import Job2SlotModel 
from dispatch.contrib.training.pomo.job2slot.OnlineJob2SlotModel import OnlineJob2SlotModel 

from datetime import datetime
from dispatch.contrib.training.pomo.TSP.TSPEnv import TSPEnv 
from dispatch.contrib.training.pomo.TSP.TSPModel import TSPModel


from dispatch.contrib.training.pomo.pick_drop_tsp.pick_drop_tsp_env import PickDropTSPEnv 
from dispatch.contrib.training.pomo.pick_drop_tsp.pick_drop_tsp_model import PickDropTSPModel 

from dispatch.contrib.training.pomo.pick_drop_tsp_with_start.pick_drop_tsp_with_start_env import PickDropWithStartTSPEnv
from dispatch.contrib.training.pomo.pick_drop_tsp_with_start.pick_drop_tsp_with_start_model import PickDropWithStartTSPModel

from dispatch.contrib.training.pomo.pick_drop_job2slot.pick_drop_job2slot_env import PickDropJob2SlotEnv 
from dispatch.contrib.training.pomo.pick_drop_job2slot.pick_drop_job2slot_model import PickDropJob2SlotModel 

# from dispatch.contrib.training.pomo.pick_drop_job2slot.online_pick_drop_job2slot_env import OnlinePickDropJob2SlotEnv 
from dispatch.contrib.training.pomo.pick_drop_job2slot.online_pick_drop_job2slot_model import OnlinePickDropJob2SlotModel
from dispatch.contrib.training.pomo.pickdrop_2in1.pickdrop_2in1_env import PickDrop2in1Env
from dispatch.contrib.training.pomo.pickdrop_2in1.pickdrop_2in1_model import PickDrop2in1Model

from dispatch.contrib.training.pomo.pickdrop_pomo_n2s.pickdrop_pomo_n2s_env import PickDropPomoN2SEnv
from dispatch.contrib.training.pomo.pickdrop_pomo_n2s.pickdrop_pomo_n2s_model import PickDropPomoN2SModel

from dispatch.contrib.training.pomo.single_job2slot_n2s.single_job2slot_n2s_env import SingleJob2SlotN2SEnv
from dispatch.contrib.training.pomo.single_job2slot_n2s.single_job2slot_n2s_model import SingleJob2SlotN2SModel


# from dispatch.contrib.training.pomo.pomo_params import device

import random

from torch.optim import Adam as Optimizer
from torch.optim.lr_scheduler import MultiStepLR as Scheduler
from torch.utils.data import DataLoader #, Dataset, BatchSampler, RandomSampler

from dispatch.contrib.training.pomo.utils.utils import *
# from dispatch.contrib.training.pomo.job2slot.job2slot_pickdrop_sampled_osrm_dataset import ( 
#      OSRMSampleDataset, EuclideanBoxDataset
# )
# from dispatch.contrib.training.pomo.job2slot.job2slot_fsm_sampled_haversine_dataset import SampledFSMHaversineDataset

from dispatch.contrib.training.pomo.dataset.job2slot_fsm_sampled_cached_osrm_dataset import OSRMSampleCachedFSMDataset, SingleENUUniformDataset
from dispatch.contrib.training.pomo.dataset.job2slot_pickdrop_sampled_cached_osrm_dataset import ENUUniformDataset, ENUSampleDataset, OSRMRandomLocationSampleCachedDataset, OSRMSampleCachedDataset
from dispatch.contrib.training.pomo.dataset.tsp_pickdrop_sampled_cached_osrm_started_dataset import ENUTSPDataset, OSRMRandomLocationSampleCachedTSPWithStartDataset, OSRMSampleCachedTSPWithStartDataset

import numpy as np
# https://www.programcreek.com/python/example/101148/torch.initial_seed
def worker_init_fn(worker_id):
    torch_seed = torch.initial_seed()

    random.seed(torch_seed + worker_id)

    if torch_seed >= 2**32:
        torch_seed = torch_seed % 2**32
    np.random.seed(torch_seed + worker_id) 


class Job2SlotInputDataTrainer:
    def __init__(self,
                 env_params,
                 model_params,
                 optimizer_params,
                 trainer_params,
                 gpu_id,
                 ):
        self.gpu_id = gpu_id

        # save arguments
        self.env_params = env_params
        self.model_params = model_params
        self.optimizer_params = optimizer_params
        self.trainer_params = trainer_params

        if self.trainer_params["training_target"] in ("single_job2slot_n2s", ):
            self.Env = SingleJob2SlotN2SEnv
            self.Model = SingleJob2SlotN2SModel
            self.location_size = self.env_params["worker_size"] + self.env_params["job_size"]
        elif self.trainer_params["training_target"] in ("pickdrop_pomo_n2s", ):
            self.Env = PickDropPomoN2SEnv
            self.Model = PickDropPomoN2SModel
            self.location_size = self.env_params["worker_size"] + self.env_params["job_size"]
        elif self.trainer_params["training_target"] in ("pickdrop_job2slot_tsp_2in1", ):
            self.Env = PickDrop2in1Env
            self.Model = PickDrop2in1Model
            self.location_size = self.env_params["worker_size"] + self.env_params["job_size"]
        elif self.trainer_params["training_target"] in ("pickdrop_job2slot_tsp_3in1", ):
            raise NotImplemented("pickdrop_job2slot_tsp_3in1 was not done, replaced by pickdrop/single_job2slot_n2s")
            self.Env = PickDrop3in1Env
            self.Model = PickDrop3in1Model
            self.location_size = self.env_params["worker_size"] + self.env_params["job_size"]
        elif self.trainer_params["training_target"] in ("online_job2slot", ):
            self.Env = Job2SlotEnv
            self.Model = OnlineJob2SlotModel
            self.location_size = self.env_params["worker_size"] + self.env_params["job_size"]
        elif self.trainer_params["training_target"] in ( "job2slot",):
            self.Env = Job2SlotEnv
            self.Model = Job2SlotModel
            self.location_size = self.env_params["worker_size"] + self.env_params["job_size"]
        elif self.trainer_params["training_target"] == "pick_drop_job2slot":
            self.Env = PickDropJob2SlotEnv
            self.Model = PickDropJob2SlotModel
            self.location_size = self.env_params["worker_size"] + self.env_params["job_size"]
        elif self.trainer_params["training_target"] == "online_pick_drop_job2slot":
            # self.Env = OnlinePickDropJob2SlotEnv
            self.Env = PickDropJob2SlotEnv
            self.Model = OnlinePickDropJob2SlotModel
            self.location_size = self.env_params["worker_size"] + self.env_params["job_size"]
        elif self.trainer_params["training_target"] == "tsp":
            self.Env = TSPEnv
            self.Model = TSPModel
            self.location_size = self.env_params["problem_size"]
        elif self.trainer_params["training_target"] == "pick_drop_tsp":
            self.Env = PickDropTSPEnv
            self.Model = PickDropTSPModel
            self.location_size = self.env_params["problem_size"] 
        elif self.trainer_params["training_target"] == "pick_drop_tsp_with_start":
            self.Env = PickDropWithStartTSPEnv
            self.Model = PickDropWithStartTSPModel
            self.location_size = self.env_params["problem_size"] 
        else:
            raise ValueError(f"self.trainer_params.training_target == {self.trainer_params['training_target']} is wrong .")


        # dataset generator
        # EuclideanBoxDataset(),  OSRMSampleCachedDataset,  OSRMSampleDataset(), SampledPickDropHaversineDataset
        # OSRMSampleCachedTSPWithStartDataset
        if self.trainer_params["training_target"] in ("pickdrop_pomo_n2s", "pick_drop_job2slot", 'online_pick_drop_job2slot', 'pickdrop_job2slot_tsp_2in1'):      # , "pickdrop_job2slot_tsp_3in1"
            if self.trainer_params["dataset_name"] == "ENU_10KM_UNIFORM":        
                self.dataset = ENUUniformDataset( # ENUUniformDataset  ENUSampleDataset
                    worker_size = self.env_params["worker_size"],
                    job_size = int(self.env_params["job_size"]/2), 
                    pomo_size=self.env_params["pomo_size"],
                    manual_seed=None,
                    env_config = env_params["rl_env_config"],
                    dataset_name = self.trainer_params["dataset_name"],
                    max_dm_count = self.trainer_params["max_dm_count"],
                    osrm_url=self.trainer_params["osrm_url"],
                ) 
            elif self.trainer_params["dataset_name"] == "dubai_double_random":        
                self.dataset = OSRMRandomLocationSampleCachedDataset( 
                    worker_size = self.env_params["worker_size"],
                    job_size = int(self.env_params["job_size"]/2), 
                    pomo_size=self.env_params["pomo_size"],
                    manual_seed=None,
                    env_config = env_params["rl_env_config"],
                    dataset_name = self.trainer_params["dataset_name"],
                    max_dm_count = self.trainer_params["max_dm_count"],
                    osrm_url=self.trainer_params["osrm_url"],
                )  
            else: # All other datasets, including london_croydon_pickdrop here
                self.dataset = OSRMSampleCachedDataset( # turkey_double
                    worker_size = self.env_params["worker_size"],
                    job_size = int(self.env_params["job_size"]/2), 
                    pomo_size=self.env_params["pomo_size"],
                    manual_seed=None,
                    env_config = env_params["rl_env_config"],
                    dataset_name = self.trainer_params["dataset_name"],
                    max_dm_count = self.trainer_params["max_dm_count"],
                    osrm_url=self.trainer_params["osrm_url"],
                ) 
        elif self.trainer_params["training_target"] in ("single_job2slot_n2s", "online_job2slot", "job2slot", ):
            if self.trainer_params["dataset_name"] == "ENU_10KM_UNIFORM":        
                self.dataset = SingleENUUniformDataset(
                    worker_size = self.env_params["worker_size"],
                    job_size = int(self.env_params["job_size"]/2), 
                    pomo_size=self.env_params["pomo_size"],
                    manual_seed=None,
                    env_config = env_params["rl_env_config"],
                    dataset_name = self.trainer_params["dataset_name"],
                    max_dm_count = self.trainer_params["max_dm_count"],
                    osrm_url=self.trainer_params["osrm_url"],
                ) 
            else:
            # if self.trainer_params["dataset_name"] == "us_la_haversine":        
            #     self.dataset = SampledFSMHaversineDataset( 
            # else: 合并后，用参数控制：ROUTER_CLASS=HaversineTravelTime1 2023-11-27 23:09:43
                self.dataset = OSRMSampleCachedFSMDataset(
                    # episode_loc_size = 500,
                    pomo_size=self.env_params["pomo_size"],
                    manual_seed=None,
                    env_config = env_params["rl_env_config"],
                    dataset_name = self.trainer_params["dataset_name"],
                    worker_size = self.env_params["worker_size"],
                    job_size = int(self.env_params["job_size"]/2),
                    max_dm_count = self.trainer_params["max_dm_count"],
                    osrm_url=self.trainer_params["osrm_url"],
                ) 

        elif self.trainer_params["training_target"] in ("pick_drop_tsp_with_start", "tsp" ):
            if self.trainer_params["dataset_name"] == "ENU_10KM_UNIFORM":        
                self.dataset = ENUTSPDataset(
                    worker_size = self.env_params["worker_size"],
                    job_size = int(self.env_params["job_size"]/2), 
                    pomo_size=self.env_params["pomo_size"],
                    manual_seed=None,
                    env_config = env_params["rl_env_config"],
                    dataset_name = self.trainer_params["dataset_name"],
                    max_dm_count = self.trainer_params["max_dm_count"],
                    osrm_url=self.trainer_params["osrm_url"],
                ) 
            elif self.trainer_params["dataset_name"] == "pick_drop_tsp_with_start_dubai_random":        
                self.dataset = OSRMRandomLocationSampleCachedTSPWithStartDataset(
                    worker_size = self.env_params["worker_size"],
                    job_size = int(self.env_params["job_size"]/2), 
                    pomo_size=self.env_params["pomo_size"],
                    manual_seed=None,
                    env_config = env_params["rl_env_config"],
                    dataset_name = self.trainer_params["dataset_name"],
                    max_dm_count = self.trainer_params["max_dm_count"],
                    osrm_url=self.trainer_params["osrm_url"],
                ) 
            else:
                self.dataset = OSRMSampleCachedTSPWithStartDataset(
                    # episode_loc_size = 500,
                    pomo_size=self.env_params["pomo_size"],
                    manual_seed=None,
                    env_config = env_params["rl_env_config"],
                    dataset_name = self.trainer_params["dataset_name"],
                    worker_size = self.env_params["worker_size"],
                    job_size = int(self.env_params["job_size"]/2),
                    max_dm_count = self.trainer_params["max_dm_count"],
                    osrm_url=self.trainer_params["osrm_url"], 
                ) 
        else:
            print("not implemented")
            exit(1)

        # Save it for later TSP sub-model
        # self.env_params["device"] = device
        self.env = self.Env(self.env_params, self.model_params)

        # print(self.dataset[1])
        if USE_DDP:
            self.dataloader = DataLoader(
                self.dataset,
                num_workers=self.trainer_params["num_dataloader_workers"],
                batch_size=self.trainer_params['train_batch_size'], 
                worker_init_fn=worker_init_fn,
                sampler=DistributedSampler(self.dataset, shuffle=False), 
                pin_memory=False,
                shuffle=False,
                generator=torch.Generator(device=self.gpu_id)
            )


            # Main Components
            orig_model = self.Model(self.model_params).to(self.gpu_id)

            self.model = DistributedDataParallel(
                orig_model, 
                device_ids=[self.gpu_id],
                broadcast_buffers=False
                )

        else:
            self.dataloader = DataLoader(
                self.dataset,
                num_workers=self.trainer_params["num_dataloader_workers"],
                batch_size=self.trainer_params['train_batch_size'], 
                worker_init_fn=worker_init_fn,
            )
            self.model = self.Model(self.model_params)



        # 2022-07-01 15:46:03 Waiting for nested_tensor to split. 
        # https://pytorch.org/docs/master/nested.html
        
        # if torch.cuda.device_count() > 1:
        #     print("Using", torch.cuda.device_count(), "GPUs!") 
        #     self.model = nn.DataParallel(self.model)
        # self.model.to(device)

        self.optimizer = Optimizer(self.model.parameters(), **self.optimizer_params['optimizer'])
        self.scheduler = Scheduler(self.optimizer, **self.optimizer_params['scheduler'])
        if USE_DDP:
            for state in self.optimizer.state.values():
                for k, v in state.items():
                    if torch.is_tensor(v):
                        # print(k, v.size())
                        state[k] = v.to(self.gpu_id)

        # result folder, logger
        self.logger = getLogger(name='trainer')
        self.result_folder = './result/' + datetime.now().strftime("%Y%m%d_%H%M%S_") \
            + self.trainer_params["training_target"]
        # self.result_log = LogData()
        # Restore
        self.start_epoch = 1 

        # utility
        self.time_estimator = TimeEstimator()


    def run(self):
        model_save_interval = self.trainer_params['logging']['model_save_interval']
        min_model_save_epoch = self.trainer_params['logging']['min_model_save_epoch']
        # img_save_interval = self.trainer_params['logging']['img_save_interval']
        self.time_estimator.reset(self.start_epoch)
        min_score = 9999999999
        self.model.train()
        if USE_DDP:
            dist.barrier()

        self.logger.info('=========================Started Training========================================')
        for epoch in range(self.start_epoch, self.trainer_params['epochs']+1):
            if USE_DDP:
                self.dataloader.sampler.set_epoch(epoch)
            train_score, train_loss = self._train_one_epoch(epoch)
            # self.result_log.append('train_score', epoch, train_score)
            # self.result_log.append('train_loss', epoch, train_loss)

            ############################
            # Logs & Checkpoint
            ############################
            elapsed_time_str, remain_time_str = self.time_estimator.get_est_string(epoch, self.trainer_params['epochs'])
            self.logger.debug("Epoch {:3d}/{:3d}: Time Est.: Elapsed[{}], Remain[{}]".format(
                epoch, self.trainer_params['epochs'], elapsed_time_str, remain_time_str))

            all_done = (epoch == self.trainer_params['epochs'])

            # Save latest images, every epoch
            # if epoch > 1000000:
            #     self.logger.debug("Saving log_image")
            #     image_prefix = '{}/latest'.format(self.result_folder)
            #     util_save_log_image_with_label(image_prefix, self.trainer_params['logging']['log_image_params_1'],
            #                         self.result_log, labels=['train_score'])
            #     util_save_log_image_with_label(image_prefix, self.trainer_params['logging']['log_image_params_2'],
            #                         self.result_log, labels=['train_loss'])

            # Save Model
            if all_done or (epoch % model_save_interval) == 0:
                if (self.gpu_id != 0) :
                    continue

                if epoch < min_model_save_epoch:
                    continue
                if train_score > min_score:
                    if (epoch % (model_save_interval*20)) != 0:
                        self.logger.info(f"Model saving is skipped at epoch {epoch}")
                        continue
                model_dict = self.model.state_dict()
                if USE_DDP:
                    model_dict = self.model.module.state_dict()


                checkpoint_dict = {
                    'epoch': epoch,
                    'model_state_dict': model_dict,
                    'optimizer_state_dict': self.optimizer.state_dict(),
                    'scheduler_state_dict': self.scheduler.state_dict(),
                    'env_params': self.env_params,
                    'model_params': self.model_params,
                    'trainer_params': self.trainer_params, 
                }
                if not os.path.exists(self.result_folder):
                    os.makedirs(self.result_folder)


                save_filename = '{}_checkpoint_{}_score{}.pt'.format(self.result_folder, epoch,int(train_score)) 
                torch.save(checkpoint_dict, save_filename)
                self.logger.info(f"Saved trained model to {save_filename}")
            self.trainer_params['max_warmup_swap_steps'] = 0
            if self.trainer_params['enable_warmup_swap_steps']:
                if epoch > 200:
                    self.trainer_params['max_warmup_swap_steps'] = epoch // 10
                
            # Save Image
            # if all_done or (epoch % (img_save_interval*100)) == 0:
            #     image_prefix = '{}/img/img-checkpoint-{}'.format(self.result_folder, epoch)
            #     util_save_log_image_with_label(image_prefix, self.trainer_params['logging']['log_image_params_1'],
            #                         self.result_log, labels=['train_score'])
            #     util_save_log_image_with_label(image_prefix, self.trainer_params['logging']['log_image_params_2'],
            #                         self.result_log, labels=['train_loss'])

            # All-done announcement
            if all_done:
                self.logger.info(" *** Training Done *** ")
                self.logger.info("Now, printing log array...")
                # util_print_log_array(self.logger, self.result_log)

    def _train_one_epoch(self, epoch):

        score_AM = AverageMeter()
        loss_AM = AverageMeter()

        num_train_episodes = self.trainer_params['train_episodes']
        episode = 0
        loop_cnt = 0
        prev_log_probs = None
        ## =====================================================================
        ## =====================================================================
        for batch_i, batch in enumerate(self.dataloader):
            # loc_xy = torch.stack(
            #     [self.dataset[b_i][0] for b_i in batch_indices]
            # )
            # dist_matrix = torch.stack(
            #     [self.dataset[b_i][1] for b_i in batch_indices]
            # )
            if len(batch) <= 2:
                assert False, "pls use dataset to create job_loc_idx" 

            loc_xy = batch[0] # .to(self.gpu_id).float()
            dist_matrix = batch[1] # .to(self.gpu_id).float()
            worker_loc_idx = batch[2] # .to(self.gpu_id).long()
            job_loc_idx = batch[3] # .to(self.gpu_id).long()
            next_job_idx = batch[4] # .to(self.gpu_id).long()
            next_job_mask = batch[5] # .to(self.gpu_id).float()
            # remaining = num_train_episodes - episode
            # batch_size = min(self.trainer_params['train_batch_size'], remaining)

            avg_score, avg_loss, batch_size, batch_info, prev_log_probs  = self._train_one_batch(
                loc_xy, dist_matrix,
                worker_loc_idx, job_loc_idx, next_job_idx, next_job_mask, prev_log_probs)
            # batch_size = avg_score.size(0)
            score_AM.update(avg_score, batch_size)
            loss_AM.update(avg_loss, batch_size)

            episode += batch_size

            # Log First 10 Batchs, only at the first epoch
            loop_cnt += 1
            if (epoch == self.start_epoch):
                if loop_cnt <= 10:
                    self.logger.info('Epoch {:3d}: Train {:3d}/{:3d}({:1.1f}%)  Score: {:.4f},  Loss: {:.4f}, {}'
                                     .format(epoch, episode, num_train_episodes, 100. * episode / num_train_episodes,
                                             score_AM.avg, loss_AM.avg, batch_info))
            if loop_cnt == 1 and False:
                worker_i = int(torch.argmax(self.env.step_state.worker_selected_loc_length[0,0]))
                tsp_env = self.env.tsp_env
                print(f"At worker_i = {worker_i}, loc_xy = { tsp_env.step_state.reset_state.loc_xy [worker_i].tolist()}") 
                print(f"next_jobs = {tsp_env.next_job_idx[worker_i,0].tolist()}") 
                print(f"solution = {tsp_env.selected_node_list[worker_i,0].tolist()}") 

            if episode >= num_train_episodes:
                break
        # Log Once, for each epoch
        if (self.gpu_id == 0):
            self.logger.info(
                'Epoch: {:3d}, Score: {:.4f}, Loss: {:.4f}, LR: {}, Episodes: {}, last_batch: {}'.format(
                    epoch, score_AM.avg, loss_AM.avg, self.scheduler.get_last_lr(), episode, batch_info)
            )

        return score_AM.avg, loss_AM.avg

    def _train_one_batch(self, 
        loc_xy, 
        dist_matrix,
        worker_loc_idx = None,
        job_loc_idx = None,
        next_job_idx = None,
        next_job_mask = None,
        prev_log_probs = None
        ):

        self.batch_size, self.pomo_size, self.worker_size = worker_loc_idx.size()
        # Prep
        ###############################################
        # self.model.train()
        self.env.load_jobs(
            loc_xy = loc_xy, 
            dist_matrix= dist_matrix,
            worker_loc_idx = worker_loc_idx,
            job_loc_idx = job_loc_idx,
            next_job_idx = next_job_idx,
            next_job_mask = next_job_mask,
            aug_factor=1, 
        )
        step_state, reward, done = self.env.reset()
        # step_state.max_warmup_swap_steps = self.trainer_params['max_warmup_swap_steps']
        
        if self.trainer_params["training_target"] not in ('online_pick_drop_job2slot', ): # online_job2slot  ?  # , 'pickdrop_pomo_n2s' 
            if USE_DDP:
                self.model.module.pre_forward(step_state.reset_state)
            else:
                self.model.pre_forward(step_state.reset_state)

        # log_prob_list = torch.zeros(size=(self.batch_size, self.pomo_size, 0))
        # shape: (batch, pomo, 0 ), for selected prob on a specific worker (like pomo job)

        # POMO Rollout
        ###############################################
        # step_state, reward, done = self.env.pre_step()
        listof_log_prob = []

        while not done:
            if step_state.job2slot_tsp_step == 1 and step_state.tsp_pre_forward_done == 0:
                if USE_DDP:
                    self.model.module.pre_tsp_forward(step_state)
                else:
                    self.model.pre_tsp_forward(step_state)
                step_state.tsp_pre_forward_done = 1

            if step_state.job2slot_n2s_step == 1:
                nbr_warmup_steps = random.randint(0, self.trainer_params['max_warmup_swap_steps'])
                if nbr_warmup_steps > 0:
                    # warm up steps to train on later stage fine swaps
                    self.model.eval()
                    with torch.no_grad():
                        for _ in range(nbr_warmup_steps):
                            selected, prob, _probs = self.model(step_state)
                            step_state, reward, done = self.env.step(selected)
                    self.model.train()

            selected, prob, _probs = self.model(step_state)
            # shape: (batch, pomo)
            step_state, reward, done = self.env.step(selected)

            log_prob = prob.log()
            if step_state.tsp_pre_forward_done == 1:
                log_prob = log_prob.reshape(self.batch_size, self.pomo_size, self.worker_size).sum(dim=2)
            log_prob = log_prob.view(self.batch_size,self.pomo_size, 1)
            # log_prob_list = torch.cat((log_prob_list, log_prob ), dim=-1)
            listof_log_prob.append(log_prob)

        # Loss
        ###############################################
        # shape: (batch, pomo, number_of_choices)
        reward = reward.view(self.batch_size,self.pomo_size)
        log_prob = torch.cat(listof_log_prob,dim=2).sum(dim=2)
        # log_prob = log_prob_list.sum(dim=2)
        advantage = reward - reward.float().mean(dim=1, keepdims=True)
        
        # shape: (batch, pomo)
        orig_loss = -advantage * log_prob  # Minus Sign: To Increase REWARD
        loss_mean = orig_loss.mean()
        # loss_mean.retain_grad()


        # if prev_log_probs is None:
        #     prev_log_probs = log_prob.detach()
        # # Finding the ratio (pi_theta / pi_theta__old):
        # ratios = torch.exp(log_prob - prev_log_probs.detach())
        
        # eps_clip = self.trainer_params["eps_clip"]
        # surr1 = ratios * advantage
        # surr2 = torch.clamp(ratios, 1 - eps_clip, 1 + eps_clip) * advantage
        # reinforce_loss = -torch.min(surr1, surr2)# .mean()
        

        # loss_mean = reinforce_loss.mean() 

        # Score
        ###############################################
        # TODO, 2022-12-31 19:45:09, change max to mean, to maximize across all POMO permutation.
        # TODO-2, change path->loc matching to mean(locs)->loc mapping, and see difference.
        
        # mean_pomo_reward = reward.mean(dim=1)  # get best results from pomo
        score_mean = -reward.float().mean().item()  # negative sign to make original positive distance value

        # from torchviz import make_dot
        # dot = make_dot(loss_mean, params=dict(self.model.named_parameters()))
        # dot.render("n2s_loss_dot_cpu_1")


        # Step & Return
        ###############################################
        self.optimizer.zero_grad()
        loss_mean.backward()
        self.optimizer.step()
        # LR Decay
        self.scheduler.step()
        batch_info = ""
        if self.trainer_params["training_target"] in ("pickdrop_pomo_n2s", ):
            last_obj_mean = round(step_state.prev_best_obj[:,0].mean().item(),2)
            prev_best_step_mean = round(step_state.prev_best_step[:,1].float().mean().item(),2)
            batch_info = f"loss = {round(loss_mean.item(),4)}, advantage_abs_mean={round(advantage.abs().mean().item(),4)}, last_obj_mean={last_obj_mean}, prev_best_step_mean = {prev_best_step_mean}, prev_best_step_0= {step_state.prev_best_step[:,1].tolist()[:8]}"


        return score_mean, loss_mean.item(), self.batch_size, batch_info, log_prob.detach()