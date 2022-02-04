import { getField, updateField } from "vuex-map-fields";
import DashboardApi from "@/live_map/api";
import GanttApi from "@/gantt/api";
const getDefaultSelectedState = () => {
  return {
    latLongWayPoints: [],
    latLongCenter: [25.1648032, 55.4165595],
    msg: {
      name: "",
    },
  };
};
const state = {
  serviceUrl: "http://router.project-osrm.org/route/v1",
  dispatch_car: {
    dispatch_car_model_visible: false,
    car_list: [
      { car_number: "PFQ5217", address_to: "area3" },
      { car_number: "PFQ5217", address_to: "area2" },
      { car_number: "SBP1818T", address_to: "area1" },
    ],
  },
  job_address_flag: true,
  company_show_flag: false,
  taxi_kpi_show_flag: false,
  selected_marker: [
    "taix",
    "pick",
    "drop",
    "heat_layer_worker",
    "heat_layer_job",
  ],
  select_mark_worker: null,
  selected: {
    ...getDefaultSelectedState(),
  },
  pick_drop_list: [],
  kpi: {
    company: {
      call_answer_rate: {
        color: "green",
        value: "99.5%",
      },
      passenger_waiting_lt_5min: {
        color: "green",
        value: "80%",
      },
      passenger_waiting_min5_min10: {
        color: "green",
        value: "20%",
      },
      passenger_waiting_gt_10min: {
        color: "green",
        value: "0%",
      },
      taxi_on_road: {
        color: "green",
        value: "85%",
      },
      hourly_jobs_received: {
        color: "green",
        value: 243,
      },
      no_shows: {
        color: "orange",
        value: 28,
      },
      mtd_jobs_completed: {
        color: "green",
        value: 1530,
      },
      accident: {
        color: "orange",
        value: 2,
      },
      complaint: {
        color: "red",
        value: 12,
      },
    },
    taxi_kpi: {
      total_duration: {
        color: "green",
        value: 100,
      },
      jobs_number: {
        color: "green",
        value: 5,
      },
      late_delivery: {
        color: "green",
        value: 0,
      },
    },
    taxi: 0,
    orders: 0,
    plannerScoresStats: {
      score: 1,
      total_travel_minutes: 1,
      inplanning_job_count: 2,
      unplanned_job_count: 3,
      onsite_working_minutes: 6,
      planning_window: "NA",
    },
  },
};

const getters = {
  getField,
};
const getRandomArbitrary = (min, max) => {
  return Math.floor(Math.random() * (max - min) + min);
};
const actions = {
  dispatch_car({ commit }, options) {
    let dispatch_car_data = {};
    dispatch_car_data.dispatch_car_model_visible = options;
    if (!options) {
      dispatch_car_data.car_list = [];
    } else {
      dispatch_car_data.car_list = [
        {
          car_number: "PF" + getRandomArbitrary(1002, 5002),
          address_to: "area" + getRandomArbitrary(1, 8),
        },
        {
          car_number: "PFQ" + getRandomArbitrary(1002, 5002),
          address_to: "area" + getRandomArbitrary(1, 8),
        },
        {
          car_number: "SBPT" + getRandomArbitrary(1002, 5002) + "T",
          address_to: "area" + getRandomArbitrary(1, 8),
        },
      ];
    }

    commit("SET_DISPATCH_CAT", dispatch_car_data);
  },
  select_car({ commit }, msg) {
    if (msg) {
      commit("SET_SELECTED_TAXI_KPI", msg);
      commit("SET_TAIX_SHOWFLAG", true);
      commit("SET_COMPANY_SHOWFLAG", false);
    }
  },
  get_job_pick_drop({ commit, state }, options) {
    return DashboardApi.get_job_pick_drop(options).then((response) => {
      const data_list = response.data.job_data_list;
      const job_address_flag = response.data.job_address_flag;

      commit("SET_JOBS_ADDRESS_FLAG", job_address_flag);
      commit("SET_PICK_DORP_JOBS", data_list);
      commit("SET_CENTER", data_list[0]);
    });
  },
  get_score_state({ commit, state }, filterOptions) {
    return GanttApi.getPlannerScoreStats(filterOptions).then((response) => {
      commit("SET_SCORE_STATE", response.data);
    });
  },
};

const mutations = {
  updateField,
  SET_ROUTE(state, worker) {
    let route_point = Object.values(worker.jobs).reduce((pre, cur, index) => {
      return [...pre, cur.position];
    }, []);
    state.selected.latLongWayPoints = [worker.position, ...route_point];
    state.selected.msg.name = worker.code;
    state.selected.latLongCenter = worker.position;
  },
  SET_ALL_WORKWE(state, value) {
    state.all_worker = value;
    state.kpi.taxi = value.length;
  },
  SET_ALL_JOBS(state, value) {
    state.all_jobs = value;
    state.kpi.orders = value.length;
  },
  SET_SCORE_STATE(state, value) {
    state.kpi.plannerScoresStats = value;
  },
  SET_COMPANY_SHOWFLAG(state, value) {
    state.company_show_flag = value;
  },
  SET_TAIX_SHOWFLAG(state, value) {
    state.taxi_kpi_show_flag = value;
  },
  SET_SELECTED_MSG(state, value) {
    state.selected.msg.name = value;
  },
  SET_CENTER(state, worker) {
    state.selected.latLongCenter = worker.position;
  },
  SET_SELECTED_VISIBLE(state, options) {
    const type = options.type;
    const value = options.flag;

    if (type == "taix") {
      state.pick_drop_list.forEach((item) => {
        item.visible = value;
      });
    } else {
      state.pick_drop_list.forEach((item_worker) => {
        item_worker.jobs.forEach((item) => {
          if (item.type == type) {
            item.visible = value;
          }
        });
      });
    }
  },
  SET_SELECTED_TAXI_KPI(state, value) {
    state.kpi.taxi_kpi = value;
  },
  SET_DISPATCH_CAT(state, value) {
    state.dispatch_car = value;
  },
  SET_JOBS_ADDRESS_FLAG(state, value) {
    state.job_address_flag = value;
  },
  SET_PICK_DORP_JOBS(state, value) {
    state.pick_drop_list = value;
  },
  SET_SERVICE_URL(state, value) {
    state.serviceUrl = value;
  },
  SET_SELECT_MARK_WORKER(state, value) {
    state.select_mark_worker = value;
  },
};

export default {
  namespaced: true,
  state,
  getters,
  actions,
  mutations,
};
