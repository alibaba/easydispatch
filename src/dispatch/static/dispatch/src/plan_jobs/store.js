import PlanJobsApi from "@/plan_jobs/api";
import TeamApi from "@/team/api";

import { getField, updateField } from "vuex-map-fields";
import { debounce } from "lodash";
import dayjs from "dayjs";

const state = {
  data: {
    datas: [],
    loading: false,
    team_list: [],
    team_id: null,
    rowNum: 30,
    colNum: 10,
    times: [
      dayjs()
        .add(-15, "day")
        .add(2, "hour")
        .toString(),
      dayjs()
        .subtract(5, "hour")
        .toString(),
    ],
  },
};

const getters = {
  getField,
};

const actions = {
  getTeams: debounce(({ commit, state }) => {
    return TeamApi.getAll({}).then((response) => {
      let team_select = Object.values(response.data.items).reduce(
        (pre, cur, index) => {
          return [...pre, { value: cur.id, label: cur.code }];
        },
        []
      );
      commit("SET_TEAM_SELECT", team_select);
    });
  }, 200),

  getPlanJobs: debounce(({ commit, state }) => {
    commit("SET_TABLE_LOADING", true);
    const option = {
      team_id: state.data.team_id,
      start_datatime: dayjs(state.data.times[0]).format("YYYY-MM-DD HH:mm:ss"),
      end_datatime: dayjs(state.data.times[1]).format("YYYY-MM-DD HH:mm:ss"),
    };
    return PlanJobsApi.get_planed_jobs(option).then((response) => {
      commit("SET_TABLE_LOADING", false);
      commit("SET_TABLE_ROWS", response.data);
    });
  }, 200),
};

const mutations = {
  updateField,
  SET_TABLE_LOADING(state, value) {
    state.data.loading = value;
  },
  SET_TABLE_ROWS(state, value) {
    state.data.datas = value;
  },
  SET_TEAM_SELECT(state, value) {
    state.data.team_list = value;
    if (value.length > 0) {
      state.data.team_id = value[0].value;
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
