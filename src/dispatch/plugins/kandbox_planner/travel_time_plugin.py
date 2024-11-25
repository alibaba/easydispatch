# https://stackoverflow.com/questions/4913349/haversine-formula-in-python-bearing-and-distance-between-two-gps-points
from json import JSONDecodeError
import logging
from math import radians, cos, sin, asin, sqrt
from tokenize import String
import requests
from typing import List
from requests.adapters import HTTPAdapter
import numpy as np
from dispatch.config import LONG_LAT_PRECISION

from dispatch.plugins.kandbox_planner.env.env_enums import KandboxPlannerPluginType
from dispatch.plugins.bases.location_plugin import KandboxTravelTimePlugin

from dispatch.plugins.kandbox_planner.env.env_enums import LocationType

from dispatch.plugins.kandbox_planner.util.cache_dict import CacheDict

travel_time_dict = CacheDict(cache_len=5000)
from urllib3.util.retry import Retry


# requests.adapters.DEFAULT_RETRIES = 5 # increase retries number
# session = requests.session()
# session.keep_alive = False # disable keep alive

session = requests.Session()
retry = Retry(connect=3, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

log = logging.getLogger("travel_time_plugin")

import math
import random

# a = (1, 2)
# b = (4, 5)

# print(math.dist(a,b))

from dispatch.contrib.plugins.env.nearest_insertion import NearestInsertion




class MultiLayerCacheTravelTime(KandboxTravelTimePlugin):
    def __init__(self, travel_speed, min_minutes):
        self.haversine_router = HaversineTravelTime(
            travel_speed=travel_speed, min_minutes=min_minutes
        )
        self.hit = 0
        self.miss = 0

    def get_travel_minutes_2locations(self, loc_1, loc_2):  # get_travel_time_2locations
        travel_time_key = (loc_1[0], loc_1[1], loc_2[0], loc_2[1])
        if travel_time_key in travel_time_dict.keys():
            self.hit += 1
            return travel_time_dict[travel_time_key]
        else:
            self.miss += 1
            travel_time_dict[travel_time_key] = self.haversine_router.get_travel_minutes_2locations(
                loc_1, loc_2
            )
            log.debug(f"travel time loaded for  ={loc_1} -> {loc_2}")
        return travel_time_dict[travel_time_key]



class HaversineTravelTime1:
    """
    Calculate HaversineTravelTime, inspired by

    # https://github.com/mrJean1/PyGeodesy
    # http://www.movable-type.co.uk/scripts/latlong.html
    """

    default_config = {
        "consider_home_start": True,
        "travel_speed": 30,
        "min_minutes": 1,
        "max_minutes": 240
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "consider_home_start": {
                "type": "boolean",
                "code": "Consider Home Start",
                "description": "If considered, home to first job is calculated. If not considered, home to first job is always zero",
            },
            "travel_speed": {
                "type": "number",
                "code": "Travel Speed (KM/H)",
                "description": "Travel Speed in Kilometer per Hour. This is used to calcuated minutes according to the distance",
            },
            "min_minutes": {
                "type": "number",
                "code": "Minimum Travel Minutes",
            },
            "max_minutes": {
                "type": "number",
                "code": "Maximum Travel Minutes",
            },

        },
    }
    # travel_speed = 40
    slug = "internal_haversine"
    title = "internal_haversine"

    def __init__(self, travel_speed=30, min_minutes=5, max_minutes=None, travel_mode=None,  env=None, redis_conn = None, osrm_url=""):
        if env is None:
            self.travel_speed = travel_speed
            self.min_minutes = min_minutes
            self.max_minutes = max_minutes
            self.consider_home_start = self.default_config['consider_home_start']

        else:
            self.travel_speed = env.get('travel_speed', self.default_config['travel_speed'])
            self.min_minutes = env.get('min_minutes', self.default_config['min_minutes'])
            self.max_minutes = env.get('max_minutes', self.default_config['max_minutes'])
            self.consider_home_start = env.get('consider_home_start', self.default_config['consider_home_start'])

    def haversine(self, lon1, lat1, lon2, lat2):
        """
        Calculate the great circle distance between two points
        on the earth (specified in decimal degrees)
        """
        # convert decimal degrees to radians
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

        # haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        r = 6371  # Radius of earth in kilometers. Use 3956 for miles
        return c * r

        # haversine( 0, 51.5, -77.1,  38.8)  = 5918.185064088763  // From London to Arlington

    def haversine_np(self, lon1, lat1, lon2, lat2): 
        lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2

        c = 2 * np.arcsin(np.sqrt(a))
        km = 6371 * c
        return km

    def get_travel_minutes_2locations(self, loc_1, loc_2):  # get_travel_time_2locations
        # new_1 = (round(loc_1[0], 5), round(loc_1[1], 5))
        # new_2 = (round(loc_2[0], 5), round(loc_2[1], 5))
        if (loc_1[0] == loc_2[0]) & (loc_1[1] == loc_2[1]):
            return 0

        # For training purpose 2021-03-31 20:43:01
        if not self.consider_home_start:
            if (len(loc_1) > 2) and (loc_1[2] == LocationType.HOME):
                return 0
            if (len(loc_2) > 2) and (loc_2[2] == LocationType.HOME):
                return 0

        distance = self.haversine(loc_1[0], loc_1[1], loc_2[0], loc_2[1])
        travel_time = distance / (self.travel_speed / 60)  # 60 minuts per hour
        # print('travel_time: ',loc_1, loc_2, "--: ", travel_time)
        if travel_time < self.min_minutes:
            return self.min_minutes
        if self.max_minutes is not None:
            if travel_time > self.max_minutes:
                return self.max_minutes
                # print([loc_1[0], loc_1[1], loc_2[0], loc_2[1]], (travel_time), "Error, too long")

        return travel_time

    def get_travel_minutes_matrix(
        self, loc_list: List, return_type=None, options = None
    ):  # get_travel_time_2locations

        matrix = np.zeros((len(loc_list), len(loc_list)))
        for i in range(len(loc_list)):
            for j in range(0, i): # len(loc_list)
                d = self.get_travel_minutes_2locations(loc_list[i], loc_list[j]) # int * 10, 2022-12-23 08:46:23 Why?
                matrix[i][j] = d
                matrix[j][i] = d

        return matrix

    def get_travel_minutes_matrix_np(self, loc_list: List):  # get_travel_time_2locations

        matrix = np.zeros((len(loc_list), len(loc_list)))
        loc_np = np.transpose(np.array(loc_list))
        loc_len = len(loc_list)

        lon = np.array([np.tile(loc_np[0], loc_len), np.repeat(loc_np[0], loc_len)])  # np.transpose

        lat = np.array([np.tile(loc_np[1], loc_len), np.repeat(loc_np[1], loc_len)])

        matrix = self.haversine_np(lon[0], lat[0], lon[1], lat[1])

        return matrix.reshape((len(loc_list), len(loc_list),)) / (
            self.travel_speed / 60
        )  # 60 minuts per hour

    def get_travel_distance_matrix(self, loc_list: List):
        """
        获取距离矩阵
        """
        raise NotImplemented("not implemented")
        pass

    def solve_tsp(self, loc_list=[], return_start_distance=False):
        if len(loc_list) < 1:
            return None, None 

        ni = NearestInsertion(locations=loc_list, travel_router=self, return_start_distance=True)
        solution_index, c, e, start_distance = ni.solve_ni()

        return solution_index, start_distance


    def get_travel_minutes_path(self, loc_list):  # get_travel_time_2locations
        if len(loc_list) < 2:
            return []

        prev_loc = loc_list[0]
        minutes_list = []
        for loc_i, loc in enumerate(loc_list):
            if loc_i==0:
                continue
            t = self.get_travel_minutes_2locations(prev_loc, loc)
            minutes_list.append(round(t, 2))

        log.info(f"{self.slug}:get_travel_minutes_path:result: loc_list = {loc_list}, minutes_list = {minutes_list}")
        return minutes_list

class OSRMTravelTime1:

    default_config = {
        "route_service_url": "",
        "verify_https": False,
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "route_service_url": {
                "type": "string",
                "code": "route_service_url",
                "description": "route service url, for exmaple: http://mprouting.easydispatch.uk",
            },
            "verify_https": {
                "type": "boolean",
                "code": "Verify HTTPS certificate",
                "description": "Verify HTTPS certificate",
            },
        },
    }
    slug = "internal_OSRMTravelTime"
    title = "internal_OSRMTravelTime"

    # travel_mode = "driving/foot"

    def __init__(
        self, travel_mode="foot", travel_speed=40, min_minutes=0.1, max_minutes=240, osrm_url=None, verify_https=True, env=None, redis_conn = None
        , return_type="duration" # "distances"
    ):
        self.return_type = return_type
        if env is None:
            self.speed_km_hour = 18 if travel_mode == "foot" else travel_speed
            self.speed_meter_minute = round(self.speed_km_hour * 1000 / 60, 1)
            self.min_minutes = min_minutes
            self.max_minutes = max_minutes
            # self.enable_home_travel = enable_home_travel
            self.return_duration = travel_mode in ("car", "driving")
            self.travel_mode = travel_mode
            self.osrm_url = osrm_url if osrm_url else "http://127.0.0.1:5000"
            self.max_distance = 100_000  # In meters
            self.verify_https = verify_https
        else:
            # Parameters are ignored and initialized by env config
            self.speed_km_hour = 30
            self.speed_meter_minute = round(self.speed_km_hour * 1000 / 60, 1)
            self.min_minutes = 1
            self.max_minutes = 240 
            self.return_duration = True
            self.travel_mode = "driving"
            self.osrm_url = env.get("route_service_url", "http://127.0.0.1:5000")
            self.max_distance = 100_000  # In meters

            
            self.verify_https = env.get('verify_https', self.default_config['verify_https'])

        # curl 'http://127.0.0.1:5000/route/v1/foot/114.7669601,25.6842057;114.9252620,25.8584520?steps=false&overview=false&generate_hints=false'
        self.route_url_template = (
            # "https://kerrypoc.dispatch.kandbox.com/route/v1/driving/{},{};{},{}?steps=false&overview=false&generate_hints=false"
            "{}/route/v1/{}/{},{};{},{}?steps=false&overview=false&generate_hints=false"
        )
        self.route_path_url_template = (
            # "https://kerrypoc.dispatch.kandbox.com/route/v1/driving/{},{};{},{}?steps=false&overview=false&generate_hints=false"
            "{}/route/v1/{}/{}?steps=false&overview=false&generate_hints=false"
        )

        self.table_url_template = "{}/table/v1/{}/{}?annotations=distance"
        self.table_url_template_for_duration = "{}/table/v1/{}/{}"
        # curl 'http://127.0.0.1:5000/table/v1/driving/114.7770000,25.6688760;114.7669601,25.6842057'

        # curl 'http://127.0.0.1:5000/table/v1/foot/114.7770000,25.6688760;114.7669601,25.6842057?annotations=distance'

        # self.trip_service ="http://127.0.0.1:5000/trip/v1/driving/13.388860,52.517037;13.397634,52.529407;13.428555,52.523219?source=first&destination=any"
        self.trip_service_url_template = "{}/trip/v1/driving/{}?source={}&destination={}"
        self.tsp_url_template = "{}/trip/v1/driving/{}?steps=false&source=first&destination=last&overview=simplified"
        print(f"travel measure is {return_type}")


    def get_osrm_url(self):
        if type(self.osrm_url) == tuple:
            return self.osrm_url[random.randint(0,len(self.osrm_url)-1)]
        return self.osrm_url

    def get_travel_minutes_2locations(self, loc_1, loc_2):  # get_travel_time_2locations

        url = self.route_url_template.format(
            self.get_osrm_url(), self.travel_mode, loc_1[0], loc_1[1], loc_2[0], loc_2[1]
        )
        # print(url)
        response = session.get(url,verify=self.verify_https)
        resp_json = response.json()
        try:
            travel_time = resp_json["routes"][0]["duration"] / 60
        except KeyError:
            log.debug(f"failed to get distance ({(loc_1, loc_2)}) {str(resp_json)}")
            travel_time = self.max_minutes
            return travel_time
        if travel_time < 1:
            travel_time = 1
        return round(travel_time, 2)

    def get_travel_minutes_path(self, loc_list):  # get_travel_time_2locations
        
        path_str=";".join([f"{loc[0]},{loc[1]}"  for loc in  loc_list])
        url = self.route_path_url_template.format(
            self.get_osrm_url(), self.travel_mode, path_str
        )
        # print(url)
        response = session.get(url,verify=self.verify_https)
        resp_json = response.json()
        minutes_list = []
        try:
            for leg in resp_json["routes"][0]["legs"]:
                travel_time = leg["duration"]/60
                if travel_time < self.min_minutes:
                    travel_time = self.min_minutes
                minutes_list.append(round(travel_time, 2))

        except KeyError:
            log.error(f"failed to get distance for {loc_list}")
            travel_time = self.max_minutes
            return [travel_time for _ in range(len(loc_list) - 1)]

        log.info(f"{self.slug}:get_travel_minutes_path:result: path_str = {path_str}, minutes_list = {minutes_list}")
        return minutes_list


    def get_travel_minutes_and_distance(self, loc_1, loc_2):  # get_travel_time_2locations

        url = self.route_url_template.format(
            self.get_osrm_url(), self.travel_mode, loc_1[0], loc_1[1], loc_2[0], loc_2[1]
        )
        # print(url)
        response = session.get(url,verify=self.verify_https)
        resp_json = response.json()
        try:
            travel_time = resp_json["routes"][0]["duration"] / 60
            travel_distance = resp_json["routes"][0]["distance"]
        except KeyError:
            log.debug(f"failed to get distance ({(loc_1, loc_2)}) {str(resp_json)}")
            travel_time = self.max_minutes
            return 0, 0
        if travel_time < 1:
            travel_time = 1
        if travel_distance < 1:
            travel_distance = 1

        return round(travel_time, 2), round(travel_distance, 2)

    def get_travel_minutes_matrix(self, loc_list: List, return_type=None, options = None):
        """
        获取时间
        """
        if return_type is None:
            return_type = self.return_type

        if len(loc_list) < 1:
            return None
        loc = loc_list[0]
        waypoints = "{},{}".format(round(loc[0],LONG_LAT_PRECISION), round(loc[1],LONG_LAT_PRECISION))  # round(loc[0], 5), round(loc[1], 5)
        for loc in loc_list[1:]:
            waypoints += ";{},{}".format(round(loc[0],LONG_LAT_PRECISION), round(loc[1],LONG_LAT_PRECISION))
        if return_type == "distances":
            url = self.table_url_template.format(self.get_osrm_url(), self.travel_mode, waypoints)
        elif return_type == "duration":
            url = self.table_url_template_for_duration.format(
                self.get_osrm_url(), self.travel_mode, waypoints
            )
        else:
            # 默认返回距离
            url = self.table_url_template.format(self.get_osrm_url(), self.travel_mode, waypoints)
        log.debug(f"attempting osrm url::: {url}")
        response = session.get(url,verify=self.verify_https)
        # log.info(f"osrm response:::  {response.text} {response.reason}")
        try:
            resp_json = response.json()
            if resp_json["code"] != "Ok":
                log.error(f"Not code==Ok, Failed to get table: {loc_list} {resp_json}")
                return None
            if return_type == "distances":
                dist_list = resp_json["distances"]
            elif return_type == "duration":
                dist_list = resp_json["durations"]
            else:
                # 默认返回距离
                dist_list = resp_json["distances"]
            matrix = np.array(dist_list, dtype=np.float)
        except KeyError:
            log.error(f"KeyError: Failed to get table: {loc_list} {resp_json}")
            return None
        except JSONDecodeError:
            log.error(f"JSONDecodeError: Failed to get table: {loc_list} {response.text} {response.reason}")
            return None

        # # 此循环目的是设置为不考虑返程，建议改在外层提高通用性
        # for i in range(len(loc_list)):
        #     matrix[i][0] = 0

        filling_max_minutes = self.max_minutes
        if return_type == "duration":
            filling_max_minutes = (
                self.max_distance * 60
            )  # round(self.max_distance/ self.speed_meter_minute, 2)

        matrix = np.nan_to_num(matrix, copy=False, nan=filling_max_minutes)
        if return_type == "distances":
            matrix = matrix / self.speed_meter_minute
        elif return_type == "duration":
            matrix = matrix / 60

        dist_mat_np = matrix 
        log.info(f"{self.slug}:distance_matrix_statistics: (max = {dist_mat_np.max()}, min = {dist_mat_np.min()}, sum = {round(dist_mat_np.sum(),2)}, mean = {round(dist_mat_np.mean(),2)}, median = {round(np.median(dist_mat_np),2)})")

        return dist_mat_np

        # 2022-06-24 01:03:43, deprecated this part and started using native Numpy operation for performance
        for i in range(len(loc_list)):
            for j in range(0, len(loc_list)):
                if np.isnan(matrix[i][j]) or (matrix[i][j] is None):
                    if return_type == "distances":
                        matrix[i][j] = (
                            self.max_distance / self.speed_meter_minute
                        )  # round(self.max_distance/ self.speed_meter_minute, 2)
                    elif return_type == "duration":
                        matrix[i][j] = self.max_minutes
                    else:
                        # 默认返回距离
                        matrix[i][j] = self.max_distance
                else:
                    if return_type == "distances":
                        matrix[i][j] = matrix[i][j] / self.speed_meter_minute  # round(, 2)
                    elif return_type == "duration":
                        matrix[i][j] = matrix[i][j] / 60  # round(, 2)
                    else:
                        # 默认返回距离
                        pass
                        # matrix[i][j] = matrix[i][j]  # round(, 2)

        # Try torch nan
        # a = torch.tensor(matrix, device="cpu")
        return matrix

    def get_travel_distance_matrix(self, loc_list: List, options = None):
        """
        获取距离矩阵
        """
        if len(loc_list) < 1:
            return None
        loc = loc_list[0]
        waypoints = "{},{}".format(round(loc[0], 5), round(loc[1], 5))
        for loc in loc_list[1:]:
            waypoints += ";{},{}".format(round(loc[0], 5), round(loc[1], 5))
        url = self.table_url_template.format(self.osrm_url, self.travel_mode, waypoints)
        # print(url)
        response = session.get(url,verify=self.verify_https)
        try:
            resp_json = response.json()
            if resp_json["code"] != "Ok":
                log.error(f"Not code==Ok, Failed to get table: {loc_list} {resp_json}")
                return None
            dist_list = resp_json["distances"]
            matrix = np.array(dist_list, dtype=np.float)
        except KeyError:
            log.error(f"KeyError: Failed to get table: {loc_list} {resp_json}")
            return None
        # # 此循环目的是设置为不考虑返程，建议改在外层提高通用性
        # for i in range(len(loc_list)):
        #     matrix[i][0] = 0
        for i in range(len(loc_list)):
            for j in range(0, len(loc_list)):
                if np.isnan(matrix[i][j]) or (matrix[i][j] is None):
                    matrix[i][j] = self.max_distance
                else:
                    matrix[i][j] = round(matrix[i][j], 2)
        return matrix



    def trip_service(self, location_str, source, destination):  # get_travel_time_2locations
        """
        This service is used in baituo, and will be for baituo only. FOr general, use solve_tsp.


        roundtrip	source	destination	supported
        true	first	last	yes
        true	first	any	yes
        true	any	last	yes
        true	any	any	yes
        false	first	last	yes
        false	first	any	no
        false	any	last	no
        false	any	any	no
        """

        url = self.trip_service_url_template.format(self.get_osrm_url(), location_str, source, destination)
        # print(url)
        response = session.get(url,verify=self.verify_https)
        resp_json = response.json()
        result = {}
        if resp_json["code"] == "Ok":
            result = resp_json
        return result

    def solve_tsp(self, loc_list: List, return_start_distance=False):
        if len(loc_list) < 1:
            return None, None 

        location_str = ";".join([f"{loc[0]},{loc[1]}" for loc in loc_list ])
        osrm_tsp_url = self.tsp_url_template.format(self.get_osrm_url(), location_str,)
        # f"https://mprouting.easydispatch.uk/trip/v1/driving/{location_str}?steps=false&overview=simplified"

        response = session.get(osrm_tsp_url,verify=self.verify_https)
        resp_json = response.json()
        result = {}
        try:
            if resp_json["code"] != "Ok":
                return None, None

            solution_index = [len(loc_list) for _ in range(len(loc_list))]
            start_distance = [0  for _ in range(len(loc_list))]
            leg_minutes = []
            for wi, waypoint in enumerate(resp_json["waypoints"]):
                solution_index[waypoint["waypoint_index"]] = wi
                if waypoint["trips_index"]!=0:
                    log.warning()(f"TSP not possible, island identified ... {waypoint['trips_index']}")
                start_distance[waypoint["waypoint_index"]] = waypoint["distance"]
            for leg in resp_json["trips"][0]["legs"]:
                leg_minutes.append( round(leg["duration"]/60,2) )

        except Exception as e:
            log.warning()(f"TSP internal error ... {str(e)}")
            return None, None
        solution_loc_list = [
            loc_list[i] for i in solution_index]

        return solution_index, leg_minutes # start_distance




# Splitted function from plugin because of Pickle problem in torch training.
class OSRMTravelTime(KandboxTravelTimePlugin, OSRMTravelTime1):
    """
    Has the following members
    """
    title = "simple osrm backend routing service"
    slug = "simple_routing_osrm_backend"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "simple osrm backend routing service"
    version = "0.1.0"

    default_config = {
        "route_service_url": "",
        "verify_https": False,
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            # "route_service_url": {
            #     "type": "string",
            #     "code": "route_service_url",
            #     "description": "route service url, for exmaple: http://mprouting.easydispatch.uk",
            # },
            "route_service_url": {
                "type": "string",
                "default": "https://routing.easydispatch.uk/uk",
                "title": "route service url, for exmaple: http://mprouting.easydispatch.uk",
                "enum": [
                    "https://localhost:5000", 
                    "https://routing.easydispatch.uk/msb", 
                    "https://routing.easydispatch.uk/gcc",
                    "https://routing.easydispatch.uk/uk", 
                    "https://routing.easydispatch.uk/uswest",
                    "https://easyroute.easydispatch.uk/france", 
                    "https://easyroute.easydispatch.uk/china",
                    "https://easyroute.easydispatch.uk/colombia"
                ]
            },
            # OSRM 地址服务：
            # 新加坡，马来，Brunei：
            # https://routing.easydispatch.uk/msb

            # 中东：
            # https://routing.easydispatch.uk/gcc

            # 英国：
            # https://routing.easydispatch.uk/uk
            # 美国西部：
            # https://routing.easydispatch.uk/uswest

            # France法国：
            # https://easyroute.easydispatch.uk/france

            # 中国：china：
            # https://easyroute.easydispatch.uk/china


            "verify_https": {
                "type": "boolean",
                "code": "Verify HTTPS certificate",
                "description": "Verify HTTPS certificate",
            },
        },
    }
    # TODO, clean up those two plugins.... 2023-01-10 20:28:54
    def __init__(
        self, config = {},
    ):
        OSRMTravelTime1.__init__(
            self,
            travel_mode = config.get("travel_mode","driving" ), # foot, driving
            travel_speed = config.get("travel_speed",40),
            min_minutes = config.get("min_minutes",1),
            max_minutes = config.get("max_minutes",240),
            osrm_url = config["route_service_url"],
            verify_https = config.get("verify_https",0) == 1,
            )

class HaversineTravelTime(KandboxTravelTimePlugin, HaversineTravelTime1):
    title = "haversine routing plugin"
    slug = "kanbox_planner_routing_haversine_proxy"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "haversine routing plugin"
    version = "0.1.0"
    def __init__(
        self, config = {},
    ):
        HaversineTravelTime1.__init__(
            self,
            travel_mode = config.get("travel_mode","foot" ),
            travel_speed = config.get("travel_speed",40),
            min_minutes = config.get("min_minutes",1),
            max_minutes = config.get("max_minutes",240), 
            # consider_home_start = config.get("consider_home_start",False) == 1,
            )



class EuclideanTravelTime(KandboxTravelTimePlugin):
    """
    Has the following members
    """

    travel_speed = 0.03  # 5 blocks / minute

    def __init__(self, travel_speed=None):
        if travel_speed is not None:
            self.travel_speed = travel_speed

    def get_travel_minutes_2locations(self, loc_1, loc_2):  # get_travel_time_2locations

        d = math.dist(loc_1, loc_2)
        return round(d / self.travel_speed, 4)



class ENUTravelTime(HaversineTravelTime):
    """
    Use Euclidean distance over a Tangent Plane with East-North-Up coordinate system.
    Unit of Measure (UOM) is meter.

    https://en.wikipedia.org/wiki/Local_tangent_plane_coordinates#Local_east,_north,_up_(ENU)_coordinates
    """
    title = "ENU routing plugin"
    slug = "simple_routing_plugin_enu"
    meter_per_minute = 300
    def __init__(
        self, config = {},
    ):
        HaversineTravelTime1.__init__(
            self,
            travel_mode = config.get("travel_mode","foot" ),
            travel_speed = config.get("travel_speed",18),
            min_minutes = config.get("min_minutes",1),
            max_minutes = config.get("max_minutes",240), 
            # consider_home_start = config.get("consider_home_start",False) == 1,
            )
        self.meter_per_minute = (self.travel_speed*1000) / 60

    def get_travel_minutes_2locations(self, loc_1, loc_2): 
        d = math.dist(loc_1, loc_2)
        return round(d / self.meter_per_minute, 4)



class TaxicabTravelTime(KandboxTravelTimePlugin):
    """
    Has the following members
    """

    travel_speed = 1  # 5 blocks / minute

    def __init__(self, travel_speed=None):
        if travel_speed is not None:
            self.travel_speed = travel_speed

    def get_travel_minutes_2locations(self, loc_1, loc_2):  # get_travel_time_2locations

        distance = abs(float(loc_1[0]) - float(loc_2[0])) + abs(float(loc_1[1]) - float(loc_2[1]))

        travel_time = distance / (self.travel_speed)
        return travel_time


if __name__ == "__main__":

    # /5 minutes
    # GPS fixed
    t = OSRMTravelTime()
    print(t.get_travel_minutes_2locations([-83.21477, 35.375], [-80.63446, 35.06158]))
    print(
        t.get_travel_minutes_matrix(
            loc_list=[[-83.21477, 35.375], [-80.63446, 35.06158]], return_type="distances"
        )
    )
