import jwt_decode from "jwt-decode";
import router from "@/router/index";
import { differenceInMilliseconds, fromUnixTime, subMinutes } from "date-fns";
import { getField, updateField } from "vuex-map-fields";
import { debounce } from "lodash";
import UserApi from "./api";
import TeamApi from "@/team/api";


const getDefaultSelectedState = () => {
  return {
    id: null,
    email: null,
    role: null,
    loading: false,
    default_team_id: null,
    team: null,
    managed_teams: null,
    is_active:false,
  };
};

const getDefaultorg = () => {
  return {
    code: null,
    id: null,
    en_code: null,
  };
};

const state = {
  status: { loggedIn: false },
  userInfo: { email: "" },
  defaultTeam: null,
  accessToken: null,
  selected: {
    ...getDefaultSelectedState(),
  },
  org: { ...getDefaultorg() },
  dialogs: {
    showEdit: false,
    showCreateEdit: false,
    showRemove: false,
  },
  table: {
    rows: {
      items: [],
      total: null,
    },
    options: {
      q: "",
      page: 1,
      itemsPerPage: 10,
      sortBy: ["email"],
      descending: [true],
    },
    loading: false,
  },
  defaultPermission: ["Owner","Planner",],
  permissionDict: {
    "job.button.start": ["Owner","Planner","Worker"],
    "job.button.finish": ["Owner","Planner","Worker"],
    "job.button.customer_approve": ["Owner","Planner","Customer"],
    "job.button.planner_approve": ["Owner","Planner",],
    "job.button.save": ["Owner","Planner"],
    "location.button.customer_create_job": [ "Customer"],
  },
};

const actions = {
  showCreateEditDialog({ commit }, value) {
    commit("SET_DIALOG_CREATE_EDIT", value);
  },
  getAll: debounce(({ commit, state }) => {
    commit("SET_TABLE_LOADING", true);
    return UserApi.getAll(state.table.options).then((response) => {
      commit("SET_TABLE_LOADING", false);
      commit("SET_TABLE_ROWS", response.data);
    });
  }, 200),
  // selectLoginUsername: debounce(({ commit, state }, filterOptions) => {
  //   commit("SET_TABLE_LOADING", true);
  //   return UserApi.select(
  //     Object.assign(Object.assign({}, state.table.options), filterOptions)
  //   )
  //     .then((response) => {
  //       commit("SET_TABLE_LOADING", false);
  //       commit("SET_TABLE_ROWS", response.data);
  //     })
  //     .catch(() => {
  //       commit("SET_TABLE_LOADING", false);
  //     });
  // }, 200),

  editShow({ commit }, plugin) {
    commit("SET_DIALOG_EDIT", true);
    if (plugin) {
      commit("SET_SELECTED", plugin);
    }
  },
  closeEdit({ commit }) {
    commit("SET_DIALOG_EDIT", false);
    commit("RESET_SELECTED");
  },
  saveOrg({ commit }) {
    if (state.org.code) {
      return UserApi.create_org(state.org)
        .then((response) => {
          commit("SET_ORG_EN_CODE", response.data);
          commit("SET_DIALOG_CREATE_EDIT", false);
          commit(
            "app/SET_SNACKBAR",
            { text: "org created successfully." },
            { root: true }
          );
        })
        .catch((err) => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "org not created. Reason: " + err.response.data.detail,
              color: "red",
            },
            { root: true }
          );
        });
    }
  },
  save({ commit, dispatch }, param) {
    if (!state.selected.id) {
      return UserApi.create(Object.assign(state.selected, param))
        .then(() => {
          dispatch("closeEdit");
          dispatch("getAll");
          commit(
            "app/SET_SNACKBAR",
            { text: "User created successfully." },
            { root: true }
          );
          if (param.password && param.is_me) {
            dispatch("basicLogin", Object.assign(state.selected, param));
          }
        })
        .catch((err) => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "User not created. Reason: " + err.response.data.detail,
              color: "red",
            },
            { root: true }
          );
        });
    } else {
      return UserApi.update(
        state.selected.id,
        Object.assign(state.selected, param)
      )
        .then(() => {
          if (param.password && param.is_me) {
            dispatch("basicLogin", Object.assign(state.selected, param));
          }
          dispatch("closeEdit");
          dispatch("getAll");
          commit(
            "app/SET_SNACKBAR",
            { text: "User updated successfully." },
            { root: true }
          );
        })
        .catch((err) => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "User not updated. Reason: " + err.response.data.detail,
              color: "red",
            },
            { root: true }
          );
        });
    }
  },
  remove({ commit, dispatch }) {
    return UserApi.delete(state.selected.id)
      .then(function() {
        dispatch("closeRemove");
        dispatch("getAll");
        commit(
          "app/SET_SNACKBAR",
          { text: "User deleted successfully." },
          { root: true }
        );
      })
      .catch((err) => {
        commit(
          "app/SET_SNACKBAR",
          {
            text: "User not deleted. Reason: " + err.response.data.detail,
            color: "red",
          },
          { root: true }
        );
      });
  },
  loginRedirect({ state }, redirectUri) {
    let redirectUrl = new URL(redirectUri);
    void state;
    router.push({ path: redirectUrl.pathname });
  },
  basicLogin({ commit }, payload) {
    UserApi.login(payload.email, payload.password)
      .then(function(res) {
        commit("SET_USER_LOGIN", res.data.token);

        router.push({ path: "/jobs" });
      })
      .catch((err) => {
        commit(
          "app/SET_SNACKBAR",
          { text: err.response.data.detail, color: "red" },
          { root: true }
        );
      });
  },
  login({ dispatch, commit }, payload) {
    commit("SET_USER_LOGIN", payload.token);
    if (payload.redirectUri != undefined){
      dispatch("loginRedirect", payload.redirectUri).then(() => {
        dispatch("createExpirationCheck");
      });
    }
  },
  logout({ commit }) {
    commit("SET_USER_LOGOUT");
    router.push({ path: "/login" });
  },
  register({ dispatch, commit }, payload) {
    UserApi.register(payload).then(function() {
        dispatch("basicLogin", payload);
        commit("SET_ORG_EN_CODE", "");
      }).catch((err) => {
        commit(
          "app/SET_SNACKBAR",
          { text: err.response.data.detail, color: "red" },
          { root: true }
        );
      });
  },
  createExpirationCheck({ state, commit }) {
    // expiration time minus 10 min
    let expire_at = subMinutes(fromUnixTime(state.userInfo.exp), 10);
    let now = new Date();

    setTimeout(function() {
      commit(
        "app/SET_REFRESH",
        {
          show: true,
          message: "Your credentials have expired. Please refresh the page.",
        },
        { root: true }
      );
    }, differenceInMilliseconds(expire_at, now));
  },
  getUserInfo({ commit }) {
    UserApi.getUserInfo().then(function(res) {
      commit("SET_USER_INFO", res.data);
      TeamApi.get(res.data.default_team_id).then(function(res) {
        commit("SET_DEFAULT_TEAM", res.data);
      });
    });
  },
  removeShow({ commit }, data) {
    commit("SET_DIALOG_DELETE", true);
    commit("SET_SELECTED", data);
  },
  closeRemove({ commit }) {
    commit("SET_DIALOG_DELETE", false);
    commit("RESET_SELECTED");
  },
};

const mutations = {
  updateField,
  SET_DIALOG_DELETE(state, value) {
    state.dialogs.showRemove = value;
  },
  SET_SELECTED(state, value) {
    state.selected = Object.assign(state.selected, value);
  },
  SET_TABLE_LOADING(state, value) {
    state.table.loading = value;
  },
  SET_TABLE_ROWS(state, value) {
    state.table.rows = value;
  },
  SET_DIALOG_EDIT(state, value) {
    state.dialogs.showEdit = value;
  },
  RESET_SELECTED(state) {
    state.selected = Object.assign(state.selected, getDefaultSelectedState());
  },
  SET_USER_INFO(state, info) {
    state.userInfo = info;
  },
  SET_DEFAULT_TEAM(state, info) {
    state.defaultTeam = info;
  },

  SET_USER_LOGIN(state, accessToken) {
    state.accessToken = accessToken;
    state.status = { loggedIn: true };
    state.userInfo = jwt_decode(accessToken);
    localStorage.setItem("token", accessToken);
  },
  SET_USER_LOGOUT(state) {
    state.status = { loggedIn: false };
    state.userInfo = null;
    state.accessToken = null;
    localStorage.removeItem("token");
  },
  SET_DIALOG_CREATE_EDIT(state, value) {
    state.dialogs.showCreateEdit = value;
  },
  SET_ORG_EN_CODE(state, info) {
    state.org.en_code = info;
  },
};

const getters = {
  getField,
  accessToken: () => state.accessToken,
  email: () => state.userInfo.email,
  exp: () => state.userInfo.exp,
  getPermission: (state) => (p) =>
  {
    let localPermission = state.defaultPermission;
    if (p in state.permissionDict) {
      localPermission=state.permissionDict[p]
    }
    // console.log(p, localPermission)
    if (state.userInfo) {
      return localPermission.includes(state.userInfo.role);
    } else {
      return false
    }
  },
};

export default {
  namespaced: true,
  state,
  getters,
  actions,
  mutations,
};
