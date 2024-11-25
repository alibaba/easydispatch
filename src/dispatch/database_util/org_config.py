from dispatch.config import DEFAULT_TEAM_TIMEZONE, MAX_NBR_OF_JOBS_PER_DAY_WORKER, NBR_OF_OBSERVED_WORKERS
import copy


# OLD_team_flex_form_schema = {
#     "type": "object",
#     "properties": {
#         "timezone": {
#             "type": "string",
#             "default": "Asia/Dubai",
#             "title": "timezone string for this team, according to pytz list: https://pypi.org/project/pytz/",
#         }, 
#         "window_refresh_at": {
#             "type": "string",
#             "default": "0;30;2;30",
#             "title": "window_refresh_at with format of start_hour;start_minute;end_h;end_m",
#         }, 
#         "fixed_horizon_flag": {
#             "type": "number",
#             "default": 1,
#             "title": "fixed_horizon_flag flag (boolean [true: always env_start_datetime , false : System current time])", 
#         },
#         "horizon_start_datetime": {"type": "string", "title": "horizon_start_datetime, in ISO format, e.g. 2023-10-03T00:00:01"},
#         "env_start_datetime": {"type": "string", "title": "env_start_datetime, in ISO format, e.g. 2023-10-03T00:00:00"},
#         "nbr_minutes_planning_windows_duration": {
#             "type": "number",
#             "default": 1440,
#             "title": "Duration minutes for planning window",
#         },
#         # "env_start_day": {"type": "string", "title": "env_start_day, please use env_start_datetime"},
#         "planning_working_days": {
#             "type": "number",
#             "default": 1,
#             "title": "Number of working days in planning Window (integer)"
#         },
#         "nbr_minutes_backward_planning_window": {
#             "type": "number",
#             "default": 1440,
#             "title": "nbr_minutes_backward_planning_window",
#         },
#         "nbr_minutes_backward_unplanned_jobs": {
#             "type": "number",
#             "default": 60,
#             "title": "nbr_minutes_backward_unplanned_jobs",
#         },
        
#         # "rolling_every_day": {
#         #     "type": "number",
#         #     "default": 0,
#         #     "title": "rolling_every_day (boolean [true: env_start_day update every day])", 
#         # }, 
#         "peak_period_spec": {
#             "type": "string",
#             "default": "10;11;12;13;18;19",
#             "title": "list of hours when algorithm prioritize merging, seperated by ;. For example 11;12",
#         },
#         "enabled_rule_codes": {
#             "type": "string",
#             "default": "basic;area_code;tolerance_check;geo_merge;max_pick2drop_merge;worker_radius",
#             "title": "list of rules enabled"
#         },
        
#         "front_routing_type": {
#             "type": "string",
#             "default": "polyline",
#             "title": "front_routing_type",
#             "description": "front_routing_type.",
#             "enum": ["polyline", "osrm"]
#         },
#         "front_routing_url": {
#             "type": "string",
#             "default": "https://routing.easydispatch.uk/uk",
#             "title": "front_routing_url"
#         },
#         # "realtime_env_update_flag": {
#         #     "type": "number",
#         #     "default": 0,
#         #     "title": "Whether or not update parameter to env in realtime. 0 means only saving to DB, but not the planning env (engine)", 
#         # },

#       "longitude_diff_max": {
#         "type": "number",
#         "default": 55.7,
#         "title": "longitude_diff_max"
#       },
#       "longitude_diff_min": {
#         "type": "number",
#         "default": 52.7,
#         "title": "longitude_diff_min"
#       },
#       "latitude_diff_max": {
#         "type": "number",
#         "default": 100,
#         "title": "latitude_diff_max"
#       },
#       "latitude_diff_min": {
#         "type": "number",
#         "default": 1,
#         "title": "latitude_diff_min"
#       },


#       "nbr_jobs_per_slot": {
#         "type": "number",
#         "default": 20,
#         "title": "Max number of Jobs per each Worker"
#       },
#       "late_delivery_tolerance_max_minutes": {
#         "type": "number",
#         "default": 15,
#         "title": "The late delivery tolerance max minutes"
#       },
#       "meter_allowed_merge_pick": {
#         "type": "number",
#         "default": 500,
#         "title": "meter_allowed_merge_pick is max meters for merging"
#       },
#       "meter_allowed_merge_drop": {
#         "type": "number",
#         "default": 1000,
#         "title": "meter_allowed_merge_drop, Drop Max Meters for merge"
#       },
#       "meter_merge_drop_scaling": {
#         "type": "number",
#         "default": 20,
#         "title": "Scaling Meters for meter_allowed_merge_drop in KM"
#       }, 
#       "meter_same_location_match": {
#         "type": "number",
#         "default": 10,
#         "title": "meter_same_location_match"
#       }, 
      
#       "nbr_observed_slots": {
#             "type": "number",
#             "default": 50,
#             "title": "nbr_observed_slots",
#         },

#       "allow_mixed_areas": {
#             "type": "number",
#             "default": 1,
#             "title": "allow mixed areas or not (1 as true/yes, 0 as not)",
#         },

#       "slot_by_shift_start": {
#             "type": "number",
#             "default": 0,
#             "title": "slot_by_shift_start (1 as true/yes, 0 as not)",
#         },
#       "slot_by_business_hour": {
#             "type": "number",
#             "default": 1,
#             "title": "slot_by_business_hour (1 as true/yes, 0 as not)",
#         }, 
#       "meter_search_radius": {
#             "type": "number",
#             "default": 50_000,
#             "title": "The maximum distance from order's start point that the algorithm can search for workers",
#       },
#       "meter_same_area": {
#           "type": "number",
#           "default": 4_000,
#           "title": "The maximum distance that same area idle workers take the order immediately. The closest worker will take first.",
#       },
#       "meter_other_area": {
#           "type": "number",
#           "default": 2_000,
#           "title": "The maximum distance that other area idle workers take the order immediately. The closest worker will take first.",
#       },

#       "default_requested_primary_worker_code": {
#           "type": "string",
#           "default": "",
#           "title": "default requested primary_worker_code",
#       },
#       "scoring_factor_standard_travel_minutes": {
#           "type": "number",
#           "default": 90,
#           "title": "standard travel minutes (scoring factor, integer)",
#       },
#       "worker_job_min_minutes": {"type": "number", "title": "worker job min minutes (integer)"},
#       "respect_initial_travel": {
#           "type": "number",
#           "default": 0,
#           "title": "Whether respect initial travel or not (1 as true/yes, 0 as not)"
#       },
#         # "horizon_start_offset_minutes": {"type": "number", "title": "Initial offset for horizon start  minutes (integer) on top of env_start_day"},
#         # "horizon_start_minutes": {"type": "number", "title": "horizon_start_minutes"},
#         "travel_speed_km_hour": {"type": "number", "title": "travel_speed_km_hour (integer)"},
#         "travel_min_minutes": {"type": "number", "title": "travel_min_minutes (integer)"},
#         "worker_icon": {"type": "string", "title": "worker_icon  (fontawesome icon)"},
#         "job_icon": {"type": "string", "title": "job_icon (fontawesome icon)"},
#         # "job_address_flag": {
#         #     "type": "number",
#         #     "default": 1,
#         #     "title": "job_address_flag (boolean ,one true,zero false)", 
#         # },
#         "begin_skip_minutes": {
#             "type": "number",
#             "title": "The number of minutes skipped at the start of the task",
#             "default": 60
#         },
#         "weekly_working_days": {
#                 "type": "string",
#                 "code": "weekly_working_days",
#                 "description": "working days in a week, for example: 1;2;3;4;5 means Monday to Friday. 0 is Sunday, 1 is Monday.", 
#             },
#         "team_holiday_days": {
#             "type": "string", "default": "", 
#             "title": "extra holiday days for this team, example: 2023-12-01;2023-12-02, each day using format YYYY-MM-DD"},
#         "inner_slot_planner": {
#             "type": "string",
#             "default": "head_tail",
#             "title": "Inner Slot Planner Type",
#             "description": "(Deprecated) Different inner slot planning.",
#             "enum": ["nearest_neighbour", "weighted_nearest_neighbour", "head_tail"],
#         },
#         "requested_skills": {
#           "type": "string",
#           "title": "(Deprecated) Available Skills (as strings) for Workers and Jobs, seperated by comma",
#           "description": "Available Skills for Workers and Jobs.",
#           "default": ""
#         },
#         # "reset_dataset": {
#         #     "type": "string",
#         #     "default": "riyadh",
#         #   "title": "(Danger, do not use) reset data. 1 mean yes, and to remove all data each time to reset.",
#         # }, 
#         # "simulation_log_dir": {
#         #     "type": "string",
#         #     "default": "/tmp",
#         #   "title": "Simulation log file path.",
#         # },
#         # "use_zulip": {
#         #     "type": "number",
#         #     "default": 0,
#         #     "title": "Whether or not use zulip for sending job to worker", 
#         # }
#     }
# }
# # reset_dataset == none, riyadh, ...


default_team_flex_form_data = {
    # "fixed_env_start_day_flag": 1, 2024-02-17 06:42:44, replaced by fixed_horizon_flag
    "horizon_start_datetime":  "2023-10-03T06:00:01",
    "timezone": DEFAULT_TEAM_TIMEZONE, #  "Europe/London", # "Asia/Dubai",
    "window_refresh_at":"0;30;2;30",
    # 2023-10-03 00:35:37, replaced by horizon_start_datetime
    # "horizon_start_minutes": 1925,

    # "env_start_day": "20231003",
    # "planning_working_days": 3,
    # "data_start_day":"2023-10-01",
    "env_start_datetime": "2023-10-03T00:00:00",
    "last_batch_run_datetime": "2023-01-01T00:00:00",
    # window span 3 days, and jobs requested in those 3 days are processed.
    "nbr_minutes_planning_windows_duration": 1440*2,
    # When I refresh window, I go back nbr_minutes_backward_unplanned_jobs to retrive unplanned jobs.
    "nbr_minutes_backward_unplanned_jobs":1440,
    # When I refresh window, I go back nbr_minutes_backward_planning_window as the start point from horizon
    "nbr_minutes_backward_planning_window": 1440,
    "front_routing_type": "polyline",
    "front_routing_url": "https://routing.easydispatch.uk/uk",
    "tile_server": "autonavi", # "osm",

    # 2024-02-08 04:02:17 replaced by "not fixed_env_start_day_flag".
    # as long as not fixed, it will be refreshed everyday.
    # "rolling_every_day": 1, 
    "longitude_diff_max": 1,
    "longitude_diff_min": 1,
    "latitude_diff_max": 1,
    "latitude_diff_min": 1,
    "initial_plugin_loading_flag": 1,
    "sync_job_area_code_when_replan": "1", # always realtime update if possible
    # 
    "realtime_env_update_flag": "1", # always realtime update if possible

    "max_job_in_worker_size": MAX_NBR_OF_JOBS_PER_DAY_WORKER,
    "weekly_working_days": "0;1;2;3;4;5;6",  
    

    # "late_delivery_tolerance_max_minutes": 5,  #--># tolerance_seconds
    #--># peak_period_spec + period_unit_second
        # "two_pick_merge_radius_max_meters": 3, # 3M, not 3KM
        # "kmedoid_radius_max_meters": 51_200,
        # "whitelist_radius_max_meters": 299_000,
        # "same_area_radius_max_meters": 4_000,
        # "different_area_radius_max_meters": 2_000,



    # This is in conjunction with location_group assignment. When LG is missing, this is used.
    "default_requested_primary_worker_code": "",
    # "nbr_observed_slots": 200,
    "slot_by_shift_start": 0,
    "slot_by_business_hour": 1,
    "shift_length_minutes": 480,
    "allow_overtime": 0,


    # "kmedoid_includes_start_flag":1,

    # "always_load_slot_pos": 1,
    # "reset_dataset": "N",
    # "nbr_initial_steps": 20,
    # "nbr_sampled_workers": 200,
    # "nbr_sampled_jobs": 3260,
    # "max_reposition_count_before_job": -1,
    # "logged_random_skip_job_max_nbr": 1,
    # "job_generation_max_count": 5500,
    # "shuffle_logged_locations": 0,
    # "simulation_log_dir": "/tmp",
        # 'reversible' : True, # if yes, I can revert one step back.
        # 'rule_set':kprl_rule_set,
        # "generic_job_commit_auto_tsp":1,

    # "scoring_factor_standard_travel_minutes": 90,
    # "job_address_flag": 1,
    "respect_initial_travel": 0,
    "worker_job_min_minutes": 1,
    "travel_speed_km_hour": 19.8,
    "travel_min_minutes": 5,
    "travel_max_minutes": 200,
    "job_icon": "fa-user",
    "worker_icon": "fa-taxi",

    # 2024-07-05 01:24:45, I decided to use only "skills" in flex form
    # "enable_customer_types": 1,
    # "enable_product_codes": 1,


    "begin_skip_minutes": 0,
    "inner_slot_planner": "head_tail",
    # "use_zulip": 0,
    # "requested_skills": "",
}

default_rust_env_config_data = {
    "enabled_rule_codes": "basic",
    "meter_search_radius": "6000",
    "meter_search_radius_whitelist": "600000",

    "enable_accum_items": "0",
    "enable_level_items": "0",
    "enable_skills": "0",
    "allow_mixed_area": "1",
    "meter_same_area": "3000",
    "meter_other_area": "1000",

    "enable_pick_pick_only": "0",
    "limit_same_location_stack": "0",
    "peak_period_spec": "",
    "period_unit_second": "3600",

    "meter_same_location_match": "10",
    "meter_priority_merge_pick": "300",
    "meter_priority_merge_drop": "1000",

    "meter_allowed_merge_pick": "2000",
    "meter_allowed_merge_drop": "4000",
    "meter_merge_drop_scaling": "20000",

    "meter_max_pick2drop_merge": "1000", 
    "tolerance_seconds": "0", 
    "nbr_k_medoids": "8", 
    "nbr_observed_slots": str(NBR_OF_OBSERVED_WORKERS), 
    "nbr_jobs_per_slot": "20", 

    "auto_purge_stale": "1", 

    "enable_future_recall": "0", 
    "data_start_seconds": "1704067200", # It will be overwritten by data_start_day, but here it provide key list
    "fixed_horizon_flag": "0", 
    "horizon_start_seconds": "0", 
    "utc_offset_seconds": "0", 
    # everyday when refresh planning window, we also detect the offset and adjust it.
}


composite_default_team_flex_form = copy.deepcopy(default_team_flex_form_data)
composite_default_team_flex_form.update(default_rust_env_config_data)


# team_env_flex_schema = {
#     "type": "object",
#     "properties": {
#       "enabled_rule_codes": {
#           "type": "string",
#           "default": "",
#           "title": "default requested primary_worker_code",
#       },
#       "capacity_weight": {
#         "type": "number",
#         "default": 1,
#         "title": "Max Weight, in Kilogram (KG)"
#       }, 
#     },
# }

# OLD_worker_flex_form_schema = {
#     "type": "object",
#     "properties": {
#       "capacity_volume": {
#         "type": "number",
#         "default": 1,
#         "title": "Max Volume, in Cubic Decimeter (dm^3)"
#       },
#       "capacity_weight": {
#         "type": "number",
#         "default": 1,
#         "title": "Max Weight, in Kilogram (KG)"
#       },
#         # "regist_default_account": {
#         #     "type": "boolean",
#         #     "title": "The default mobile phone number is used as the login account and password",
#         #     "default": False,
#         # },
#         # "mobile_phone": {"type": "string", "default": "", "title": "workers mobile phone;"},
#         # "zulip_email": {"type": "string", "default": "", "title": "zulip user email"},
#     },
# }

order_flex_form_schema = {
  "type": "object",
  "properties": {
  }
}
# OLD_job_flex_form_schema = {
#     "type": "object",
#     "properties": {
#       "volume": {
#         "type": "number",
#         "default": 1,
#         "title": "Requested Volume, in Cubic Decimeter (dm^3)"
#       },
#       "weight": {
#         "type": "number",
#         "default": 1,
#         "title": "Requested Weight, in gram (g)"
#       },
#         "location_group_code": {
#           "type": "string",
#           "default": "",
#           "title": "location_group_code"
#         },
#         "job_schedule_type": {
#             "type": "string",
#             "default": "N",
#             "title": "Job Type",
#             "description": "This affects timing, N=Normal, FS=Fixed Schedule.",
#             "enum": ["N", "FS"],
#         },
#         "tolerance_start_minutes": {
#             "type": "number",
#             "default": -1440 * 3,
#             "title": "requested min tolerance minutes backward, in minutes. One day is 1440 minutes",
#         },
#         "tolerance_end_minutes": {
#             "type": "number",
#             "default": 1440 * 3,
#             "title": "requested max tolerance minutes forward, in minutes. One day is 1440 minutes",
#         },
#         "min_number_of_workers": {
#             "type": "number",
#             "default": 1,
#             "title": "Min number of workers. Bigger than one means shared job among multiple workers",
#         },
#         "max_number_of_workers": {
#             "type": "number",
#             "default": 1,
#             "title": "Max number of workers. Bigger than one means shared job among multiple workers",
#         },
#     },
# }
msg_template = {
    "mgs_template": [
        {
            "id": "1",
            "code": "",
            "process_type": "",
            "status": "",
            "is_avtive": "",
            "content": "",
            "env": "",
            "created_at": "",
            "updated_at": "",
            "updated_by": "",
            "is_deleted": "",
        }
    ]
}

DEFAULT_WORK_CALENDAR={
  "promotional_working_days": {
    "2022-02-03": {
      "open": "0800",
      "close": "1700"
    },
    "2022-02-04": {
      "open": "0800",
      "close": "1700"
    }
  },
  "statutory_holidays": { 
    "2022-02-05":{
      "isOpen": False 
    },
    "2022-02-06":{
      "isOpen": False 
    },
  }
  
}

""" 
  ,
  "normal_working_day": {
    "sunday": [
      {
        "open": "",
        "close": "",
        "isOpen": False
      }
    ],
    "monday": [
      {
        "open": "0800",
        "close": "1700",
        "isOpen": True
      }
    ],
    "tuesday": [
      {
        "open": "0800",
        "close": "1700",
        "isOpen": True
      }
    ],
    "wednesday": [
      {
        "open": "0800",
        "close": "1700",
        "isOpen": True
      }
    ],
    "thursday": [
      {
        "open": "0800",
        "close": "1700",
        "isOpen": True
      }
    ],
    "friday": [
      {
        "open": "0800",
        "close": "1700",
        "isOpen": True
      }
    ],
    "saturday": [
      {
        "open": "0800",
        "close": "1700",
        "isOpen": True
      }
    ]
  },
"""



####################################################################################
####################################################################################
####################################################################################

FLEX_FORM_SCHEMA_DICT = {
  "common": {
    "team":{
        "timezone": {
            "type": "string",
            "default": DEFAULT_TEAM_TIMEZONE, # "Europe/London", # "Asia/Dubai",
            "title": "timezone string for this team, according to pytz list: https://pypi.org/project/pytz/",
        }, 
        "weekly_working_days": {
                "type": "string",
                "code": "weekly_working_days",
                "description": "working days in a week, for example: 1;2;3;4;5 means Monday to Friday. 0 is Sunday, 1 is Monday.", 
            },
        "team_holiday_days": {
            "type": "string", "default": "", 
            "title": "extra holiday days for this team, example: 2023-12-01;2023-12-02, each day using format YYYY-MM-DD"},
        "window_refresh_at": {
            "type": "string",
            "default": "0;30;2;30",
            "title": "window_refresh_at with format of start_hour;start_minute;end_h;end_m",
        }, 
        "fixed_horizon_flag": {
            "type": "number",
            "default": 1,
            "title": "fixed_horizon_flag flag (boolean [true: always env_start_datetime , false : System current time])", 
        },
        "horizon_start_datetime": {"type": "string", "title": "horizon_start_datetime, in ISO format, e.g. 2023-10-03T00:00:01"},
        "env_start_datetime": {"type": "string", "title": "env_start_datetime, in ISO format, e.g. 2023-10-03T00:00:00"},
        "nbr_minutes_planning_windows_duration": {
            "type": "number",
            "default": 1440,
            "title": "Duration minutes for planning window",
        },
        "planning_working_days": {
            "type": "number",
            "default": 1,
            "title": "Number of working days in planning Window (integer)"
        },
        "nbr_minutes_backward_planning_window": {
            "type": "number",
            "default": 1440,
            "title": "nbr_minutes_backward_planning_window",
        },
        "nbr_minutes_backward_unplanned_jobs": {
            "type": "number",
            "default": 60,
            "title": "nbr_minutes_backward_unplanned_jobs",
        }, 
        # "description": "AutoNavi: https://webrd01.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z} ; \n osrm: http://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
        "tile_server":{
            "type": "string",
            "default": "osm",
            "title": "Map Tile Server",
            "enum": ["autonavi", "osm"]
        },
        
        "front_routing_type": {
            "type": "string",
            "default": "polyline",
            "title": "front_routing_type",
            "description": "front_routing_type.",
            "enum": ["polyline", "osrm"]
        },
        "front_routing_url": {
            "type": "string",
            "default": "https://routing.easydispatch.uk/uk",
            "title": "front_routing_url"
        }, 
        "realtime_env_update_flag": {
            "type": "number",
            "default": 0,
            "title": "Whether or not update parameter to env in realtime. 0 means only saving to DB, but not the planning env (engine)", 
        },
      "meter_same_location_match": {
        "type": "number",
        "default": 10,
        "title": "meter_same_location_match"
      }, 
        "peak_period_spec": {
            "type": "string",
            "default": "10;11;12;13;18;19",
            "title": "list of hours when algorithm prioritize merging, seperated by ;. For example 11;12",
        },
        "enabled_rule_codes": {
            "type": "string",
            "default": "basic;area_code;tolerance_check;geo_merge;max_pick2drop_merge;worker_radius",
            "title": "list of rules enabled"
        },
      "longitude_diff_max": {
        "type": "number",
        "default": 55.7,
        "title": "longitude_diff_max"
      },
      "longitude_diff_min": {
        "type": "number",
        "default": 52.7,
        "title": "longitude_diff_min"
      },
      "latitude_diff_max": {
        "type": "number",
        "default": 100,
        "title": "latitude_diff_max"
      },
      "latitude_diff_min": {
        "type": "number",
        "default": 1,
        "title": "latitude_diff_min"
      },


      "nbr_jobs_per_slot": {
        "type": "number",
        "default": 6,
        "title": "Max number of Jobs per each Worker"
      },

      
      "nbr_observed_slots": {
            "type": "number",
            "default": 50,
            "title": "nbr_observed_slots",
        },


      "slot_by_shift_start": {
            "type": "number",
            "default": 0,
            "title": "slot_by_shift_start (1 as true/yes, 0 as not)",
        },
      "slot_by_business_hour": {
            "type": "number",
            "default": 1,
            "title": "slot_by_business_hour (1 as true/yes, 0 as not)",
        }, 
      "meter_search_radius": {
            "type": "number",
            "default": 50_000,
            "title": "The maximum distance from order's start point that the algorithm can search for workers",
      },
      "meter_same_area": {
          "type": "number",
          "default": 4_000,
          "title": "The maximum distance that same area idle workers take the order immediately. The closest worker will take first.",
      },
      "meter_other_area": {
          "type": "number",
          "default": 2_000,
          "title": "The maximum distance that other area idle workers take the order immediately. The closest worker will take first.",
      },
      "allow_mixed_areas": {
            "type": "number",
            "default": 1,
            "title": "allow mixed areas or not (1 as true/yes, 0 as not)",
        },

      "default_requested_primary_worker_code": {
          "type": "string",
          "default": "",
          "title": "default requested primary_worker_code",
      },
      "scoring_factor_standard_travel_minutes": {
          "type": "number",
          "default": 90,
          "title": "standard travel minutes (scoring factor, integer)",
      },
      "worker_job_min_minutes": {"type": "number", "title": "worker job min minutes (integer)"},
      "respect_initial_travel": {
          "type": "number",
          "default": 0,
          "title": "Whether respect initial travel or not (1 as true/yes, 0 as not)"
      },
        # "horizon_start_offset_minutes": {"type": "number", "title": "Initial offset for horizon start  minutes (integer) on top of env_start_day"},
        # "horizon_start_minutes": {"type": "number", "title": "horizon_start_minutes"},
        "travel_speed_km_hour": {"type": "number", "title": "travel_speed_km_hour (integer)"},
        "travel_min_minutes": {"type": "number", "title": "travel_min_minutes (integer)"},
        "worker_icon": {"type": "string", "title": "worker_icon  (fontawesome icon)"},
        "job_icon": {"type": "string", "title": "job_icon (fontawesome icon)"},
        "begin_skip_minutes": {
            "type": "number",
            "title": "The number of minutes skipped at the start of the task",
            "default": 60
        },
        "inner_slot_planner": {
            "type": "string",
            "default": "head_tail",
            "title": "Inner Slot Planner Type",
            "description": "(Deprecated) Different inner slot planning.",
            "enum": ["nearest_neighbour", "weighted_nearest_neighbour", "head_tail"],
        },
        "requested_skills": {
          "type": "string",
          "title": "(Deprecated) Available Skills (as strings) for Workers and Jobs, seperated by comma. Not tracked by team anymore.",
          "description": "Available Skills for Workers and Jobs.",
          "default": ""
        },       
    },
    "worker": {   
        "area_code": {
          "type": "string",
          "default": "A",
          "title": "area_code"
        },

     },
    "job":{
        "area_code": {
          "type": "string",
          "default": "A",
          "title": "area_code"
        },
        "tolerance_start_minutes": {
            "type": "number",
            "default": -1440 * 3,
            "title": "requested min tolerance minutes backward, in minutes. One day is 1440 minutes",
        },
        "tolerance_end_minutes": {
            "type": "number",
            "default": 1440 * 3,
            "title": "requested max tolerance minutes forward, in minutes. One day is 1440 minutes",
        },

    }
  },
  "pickdrop":{
    "team": {
      "late_delivery_tolerance_max_minutes": {
        "type": "number",
        "default": 15,
        "title": "The late delivery tolerance max minutes"
      },
      "meter_allowed_merge_pick": {
        "type": "number",
        "default": 500,
        "title": "meter_allowed_merge_pick is max meters for merging"
      },
      "meter_allowed_merge_drop": {
        "type": "number",
        "default": 1000,
        "title": "meter_allowed_merge_drop, Drop Max Meters for merge"
      },
      "meter_merge_drop_scaling": {
        "type": "number",
        "default": 20,
        "title": "Scaling Meters for meter_allowed_merge_drop in KM"
      }, 
    },
    "worker": {        },
    "job": {
        "location_group_code": {
          "type": "string",
          "default": "",
          "title": "location_group_code"
        },
    }
  },
  "single":{
    "team": {  },
    "worker": {
      "capacity_volume": {
        "type": "number",
        "default": 1,
        "title": "Max Volume, in Cubic Decimeter (dm^3)"
      },
      "capacity_weight": {
        "type": "number",
        "default": 1,
        "title": "Max Weight, in Kilogram (KG)"
      },

    },
    "job": {
      "volume": {
        "type": "number",
        "default": 1,
        "title": "Requested Volume, in Cubic Decimeter (dm^3)"
      },
      "weight": {
        "type": "number",
        "default": 1,
        "title": "Requested Weight, in gram (g)"
      },
  
    }

  },
  "FSM": {
    "team": {  },
    "worker": {
      "capacity_volume": {
        "type": "number",
        "default": 1,
        "title": "Max Volume, in Cubic Decimeter (dm^3)"
      },
      "capacity_weight": {
        "type": "number",
        "default": 1,
        "title": "Max Weight, in Kilogram (KG)"
      },
      "capacity_job": {
        "type": "number",
        "default": 1,
        "title": "Max number of jobs for this worker in each working shift. 1 order is 2 jobs."
      },
      "max_overtime_minutes_day": {
        "type": "number",
        "default": 60,
        "title": "max_overtime_minutes_day"
      },
      "max_overtime_minutes_window": {
        "type": "number",
        "default": 180,
        "title": "max_overtime_minutes in this planning window"
      },
      "level": {
        "type": "number",
        "default": 1,
        "title": "Employee Skill Level"
      },
      "skills": {
        "type": "string",
        "title": "Skills (as strings) for this Worker",
        "description": "Skills (as strings) for this Worker, seperated by ;",
        "default": ""
      },       
      "is_assistant_to": {
        "type": "string",
        "title": "whether this Worker is assistant to another worker, empty means not", 
        "default": ""
      },       

    },
    "job": {
        "job_schedule_type": {
            "type": "string",
            "default": "N",
            "title": "Job Type",
            "description": "This affects timing, N=Normal, FS=Fixed Schedule.",
            "enum": ["N", "FS"],
        },
        "min_number_of_workers": {
            "type": "number",
            "default": 1,
            "title": "Min number of workers. Bigger than one means shared job among multiple workers",
        },
        "max_number_of_workers": {
            "type": "number",
            "default": 1,
            "title": "Max number of workers. Bigger than one means shared job among multiple workers",
        },    
    }
  }  

}

DEFAULT_WORKER_FLEX_FORM_DATA= {
  "area_code": "A",
  "capacity_volume": 999,
  "capacity_weight": 999,
}


DEFAULT_JOB_FLEX_FORM_DATA= {
  "area_code": "A",
  "volume": 1,
  "weight": 1, 
}


DEFAULT_ORG_SETTING={
  "features": {
    "inventory": False,
    "zchat_integration": False,
    "order_new":True,
    "gantt_auto_refresh_seconds":5
  }, 
  "env_slug": "configurable_dispatch_env", # logged_configurable_env, configurable_dispatch_env
  "default_worker_flex_form_data":DEFAULT_WORKER_FLEX_FORM_DATA,
  "default_job_flex_form_data":DEFAULT_JOB_FLEX_FORM_DATA,
  #  创建新用户的map job 模板 
  'order_job_template':  {
          'live_map': 
          {
            
            #  默认为 team_id =1 , default_team , 一般情况下也不需要 其他 的 , 创建 job 会根据 token 确认哪个用户 
            'team_id': '1', 
            'team_code': 'default_team', 
            'create_order_template': 
                  {
                    'external_order_code': 'TS12', 
                    'order_source_code': 'SOURCE1',
                    'business_code': 'delivery', 
                    'flex_form_data': {'area_code': 'A'}, 
                    'external_business_status': None, 
                    'status_code': 'sync', 
                    'business_order_status': 'inbound_success',
                    'reason_code': None, 
                    'external_order_status': 'status1', 
                    'order_exception_status': None, 
                    'order_type': 'pickdrop', 
                    'start_time': None, 
                    'scheduled_primary_worker_code': None, 
                    'is_deleted': 0, 
                    'auto_planning': True, 
                    'auto_commit': True, 
                    'location_group_code': None, 
                    'accept_order': 'Y', 
                    'mandatory_assign': 'not_mandatory'
                    }, 
            'create_job_template': 
                    {
                      'requested_primary_worker_code': None, 
                      'location_code': None, 
                      'job_type': 'visit',
                      'planning_status': 'U', 
                      'auto_planning': True, 
                      'is_active': True,
                      'name': None, 
                      'description': None, 
                      'flex_form_data': {'area_code': 'A'},
                      'requested_duration_minutes': 0.5,
                      'scheduled_start_datetime': None, 
                      'scheduled_duration_minutes': 0.5, 
                      'scheduled_primary_worker_code': None, 
                      'order_code': 'order_code',
                      'tolerance_start_minutes': 0, 
                      'tolerance_end_minutes': 15
                      }
              }
          }
}




####################################################################################

FLEX_FORM_SCHEMA_DICT["single_area_code_cvrp"] = FLEX_FORM_SCHEMA_DICT["single"]

def get_flex_form_schema(planner_type, schema_type, ):
  schema = {
    "type": "object",
    "properties": FLEX_FORM_SCHEMA_DICT["common"][schema_type]
  }

  schema["properties"].update(FLEX_FORM_SCHEMA_DICT[planner_type][schema_type])
  return schema


####################################################################################
####################################################################################
