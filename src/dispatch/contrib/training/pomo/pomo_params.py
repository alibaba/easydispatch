##########################################################################################
# Machine Environment Config
import torch
torch.set_printoptions(edgeitems=5, linewidth = 2000)
import numpy as np
np.set_printoptions(edgeitems=5, linewidth = 2000)

from dispatch.config import (
    ADDR_DIM, MIN_MODEL_SAVE_EPOCH, basedir, USE_CUDA, 
    USE_DDP,
    TRAIN_EPISODES, TRAIN_BATCH_SIZE, TRAIN_POMO_SIZE, NUM_DATALOADER_WORKERS, 
    MAP_SCALE, ROUTER_CLASS, MAX_NBR_JOB_IN_WORKER, TRAIN_WORKER_SIZE, TRAIN_JOB_SIZE,
    EMBEDDING_DIM, HEAD_NUM, ENCODER_LAYER_NUM, ALLOW_CHANGING_WORKER_FLAG
)


# dataset_name ='us_la_haversine'   
# TRAINING_TARGET = "single_job2slot_n2s" # pickdrop_pomo_n2s pickdrop_job2slot_tsp_2in1


# 2023-11-02 17:24:26, ENU_10KM_UNIFORM + pickdrop_pomo_n2s, works. 
# Final result on ed1v100: /home/dispatch/easydispatch/training_pomo_n2s_swap_5_workermean_32_dropout__enu__20230908_1_score_5.98_duan.txt
###############################
dataset_name ='ENU_10KM_UNIFORM'   
# dataset_name ='london_croydon_pickdrop'   

# TRAINING_TARGET = "pickdrop_pomo_n2s" # pickdrop_pomo_n2s pickdrop_job2slot_tsp_2in1

# dataset_name ='us_la_haversine'   
TRAINING_TARGET = "single_job2slot_n2s"


# us_la_haversine, london,  online_job2slot, dubai_single
# 
#  "ganzhou", setagaya , singapore,  setagaya_double, ENU_10KM_UNIFORM,  turkey_double
# riyadh_double, dubai_double, dubai_double_random
# pick_drop_tsp_with_start_dubai_random
# 


# 2023-11-02 19:45:47, building single_job2slot_n2s to compete against job2slot
# 2023-03-19 19:12:10   "pickdrop_job2slot_tsp_2in1" + dataset_name ='dubai_double_random' 
# 2023-03-19 19:12:21 pick_drop_tsp_with_start + dataset_name ='dubai_double'
# + pick_drop_tsp_with_start_dubai_random

# "pickdrop_job2slot_tsp_2in1",    "pick_drop_tsp_with_start"
# "tsp", +  "online_job2slot" : Done 2022-11-22 04:16:29 (from Oct to Nov).
# tsp, pick_drop_tsp,  -- The TSP for FSM, no pick drop.
# "job2slot",online_job2slot, -- This is FSM implementation.
# 
# pick_drop_tsp_with_start was successfully, on singapore dataset,  at 2022-06-08 15:43:19.  20221122_055252_pick_drop_tsp_with_start_checkpoint_5130.pt
# -- model saved in etc/training_logs/traning_20221121_tsp_singapore_1.log
# online_pick_drop_job2slot , 2022-12-02 00:55:36, singapore dataset, only reach 1345->950 score after 5 days, on /data/easydispatch/traning_20221125_pickdrop_job2slot_singapore.log
# pick_drop_job2slot, pick_drop_job2slot , 2022-12-12,  singapore dataset, only reach 1345->980 score after 10 days, in file traning_20221201_static_pickdrop_job2slot_singapore.log
# "pickdrop_job2slot_tsp_2in1" vs pickdrop_job2slot_tsp_3in1
# "pickdrop_tsp_n2s" vs "pick_drop_tsp_with_start", 2023-03-04 11:53:01

# 2023-06-03 16:06:56, job2slot + tsp & singapore / us_la_haversine works.
# 2023-06-29 11:12:03   "pickdrop_job2slot_tsp_2in1" + dataset_name ='turkey_double' 

# 2023-08-05 18:44:54, pickdrop_job2slot_tsp_2in1 
# 2023-08-25 19:01:20 pickdrop_pomo_n2s is added.
# 2023-09-07 15:31:37 pickdrop_pomo_n2s trained. 


from pathlib import Path
path = Path(basedir)
data_basedir = path.parent.parent.absolute()


DEBUG_MODE = False
# USE_CUDA = False
USE_MPS = False
# CUDA_DEVICE_NUM = 0

# cuda
# device = torch.device('cpu')
# torch.set_default_dtype('torch.FloatTensor')

# if USE_CUDA:
#     # cuda_device_num = CUDA_DEVICE_NUM
#     # torch.cuda.set_device(cuda_device_num)
#     # device = torch.device('cuda', cuda_device_num)
#     device = torch.device('cuda:0')
#     torch.set_default_dtype('torch.cuda.FloatTensor')

# if USE_MPS:
#     device = torch.device('mps:0')

# print('USE_CUDA: {}, CUDA_DEVICE_NUM is disabled'.format(USE_CUDA))
# print('USE_MPS: {}, device = {}'.format(USE_MPS, device))


##########################################################################################
# parameters
dataset_params = {
    'ENU_10KM_UNIFORM':{
        "file_path":"",
        "worker_file_path":"",
        "location_type": "double_enu_10km", #  "double",  "double_enu_10km"-- this avoids loading csv
        'east_mean' : 0, 
        'east_variance' : MAP_SCALE,
        'north_mean' : 0, 
        'north_variance' : MAP_SCALE,
        'geo_longitude_max' : MAP_SCALE, 
        'geo_longitude_min' : 0-MAP_SCALE,
        'geo_latitude_max'  : MAP_SCALE,
        'geo_latitude_min'  : 0-MAP_SCALE,
        "worker_cache_size" : 20,
        "job_cache_size" : 180,
    }, 	
    'turkey_double':{
        "file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/turkey-atp/job_log.csv",
        "worker_file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/turkey-atp/worker_log.csv",
        "location_type": "double",
        'geo_longitude_max' : 35.4 , 
        'geo_longitude_min' : 35.2 ,
        'geo_latitude_max'  : 37.1 ,
        'geo_latitude_min'  : 36.9 , 
        "worker_cache_size" : 20,
        "job_cache_size" : 180,
    },
    'dubai_double_random':{
        "file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/dubai/training_random_loc/drop_random_loc.csv",
        "worker_file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/dubai/training_random_loc/pick_random_loc.csv",
        "location_type": "double",
        'geo_longitude_max' : 55.7, 
        'geo_longitude_min' : 55.0,
        'geo_latitude_max'  : 25.5,
        'geo_latitude_min'  : 24.9, 
        "worker_cache_size" : 40,
        "job_cache_size" : 180,
    },
    'dubai_double':{
        "file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/dubai/large/job_log.csv",
        "worker_file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/dubai/large/worker_log.csv",
        "location_type": "double",
        'geo_longitude_max' : 56, 
        'geo_longitude_min' : 54.95,
        'geo_latitude_max'  : 25.81,
        'geo_latitude_min'  : 24.80, 
        "worker_cache_size" : 20,
        "job_cache_size" : 180,
    },
    'dubai_single':{
        "file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/dubai/large/job_log.csv",
        "worker_file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/dubai/large/worker_log.csv",
        "location_type": "single",
        'geo_longitude_max' : 56, 
        'geo_longitude_min' : 54.95,
        'geo_latitude_max'  : 25.81,
        'geo_latitude_min'  : 24.80, 
        "worker_cache_size" : 20,
        "job_cache_size" : 180,
    },
    'riyadh_double':{
        "file_path":f"{data_basedir}/sample_data/riyadh_restaurants/job_log.csv",
        "worker_file_path":f"{data_basedir}/sample_data/riyadh_restaurants/worker_log.csv",
        "location_type": "double",
        'geo_longitude_max' : 46.7401973539, 
        'geo_longitude_min' : 46.584655,
        'geo_latitude_max'  : 24.826898,
        'geo_latitude_min'  : 24.635626,
        "worker_cache_size" : 20,
        "job_cache_size" : 180,
    },
    'setagaya_double':{
        "file_path":f"{data_basedir}/sample_data/setagaya/orig/job_log_case_2.csv",
        "worker_file_path":f"{data_basedir}/sample_data/setagaya/orig/worker_log_case_2_48workers.csv",
        "location_type": "double",
        'geo_longitude_max' : 139.87, 
        'geo_longitude_min' : 139.41,
        'geo_latitude_max'  : 35.70,
        'geo_latitude_min'  : 35.62,
        "worker_cache_size" : 20,
        "job_cache_size" : 180,
    },
    'setagaya':{
        "file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/setagaya.csv",
        "location_type": "single",
        'geo_longitude_max' : 139.87, 
        'geo_longitude_min' : 139.41,
        'geo_latitude_max'  : 35.70,
        'geo_latitude_min'  : 35.62,
        "worker_cache_size" : 80,
        "job_cache_size" : 210,
    }, 
    'pick_drop_tsp_with_start_dubai_random':{
        "file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/dubai/training_random_loc/drop_random_loc.csv",
        "worker_file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/dubai/training_random_loc/pick_random_loc.csv",
        "location_type": "double",
        'geo_longitude_max' : 55.7, 
        'geo_longitude_min' : 55.0,
        'geo_latitude_max'  : 25.5,
        'geo_latitude_min'  : 24.9, 
        "worker_cache_size" : 40,
        "job_cache_size" : 180,
    },
    'singapore':{
        "file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/singapore_postcode.csv",
        "location_type": "single",
        'geo_longitude_max' : 104.4, 
        'geo_longitude_min' : 103.7,
        # 'geo_longitude_min' : 103.4,
        'geo_latitude_max'  : 1.7,
        'geo_latitude_min'  : 1.26,
        # 'geo_latitude_min'  : 1.0,
        "worker_cache_size" : 80,
        "job_cache_size" : 210,
    },
    'ganzhou':{
        "file_path":f"{data_basedir}/sample_data/ganzhou_job_log_20000.csv",
        "worker_file_path":f"{data_basedir}/sample_data/ganzhou_job_log_20000.csv",
        # "file_path":"/home/dispatch/ganzhou_202105/job_log.csv",
        "location_type": "double",
        'geo_longitude_max' : 115.1,
        'geo_longitude_min' : 114.6,
        'geo_latitude_max'  : 26.0,
        'geo_latitude_min'  : 25.5,
        "worker_cache_size" : 80,
        "job_cache_size" : 210,
    },
    "london":{
        "file_path":f"{data_basedir}/src/dispatch/plugins/kandbox_planner/util/sample_london_addreses.csv",
        "location_type": "single",
        'geo_longitude_max' : 0.5, 
        'geo_longitude_min' : -1,
        'geo_latitude_max'  : 51,
        'geo_latitude_min'  : 42,
        "worker_cache_size" : 80,
        "job_cache_size" : 210,
    },
    "london_croydon_pickdrop":{ # -0.136646,51.348817,-0.065834,51.3874407
        "file_path":f"/home/dispatch/easydispatch/src/dispatch/contrib/sample_data/london/croydon/client2client/job_log.csv",
        "worker_file_path":f"/home/dispatch/easydispatch/src/dispatch/contrib/sample_data/london/croydon/client2client/worker_log.csv",
        "location_type": "double",
        'geo_longitude_max' : -0.05, 
        'geo_longitude_min' : -0.15,
        'geo_latitude_max'  : 51.4,
        'geo_latitude_min'  : 51.3,
        "worker_cache_size" : 80,
        "job_cache_size" : 210,
    },
    "us_la_haversine":{ 
        "file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/us_west/20230901/transformed/job_log.csv",
        "worker_file_path":f"{data_basedir}/src/dispatch/contrib/sample_data/us_west/20230901/transformed/worker_log.csv",
        "location_type": "single",
        'geo_longitude_max' : -118.7, 
        'geo_longitude_min' : -116.7,
        'geo_latitude_max'  : 34.3,
        'geo_latitude_min'  : 33.3,
        "worker_cache_size" : 80,
        "job_cache_size" : 210,
    }
} 
env_params = {
    'worker_size': TRAIN_WORKER_SIZE,  # 6， 8, 
    'pomo_size': TRAIN_POMO_SIZE,  # 8, 64 # When training TSP_pick_drop, pomo_size == worker_size == 8.
    'job_size': TRAIN_JOB_SIZE,  # 32， 42,   # For training, job_size is double of order_size. 10 means 5 orders, 10 jobs. Inside model, job_size = 5
    'problem_size': TRAIN_JOB_SIZE + 1,  # 50, 20, 11,   33
    "allow_changing_worker_flag": ALLOW_CHANGING_WORKER_FLAG,
    # in 2in1 model, max_job_in_worker_size is the TSP problem_size
    'max_job_in_worker_size': MAX_NBR_JOB_IN_WORKER, # 2in1 should +2
    'serving_only_n_no_reward': False,
    "rl_env_config": None,
    # "device": device,

    # Used by online env
    "solve_tsp_in_each_step": False,

    # default TSP
    # 'tsp_model_path': "/home/duanvm1/git/kandbox/easydispatch/src/dispatch/contrib/training/pomo/TSP/trained_model/saved_tsp20_model/checkpoint-500.pt",
    # 'tsp_model_path':"/home/dispatch/easydispatch/src/dispatch/contrib/training/pomo/TSP/trained_model/saved_tsp20_model/checkpoint-500.pt",

    # job2slot-FSM-OSRM version
    # 'tsp_model_path':"/home/dispatch/easydispatch/src/dispatch/contrib/training/pomo/result/20220305_222328_train_job2slot_w8_j42/checkpoint-600.pt",
    # job2slot-Pick drop-Euclidean
    # 'tsp_model_path':"/home/dispatch/easydispatch/src/dispatch/contrib/training/pomo/result/20220320_173104_train_job2slot_w8_j42/checkpoint-200.pt",

    # job2slot-Pick drop-OSRM, last ganzhou pickdrop at 2022-10-10 01:34:55
    # 'tsp_model_path':"/home/dispatch/easydispatch/etc/trained_models/pomo/pickdrop_tsp_with_start/20220527_045521_tsp_with_start_pick_drop_osrm_checkpoint-1920.pt",

    # tsp-OSRM, retraining Singapore `TSP` at 2022-10-10 01:34:55
    # 'tsp_model_path':"/data/easydispatch/result/20221010_012206_tsp/checkpoint_90.pt",
    # 2022-10-12 14:07:40 singapre tsp:   
    # 'tsp_model_path':f"{data_basedir}/project/5gmax/trained_models/20221011_062301_tsp_score_623_checkpoint_1695.pt",

    

    # 2022-11-15 14:07:40 singapre pick drop trained tsp:
    # 'tsp_model_path':"/data/easydispatch/project/5gmax/trained_models/pick_drop/20221122_055252_pick_drop_tsp_with_start_checkpoint_5130.pt",

    # 2022-12-24 06:35:08, firsrt viable model with end_minutes limit 
    # 'tsp_model_path':f"{data_basedir}/result/20221224_054844_pick_drop_tsp_with_start/checkpoint_270.pt",
    # 'tsp_model_path':f"{data_basedir}/etc/trained_models/pomo/pickdrop_setagaya/20221225_193703_pick_drop_tsp_with_start_checkpoint_520_score_155.pt",

    # 2023-06-03 17:01:59, testing us west
    'tsp_model_path':f"{data_basedir}/online_models/us_la_20230604_005345_tsp_checkpoint_140_score3367.pt",
}


model_params = {
    'loc_dim': ADDR_DIM,
    'max_job_in_worker_size': MAX_NBR_JOB_IN_WORKER, # In env, as well as here. When initializing model, only model_params is feeded in.
    'embedding_dim': EMBEDDING_DIM,
    'sqrt_embedding_dim': EMBEDDING_DIM**(1 / 2),
    'encoder_layer_num': ENCODER_LAYER_NUM,
    'qkv_dim': EMBEDDING_DIM // HEAD_NUM,
    'head_num': HEAD_NUM,
    'logit_clipping': 10,
    'ff_hidden_dim': 512,
    'eval_type': "softmax", # 'argmax', "softmax"
    "v_range":6.0,


    'model_load': False,

    # job2slot-FSM-Euclidean
    # 'job2slot_model_path': "/home/dispatch/easydispatch/etc/trained_models/pomo/20220513_201114_euc_fsm_job2slot_w8_j42checkpoint-400.pt",

    # job2slot-FSM-OSRM version
    # 'job2slot_model_path':"/home/dispatch/easydispatch/src/dispatch/contrib/training/pomo/result/20220306_155105_train_job2slot_w8_j42/checkpoint-350.pt",

    # job2slot-Pick drop-Euclidean
    # 'job2slot_model_path': '/home/dispatch/easydispatch/etc/trained_models/pomo/pickdrop/20220430_160526_pickdrop_global_w8_j42_checkpoint-20900_score_11.43.pt',
    # job2slot-pickdrop-osrm-ganzhou
    # 'job2slot_model_path': '/home/dispatch/easydispatch/result/20220626_021204_pick_drop_job2slot/checkpoint_1920.pt',
    # job2slot-Pick drop- Haversine - Ganzhou
    # 2022-04-30 14:59:59 重新训练一个，不小心删了
    # 'job2slot_model_path': '/home/dispatch/easydispatch/etc/trained_models/pomo/pickdrop/20220430_160526_job2slot_w8_j42_pickdrop_checkpoint_1700_11.7.pt',
    # 2022-07-09 21:54:10 WRONG online 模型, wrong target.
    # 'job2slot_model_path': '/data/easydispatch/etc/trained_models/pomo/pickdrop_online_osrm_ganzhou/20220702_232239_pick_drop_job2slot_online_osrm_checkpoint_965.pt',

    # 2022-07-12 14:46:05 correct ganzhou online 模型, after fixing bug
    # 'job2slot_model_path': '/data/easydispatch/etc/trained_models/pomo/training_logs/result/20220711_231810_online_pick_drop_job2slot/checkpoint_185.pt',
    # 2022-11-22 01:53:03 Use new singapore job2slot model
    # 'job2slot_model_path': '/data/easydispatch/project/5gmax/trained_models/20221012_141254_online_job2slot_score_669_checkpoint_1960.pt',

    # 2022-12-31 10:50:52, trained on japan data.
    # 'job2slot_model_path': f"{data_basedir}/etc/trained_models/pomo/pickdrop_setagaya/20221226_181231_online_pick_drop_job2slot_checkpoint_1000_score_146.pt"

    # 2023-01-08 02:28:56, trained on japan data. with 4 dimension, 2in1 model
    # 'job2slot_model_path': f"{data_basedir}/etc/trained_models/pomo/pickdrop_setagaya/20230107_060832_pickdrop_job2slot_tsp_2in1_checkpoint_340_score_99.pt"

    # 2023-01-08 16:18:25, trained on japan data. with 4 dimension, 2in1 model, 7 orders per worker
    # 'job2slot_model_path': f"{data_basedir}/etc/trained_models/pomo/pickdrop_setagaya/20230107_202908_pickdrop_job2slot_tsp_2in1_7orders_checkpoint_650_score_155.pt"
    
    # 2023-01-26 17:39:00, trained on standard 10KM ENU coordinate dataset (ENUSampleDataset). with 4 dimension, 2in1 model, 7 orders per worker
    # 'job2slot_model_path': f"{data_basedir}/etc/trained_models/pomo/enu_2in1/20230126_155000_pickdrop_job2slot_tsp_2in1_enu_10km_checkpoint_2520.pt"


    # 2023-01-30 12:04:14, trained on Riyadh restaurant dataset (ENUSampleDataset). with 4 dimension, 2in1 model, 7 orders per worker
    # 'job2slot_model_path': f"{data_basedir}/etc/trained_models/pomo/riyadh_20230130/20230130_180531_pickdrop_job2slot_tsp_2in1_checkpoint_5470_score_997.pt",
    
    # 2023-09-08 08:20:29, trained on ENU random data. score 6.44, training log: training_pomo_2in1___enu__20230907_2.txt
    # 'job2slot_model_path': f"{data_basedir}/etc/trained_models/pomon2s/enu/20230908_045421_pickdrop_job2slot_tsp_2in1_checkpoint_3340_score6.pt",

    
    # "job2slot_n2s_model_path": f"{data_basedir}/result/20230826_055502_pickdrop_pomo_n2s_checkpoint_4960_score6.pt", 

}



trainer_params = {
    "training_target": TRAINING_TARGET, 
    "eps_clip":0.2, 
    "max_warmup_swap_steps":  0,
    "enable_warmup_swap_steps": True,

    ########################################
    # 'cuda_device_num': CUDA_DEVICE_NUM,
    'epochs': 999999,
    'episode_loc_size': 500,
    'train_episodes':  TRAIN_EPISODES,  #*400 128, 16, 64 * 16,   
    # 8*50, batch 3, loader 4, pomo 16 for job2slot.
    'train_batch_size': TRAIN_BATCH_SIZE,  # 16, # 128, 64 , 8*6, 3, 256 
    'num_dataloader_workers': NUM_DATALOADER_WORKERS,  # 4, #, 64, 8, 0, 64
    'max_dm_count': 2048*4, # cache
    'prev_model_path': None,
    # 'osrm_url': ("http://192.168.9.251:5001","http://127.0.0.1:5001"),
    'osrm_url': ( "http://127.0.0.1:5009", ),
    "router_class": ROUTER_CLASS, #  OSRMTravelTime1, HaversineTravelTime1
    
    'dataset_name':dataset_name,
    
    # Moved to dataset dictionary
    # 'geo_longitude_max' : dataset_params[dataset_name]["geo_longitude_max"], 
    # 'geo_longitude_min' : dataset_params[dataset_name]["geo_longitude_min"], 
    # 'geo_latitude_max'  : dataset_params[dataset_name]["geo_latitude_max"], 
    # 'geo_latitude_min'  : dataset_params[dataset_name]["geo_latitude_min"], 

    'logging': {
        "min_model_save_epoch": MIN_MODEL_SAVE_EPOCH,
        'model_save_interval': 10,
        'img_save_interval': 500000,
        'log_image_params_1': {
            'json_foldername': 'log_image_style',
            'filename': 'style_cvrp_20.json'
        },
        'log_image_params_2': {
            'json_foldername': 'log_image_style',
            'filename': 'style_loss_1.json'
        },
    }
}

logger_params = {
    'log_file': {
        'desc':  "{}_w{}_j{}".format( 
            trainer_params["training_target"], 
            env_params["worker_size"],
            env_params["job_size"],) ,
        'filename': 'run_log'
    }
}


optimizer_params = {
    'optimizer': {
        'lr': 3e-4,
        'weight_decay': 1e-6
    },
    'scheduler': {
        'milestones': [10_000, 80_000, 320_000, 800_000, 2_000_000, 10_000_000,  80_000_000, 640_000_000, ],
        'gamma': 0.3
    }
}



pomo_params = {}
pomo_params.update(model_params)
pomo_params.update(env_params)
pomo_params.update(trainer_params)




# Online testing 2022-06-29 16:51:35
# trainer_params.update({
#     'training_target': 'online_pick_drop_job2slot',
#     'train_episodes': 160,  # 128, 16, 64 * 16
#     'train_batch_size': 1,  # 16, # 128, 64
#     'num_dataloader_workers': 0,  # 4, #, 64, 8, 0, 64
# })
# env_params.update({
#     'worker_size': 8,  # 6， 8, 
#     'job_size': 42,  # 32， 42,  
#     'pomo_size': 2,  # 6, 64
# })

tester_params = dict(trainer_params)
tester_params.update({
    # 'train_episodes': 18,  # 128, 16, 64 * 16
    'train_batch_size': 1,  # 16, # 128, 64
    'num_dataloader_workers': 0,  # 4, #, 64, 8, 0, 64
    # 'training_target': 'online_pick_drop_job2slot', # online_pick_drop_job2slot pick_drop_job2slot
    'max_dm_count': 10,
})
