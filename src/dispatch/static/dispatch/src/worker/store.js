import WorkerApi from "@/worker/api";
import DashboardApi from "@/live_map/api";
import { debounce, forEach } from "lodash";
import { getField, updateField } from "vuex-map-fields";
const getDefaultSelectedPoint = () => {
  return {
    latLongCenter: [1.3951627287379205, 103.90117876532882],
    msg: {
      name: "",
    },
    all_jobs: [],
  };
};
const getDefaultBusinessHour = () => {
  return {
    sunday: [
      {
        open: "",
        close: "",
        id: "5ca5578b0c5c7",
        isOpen: false,
      },
    ],
    monday: [
      {
        open: "0800",
        close: "1700",
        id: "5ca5578b0c5d1",
        isOpen: true,
      },
    ],
    tuesday: [
      {
        open: "0800",
        close: "1700",
        id: "5ca5578b0c5d8",
        isOpen: true,
      },
    ],
    wednesday: [
      {
        open: "0800",
        close: "1700",
        id: "5ca5578b0c5df",
        isOpen: true,
      },
    ],
    thursday: [
      {
        open: "0800",
        close: "1700",
        id: "5ca5578b0c5e6",
        isOpen: true,
      },
    ],
    friday: [
      {
        open: "0800",
        close: "1700",
        id: "5ca5578b0c5ec",
        isOpen: true,
      },
    ],
    saturday: [
      {
        open: "",
        close: "",
        id: "5ca5578b0c5f8",
        isOpen: false,
      },
    ],
  };
};
const getDefaultSelectedState = () => {
  return {
    id: null,
    code: null,
    name: null,
    team: null,
    location: null,
    dispatch_user:null,
    description: null,
    is_active: null,
    flex_form_data: {
      level: 3,
      skills: ["electric_1"],
      assistant_to: null,
      is_assistant: false,
      maxAcceptOrderCount: 13,
    },
    business_hour: { ...getDefaultBusinessHour() },
    created_at: null,
    updated_at: null,
    skills: [],
    loaded_items: [],
    loaded_items_conbobox: [],
    loading: false,
  };
};

const state = {
  selected_marker: ["start", "heat_layer_job"],
  selected: {
    ...getDefaultSelectedState(),
  },
  selected_point: {
    ...getDefaultSelectedPoint(),
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
      descending: [false],
    },
    loading: false,
  },
};

const getters = {
  getField,
};

const actions = {
  onchange_route({ commit }, latLongWayPoints) {
    if (latLongWayPoints) {
      commit("SET_SELECTED_LAT_LONG", latLongWayPoints);
    }
  },
  get_live_map_job({ commit, state }, options) {
    return DashboardApi.get_live_map_job(options).then((response) => {
      const data_list = response.data.job_data_list;

      commit("SET_ALL_JOBS", data_list);
      commit("SET_SELECTED_LAT_LONG", [
        data_list[0].position_from,
        data_list[0].position_to,
        data_list[0].tooltip,
      ]);
    });
  },
  selectWorker: debounce(({ commit, state }, filterOptions) => {
    commit("SET_TABLE_LOADING", true);
    return WorkerApi.select(
      Object.assign(Object.assign({}, state.table.options), filterOptions)
    )
      .then((response) => {
        commit("SET_TABLE_LOADING", false);
        commit("SET_TABLE_ROWS", response.data);
      })
      .catch(() => {
        commit("SET_TABLE_LOADING", false);
      });
  }, 200),

  getAll: debounce(({ commit, state }, filterOptions) => {
    commit("SET_TABLE_LOADING", true);
    return WorkerApi.getAll(Object.assign(state.table.options, filterOptions))
      .then((response) => {
        commit("SET_TABLE_LOADING", false);
        commit("SET_TABLE_ROWS", response.data);
      })
      .catch(() => {
        commit("SET_TABLE_LOADING", false);
      });
  }, 200),
  createEditShow({ commit }, worker) {
    commit("SET_DIALOG_CREATE_EDIT", true);
    if (worker) {
      commit("SET_SELECTED", worker);
    }
  },
  removeShow({ commit }, worker) {
    commit("SET_DIALOG_DELETE", true);
    commit("SET_SELECTED", worker);
  },
  closeCreateEdit({ commit }) {
    commit("SET_DIALOG_CREATE_EDIT", false);
    commit("RESET_SELECTED");
  },
  closeRemove({ commit }) {
    commit("SET_DIALOG_DELETE", false);
    commit("RESET_SELECTED");
  },
  setSelectedFormData({ commit }, value) {
    commit("SET_SELECTED_FORM_DATA", value);
  },
  setSelectedFormDataAndSave({ dispatch }, value) {
    return dispatch("setSelectedFormData", value).then(() => {
      dispatch("save");
    });
  },

  save({ commit, dispatch }) {
    if (!state.selected.id) {
      return WorkerApi.create(state.selected)
        .then(() => {
          dispatch("closeCreateEdit");
          dispatch("getAll");
          commit("RESET_SELECTED");
          commit(
            "app/SET_SNACKBAR",
            { text: "Worker created successfully." },
            { root: true }
          );
        })
        .catch((err) => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "Worker not created. Reason: " + err.response.data.detail,
              color: "red",
            },
            { root: true }
          );
        });
    } else {
      return WorkerApi.update(state.selected.id, state.selected)
        .then(() => {
          dispatch("closeCreateEdit");
          dispatch("getAll");
          commit("RESET_SELECTED");
          commit(
            "app/SET_SNACKBAR",
            { text: "Worker updated successfully." },
            { root: true }
          );
        })
        .catch((err) => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "Worker not updated. Reason: " + err.response.data.detail,
              color: "red",
            },
            { root: true }
          );
        });
    }
  },
  remove({ commit, dispatch }) {
    return WorkerApi.delete(state.selected.id)
      .then(() => {
        dispatch("closeRemove");
        dispatch("getAll");
        commit(
          "app/SET_SNACKBAR",
          { text: "Worker deleted successfully." },
          { root: true }
        );
      })
      .catch((err) => {
        commit(
          "app/SET_SNACKBAR",
          {
            text: "Worker not deleted. Reason: Related data cannot be deleted",
            color: "red",
          },
          { root: true }
        );
      });
  },
};

const mutations = {
  updateField,
  SET_ALL_JOBS(state, value) {
    // This is only for demo purpose.
    if (state.selected.code == "Jenna") {
      let jobList = [];
      forEach(value, function(v) {
        if (v.position_from.lat < 51.42) {
          jobList.push(v);
        }
      });
      state.selected_point.all_jobs = jobList;
    } else {
      state.selected_point.all_jobs = value;
    }
  },
  SET_SELECTED_LAT_LONG(state, value) {
    state.selected_point.msg.name = value[2];
    state.selected_point.latLongCenter = [value[0]["lat"], value[0]["lng"]];
  },
  SET_SELECTED(state, value) {
    state.selected = Object.assign(state.selected, value);
    if (value.loaded_items) {
      let request_item = value.loaded_items.reduce((pre, cur, index) => {
        return [...pre, { text: cur }];
      }, []);
      state.selected.loaded_items_conbobox = request_item;
    }
  },
  SET_SELECTED_FORM_DATA(state, value) {
    //state.selected.flex_form_data = value
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
  SET_SELECTED_VISIBLE(state, options) {
    const type = options.type;
    const value = options.flag;
    if (type == "start") {
      state.selected_point.all_jobs.forEach((item) => {
        item.visible_from = value;
      });
    }
  },
  SET_ITEMS(state, value) {
    state.selected.loaded_items = value;
  },
  SET_SELECTED_BUSINESS_HOUR(state, value) {
    state.selected.business_hour = Object.assign(
      state.selected.business_hour,
      value
    );
  },
};

export default {
  namespaced: true,
  state,
  getters,
  actions,
  mutations,
};
