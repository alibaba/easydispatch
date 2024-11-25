import copy
from dispatch.plugins.base import Plugin, ConfigurablePlugin
from dispatch.models import PluginOptionModel
from dispatch.plugins.kandbox_planner.env.env_enums import KandboxPlannerPluginType

class KandboxTravelTimePlugin(Plugin):
    """
    get_travel_minutes_2locations() must be superceded to return minutes
    """

    type = KandboxPlannerPluginType.kandbox_routing_adapter
    _schema = PluginOptionModel
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan"
    version = "0.1.0"

    # def get_travel_minutes_2locations(self, loc_1, loc_2):  # get_travel_time_2locations
    #     raise NotImplementedError


class KandboxLocationServicePlugin(Plugin):
    """
     get location lat lon plugin
    """

    type = KandboxPlannerPluginType.kandbox_location_service
    _schema = PluginOptionModel

    def do_post_location(self, payload):  #
        raise NotImplementedError

    def do_get_location(self, payload):  #
        raise NotImplementedError

    def get_location(self, payload):  #
        raise NotImplementedError
