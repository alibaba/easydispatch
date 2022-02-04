import API from "@/api";

const resource = "/items";

export default {
  getAll(options) {
    return API.get(`${resource}/`, { params: { ...options } });
  },

  get(itemId) {
    return API.get(`${resource}/${itemId}`);
  },

  create(payload) {
    return API.post(`${resource}/`, payload);
  },

  update(itemId, payload) {
    return API.put(`${resource}/${itemId}`, payload);
  },

  delete(itemId) {
    return API.delete(`${resource}/${itemId}`);
  },
};
