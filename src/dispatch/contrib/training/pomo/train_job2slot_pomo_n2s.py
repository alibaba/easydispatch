

##########################################################################################
# Path Config


# import os
# import sys
# os.chdir(os.path.dirname(os.path.abspath(__file__)))
# sys.path.insert(0, "..")  # for problem_def
# sys.path.insert(0, "../..")  # for utils


##########################################################################################
# import


import logging

# from dispatch.contrib.training.pomo.utils.utils import create_logger, copy_all_src

#OLD
# from dispatch.contrib.training.pomo.job2slot.Job2SlotTrainer import Job2SlotTrainer as Trainer



# v 1
from dispatch.contrib.training.pomo.job2slot_input_data_trainer import Job2SlotInputDataTrainer as Trainer

# v 2
# from dispatch.contrib.training.pomo.job2slot.pomo_n2s_trainer  import Job2SlotInputDataTrainer as Trainer

from dispatch.contrib.training.pomo.pomo_params import ( 
    USE_DDP,
    env_params, pomo_params, optimizer_params, trainer_params, logger_params, 
    DEBUG_MODE) # model_params
from dispatch.contrib.training.pomo.pomo_params import pomo_params as model_params

##########################################################################################
# main



import torch.multiprocessing as mp
from torch.utils.data.distributed import DistributedSampler
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.distributed import init_process_group, destroy_process_group
import os

def ddp_setup(rank, world_size):
    """
    Args:
        rank: Unique identifier of each process
        world_size: Total number of processes
    """
    os.environ["MASTER_ADDR"] = "localhost"
    os.environ["MASTER_PORT"] = "12355"
    init_process_group(backend="nccl", rank=rank, world_size=world_size)

    torch.set_default_device('cuda')
    torch.cuda.set_device(rank)

    torch.set_default_tensor_type('torch.cuda.FloatTensor')
    # torch.set_default_dtype(torch.float32)
    # torch.set_default_device(f'cuda:{rank}')


# from dispatch.contrib.training.slotattention.train_job2slot.training_util import (
#     device, 
#     get_env_config
# )
# from dispatch.contrib.training.slotattention.train_job2slot.train_args_parser import parser

from dispatch.logging import configure_logging
configure_logging()



def main(rank: int, world_size: int,):
    if USE_DDP:
        ddp_setup(rank, world_size)
    if DEBUG_MODE:
        _set_debug_mode()
    # args = parser.parse_args()
    # e_config = get_env_config(args)
    # e_config["travel_min_minutes"] = 10 
    
    env_params["rl_env_config"] = None

    # create_logger(**logger_params)
    _print_config(rank)

    trainer = Trainer(env_params=env_params,
                      model_params=model_params,
                      optimizer_params=optimizer_params,
                      trainer_params=trainer_params,
                      gpu_id = rank,
                      )

    # copy_all_src(trainer.result_folder)

    trainer.run()
    if USE_DDP:
        destroy_process_group()


def _set_debug_mode():
    global trainer_params
    trainer_params['epochs'] = 2
    trainer_params['train_episodes'] = 4
    trainer_params['train_batch_size'] = 2


def _print_config(rank):
    logger = logging.getLogger('root')
    logger.info('DEBUG_MODE: {}, rank {} '.format(DEBUG_MODE, rank))
    [logger.info(f"rank: {rank}, " + g_key + "{}".format(globals()[g_key])) for g_key in globals().keys() if g_key.endswith('params')]



##########################################################################################
import torch
if __name__ == "__main__":
    # torch.multiprocessing.set_start_method('spawn')
    world_size = torch.cuda.device_count()
    if USE_DDP:
        mp.spawn(main, args=(world_size, ), nprocs=world_size)
    else:
        main(rank=0, world_size = 0)
