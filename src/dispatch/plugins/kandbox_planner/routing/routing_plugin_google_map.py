
from json import JSONDecodeError
import logging
import copy

import vroom
from dispatch.plugins.kandbox_planner.routing.routing_plugin_osrm_opti_tsp import OSRMOptiTSPRoutingPlugin
import googlemaps
from typing import List

import numpy as np
from dispatch.config import LONG_LAT_PRECISION, VROOM_SOLVER_NB_THREADS


from dispatch.plugins.kandbox_planner.travel_time_plugin import OSRMTravelTime
from dispatch.plugins.kandbox_planner.util.cache_dict import CacheDict

travel_time_dict = CacheDict(cache_len=5000)

SLUG_NAME = "google_map_opti_routing_backend"

log = logging.getLogger(SLUG_NAME)


class GoogleMapOptiRoutingPlugin(OSRMOptiTSPRoutingPlugin):
    """
    Has the following members
    """
    title = "Google map backend routing service"
    slug = SLUG_NAME
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "Google map  backend routing service"
    version = "0.1.0"

    default_config = {
        "service_key": "a",
        "route_service_url": "https://routing.easydispatch.uk/gcc",
        "max_nbr_elements": "10",

    }
    config_form_spec = {
        "type": "object",
        "properties": { 
            "service_key": {
                "type": "string",
                "default": "a",
                "title": "service_key", 
            }, 
            "route_service_url": {
                "type": "string",
                "default": "https://routing.easydispatch.uk/gcc",
                "title": "route_service_url", 
            }, 
            "max_nbr_elements": {
                "type": "number",
                "default": 10,
                "title": "max_nbr_elements is limitted by google api. System will fall back to other routing beyond this limit"
            },

            "verify_https": {
                "type": "boolean",
                "code": "Verify HTTPS certificate",
                "description": "Verify HTTPS certificate",
            },
        },
    }
    def __init__(
        self, config = {},
    ):
        self.config = copy.deepcopy(self.default_config)
        if config:
            self.config.update(config)

        self.service_key = str(self.config.get('service_key',"service_key") ) 
        self.gmaps = googlemaps.Client(key=self.service_key)

        # self.speed_km_hour = int(self.config.get('speed_km_hour',18) )
        # self.speed_meter_minute = round(self.speed_km_hour * 1000 / 60, 1)
        # self.min_minutes = int(self.config.get('min_minutes',1) )
        # self.max_minutes = int(self.config.get('max_minutes',240) )
        # self.travel_mode = str(self.config.get('travel_mode',"car") )
        # self.return_type = "duration" if self.travel_mode in ("car", "driving") else "distances"

        # self.max_distance = 100_000  # In meters
        # self.verify_https = self.config.get('verify_https',"0") == 1

        self.osrm_plugin = OSRMTravelTime(self.config)
        self.max_nbr_elements = int(self.config.get("max_nbr_elements", 10))


 

    def get_travel_minutes_matrix(self, loc_list: List, return_type=None, options = None):
        """
        获取时间矩阵
        """
        if len(loc_list) > self.max_nbr_elements:
            return self.osrm_plugin.get_travel_minutes_matrix(
                loc_list=loc_list, return_type = return_type, options=options)

        addr = [
            (round(a[1],LONG_LAT_PRECISION),round(a[0],LONG_LAT_PRECISION))
            for a in loc_list
        ]

        # Get distance by [(latitude, longitude)]
        # assert False
        if options and  "departure_time" in options:
            result = self.gmaps.distance_matrix(
                addr, addr, mode = 'driving',
                departure_time = options["departure_time"]
            )
        else:
            result = self.gmaps.distance_matrix(
                addr, addr, mode = 'driving',
            )

        dist_mat = np.ndarray((len(addr),len(addr)))

        for ri, row in enumerate(result["rows"]):
            for ei, elem in enumerate(row["elements"]):
                dist_mat[ri, ei] = elem["duration"]["value"]
        dist_mat_np = dist_mat / 60
        log.info(f"{self.slug}:distance_matrix_statistics: (max = {dist_mat_np.max()}, min = {dist_mat_np.min()}, sum = {round(dist_mat_np.sum(),2)}, mean = {round(dist_mat_np.mean(),2)}, median = {round(np.median(dist_mat_np),2)})")

        return dist_mat_np
 
    def get_travel_minutes_path(self, loc_list):  # get_travel_time_2locations
        return self.osrm_plugin.get_travel_minutes_path(
            loc_list=loc_list)

        # use self.gmaps.directions in future.