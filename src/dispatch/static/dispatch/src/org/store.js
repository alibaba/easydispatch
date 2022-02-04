import OrgApi from "@/org/api";

import { getField, updateField } from "vuex-map-fields";
import { debounce } from "lodash";

const getDefaultSelectedState = () => {
  return {
    id: null,
    code: null,
    callback_url: null,
    team_flex_form_schema: {},
    worker_flex_form_schema: {},
    job_flex_form_schema: {},
    max_nbr_workers: 0,
    max_nbr_teams: 0,
    max_nbr_jobs: 0,
    worker_count: 0,
    team_count: 0,
    job_count: 0,
    zulip_is_active: false,
    zulip_site: "",
    zulip_user_name: "",
    zulip_password: "",
    created_at: null,
    updated_at: null,
    loading: false,
  };
};
const state = {
  selected: {
    ...getDefaultSelectedState(),
  },
  register_code: "",
  dialogs: {
    showRemove: false,
    showCreateEdit: false,
  },
};

const getters = {
  getField,
};

const actions = {
  showCreateEditDialog({ commit }) {
    commit("SET_DIALOG_CREATE_EDIT", true);
  },
  closeCreateEditDialog({ commit }) {
    commit("SET_DIALOG_CREATE_EDIT", false);
    commit("SET_REGISTER_CODE", "");
  },
  getOrg: debounce(({ commit, state }) => {
    return OrgApi.getAll().then((response) => {
      commit("SET_SELECTED", response.data);
    });
  }, 200),
  removeShow({ commit, state }) {
    commit("SET_DIALOG_DELETE", true);
  },
  closeRemove({ commit }) {
    commit("SET_DIALOG_DELETE", false);
  },
  addUserOrg({ commit }, param) {
    if (param) {
      return OrgApi.add_user_org(param)
        .then((response) => {
          commit("SET_REGISTER_CODE", response.data["register_code"]);
          commit(
            "app/SET_SNACKBAR",
            { text: "register code created successfully." },
            { root: true }
          );
        })
        .catch((err) => {
          commit(
            "app/SET_SNACKBAR",
            {
              text:
                "addUserOrg error. Reason: " +
                JSON.stringify(err.response.data.detail),
              color: "red",
            },
            { root: true }
          );
        });
    }
  },
  save({ commit, dispatch }) {
    if (!state.selected.id) {
      return OrgApi.create(state.selected)
        .then(() => {
          dispatch("getOrg");
          commit(
            "app/SET_SNACKBAR",
            { text: "Org created successfully." },
            { root: true }
          );
        })
        .catch((err) => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "Org not created. Reason: " + err.response.data.detail,
              color: "red",
            },
            { root: true }
          );
        });
    } else {
      return OrgApi.update(state.selected.id, state.selected)
        .then(() => {
          dispatch("getOrg");
          commit(
            "app/SET_SNACKBAR",
            { text: "Organization setting is updated successfully." },
            { root: true }
          );
        })
        .catch((err) => {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "Update Failed. Reason: " + err.response.statusText,
              color: "red",
            },
            { root: true }
          );
        });
    }
  },
  remove({ commit, dispatch }) {
    return OrgApi.delete(state.selected.id)
      .then(function() {
        dispatch("closeRemove");
        commit("RESET_SELECTED");
        commit(
          "app/SET_SNACKBAR",
          { text: "org deleted successfully." },
          { root: true }
        );
      })
      .catch((err) => {
        commit(
          "app/SET_SNACKBAR",
          {
            text:
              "Org not deleted. Reason: Related data cannot be deleted" + err,
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
  SET_DIALOG_DELETE(state, value) {
    state.dialogs.showRemove = value;
  },
  RESET_SELECTED(state) {
    state.selected = Object.assign(state.selected, getDefaultSelectedState());
  },
  SET_DIALOG_CREATE_EDIT(state, value) {
    state.dialogs.showCreateEdit = value;
  },
  SET_REGISTER_CODE(state, value) {
    state.register_code = value;
  },
};

export default {
  namespaced: true,
  state,
  getters,
  actions,
  mutations,
};
