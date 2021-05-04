import json

import pandas as pd

import datetime

# from dispatch.plugins.kandbox_planner.env.env_models import WorkingTimeSlot


def generic_json_encoder(obj):
    # print(obj)
    if isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, pd.Timestamp):
        return str(obj)
    elif isinstance(obj, datetime.datetime):
        return str(obj)
    """elif WorkingTimeSlot == type(o):
        return python_dataclasses_astuple(o)"""

    raise TypeError
