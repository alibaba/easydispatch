import DepotApi from "@/depot/api";

import { getField, updateField } from "vuex-map-fields";
import { debounce } from "lodash";

const getDefaultSelectedState = () => {
  return {
    id: null,
    code: null,
    name: null,
    description: null,
    location: null,
    max_volume: null,
    max_weight: null,
    org_id: 0,
    flex_form_data: {},
    is_active: null,
    created_at: null,
    updated_at: null,
    loading: false,
  };
};

const state = {
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
    return DepotApi.getAll(state.table.options).then((response) => {
      commit("SET_TABLE_LOADING", false);
      commit("SET_TABLE_ROWS", response.data);
    });
  }, 200),
  createEditShow({ commit }, item) {
    commit("SET_DIALOG_CREATE_EDIT", true);
    if (item) {
      commit("SET_SELECTED", item);
    }
  },
  removeShow({ commit }, item) {
    commit("SET_DIALOG_DELETE", true);
    commit("SET_SELECTED", item);
  },
  closeCreateEdit({ commit }) {
    commit("SET_DIALOG_CREATE_EDIT", false);
    commit("RESET_SELECTED");
  },
  closeRemove({ commit }) {
    commit("SET_DIALOG_DELETE", false);
    commit("RESET_SELECTED");
  },
  setSelected({ commit }, item) {
    commit("SET_SELECTED", item);
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
    if (!state.selected.location.location_code) {
      commit(
        "app/SET_SNACKBAR",
        {
          text: "location field is required",
          color: "red",
        },
        { root: true }
      );
      return false;
    }
    if (!state.selected.id) {
      return DepotApi.create(state.selected)
        .then(() => {
          dispatch("closeCreateEdit");
          dispatch("getAll");
          commit(
            "app/SET_SNACKBAR",
            { text: "Depot created successfully." },
            { root: true }
          );
        })
        .catch((err) => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "Depot not created. Reason: " + err.response.data.detail,
              color: "red",
            },
            { root: true }
          );
        });
    } else {
      return DepotApi.update(state.selected.id, state.selected)
        .then(() => {
          dispatch("closeCreateEdit");
          dispatch("getAll");
          commit(
            "app/SET_SNACKBAR",
            { text: "Depot updated successfully." },
            { root: true }
          );
        })
        .catch((err) => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "Depot not updated. Reason: " + err.response.statusText,
              color: "red",
            },
            { root: true }
          );
        });
    }
  },
  remove({ commit, dispatch }) {
    return DepotApi.delete(state.selected.id)
      .then(function() {
        dispatch("closeRemove");
        dispatch("getAll");
        commit(
          "app/SET_SNACKBAR",
          { text: "Depot deleted successfully." },
          { root: true }
        );
      })
      .catch((err) => {
        commit(
          "app/SET_SNACKBAR",
          {
            text: "Depot not deleted. Reason: Related data cannot be deleted",
            color: "red",
          },
          { root: true }
        );
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
};

export default {
  namespaced: true,
  state,
  getters,
  actions,
  mutations,
};
