team_flex_form_schema = {
    "type": "object",
    "properties": {
        "env_start_day": {
            "type": "string",
            "title": "env_start_day ,team start day (string)"
        },
        "planning_working_days": {
            "type": "number",
            "default": 1,
            "title": "Number of working days in planning Window (integer)"
        },
        "holiday_days": {
            "type": "string",
            "default": "",
            "title": "holiday days, seperated by ;"
        },
        "default_requested_primary_worker_code": {
            "type": "string",
            "default": "",
            "title": "default requested primary_worker_code"
        },
        "scoring_factor_standard_travel_minutes": {
            "type": "number",
            "default": 90,
            "title": "standard travel minutes (scoring factor, integer)"
        },
        "worker_job_min_minutes": {
            "type": "number",
            "title": "worker job min minutes (integer)"
        },
        "respect_initial_travel": {
            "type": "boolean",
            "title": "Whether respect initial travel or not (boolean)"
        },
        "horizon_start_minutes": {
            "type": "number",
            "title": "horizon start minutes (integer)"
        },
        "travel_speed_km_hour": {
            "type": "number",
            "title": "travel_speed_km_hour (integer)"
        },
        "travel_min_minutes": {
            "type": "number",
            "title": "travel_min_minutes (integer)"
        },
        "worker_icon": {
            "type": "string",
            "title": "worker_icon  (fontawesome icon)"
        },
        "job_icon": {
            "type": "string",
            "title": "job_icon (fontawesome icon)"
        },
        "job_address_flag": {
            "type": "boolean",
            "title": "job_address_flag (boolean ,one true,two false)",
            "default": True
        },
        "fixed_env_start_day_flag": {
            "type": "boolean",
            "title": "fixed_env_start_day_flag (boolean [true: env_start_day whole day, false : System current time])",
            "default": True
        },
        "rolling_every_day": {
            "type": "boolean",
            "title": "rolling_every_day (boolean [true: env_start_day update every day])",
            "default": False
        },
        "begin_skip_minutes": {
            "type": "number",
            "title": "The number of minutes skipped at the start of the task",
            "default": 0
        },
        "inner_slot_planner": {
            "type": "string",
            "default": "weighted_nearest_neighbour",
            "title": "Inner Slot Planner Type",
            "description": "Different inner slot planning.",
            "enum": [
                    "nearest_neighbour",
                    "weighted_nearest_neighbour",
                    "head_tail"
            ]
        }, 
        "requested_skills": {
            "type": "array",
            "title": "Available Skills for Workers and Jobs",
            "description": "Available Skills for Workers and Jobs.",
            "default": [ ], 
            "items": {
                "type": "string"
            }
        }, 
        "routing_service_path": {
            "type": "string",
            "title": "Service URL for live map routing path",
        },
        "use_zulip": {
            "type": "boolean",
            "title": "Whether or not use zulip for sending job to worker",
            "default": False
        }
    }
}
worker_flex_form_schema = {
    "type": "object",
    "properties": {

        "zulip_email": {
            "type": "string",
            "default": "",
            "title": "zulip user email"
        }
    }
}
job_flex_form_schema = {
    "type": "object",
    "properties": {
        "job_schedule_type": {
            "type": "string",
            "default": "N",
            "title": "Job Type",
            "description": "This affects timing, N=Normal, FS=Fixed Schedule.",
            "enum": [
                    "N",
                    "FS"
            ]
        },
        "tolerance_start_minutes": {
            "type": "number",
            "default": -1440*3,
            "title": "requested min tolerance minutes backward, in minutes. One day is 1440 minutes"
        },
        "tolerance_end_minutes": {
            "type": "number",
            "default": 1440*3,
            "title": "requested max tolerance minutes forward, in minutes. One day is 1440 minutes"
        },
        "min_number_of_workers": {
            "type": "number",
            "default": 1,
            "title": "Min number of workers. Bigger than one means shared job among multiple workers"
        },
        "max_number_of_workers": {
            "type": "number",
            "default": 1,
            "title": "Max number of workers. Bigger than one means shared job among multiple workers"
        }
    }
}
