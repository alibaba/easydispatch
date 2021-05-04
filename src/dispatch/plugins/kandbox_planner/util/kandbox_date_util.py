import datetime

# import pandas as pd
# import numpy as np
import json
import math
from dispatch import  config
import numpy as np


def minutes_to_time_string(minutes):
    if 0 < minutes < 24 * 60:
        return ":".join(str(datetime.timedelta(minutes=minutes)).split(":")[0:2])
    else:
        return ":".join(str(datetime.timedelta(minutes=minutes % (24 * 60))).split(":")[0:2])


def time_string_hhmm_to_minutes(time_str):
    return int(time_string_hhmm_to_seconds(time_str) / 60)


def strp_minutes_from_datetime(input_date):
    return input_date.hour * 60 + input_date.minute


def day_minutes_to_datetime(k_day="20191201", minutes=1):
    new_date = datetime.datetime.strptime(k_day, config.KANDBOX_DATE_FORMAT) + datetime.timedelta(
        minutes=minutes
    )

    return new_date


def extract_minutes_from_datetime(k_datetime):

    return time_string_hhmm_to_minutes(time_str=datetime.datetime.strftime(k_datetime, "%H:%M"))


def datetime_to_google_calendar_date_str(k_date):

    return "{}-00:00".format(k_date.isoformat().split(".")[0])


def seconds_to_time_string(seconds):
    return str(datetime.timedelta(seconds=seconds))


def time_string_to_seconds(time_str):
    # t = "10:15:30"
    t = time_str
    sp = t.split(":")
    if len(sp) == 2:
        m, s = sp
        return int(datetime.timedelta(hours=0, minutes=int(m), seconds=int(s)).total_seconds())
    else:
        h, m, s = sp
        return int(datetime.timedelta(hours=int(h), minutes=int(m), seconds=int(s)).total_seconds())


def time_string_to_minutes(time_str):
    return int(time_string_to_seconds(time_str) / 60)


def time_string_hhmm_to_seconds(time_str):
    t = "10:15"
    t = time_str
    try:
        sp = t.split(":")
    except:
        print("An exception occurred with value {}".format(time_str))
        return 0

    if len(sp) == 2:
        h, m = sp
        return int(datetime.timedelta(hours=int(h), minutes=int(m), seconds=0).total_seconds())
    else:
        h, m, s = sp
        return int(datetime.timedelta(hours=int(h), minutes=int(m), seconds=int(s)).total_seconds())


def get_right_end_minutes(startDate, endDate):

    if startDate > endDate:
        return endDate + 1440
    else:
        return endDate


def int_hhmm_to_minutes(int_time_str):
    t = int(int_time_str)
    return math.floor(t / 100) * 60 + int(t % 100)


def transform_weekly_worker_time_from_rhythm_v6(time_str):
    weekly_working_minutes = []
    ws = time_str.split(";")
    for work_day in ws:
        if len(work_day) < 2:
            weekly_working_minutes.append([0, 0])
            continue
        work_day_start = int_hhmm_to_minutes(work_day.split("_")[0])
        work_day_end = int_hhmm_to_minutes(work_day.split("_")[1])
        if work_day_end < work_day_start:
            work_day_end += 12 * 60

        weekly_working_minutes.append([work_day_start, work_day_end])

    return json.dumps(weekly_working_minutes)


# print(transform_weekly_worker_time_from_rhythm_v6 ('0_0000_00;1_0830_0550;2_0830_0550;3_0830_0550;4_0830_0550;5_0830_0550;6_0830_0240'))


def clip_time_period(p1, p2):
    # each P is [<=, <]
    if p1[0] >= p2[1]:
        return []
    if p1[1] <= p2[0]:
        return []
    if p1[0] < p2[0]:
        start = p2[0]
    else:
        start = p1[0]

    if p1[1] < p2[1]:
        end = p1[1]
    else:
        end = p2[1]
    return [start, end]


# Inspired by https://www.geeksforgeeks.org/find-intersection-of-intervals-given-by-two-lists/
# Python3 implementation to find intersecting intervals

# In fact not used so far, 2020-09-24 23:17:37
def intersect_time_periods(time_periods, minimum_length=0, first_minimum_length_match_only=False):
    """ Find intersect_time_periods. If minimum_length first
        2020-09-22 10:18:58: I created this only because interval tree has not query of length_greater_than , https://github.com/chaimleib/intervaltree

        Parameters
        ----------
        action : list(float)
            Input array of worker+day array. The rest of values in action_dict are discarded and re-calculated.

        minimum_length : int
            If not None and > 0, it returns maximum one time period which is longer than first_minimum_length_match

        Returns
        -------
        time_period_list: list
            A list of time period

    """
    # i and j pointers for arr1
    # and arr2 respectively
    MININUM_TIME_POINT = -1

    list_lengths = [len(x) for x in time_periods]
    nbr_of_all_time_periods = sum(list_lengths)
    time_period_indices = [0 for _ in range(len(time_periods))]
    result_list = []

    # n = len(arr1)
    # m = len(arr2)

    # Loop through all intervals unless one
    # of the interval gets exhausted
    while sum(time_period_indices) < nbr_of_all_time_periods:
        current_time_periods = []
        for idx, tp in enumerate(time_periods):
            current_time_periods.append(tp[time_period_indices[idx]])
        # Left bound for intersecting segment
        left_points = [x[0] for x in current_time_periods]
        left_point_max = max(left_points)

        # Right bound for intersecting segment
        right_points = [
            x[1] for x in current_time_periods
        ].copy()  # no need to copy, new list anyway?
        right_point_min = min(right_points)

        # If segment is valid
        if right_point_min - left_point_max >= minimum_length:
            if first_minimum_length_match_only:
                return [[left_point_max, right_point_min]]
            else:
                result_list.append([left_point_max, right_point_min])
        # If i-th interval's right bound is
        # smaller increment i else increment j
        found_index_to_step = False
        for _ in range(len(list_lengths)):
            right_min_index = np.argmin([x[1] for x in current_time_periods])
            if time_period_indices[right_min_index] < list_lengths[right_min_index] - 1:
                time_period_indices[right_min_index] += 1
                right_points[right_min_index] = MININUM_TIME_POINT
                found_index_to_step = True
                break
        if not found_index_to_step:
            break
    return result_list


# Inspired by https://www.geeksforgeeks.org/find-intersection-of-intervals-given-by-two-lists/
# Python3 implementation to find intersecting intervals

"""
if __name__ == "__main__":

    # Test code
    arr1 = [[0, 4], [5, 10], [13, 20], [24, 25]]

    arr2 = [[1, 5], [8, 12], [15, 24], [25, 26]]

    arr3 = [[2, 3], [9, 12], [15, 16], [23, 24]]
    arr4 = [[9, 12], [23, 24]]

    print(intersect_time_periods([arr1, arr2]))
    # [[1, 4], [5, 5], [8, 10], [15, 20], [24, 24], [25, 25]]
    print(intersect_time_periods([arr1, arr2, arr3]))
    # [[2, 3], [9, 10], [15, 16], [24, 24]]

    print(intersect_time_periods([arr1, arr2, arr3, arr4]))
    # [[9, 10], [24, 24]]

    print(
        intersect_time_periods([arr1, arr2], minimum_length=2, first_minimum_length_match_only=True)
    )
    # [[1, 4]]
    print(intersect_time_periods([arr1], minimum_length=2, first_minimum_length_match_only=True))
    # [[0, 4]]
    """


def transform_kandbox_day_2_postgres_datetime(k_day=None):

    new_date = datetime.datetime.strftime(
        datetime.datetime.strptime(k_day, config.KANDBOX_DATE_FORMAT),
        config.KANDBOX_DATETIME_FORMAT_WITH_MS,
    )
    return new_date


def add_days_2_day_string(k_day=None, days=None):

    new_date = datetime.datetime.strptime(k_day, config.KANDBOX_DATE_FORMAT) + datetime.timedelta(
        days=days
    )

    return datetime.datetime.strftime(new_date, config.KANDBOX_DATE_FORMAT)


def days_between_2_day_string(start_day=None, end_day=None):

    start_date = datetime.datetime.strptime(start_day, config.KANDBOX_DATE_FORMAT)
    end_date = datetime.datetime.strptime(end_day, config.KANDBOX_DATE_FORMAT)

    return (end_date - start_date).days


def get_current_day_string():

    start_date = datetime.datetime.strptime(datetime.datetime.now(), "YYYYMMDD")
    return start_date
