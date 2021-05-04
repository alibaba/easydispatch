import store from "@/store";

function login(to, from, next) {
  let token = localStorage.getItem("token");

  if (token) {
    store.commit("auth/SET_USER_LOGIN", token);
    next();
  } else {
    // prevent redirect loop
    if (to.path !== "/login") {
      next("/login");
    } else {
      next();
    }
  }
}

function logout(next) {
  store.commit("auth/SET_USER_LOGOUT");
  next();
}

export default {
  login,
  logout
};
