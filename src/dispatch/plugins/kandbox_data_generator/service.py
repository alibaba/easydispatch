import pypd
from pypd.models.service import Service

from dispatch.exceptions import DispatchPluginException

# from .config import PAGERDUTY_API_KEY, PAGERDUTY_API_FROM_EMAIL


from datetime import datetime
from datetime import timedelta

from random import seed
from random import randint

# seed random number generator
seed(1978)
from pprint import pprint

# import config.settings.local as config


def populate_all(service_id: str = None, service_name: str = None):
    """Gets the oncall for a given service id or name."""
    if True:
        print("Done populate_all")
    elif False:
        service = pypd.Service.find(query=service_name)

        if not service:
            raise DispatchPluginException(
                f"No on-call service found with service name: {service_name}"
            )

        return get_oncall_email(service[0])

    raise DispatchPluginException("Cannot fetch oncall. Must specify service_id or service_name.")
