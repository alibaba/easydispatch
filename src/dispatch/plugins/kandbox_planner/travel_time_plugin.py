# https://stackoverflow.com/questions/4913349/haversine-formula-in-python-bearing-and-distance-between-two-gps-points
import logging
from math import radians, cos, sin, asin, sqrt
import requests

from dispatch.plugins.bases.kandbox_planner import KandboxTravelTimePlugin

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

    def __init__(self, travel_speed=30, min_minutes=5):
        self.travel_speed = travel_speed
        self.min_minutes = min_minutes

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
        # if (len(loc_1) > 2) and (loc_1[2] == "H"):
        #     return 0
        # if (len(loc_2) > 2) and (loc_2[2] == "H"):
        #     return 0

        distance = self.haversine(loc_1[0], loc_1[1], loc_2[0], loc_2[1])
        travel_time = distance / (self.travel_speed / 60)  # 60 minuts per hour
        # print('travel_time: ',loc_1, loc_2, "--: ", travel_time)
        if travel_time < self.min_minutes:
            travel_time = self.min_minutes
        return travel_time


class OSRMTravelTime(KandboxTravelTimePlugin):
    """
    Has the following members
    """

    travel_mode = "car"

    def __init__(self, travel_mode="car"):
        self.travel_mode = travel_mode
        self.url_template = (
            "https://kerrypoc.dispatch.kandbox.com/route/v1/driving/{},{};{},{}?steps=false&overview=false"
            # "http://127.0.0.1:5000/route/v1/driving/{},{};{},{}?steps=false&overview=false"
        )

    def get_travel_minutes_2locations(self, loc_1, loc_2):  # get_travel_time_2locations

        url = self.url_template.format(loc_1[0], loc_1[1], loc_2[0], loc_2[1])
        # print(url)
        response = requests.get(url)
        resp_json = response.json()
        try:
            travel_time = resp_json["routes"][0]["duration"] / 60
        except KeyError:
            print(resp_json)
            travel_time = 9999
            return travel_time
        if travel_time < 1:
            travel_time = 1
        return travel_time


if __name__ == "__main__":

    # /5 minutes
    # GPS fixed
    t = OSRMTravelTime()
    print(t.get_travel_minutes_2locations([-83.21477, 35.375], [-80.63446, 35.06158]))
