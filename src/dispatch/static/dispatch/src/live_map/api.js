import API from "@/api";

const worker_resource = "/workers";
const jobs_resource = "/jobs";

export default {
  get_all_worker(options) {
    return API.get(`${worker_resource}/all/worker_list`, {
      params: { ...options },
    });
  },
  get_live_map_job(options) {
    return API.get(`${jobs_resource}/live_map/job_list`, {
      params: { ...options },
    });
  },
  get_job_pick_drop(options) {
    return API.get(`${jobs_resource}/live_map/job_pick_drop`, {
      params: { ...options },
    });
  },
};
