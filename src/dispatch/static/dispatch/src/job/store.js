import JobApi from "@/job/api";

import { getField, updateField } from "vuex-map-fields";
import { debounce, forEach, each, has } from "lodash";
import { v4 as uuidv4 } from 'uuid';

function getCurrentTime() {
  var date = new Date();
  var month = zeroFill(date.getMonth() + 1);
  var day = zeroFill(date.getDate());
  var hour = zeroFill(date.getHours());
  var minute = zeroFill(date.getMinutes());
  var second = zeroFill(date.getSeconds());

  var curTime =
    date.getFullYear() +
    "-" +
    month +
    "-" +
    day +
    "T" +
    hour +
    ":" +
    minute +
    ":" +
    second;

  return curTime;
}
function zeroFill(i) {
  if (i >= 0 && i <= 9) {
    return "0" + i;
  } else {
    return i;
  }
}
const getDefaultSelectedState = () => {
  return {
    id: null,
    code: null,
    name: null,
    description: null,
    job_type: "visit",
    // location: {
    //   location_code: "job_loc_1",
    //   geo_longitude: -0.306,
    //   geo_latitude: 51.429
    // },
    location: null,
    team: null,
    flex_form_data: {
      job_schedule_type: "N",
      requested_min_level: 1,
      tolerance_start_minutes: -1440 * 3,
      tolerance_end_minutes: 1440 * 3,
      min_number_of_workers: 1,
      max_number_of_workers: 1,
    },
    requested_start_datetime: getCurrentTime(),
    requested_duration_minutes: 30,
    scheduled_start_datetime: getCurrentTime(),
    scheduled_duration_minutes: null,

    requested_primary_worker: null,
    scheduled_primary_worker: null,
    scheduled_secondary_workers: null,
    auto_planning: false,
    created_at: null,
    updated_at: null,
    events: null,
    planning_status: "U",
    life_cycle_status: "Created",
    tags: [],
    requested_skills: [],
    requested_items: [],
    requested_items_conbobox: [],
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
    showJobEdit4WorkerFlag: false,
    showJobEdit4CustomerFlag: false,
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
        planning_status: [],
        life_cycle_status: [],
        tag: [],
      },
      q: "",
      page: 1,
      itemsPerPage: 10,
      sortBy: ["scheduled_primary_worker_id"],
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
  getByJobIdNoToken({ commit, state }, params) {
    return JobApi.getJobByNoToken(params).then((response) => {
      commit("SET_SELECTED", response.data);
    });
  },
  getByJobId({ commit }, jobId) {
    return JobApi.get( jobId).then((response) => {
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
  showJobEdit4Worker({ commit }, job) {
    commit("SET_DIALOG_SHOW_EDIT_JOB_4_WORKER", true);
    if (job) {
      commit("SET_SELECTED", job);
    }
  },
  showJobEdit4Customer({ commit }, {job, loc}) {
    if (job) {
      commit("SET_SELECTED", job);
    } else {
      let job = getDefaultSelectedState()
      job.code = uuidv4();
      job.team = {
        code:"default_team",
      }
      if (loc) {
        job.location = loc
      }
      commit("SET_SELECTED", job);
    }

    commit("SET_DIALOG_SHOW_EDIT_JOB_4_CUSTOMER", true);
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
      return dispatch("setSelected", value).then(() => {
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
    if (!state.selected.location) {
      commit(
        "app/SET_SNACKBAR",
        {
          text: "Please select a valid location.",
          color: "red",
        },
        { root: true }
      );
      return;
    }
    // commit("SET_SELECTED", { flex_form_data: value });
    if (state.selected.requested_primary_worker == "") {
      state.selected.requested_primary_worker = null;
    }
    if (state.selected.scheduled_primary_worker == "") {
      state.selected.scheduled_primary_worker = null;
    }
    if (state.selected.scheduled_secondary_workers == "") {
      state.selected.scheduled_secondary_workers = null;
    }

    commit("SET_SELECTED_LOADING", true);
    if (!state.selected.id) {
      return JobApi.create(state.selected)
        .then((response) => {
          if (response.data["state"] != -1) {
            commit("SET_SELECTED", response.data);
            commit("SET_SELECTED_LOADING", false);

            dispatch("closeEditSheet");
            dispatch("closeNewSheet");
            dispatch("getAll");
            commit(
              "app/SET_SNACKBAR",
              { text: "Job create successfully." },
              { root: true }
            );
          } else {
            commit(
              "app/SET_SNACKBAR",
              {
                text:
                  "Job not saved. Reasons: " +
                  JSON.stringify(response.data["msg"]),
                color: "red",
              },
              { root: true }
            );
          }
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
          commit("SET_SELECTED_LOADING", false);
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
          commit("SET_SELECTED_LOADING", false);
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
  updateJobByNoToken({ commit, dispatch }, token) {
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

    commit("SET_SELECTED_LOADING", true);

    return JobApi.updateJobByNoToken(state.selected.id, {
      ...state.selected,
      token: token,
    })
      .then(() => {
        commit("SET_SELECTED_LOADING", false);
        commit(
          "app/SET_SNACKBAR",
          { text: "Job updated successfully." },
          { root: true }
        );
      })
      .catch((err) => {
        commit("SET_SELECTED_LOADING", false);
        commit(
          "app/SET_SNACKBAR",
          {
            text: "Job not updated. Reason: " + err.response.data.detail,
            color: "red",
          },
          { root: true }
        );
      });
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
            text: "Job not deleted. Reason: Related data cannot be deleted",
            color: "red",
          },
          { root: true }
        );
      });
  },
  updateJobLifeCycle({ commit, dispatch, state }, {userEmail, workerComment, newStatus}) {
    if (((newStatus == "Onsite_Started") && (state.selected.life_cycle_status != "Created")) 
        || ((newStatus == "Completed") && (state.selected.life_cycle_status != "Onsite_Started"))
    ) {
      commit(
        "app/SET_SNACKBAR",
        {
          text: "Job is not in expected status and can not be started/completed.",
          color: "red",
        },
        { root: true }
      );
      return;
    }

    let jobStatus = {
      code: state.selected.code,
      life_cycle_status: newStatus,
      update_source: userEmail,
      comment: workerComment,
    };
    return JobApi.update_job_life_cycle(state.selected.id, jobStatus)
      .then(function() {  
        commit(
          "SET_SELECTED",
          { life_cycle_status: newStatus,}, 
        ); 
        commit(
          "app/SET_SNACKBAR",
          { text: "Job status is updatetd successfully." },
          { root: true }
        );
      })
      .catch((err) => {
        commit(
          "app/SET_SNACKBAR",
          {
            text: "Failed to update Job status.",
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
    if (value.requested_items) {
      let request_item = value.requested_items.reduce((pre, cur, index) => {
        return [...pre, { text: cur }];
      }, []);
      state.selected.requested_items_conbobox = request_item;
    }

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
  SET_DIALOG_SHOW_EDIT_JOB_4_WORKER(state, value) {
    state.dialogs.showJobEdit4WorkerFlag = value;
  }, 
  SET_DIALOG_SHOW_EDIT_JOB_4_CUSTOMER(state, value) {
    state.dialogs.showJobEdit4CustomerFlag = value;
  },

  SET_DIALOG_SHOW_EDIT_SHEET(state, value) {
    state.dialogs.showEditSheet = value;
    if (!value) {
      state.dialogs.showJobEdit4CustomerFlag = false;
      state.dialogs.showJobEdit4WorkerFlag = false;
    }
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
  SET_ITEMS(state, value) {
    state.selected.requested_items = value;
  },
  SET_SELECTED_ID(state, value) {
    state.selected.id = value;
  },
};

export default {
  namespaced: true,
  state,
  getters,
  actions,
  mutations,
};
