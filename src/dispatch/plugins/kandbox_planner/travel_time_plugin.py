# https://stackoverflow.com/questions/4913349/haversine-formula-in-python-bearing-and-distance-between-two-gps-points
import logging
from math import radians, cos, sin, asin, sqrt
import requests
from typing import List
import numpy as np
from dispatch.plugins.bases.kandbox_planner import KandboxTravelTimePlugin
from dispatch.plugins.kandbox_planner.env.env_enums import LocationType

from dispatch.plugins.kandbox_planner.util.cache_dict import CacheDict

travel_time_dict = CacheDict(cache_len=5000)


log = logging.getLogger(__file__)


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


class HaversineTravelTime(KandboxTravelTimePlugin):
    """
    Calculate HaversineTravelTime, inspired by

    # https://github.com/mrJean1/PyGeodesy
    # http://www.movable-type.co.uk/scripts/latlong.html
    """

    # travel_speed = 40
    slug = "internal_haversine"

    def __init__(self, travel_speed=30, min_minutes=5, max_minutes=None, travel_mode=None):
        self.travel_speed = travel_speed
        self.min_minutes = min_minutes
        self.max_minutes = max_minutes

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

    def get_travel_minutes_2locations(self, loc_1, loc_2):  # get_travel_time_2locations
        if (loc_1[0] == loc_2[0]) & (loc_1[1] == loc_2[1]):
            return 0

        # For training purpose 2021-03-31 20:43:01
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

    def get_travel_minutes_matrix(self, loc_list: List):  # get_travel_time_2locations

        matrix = np.zeros((len(loc_list), len(loc_list)))
        for i in range(len(loc_list)):
            for j in range(1, len(loc_list)):
                matrix[i][j] = int(self.get_travel_minutes_2locations(
                    loc_list[i],
                    loc_list[j]
                ) * 10)

        return matrix


class OSRMTravelTime(KandboxTravelTimePlugin):
    """
    Has the following members
    """

    # travel_mode = "driving/foot"

    def __init__(self, travel_mode="foot", travel_speed=5, min_minutes=1, max_minutes=240):
        self.speed_km_hour = 5 if travel_mode == 'foot' else 50
        self.speed_meter_minute = round(self.speed_km_hour * 1000 / 60, 1)
        self.min_minutes = min_minutes
        self.max_minutes = max_minutes
        self.travel_mode = travel_mode

        # curl 'http://127.0.0.1:5000/route/v1/foot/114.7669601,25.6842057;114.9252620,25.8584520?steps=false&overview=false&generate_hints=false'
        self.route_url_template = (
            # "https://kerrypoc.dispatch.kandbox.com/route/v1/driving/{},{};{},{}?steps=false&overview=false&generate_hints=false"
            "http://127.0.0.1:5000/route/v1/{}/{},{};{},{}?steps=false&overview=false&generate_hints=false"
        )

        self.table_url_template = (
            "http://127.0.0.1:5000/table/v1/{}/{}?annotations=distance"
        )
        # curl 'http://127.0.0.1:5000/table/v1/driving/114.7770000,25.6688760;114.7669601,25.6842057'

        # curl 'http://127.0.0.1:5000/table/v1/foot/114.7770000,25.6688760;114.7669601,25.6842057?annotations=distance'

    def get_travel_minutes_2locations(self, loc_1, loc_2):  # get_travel_time_2locations

        url = self.route_url_template.format(
            self.travel_mode, loc_1[0], loc_1[1], loc_2[0], loc_2[1]
        )
        # print(url)
        response = requests.get(url)
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

    def get_travel_minutes_matrix(self, loc_list: List):  # get_travel_time_2locations
        if len(loc_list) < 1:
            return None
        loc = loc_list[0]
        waypoints = "{},{}".format(round(loc[0], 5), round(loc[1], 5))
        for loc in loc_list[1:]:
            waypoints += ";{},{}".format(round(loc[0], 5), round(loc[1], 5))

        url = self.table_url_template.format(self.travel_mode, waypoints)
        response = requests.get(url)
        try:
            resp_json = response.json()
            if resp_json["code"] != "Ok":
                log.error(f"Not code==Ok, Failed to get table: {loc_list} {resp_json}")
                return None
            dist_list = resp_json["distances"]
            matrix = np.array(dist_list)
        except KeyError:
            log.error(f"KeyError: Failed to get table: {loc_list} {resp_json}")
            return None
        for i in range(len(loc_list)):
            matrix[i][0] = 0
        for i in range(len(loc_list)):
            for j in range(1, len(loc_list)):
                if matrix[i][j] is None:
                    matrix[i][j] = self.max_minutes
                else:
                    matrix[i][j] = round(matrix[i][j] / 300, 2)

        return matrix


if __name__ == "__main__":

    # /5 minutes
    # GPS fixed
    t = OSRMTravelTime()
    print(t.get_travel_minutes_2locations([-83.21477, 35.375], [-80.63446, 35.06158]))
