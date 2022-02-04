import API from "@/api";

const resource = "/orgs";

export default {
  getAll(options) {
    return API.get(`${resource}/`, { params: { ...options } });
  },

  get(id) {
    return API.get(`${resource}/id/${id}`);
  },

  create(payload) {
    return API.post(`${resource}/`, payload);
  },

  update(id, payload) {
    return API.put(`${resource}/${id}`, payload);
  },

  delete(id) {
    return API.delete(`${resource}/${id}`);
  },
  add_user_org(payload) {
    return API.post(`${resource}/add_user_org`, payload);
  },
};
