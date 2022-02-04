import API from "@/api";

const resource = "/jobs";
const auth = "/auth";

export default {
  getAll(options) {
    return API.get(`${resource}/`, { params: { ...options } });
  },

  get(jobId) {
    return API.get(`${resource}/${jobId}`);
  },

  getJobByNoToken(param) {
    return API.get(`${auth}/get_job_no_token/${param.job_id}/${param.token}`);
  },
  updateJobByNoToken(jobId, payload) {
    return API.put(`${auth}/update_job_no_token/${jobId}`, payload);
  },
  getMetricForecast(jobType) {
    return API.get(`${resource}/metric/forecast/${jobType}`);
  },

  create(payload) {
    return API.post(`${resource}/`, payload);
  },

  update(jobId, payload) {
    return API.put(`${resource}/${jobId}`, payload);
  },

  update_job_life_cycle(jobId, payload) {
    return API.put(`${resource}/update_job_life_cycle/${jobId}`, payload);
  },


  join(jobId, payload) {
    return API.post(`${resource}/${jobId}/join`, payload);
  },

  // TODO: Still not clear to me we'll actually use delete() here, and like
  // this, for jobs.
  delete(jobId) {
    return API.delete(`${resource}/${jobId}`);
  },
};
