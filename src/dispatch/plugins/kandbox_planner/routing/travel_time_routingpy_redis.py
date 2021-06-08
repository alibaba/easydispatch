# https://stackoverflow.com/questions/4913349/haversine-formula-in-python-bearing-and-distance-between-two-gps-points
import logging
from math import radians, cos, sin, asin, sqrt
import requests

from dispatch.plugins.bases.kandbox_planner import KandboxTravelTimePlugin
from dispatch.plugins.kandbox_planner.travel_time_plugin import HaversineTravelTime, OSRMTravelTime


log = logging.getLogger(__name__)


class RoutingPyRedisTravelTime(KandboxTravelTimePlugin):
    def __init__(self, travel_speed, min_minutes, redis_conn, travel_mode):
        self.haversine_router = HaversineTravelTime(
            travel_speed=travel_speed, min_minutes=min_minutes
        )
        self.routing_router = OSRMTravelTime(
            travel_mode=travel_mode
        )
        self.redis_conn = redis_conn
        self.haversine_router_hit = 0
        self.routing_router_hit = 0
        self.redis_router_hit = 0
        self.all_hit = 0

    def get_travel_minutes_2locations(self, loc_1, loc_2):
        travel_time_key = "routing_longlat_{}_{}_{}_{}".format(
            loc_1[0], loc_1[1], loc_2[0], loc_2[1])
        travel_minutes = self.redis_conn.get(travel_time_key)

        if travel_minutes is None:
            travel_minutes = self.routing_router.get_travel_minutes_2locations(loc_1, loc_2)
            self.redis_conn.set(travel_time_key, travel_minutes)
            self.routing_router_hit += 1
            self.all_hit += 1
            log.debug(f"travel time loaded for  ={loc_1} -> {loc_2}")
            return travel_minutes

        else:
            self.redis_router_hit += 1
            self.all_hit += 1
            log.debug(f"travel time hit on redis for  ={loc_1} -> {loc_2}")
            return float(travel_minutes)


if __name__ == "__main__":

    import redis
    redis_conn = redis.Redis(host="localhost", port=6379, password=None)
    start = [-0.354723057995226, 51.4710467053333]
    end = [-0.174174692503457, 51.5346308751186]

    t = RoutingPyRedisTravelTime(travel_speed=40, min_minutes=10,
                                 redis_conn=redis_conn, travel_mode="car")
    print(t.get_travel_minutes_2locations(start, end))

    print(t.get_travel_minutes_2locations(start, end))
    print(t.get_travel_minutes_2locations(start, end))
    print(t.all_hit, t.redis_router_hit)
