import math
import logging
from itertools import groupby

from datetime import date
from dateutil.relativedelta import relativedelta

from calendar import monthrange

import pandas as pd
from statsmodels.tsa.api import ExponentialSmoothing

from dispatch.job_type.models import JobType
from .models import Job

log = logging.getLogger(__name__)


def month_grouper(item):
    """Determines the last day of a given month."""
    key = date(
        item.reported_at.year,
        item.reported_at.month,
        monthrange(item.reported_at.year, item.reported_at.month)[-1],
    )
    return key


def make_forecast(db_session, job_type: str = None, periods: int = 24, grouping: str = "month"):
    """Makes an job forecast."""
    query = db_session.query(Job).join(JobType)

    # exclude simulations
    query = query.filter(JobType.name != "Simulation")

    # exclude current month
    query = query.filter(Job.reported_at < date.today().replace(day=1))

    if job_type != "all":
        if job_type:
            query = query.filter(JobType.name == job_type)

    if grouping == "month":
        grouper = month_grouper
        query.filter(Job.reported_at > date.today() + relativedelta(months=-periods))

    jobs = query.all()
    jobs_sorted = sorted(jobs, key=grouper)

    dataframe_dict = {"ds": [], "y": []}

    for (last_day, items) in groupby(jobs_sorted, grouper):
        dataframe_dict["ds"].append(str(last_day))
        dataframe_dict["y"].append(len(list(items)))

    dataframe = pd.DataFrame.from_dict(dataframe_dict)

    if dataframe.empty:
        return {
            "categories": [],
            "series": [{"name": "Predicted", "data": []}],
        }

    # reset index to by month and drop month column
    dataframe.index = dataframe.ds
    dataframe.index.freq = "M"
    dataframe.drop("ds", inplace=True, axis=1)

    # fill periods without jobs with 0
    idx = pd.date_range(dataframe.index[0], dataframe.index[-1], freq="M")
    dataframe = dataframe.reindex(idx, fill_value=0)

    try:
        forecaster = ExponentialSmoothing(
            dataframe, seasonal_periods=12, trend="add", seasonal="add"
        ).fit(use_boxcox=True)
    except Exception as e:
        log.error(f"Issue forecasting jobs: {e}")
        return {
            "categories": [],
            "series": [{"name": "Predicted", "data": []}],
        }

    forecast = forecaster.forecast(12)
    forecast_df = pd.DataFrame({"ds": forecast.index.astype("str"), "yhat": forecast.values})

    forecast_data = forecast_df.to_dict("series")

    return {
        "categories": list(forecast_data["ds"]),
        "series": [
            {
                "name": "Predicted",
                "data": [max(math.ceil(x), 0) for x in list(forecast_data["yhat"])],
            }
        ],
    }
