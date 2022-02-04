# https://stackoverflow.com/questions/4913349/haversine-formula-in-python-bearing-and-distance-between-two-gps-points
import logging
from math import radians, cos, sin, asin, sqrt
import requests
from typing import List
import numpy as np
import redis
from dispatch.plugins.bases.kandbox_planner import KandboxTravelTimePlugin
from dispatch.plugins.kandbox_planner.travel_time_plugin import OSRMTravelTime
from dispatch import config

log = logging.getLogger(__name__)


class RoutingPyOsrmRedis(KandboxTravelTimePlugin):
    title = " routing osrm proxy service"
    slug = "kanbox_planner_routing_osrm_proxy"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    description = "Env Proxy for GYM for RL."
    version = "0.1.0"

    default_config = {
        "travel_mode": "foot"
    }
    config_form_spec = {
        "type": "object",
        "properties": {
            "travel_mode": {
                "type": "string",
                "code": "Travel Mode",
                "description": "travel_mode type.",
                "enum": ["foot", "driving"],
            }

        },
    }

    def __init__(self, env={}, redis_conn=None):
        self.travel_mode = env.get('travel_mode', self.default_config['travel_mode'])
        self.routing_router = OSRMTravelTime(
            travel_mode=self.travel_mode
        )
        if redis_conn is None:
            self.redis_conn = redis.Redis(host=config.REDIS_HOST,
                                          port=config.REDIS_PORT, password=None)
        else:
            self.redis_conn = redis_conn
        self.routing_router_hit = 0
        self.redis_router_hit = 0
        self.all_hit = 0

    def get_travel_minutes_2locations(self, loc_1, loc_2):
        new_1 = (round(loc_1[0], 5), round(loc_1[1], 5))
        new_2 = (round(loc_2[0], 5), round(loc_2[1], 5))
        travel_time_key = "osrm_{}_{}_{}_{}_{}".format(self.travel_mode,
                                                       new_1[0], new_1[1], new_2[0], new_2[1], )
        travel_minutes = self.redis_conn.get(travel_time_key)

        self.all_hit += 1
        if travel_minutes is None:
            travel_minutes = self.routing_router.get_travel_minutes_2locations(new_1, new_2)
            self.redis_conn.set(travel_time_key, travel_minutes)
            self.redis_conn.expire(travel_time_key, 3600 * 24)
            self.routing_router_hit += 1
            log.debug(f"travel time loaded for  ={loc_1} -> {loc_2}")

        else:
            self.redis_router_hit += 1
            log.debug(f"travel time hit on redis for  ={loc_1} -> {loc_2}")

        return round(float(travel_minutes), 3)

    def get_travel_minutes_matrix(self, loc_list: List):  # get_travel_time_2locations

        matrix = self.routing_router.get_travel_minutes_matrix(loc_list)

        return matrix


if __name__ == "__main__":

    import redis
    redis_conn = redis.Redis(host="localhost", port=6379, password=None)
    start = [-0.354723057995226, 51.4710467053333]
    end = [-0.174174692503457, 51.5346308751186]

    t = RoutingPyOsrmRedis(redis_conn=redis_conn, travel_mode="car")
    print(t.get_travel_minutes_2locations(start, end))

    print(t.get_travel_minutes_2locations(start, end))
    print(t.get_travel_minutes_2locations(start, end))
    print(t.all_hit, t.redis_router_hit)
