# https://stackoverflow.com/questions/4913349/haversine-formula-in-python-bearing-and-distance-between-two-gps-points
import logging
from math import radians, cos, sin, asin, sqrt
import requests
from typing import List
import numpy as np
import redis
from dispatch.plugins.bases.kandbox_planner import KandboxTravelTimePlugin
from dispatch.plugins.kandbox_planner.env.env_enums import LocationType
from dispatch import config

log = logging.getLogger(__name__)


class RoutingHaversineTravelTime(KandboxTravelTimePlugin):
    """
    Calculate HaversineTravelTime, inspired by

    # https://github.com/mrJean1/PyGeodesy
    # http://www.movable-type.co.uk/scripts/latlong.html
    """

    title = "routing havcersine proxy"
    slug = "kanbox_planner_routing_haversine_proxy"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "Env Proxy for GYM for RL."
    version = "0.1.0"

    default_config = {
        "travel_speed": 30,
        "min_minutes": 5,
        "max_minutes": 240
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "travel_speed": {
                "type": "number",
                "code": "properties"
            },
            "min_minutes": {
                "type": "number",
                "code": "min_minutes",
            },
            "max_minutes": {
                "type": "number",
                "code": "max_minutes",
            },

        },
    }
    # travel_speed = 40

    def __init__(self, env={}, redis_conn=None):
        self.travel_speed = env.get('travel_speed', self.default_config['travel_speed'])
        self.min_minutes = env.get('min_minutes', self.default_config['min_minutes'])
        self.max_minutes = env.get('max_minutes', self.default_config['max_minutes'])

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

    def get_travel_minutes_2locations(self, loc_1, loc_2):  # get_travel_time_2locations

        new_1 = (round(loc_1[0], 5), round(loc_1[1], 5))
        new_2 = (round(loc_2[0], 5), round(loc_2[1], 5))

        if (loc_1[0] == loc_2[0]) & (loc_1[1] == loc_2[1]):
            return 0

        # For training purpose 2021-03-31 20:43:01
        if (len(loc_1) > 2) and (loc_1[2] == LocationType.HOME):
            return 0
        if (len(loc_2) > 2) and (loc_2[2] == LocationType.HOME):
            return 0

        distance = self.haversine(loc_1[0], loc_1[1], loc_2[0], loc_2[1])
        travel_minutes = distance / (self.travel_speed / 60)  # 60 minuts per hour
        if travel_minutes < self.min_minutes:
            travel_minutes = self.min_minutes
        if self.max_minutes is not None:
            if travel_minutes > self.max_minutes:
                travel_minutes = self.max_minutes
        log.debug(f"travel time loaded for  ={loc_1} -> {loc_2}")

        return round(float(travel_minutes), 3)

    def get_travel_minutes_matrix(self, loc_list: List):  # get_travel_time_2locations

        matrix = np.zeros((len(loc_list), len(loc_list)))
        for i in range(len(loc_list)):
            for j in range(1, len(loc_list)):
                matrix[i][j] = int(self.get_travel_minutes_2locations(
                    loc_list[i],
                    loc_list[j]
                ) * 10)

        return matrix


if __name__ == "__main__":

    start = [-0.354723057995226, 51.4710467053333]
    end = [-0.174174692503457, 51.5346308751186]

    t = RoutingHaversineTravelTime({
        "travel_speed": 30,
        "min_minutes": 5,
        "max_minutes": 240
    })
    print(t.get_travel_minutes_2locations(start, end))
