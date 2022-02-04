import TeamApi from "@/team/api";

import { getField, updateField } from "vuex-map-fields";
import { debounce } from "lodash";

const getDefaultSelectedState = () => {
  let today = new Date();
  let env_start_day = today
    .toISOString()
    .split("T")[0]
    .replace(/-/g, "");
  return {
    id: null,
    code: null,
    planner_service: null,

    name: null,
    description: null,

    flex_form_data: {
      env_start_day: env_start_day,
      planning_working_days: 1,
      scoring_factor_standard_travel_minutes: 90,
      job_address_flag: true,
      worker_icon: "fa-taxi",
      job_icon: "fa-user",
      holiday_days: "",
      weekly_rest_day: "",
      default_requested_primary_worker_code: "",
      travel_min_minutes: 5,
      travel_speed_km_hour: 19.8,
      horizon_start_minutes: 1925,
      respect_initial_travel: false,
      worker_job_min_minutes: 1,
      enable_env_start_day_is_other_day: false,
    },
    created_at: null,
    updated_at: null,
    loading: false,
  };
};

const state = {
  worker_icon: "",
  job_icon: "",
  selected: {
    ...getDefaultSelectedState(),
  },
  dialogs: {
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
      sortBy: ["name"],
      descending: [true],
    },
    loading: false,
  },
};

const getters = {
  getField,
};

const actions = {
  getAll: debounce(({ commit, state }) => {
    commit("SET_TABLE_LOADING", true);
    return TeamApi.getAll(state.table.options).then((response) => {
      commit("SET_TABLE_LOADING", false);
      commit("SET_TABLE_ROWS", response.data);
    });
  }, 200),
  createEditShow({ commit }, team) {
    commit("SET_DIALOG_CREATE_EDIT", true);
    if (team) {
      commit("SET_SELECTED", team);
    }
  },
  removeShow({ commit }, team) {
    commit("SET_DIALOG_DELETE", true);
    commit("SET_SELECTED", team);
  },
  closeCreateEdit({ commit }) {
    commit("SET_DIALOG_CREATE_EDIT", false);
    commit("RESET_SELECTED");
  },
  closeRemove({ commit }) {
    commit("SET_DIALOG_DELETE", false);
    commit("RESET_SELECTED");
  },
  setSelected({ commit }, team) {
    commit("SET_SELECTED", team);
  },

  setSelectedFormDataAndSave({ dispatch }, value) {
    if (value) {
      return dispatch("setSelected", value).then(() => {
        dispatch("save");
      });
    } else {
      return dispatch("save");
    }
  },
  save({ commit, dispatch }) {
    if (!state.selected.id) {
      return TeamApi.create(state.selected)
        .then(() => {
          dispatch("closeCreateEdit");
          dispatch("getAll");
          commit(
            "app/SET_SNACKBAR",
            { text: "Team created successfully." },
            { root: true }
          );
        })
        .catch((err) => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "Team not created. Reason: " + err.response.data.detail,
              color: "red",
            },
            { root: true }
          );
        });
    } else {
      return TeamApi.update(state.selected.id, state.selected)
        .then(() => {
          dispatch("closeCreateEdit");
          dispatch("getAll");
          commit(
            "app/SET_SNACKBAR",
            { text: "Team updated successfully." },
            { root: true }
          );
        })
        .catch((err) => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "Team not updated. Reason: " + err.response.statusText,
              color: "red",
            },
            { root: true }
          );
        });
    }
  },
  remove({ commit, dispatch }) {
    return TeamApi.delete(state.selected.id)
      .then(function() {
        dispatch("closeRemove");
        dispatch("getAll");
        commit(
          "app/SET_SNACKBAR",
          { text: "Team deleted successfully." },
          { root: true }
        );
      })
      .catch((err) => {
        commit(
          "app/SET_SNACKBAR",
          {
            text: "Team not deleted. Reason: Related data cannot be deleted",
            color: "red",
          },
          { root: true }
        );
      });
  },
  reset_planning_window({ commit, dispatch }, code) {
    return TeamApi.reset_planning_window({ team_code: code })
      .then(function() {
        commit(
          "app/SET_SNACKBAR",
          { text: "reset_planning_window successfully." },
          { root: true }
        );
      })
      .catch((err) => {
        commit(
          "app/SET_SNACKBAR",
          {
            text:
              "reset_planning_window error. Reason: " +
              err.response.data.detail,
            color: "red",
          },
          { root: true }
        );
      });
  },
  reset_callback({ commit, dispatch }) {
    return TeamApi.reset_callback({})
      .then(function() {
        commit(
          "app/SET_SNACKBAR",
          { text: "reset_callback successfully." },
          { root: true }
        );
      })
      .catch((err) => {
        commit(
          "app/SET_SNACKBAR",
          {
            text: "reset_callback error. Reason: " + err.response.data.detail,
            color: "red",
          },
          { root: true }
        );
      });
  },
  init_icon({ commit, dispatch }, team_id) {
    return TeamApi.get(team_id).then(function(response) {
      commit("SET_ICON", {
        worker_icon: response.data.flex_form_data["worker_icon"],
        job_icon: response.data.flex_form_data["job_icon"],
      });
    });
  },
  get_team_by_id({ commit, dispatch }, team_id) {
    return TeamApi.get(team_id).then(function(response) {
      commit("SET_SELECTED", response.data);
    });
  },
};

const mutations = {
  updateField,
  SET_SELECTED(state, value) {
    state.selected = Object.assign(state.selected, value);
  },
  SET_TABLE_LOADING(state, value) {
    state.table.loading = value;
  },
  SET_TABLE_ROWS(state, value) {
    state.table.rows = value;
  },
  SET_DIALOG_CREATE_EDIT(state, value) {
    state.dialogs.showCreateEdit = value;
  },
  SET_DIALOG_DELETE(state, value) {
    state.dialogs.showRemove = value;
  },
  RESET_SELECTED(state) {
    state.selected = Object.assign(state.selected, getDefaultSelectedState());
  },
  SET_ICON(state, value) {
    state.worker_icon = value.worker_icon;
    state.job_icon = value.job_icon;
  },
};

export default {
  namespaced: true,
  state,
  getters,
  actions,
  mutations,
};
