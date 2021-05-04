import API from "@/api";

const resource = "/jobs";

export default {
  getAll(options) {
    return API.get(`${resource}/`, { params: { ...options } });
  },

  get(jobId) {
    return API.get(`${resource}/${jobId}`);
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

  join(jobId, payload) {
    return API.post(`${resource}/${jobId}/join`, payload);
  },

  // TODO: Still not clear to me we'll actually use delete() here, and like
  // this, for jobs.
  delete(jobId) {
    return API.delete(`${resource}/${jobId}`);
  }
};
