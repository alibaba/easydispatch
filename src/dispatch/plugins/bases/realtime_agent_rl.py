from dispatch.config import MODEL_ROOT_DIR
from dispatch.plugins.bases.realtime_agent import KandboxAgentPlugin
import pymap3d
import torch
import logging
import copy
log = logging.getLogger("rl_realtime_agent")
device = torch.device('cpu')


from dispatch.contrib.training.pomo.pomo_params import  env_params as default_env_params
from dispatch.contrib.training.pomo.pomo_params import  model_params as default_model_params


class KandboxRLAgentPlugin(KandboxAgentPlugin):
    def __init__(self, config=None,):
        self.config = copy.deepcopy(self.default_config)
        if config:
            self.config.update(config)
        checkpoint_fullname = self.config["job2slot_model_path"].replace("$ROOT", MODEL_ROOT_DIR)
        checkpoint = torch.load(checkpoint_fullname, map_location=device)
        if "env_params" in checkpoint:
            self.env_params = checkpoint["env_params"]
        else:
            self.env_params = copy.copy(default_env_params)

        if "model_params" in checkpoint:
            self.model_params = checkpoint["model_params"]
        else:
            self.model_params = copy.copy(default_model_params)
 
        self.env_params["pomo_size"] = 1
        self.model_params['eval_type'] == 'argmax'

        self.load_model(checkpoint)
        log.info(f'Loaded job2slot model from {checkpoint_fullname}'  )

        self.decode_type = "greedy"
        self.job2slot_env.training = False
        self.batch_size = 1
        self.pomo_size = 1
        self.worker_size = 1
        self.max_job_in_worker_size = self.env_params['max_job_in_worker_size']


    def normalize_addr(self,loc_xy, env): 
        enu_max_meters = float(env.config.get("enu_max_meters",40_000))
        if self.config["coordinate"] == "enu_normal":
            # 2023-11-16 22:12:49 I make it 0-1, instead of -1 ~ 1, 
            longitude_mu = env.team_geo_longitude - float(env.config.get("enu_longitude_diff_min", 0.2) )
            latitude_mu = env.team_geo_latitude - float(env.config.get("enu_latitude_diff_min", 0.2) ) 

            # longitude_mu = (float(env.config["longitude_diff_max"]) + float(env.config["longitude_diff_min"])) / 2
            # longitude_cov = env.config["longitude_diff_max"] - longitude_mu
            # latitude_mu = (float(env.config["latitude_diff_max"]) + float(env.config["latitude_diff_min"])) / 2
            # latitude_cov = env.config["latitude_diff_max"] - latitude_mu

            altitude = float(env.config.get("enu_geo_altitude", 50))
            enu_loc_list = []
            for i in range(loc_xy.size(0)):
                loc = loc_xy[i,0:2].tolist()
                east, north, u = pymap3d.geodetic2enu(loc[1], loc[0], altitude, latitude_mu, longitude_mu, altitude)
                enu_loc_list.append([east, north,])
            
            enu_t = torch.tensor(enu_loc_list)

            loc_xy[:,0] = enu_t[:,0] / enu_max_meters
            loc_xy[:,1] = enu_t[:,1] / enu_max_meters

        else:
            # wgs84_minmax 
            longitude_max = env.team_geo_longitude + float(env.config["longitude_diff_max"])
            longitude_min = env.team_geo_longitude - float(env.config["longitude_diff_min"])
            latitude_max = env.team_geo_longitude + float(env.config["latitude_diff_max"])
            latitude_min = env.team_geo_longitude - float(env.config["latitude_diff_min"])
            loc_xy[:,0] = (loc_xy[:,0] - longitude_min) / (longitude_max - longitude_min)
            loc_xy[:,1] = (loc_xy[:,1] - latitude_min) / (latitude_max - latitude_min)
        # loc_xy[:,2] = (loc_xy[:,2] - 0) / ALLOWED_MAXIMUM_MINUTES
        return loc_xy
