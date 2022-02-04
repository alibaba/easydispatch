import API from "@/api";

const resource = "/item_inventory";

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
  selectAll() {
    return API.get(`auth/item_inventory/get_all/`);
  },
};
