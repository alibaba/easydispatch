import API from "@/api";

const resource = "/planner_service";

export default {
  get_planed_jobs(option) {
    return API.get(
      `${resource}/get_planed_jobs/?start_datatime=${option.start_datatime}&end_datatime=${option.end_datatime}&team_id=${option.team_id}`
    );
  },
};
