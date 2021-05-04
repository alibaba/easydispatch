import API from "@/api";

const resource = "/service_plugins";

export default {
  getAll(options) {
    return API.get(`${resource}/`, { params: { ...options } });
  },

  get(servicePluginId) {
    return API.get(`${resource}/${servicePluginId}`);
  },

  create(payload) {
    return API.post(`${resource}/`, payload);
  },

  update(servicePluginId, payload) {
    return API.put(`${resource}/${servicePluginId}`, payload);
  },

  delete(servicePluginId) {
    return API.delete(`${resource}/${servicePluginId}`);
  }
};
