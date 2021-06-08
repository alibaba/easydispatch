import JobApi from "@/job/api";

import { getField, updateField } from "vuex-map-fields";
import { debounce, forEach, each, has } from "lodash";

const getDefaultSelectedState = () => {
  return {
    id: null,
    code: null,
    name: null,
    description: null,
    // location: {
    //   location_code: "job_loc_1",
    //   geo_longitude: -0.306,
    //   geo_latitude: 51.429
    // },
    location: null,
    team: null,
    flex_form_data: null,
    requested_start_datetime: null,
    requested_duration_minutes: null,
    scheduled_start_datetime: null,
    scheduled_duration_minutes: null,

    requested_primary_worker: null,
    scheduled_primary_worker: null,
    scheduled_secondary_workers: null,
    auto_planning: false,
    created_at: null,
    events: null,
    planning_status: null,
    tags: [],
    loading: false,
  };
};

const state = {
  selected: {
    ...getDefaultSelectedState(),
  },
  dialogs: {
    showEditSheet: false,
    showNewSheet: false,
    showRemove: false,
  },
  table: {
    rows: {
      items: [],
      total: null,
    },
    options: {
      filters: {
        reporter: [],
        commander: [],
        job_type: [],
        job_priority: [],
        status: [],
        tag: [],
      },
      q: "",
      page: 1,
      itemsPerPage: 10,
      sortBy: ["code"],
      descending: [true],
    },
    loading: false,
  },
};

const getters = {
  getField,
  tableOptions({ state }) {
    // format our filters
    return state.table.options;
  },
};

const actions = {
  getAll: debounce(({ commit, state }) => {
    commit("SET_TABLE_LOADING", true);

    let tableOptions = Object.assign({}, state.table.options);
    delete tableOptions.filters;

    tableOptions.fields = [];
    tableOptions.ops = [];
    tableOptions.values = [];

    forEach(state.table.options.filters, function(value, key) {
      each(value, function(value) {
        if (has(value, "id")) {
          tableOptions.fields.push(key + ".id");
          tableOptions.values.push(value.id);
        } else {
          tableOptions.fields.push(key);
          tableOptions.values.push(value);
        }
        tableOptions.ops.push("==");
      });
    });
    return JobApi.getAll(tableOptions)
      .then((response) => {
        commit("SET_TABLE_LOADING", false);
        commit("SET_TABLE_ROWS", response.data);
      })
      .catch(() => {
        commit("SET_TABLE_LOADING", false);
      });
  }, 200),
  get({ commit, state }) {
    return JobApi.get(state.selected.id).then((response) => {
      commit("SET_SELECTED", response.data);
    });
  },
  showNewSheet({ commit }, job) {
    commit("SET_DIALOG_SHOW_NEW_SHEET", true);
    if (job) {
      commit("SET_SELECTED", job);
    }
  },
  closeNewSheet({ commit }) {
    commit("SET_DIALOG_SHOW_NEW_SHEET", false);
    commit("RESET_SELECTED");
  },
  showEditSheet({ commit }, job) {
    commit("SET_DIALOG_SHOW_EDIT_SHEET", true);
    if (job) {
      commit("SET_SELECTED", job);
    }
  },
  closeEditSheet({ commit }) {
    commit("SET_DIALOG_SHOW_EDIT_SHEET", false);
    commit("RESET_SELECTED");
  },
  removeShow({ commit }, job) {
    commit("SET_DIALOG_DELETE", true);
    commit("SET_SELECTED", job);
  },
  setSelected({ commit }, job) {
    commit("SET_SELECTED", job);
  },

  closeRemove({ commit }) {
    commit("SET_DIALOG_DELETE", false);
    commit("RESET_SELECTED");
  },
  setSelectedFormDataAndSave({ dispatch }, value) {
    if (value) {
      return dispatch("setSelected", { flex_form_data: value }).then(() => {
        dispatch("save");
      });
    } else {
      return dispatch("save");
    }
  },
  save({ commit, dispatch }) {
    if (!state.selected.team) {
      commit(
        "app/SET_SNACKBAR",
        {
          text: "Please select a team. ",
          color: "red",
        },
        { root: true }
      );
      return;
    }
    // commit("SET_SELECTED", { flex_form_data: value });

    if (!state.selected.id) {
      commit("SET_SELECTED_LOADING", true);
      return JobApi.create(state.selected)
        .then((response) => {
          commit("SET_SELECTED", response.data);
          commit("SET_SELECTED_LOADING", false);
          this.interval = setInterval(function() {
            if (state.selected.id) {
              dispatch("get");
            }
          }, 5000);
        })
        .catch((err) => {
          commit("SET_SELECTED_LOADING", false);
          commit(
            "app/SET_SNACKBAR",
            {
              text:
                "Job not saved. Reasons: " +
                JSON.stringify(err.response.data.detail),
              color: "red",
            },
            { root: true }
          );
        });
    } else {
      return JobApi.update(state.selected.id, state.selected)
        .then(() => {
          dispatch("closeEditSheet");
          dispatch("closeNewSheet");
          dispatch("getAll");
          commit(
            "app/SET_SNACKBAR",
            { text: "Job updated successfully." },
            { root: true }
          );
        })
        .catch((err) => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "Job not updated. Reason: " + err.response.data.detail,
              color: "red",
            },
            { root: true }
          );
        });
    }
  },
  remove({ commit, dispatch }) {
    return JobApi.delete(state.selected.id)
      .then(function() {
        dispatch("closeRemove");
        dispatch("getAll");
        commit(
          "app/SET_SNACKBAR",
          { text: "Job deleted successfully." },
          { root: true }
        );
      })
      .catch((err) => {
        commit(
          "app/SET_SNACKBAR",
          {
            text: "Job not deleted. Reason: " + err.response.data.detail,
            color: "red",
          },
          { root: true }
        );
      });
  },
  resetSelected({ commit }) {
    commit("RESET_SELECTED");
  },
  joinJob({ commit }, jobId) {
    JobApi.join(jobId, {}).then(() => {
      commit(
        "app/SET_SNACKBAR",
        { text: "You have successfully joined the job." },
        { root: true }
      );
    });
  },
};

const mutations = {
  updateField,
  SET_SELECTED(state, value) {
    state.selected = Object.assign(state.selected, value);
    /*
    if (value.flex_form_data) {
      state.selected.flex_form_data = value.flex_form_data
    }*/
  },
  SET_TABLE_LOADING(state, value) {
    state.table.loading = value;
  },
  SET_TABLE_ROWS(state, value) {
    state.table.rows = value;
  },
  SET_DIALOG_SHOW_EDIT_SHEET(state, value) {
    state.dialogs.showEditSheet = value;
  },
  SET_DIALOG_SHOW_NEW_SHEET(state, value) {
    state.dialogs.showNewSheet = value;
  },
  SET_DIALOG_DELETE(state, value) {
    state.dialogs.showRemove = value;
  },
  RESET_SELECTED(state) {
    state.selected = Object.assign(state.selected, getDefaultSelectedState());
  },
  SET_SELECTED_LOADING(state, value) {
    state.selected.loading = value;
  },
};

export default {
  namespaced: true,
  state,
  getters,
  actions,
  mutations,
};
