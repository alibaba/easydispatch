import LocationApi from "@/location/api";

import { getField, updateField } from "vuex-map-fields";
import { debounce } from "lodash";

const getDefaultSelectedState = () => {
  return {
    id: null,
    location_code: null,
    geo_longitude: null,
    geo_latitude: null,
    geo_address_text: null,
    geo_json: null
  };
};

const state = {
  selected: {
    ...getDefaultSelectedState()
  },
  dialogs: {
    showCreateEdit: false,
    showRemove: false
  },
  table: {
    rows: {
      items: [],
      total: null
    },
    options: {
      q: "",
      page: 1,
      itemsPerPage: 10,
      sortBy: ["view_order"],
      descending: [false]
    },
    loading: false
  }
};

const getters = {
  getField
};

const actions = {
  getAll: debounce(({ commit, state }) => {
    commit("SET_TABLE_LOADING", true);
    return LocationApi.getAll(state.table.options)
      .then(response => {
        commit("SET_TABLE_LOADING", false);
        commit("SET_TABLE_ROWS", response.data);
      })
      .catch(() => {
        commit("SET_TABLE_LOADING", false);
      });
  }, 200),
  createEditShow({ commit }, location) {
    commit("SET_DIALOG_CREATE_EDIT", true);
    if (location) {
      commit("SET_SELECTED", location);
    }
  },
  removeShow({ commit }, location) {
    commit("SET_DIALOG_DELETE", true);
    commit("SET_SELECTED", location);
  },
  closeCreateEdit({ commit }) {
    commit("SET_DIALOG_CREATE_EDIT", false);
    commit("RESET_SELECTED");
  },
  closeRemove({ commit }) {
    commit("SET_DIALOG_DELETE", false);
    commit("RESET_SELECTED");
  },
  save({ commit, state, dispatch }) {
    if (!state.selected.id) {
      return LocationApi.create(state.selected)
        .then(() => {
          dispatch("closeCreateEdit");
          dispatch("getAll");
          commit(
            "app/SET_SNACKBAR",
            { text: "Location created successfully." },
            { root: true }
          );
        })
        .catch(err => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "Location not created. Reason: " + err.response.data.detail,
              color: "red"
            },
            { root: true }
          );
        });
    } else {
      return LocationApi.update(state.selected.id, state.selected)
        .then(() => {
          dispatch("closeCreateEdit");
          dispatch("getAll");
          commit(
            "app/SET_SNACKBAR",
            { text: "Location updated successfully." },
            { root: true }
          );
        })
        .catch(err => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "Location not updated. Reason: " + err.response.data.detail,
              color: "red"
            },
            { root: true }
          );
        });
    }
  },
  remove({ commit, dispatch }) {
    return LocationApi.delete(state.selected.id)
      .then(function() {
        dispatch("closeRemove");
        dispatch("getAll");
        commit(
          "app/SET_SNACKBAR",
          { text: "Location deleted successfully." },
          { root: true }
        );
      })
      .catch(err => {
        commit(
          "app/SET_SNACKBAR",
          {
            text: "Location not deleted. Reason: " + err.response.data.detail,
            color: "red"
          },
          { root: true }
        );
      });
  }
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
  }
};

export default {
  namespaced: true,
  state,
  getters,
  actions,
  mutations
};
