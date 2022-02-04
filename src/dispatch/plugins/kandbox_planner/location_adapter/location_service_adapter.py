# https://stackoverflow.com/questions/4913349/haversine-formula-in-python-bearing-and-distance-between-two-gps-points
import traceback
import logging
import requests
import json
from dispatch.plugins.bases.kandbox_planner import KandboxLocationServicePlugin
from dispatch.plugins import dispatch_core as dispatch_plugin

log = logging.getLogger(__name__)


class LocationAdapterService(KandboxLocationServicePlugin):

    title = "Dispatch Plugin - Location Service"
    slug = "dispatch-location-service"
    description = "Generic basic loaction provider."
    version = dispatch_plugin.__version__

    author = "Kandbox"
    author_url = "https://github.com/alibaba/easydispatch.git"

    def __init__(self, config):
        self.url = config.get('url')
        self.token = config.get('token')
        self.headers = config.get('headers', {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
            'content-type': "application/json"
        })
        self.request_method = config.get('request_method')
        if self.token:
            char = '?'
            if '?' in self.url:
                char = '&'
            self.request_url = f"{self.url}{char}token={self.token}"
        else:
            self.request_url = self.url

    def do_post_location(self, payload):
        """
        post method
        """

        param = json.dumps(payload)
        msg = {
            "flag": False,
            "type": None,
            "msg": None,
            "data": None
        }
        try:
            res = requests.post(url=self.request_url,
                                headers=self.headers,
                                data=param, timeout=5)
            if res:
                res.content.decode('utf-8')
                if res.status_code != 200:
                    log.error(f"do_post_location:{res.status_code}-{res.text}")
                    msg = {
                        "flag": False,
                        "type": 'Location Request Error',
                        "msg": res.text,
                        "data": None
                    }
                else:
                    msg = {
                        "flag": True,
                        "type": 'Location Request Succeed',
                        "msg": None,
                        "data": res.json()
                    }
        except Exception as e:
            log.error(f'do_post_location ,{e}')
            print(traceback.format_exc())
            msg = {
                "flag": False,
                "type": 'Location Request TimeOut',
                "msg": e,
                "data": None
            }
        return msg

    def do_get_location(self, payload):
        """
        get method
        """
        msg = {
            "type": None,
            "msg": None,
            "data": None
        }
        try:
            res = requests.get(url=self.request_url,
                               headers=self.headers,
                               params=payload, timeout=5)
            if res:
                res.content.decode('utf-8')
                if res.status_code != 200:
                    log.error(f"do_post_location:{res.status_code}-{res.text}")
                    msg = {
                        "flag": False,
                        "type": 'Location Request Error',
                        "msg": res.text,
                        "data": None
                    }
                else:
                    msg = {
                        "flag": True,
                        "type": 'Location Request Succeed',
                        "msg": None,
                        "data": res.json()
                    }
        except Exception as e:
            log.error(f'do_post_location ,{e}')
            msg = {
                "flag": False,
                "type": 'Location Request TimeOut',
                "msg": e,
                "data": None
            }
        return msg

    def get_location(self, payload):

        if self.request_method == 'POST':
            return self.do_post_location(payload)
        elif self.request_method == 'GET':
            return self.do_get_location(payload)

    def get_pldt_location(self, payload):

        data = self.get_location(payload)
        if data and data['flag'] and data['data']['code'] == 200 and 'phpocgeocode' in data['data']['result']:
            _location_data = data['data']
            _location_ret = _location_data['result']
            geo_latitude = _location_ret['phpocgeocode']['geocode']['latitude']
            geo_longitude = _location_ret['phpocgeocode']['geocode']['longitude']
            location_code = f"{_location_ret['phpocgeocode']['address_id']}_{_location_ret['phpocgeocode']['input_address'].replace(' ', '_')}"
            location_id = _location_ret['phpocgeocode']['address_id']
        else:
            geo_latitude = ''
            geo_longitude = ''
            location_code = ''
            location_id = ''

        return data['flag'] if data else False, {
            'location_code': location_code,
            'latitude': geo_latitude,
            'longitude': geo_longitude,
            'location_id': location_id,
        }, data if data else {}

# Testing moved to etc.pldt...