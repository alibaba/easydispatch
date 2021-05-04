import API from "@/api";

const resource = "/locations";

export default {
  getAll(options) {
    return API.get(`${resource}/`, { params: { ...options } });
  },
  get(locationId) {
    return API.get(`${resource}/${locationId}`);
  },

  create(payload) {
    return API.post(`${resource}/`, payload);
  },

  update(locationId, payload) {
    return API.put(`${resource}/${locationId}`, payload);
  },

  delete(locationId) {
    return API.delete(`${resource}/${locationId}`);
  }
};
