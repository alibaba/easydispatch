import API from "@/api";

const resource = "/user";

export default {
  getAll(options) {
    return API.get(`${resource}/`, { params: { ...options } });
  },
  get(userId) {
    return API.get(`${resource}/${userId}`);
  },
  update(userId, payload) {
    return API.put(`${resource}/${userId}`, payload);
  },
  getUserInfo() {
    return API.get(`/auth/me`);
  },
  login(email, password) {
    return API.post(`/auth/login`, { email: email, password: password });
  },
  register(userDict) { //email, password, en_code, org_code
    return API.post(`/auth/register`,userDict
      // {
      // email: email,
      // password: password,
      // en_code,
      // org_code,
      // }
    );
  },
  create_org(payload) {
    return API.post(`/auth/register_user_org`, payload);
  },
  delete(id) {
    return API.delete(`${resource}/${id}`);
  },
};
