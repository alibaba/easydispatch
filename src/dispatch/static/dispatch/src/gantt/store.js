import GanttApi from "@/gantt/api";

import { getField, updateField } from "vuex-map-fields";
import { debounce, forEach } from "lodash";
import addMinutes from "date-fns/addMinutes";

const getDefaultSelectedState = () => {
  return {
    latLongRouteArray: null,
    recommendationedActions: [],
    job: null,
    selectedJobIndex: 0
  };
};

const state = {
  selected: {
    ...getDefaultSelectedState()
  },
  planned_jobs_data_last_upate_date_string: "N/A",
  dialogs: {
    dialogFilterVisible: false,
    dialogMapRouteVisible: false,
    dialogActionWithRecommendationVisible: false
  },
  envTableLoading: false,
  autoCommitFlag: false,
  chartDraggable: false,
  chartClickShowMapFlag: false,
  //fromLatLong: null,
  //toLatLong: null,
  global_loaded_data: {
    //global_loaded_data_TODEL: {
    workers_dimensions: [
      "index",
      "skills",
      "max_conflict_level",
      "worker_code",
      "geo_longitude",
      "geo_latitude",
      "weekly_working_minutes"
    ],
    workers_data: [],
    jobs_dimensions: [
      "scheduled_worker_index",
      "scheduled_start_datetime",
      "scheduled_end_datetime",
      "job_code",
      "job_schedule_type",
      "scheduled_travel_minutes_before",
      "scheduled_travel_prev_code",
      "conflict_level",
      "scheduled_primary_worker_id",
      "geo_longitude",
      "geo_latitude",
      "changed_flag"
    ],
    planned_jobs_data: [],
    all_jobs_in_env: [],
    start_time: "2020-06-16T00:00:00",
    end_time: "2020-06-18T00:00:00"
  },
  chartClickBehaviour: "show_job", //drag_n_drop
  global_job_dict: {},
  global_worker_dict: {},
  // changedJobFlag: false,
  plannerScoresAPICallInProgressFlag: false,
  plannerScoresShowFlag: false,
  plannerScoresStats: {
    score: 1,
    total_travel_minutes: 1,
    inplanning_job_count: 2,
    unplanned_job_count: 3,
    onsite_working_minutes: 6,
    planning_window: "NA"
  },
  plannerHealthCheckResultShowFlag: false,
  singleJobCheckAPICallInProgressFlag: false,
  singleJobDropCheckShowFlag: false,
  singleJobDropCheckOptions: null,
  singleJobDropCheckResult: {
    //result: "NA",
    //score: "1",
    status_code: "Error",
    score: "0.5",
    travel_time: 30,
    messages: [
      {
        score_type: "Within Working Hour",
        score: 1,
        message: [
          {
            score: 1,
            message: ["Job is between start and end time of the worker"]
          }
        ]
      }
    ]
  },
  // global_planner_game_list: {},
  globalRecommendedSlotsData: {},
  selectedWorkerList: ["duanorg_Duan", "duanorg_Harry"],
  plannerFilters: {
    team: { id: 2 },
    windowDates: ["2020-10-13", "2020-10-14"],
    forceReloadFlag: false
  },
  INDEX_CONFIG: {
    POS_JOB_INDEX_worker_index: 0,
    POS_JOB_INDEX_start_datetime: 1,
    POS_JOB_INDEX_end_datetime: 2,
    POS_JOB_INDEX_job_code: 3 + 0,
    POS_JOB_INDEX_job_type: 4 + 0,
    POS_JOB_INDEX_travel_minutes_before: 5 + 0,
    POS_JOB_INDEX_travel_prev_code: 6 + 0,
    POS_JOB_INDEX_conflict_level: 7 + 0,
    POS_JOB_INDEX_worker_code: 8,
    POS_JOB_INDEX_geo_longitude: 9 + 0,
    POS_JOB_INDEX_geo_latitude: 10 + 0,
    POS_JOB_INDEX_changed_flag: 11 + 0,
    POS_JOB_INDEX_prev_geo_longitude: 12 + 0,
    POS_JOB_INDEX_prev_geo_latitude: 13 + 0,
    POS_JOB_INDEX_prev_location_type: 14 + 0,
    POS_WORKER_INDEX_worker_index: 0,
    POS_WORKER_INDEX_worker_code: 3,
    POS_WORKER_INDEX_skills: 1 + 0,
    POS_WORKER_INDEX_max_conflict_level: 2 + 0,
    POS_WORKER_INDEX_geo_longitude: 4 + 0,
    POS_WORKER_INDEX_geo_latitude: 5 + 0,
    POS_WORKER_INDEX_weekly_working_minutes: 6 + 0,
    POS_WORKER_INDEX_selected: 7,

    POS_WORKING_TIME_INDEX_worker_index: 0,
    POS_WORKING_TIME_INDEX_start_ms: 1 + 0,
    POS_WORKING_TIME_INDEX_end_ms: 2 + 0,
    HEIGHT_RATIO: 0.6
  }
  /*
  draggbleConfig: {
    draggable: false,
    draggingEl: null,
    dropShadow: null,
    draggingCursorOffset: [0, 0],
    draggingTimeLength: null,
    draggingRecord: null,
    dropRecord: null,
    cartesianXBounds: [],
    cartesianYBounds: [],
    single_job_drop_check_ajay_lock: false
  }
  */
};

const getters = {
  getField,
  getPlannerFilters: state => () => {
    // original getter body
    return {
      team_id: state.plannerFilters.team.id, //3,
      start_day: state.plannerFilters.start_day, //state.plannerFilters.windowDates[0].replace("-", "").replace("-", ""), //"TODO",
      end_day: state.plannerFilters.end_day, //state.plannerFilters.windowDates[1].replace("-", "").replace("-", "")
      force_reload: state.plannerFilters.forceReloadFlag
    };
  }, //(state) {

  getSingleJobDropCheckOptions(state) {
    if (!state.singleJobDropCheckOptions) {
      return {};
    }
    return state.singleJobDropCheckOptions;
  }
};

const actions = {
  getPlannerWorkerJobDataset: debounce(({ commit, getters }) => {
    commit("SET_TABLE_LOADING", true);
    let plannerFilters_ = getters.getPlannerFilters();

    return GanttApi.getPlannerWorkerJobDataset(plannerFilters_)
      .then(response => {
        commit("SET_TABLE_LOADING", false);
        commit("SET_ENV_LOADED_DATA", response.data);
        //TODO
        // commit("SET_JOB_HEALTH_CHECK_RESULT_SHOW_FLAG", true)

        commit("SET_DIALOG_FILTER_VISIBLE", false);
      })
      .catch(err => {
        commit("SET_TABLE_LOADING", false);
        commit(
          "app/SET_SNACKBAR",
          {
            text:
              `Failed to load workers and jobs. Reason: ` +
              JSON.stringify(err.response.data),
            color: "red"
          },
          { root: true }
        );
      });
  }, 100),

  getPlannerScoreStats: debounce(({ commit, getters }) => {
    // commit("SET_TABLE_LOADING", true)
    let plannerFilters_ = getters.getPlannerFilters();

    return GanttApi.getPlannerScoreStats(plannerFilters_)
      .then(response => {
        // commit("SET_TABLE_LOADING", false)
        commit("SET_PLANNER_SCORE_STATS", response.data);
        commit("SET_PLANNER_SCORE_SHOW_FLAG", true);

        commit("SET_DIALOG_FILTER_VISIBLE", false);
      })
      .catch(err => {
        // commit("SET_TABLE_LOADING", false)
        commit(
          "app/SET_SNACKBAR",
          {
            text:
              `Failed to load score statistics. Reason: ` +
              JSON.stringify(err.response.data),
            color: "red"
          },
          { root: true }
        );
      });
  }, 1000),

  doSingleJobDropCheck: debounce(
    ({ commit, dispatch, getters }, jobActionOptions) => {
      //

      commit("SET_SINGLE_JOB_DROP_CHECK_OPTIONS", jobActionOptions);
      commit("SET_SINGLE_JOB_CHECK_API_CALL_IN_PROGRESS_FLAG", true);

      commit("MUTATE_JOB_STATUS_BY_CURRENT_ACTION");

      if (state.autoCommitFlag) {
        console.log(
          "state.autoCommitFlag=True, auto committing job, commitChangedJobs"
        );
        dispatch("commitChangedJobs");
      }

      return GanttApi.doSingleJobDropCheck(getters.getSingleJobDropCheckOptions)
        .then(response => {
          commit("SET_SINGLE_JOB_CHECK_API_CALL_IN_PROGRESS_FLAG", false);
          commit("SET_SINGLE_JOB_CHECK_RESULT", response.data);
        })
        .catch(err => {
          commit("SET_SINGLE_JOB_CHECK_API_CALL_IN_PROGRESS_FLAG", false);
          commit(
            "app/SET_SNACKBAR",
            {
              text:
                `Failed to check rules for job ${jobActionOptions.job_code} . Reason: ` +
                JSON.stringify(err.response.data.detail),
              color: "red"
            },
            { root: true }
          );
        });
    },
    200
  ),

  /* setPlannerFilters___({ commit }, data) {},
  autoCommitFirstRecommendation({ commit, getters }, job) {
    //2020-10-09 13:12:05
  },*/

  showActionWithRecommendation({ commit, dispatch, getters }, job) {
    if (job) {
      commit("SET_SELECTED", { job: job });
    }
    commit("SET_SINGLE_JOB_CHECK_API_CALL_IN_PROGRESS_FLAG", true);

    let jobActionOptions = { ...getters.getPlannerFilters() };
    jobActionOptions.job_code = job.job_code;

    GanttApi.getRecommendedSlots(jobActionOptions)
      .then(response => {
        let recommendedSlots = response.data.recommendations;
        if (recommendedSlots.length < 1) {
          commit(
            "app/SET_SNACKBAR",
            {
              text: "Failed to get recommendations, maybe all occupied",
              color: "red"
            },
            { root: true }
          );
        }
        commit("SET_SELECTED", { recommendationedActions: recommendedSlots });
        if (state.autoCommitFlag) {
          console.log("state.autoCommitFlag", state.autoCommitFlag);

          jobActionOptions.scheduled_start_datetime =
            recommendedSlots[0].scheduled_start_datetime;
          jobActionOptions.scheduled_duration_minutes =
            recommendedSlots[0].scheduled_duration_minutes;

          let wCodes = recommendedSlots[0].scheduled_worker_codes;
          jobActionOptions.scheduled_primary_worker_id = wCodes[0];
          jobActionOptions.scheduled_secondary_worker_ids = wCodes.slice(
            1,
            wCodes.length
          );

          dispatch("setConfirmedJobActionAndCheck", jobActionOptions);
        } else {
          commit("SET_DIALOG_Action_With_Recommendation_Visible", true);
        }

        commit("SET_SINGLE_JOB_CHECK_API_CALL_IN_PROGRESS_FLAG", false);
      })
      .catch(err => {
        commit("SET_SINGLE_JOB_CHECK_API_CALL_IN_PROGRESS_FLAG", false);
        commit(
          "app/SET_SNACKBAR",
          {
            text:
              "Failed to get recommendations. Reason: " +
              err.response.data.detail,
            color: "red"
          },
          { root: true }
        );
      });
  },

  setConfirmedJobActionAndCheck({ commit, dispatch }, jobActionOptions) {
    // commit("SET_SINGLE_JOB_DROP_CHECK_OPTIONS", jobActionOptions)

    commit("SET_DIALOG_Action_With_Recommendation_Visible", false);
    commit("SET_DIALOG_SHOW_MAP_ROUTE", false);

    dispatch("doSingleJobDropCheck", jobActionOptions);
  },
  showDialogMapRoute({ commit }, latLongRouteArray) {
    if (latLongRouteArray) {
      commit("SET_SELECTED_LAT_LONG", latLongRouteArray);
    }
    commit("SET_DIALOG_SHOW_MAP_ROUTE", true);
  },
  closeDialogMapRoute({ commit }) {
    commit("SET_DIALOG_SHOW_MAP_ROUTE", false);
    commit("RESET_SELECTED");
  },
  closeRemove({ commit }) {
    commit("SET_DIALOG_DELETE", false);
    commit("RESET_SELECTED");
  },
  commitSingleJob({ commit, dispatch }, jobActionOptions) {
    GanttApi.commitJobAction(jobActionOptions)
      .then(response => {
        console.log(response.data);
        if (response.data.errorNumber != 0) {
          commit(
            "app/SET_SNACKBAR",
            {
              text:
                "Failed to commit the change, please check rules and try again. \nMessage: " +
                JSON.stringify(response.data),
              color: "red",
              timeout: -1,
              top: true
            },
            { root: true }
          );
        } else {
          commit("COMMIT_CHANGED_JOB_FLAG", jobActionOptions.job_code);
          commit(
            "app/SET_SNACKBAR",
            {
              text: `Job (${jobActionOptions.job_code}) is committed successfully.`
            },
            { root: true }
          );
          dispatch("getPlannerWorkerJobDataset");
        }
      })
      .catch(err => {
        commit(
          "app/SET_SNACKBAR",
          {
            text:
              `Failed to commit job (${jobActionOptions.job_code}), please retry or reload_env / start over. \nReason: ` +
              err.response.data.detail,
            color: "red"
          },
          { root: true }
        );
      });
  },
  commitChangedJobs({ getters, dispatch }) {
    /*
    if (!state.changedJobFlag) {
      commit("app/SET_SNACKBAR", { text: "No changed jobs to commit." }, { root: true })
      return
    }
    */
    let plannerFilters_ = getters.getPlannerFilters();

    //let changedJobList = []

    forEach(state.global_loaded_data.all_jobs_in_env, function(value) {
      if (value.changed_flag == 1) {
        let newJob = { ...value };
        newJob = Object.assign(newJob, plannerFilters_);
        dispatch("commitSingleJob", newJob);
      }
    });
    // do manual reload . 2021-02-24 08:55:16 moved to .then of commit api.
    // dispatch("getPlannerWorkerJobDataset")
  }
};

const mutations = {
  updateField,
  SET_DIALOG_SHOW_MAP_ROUTE(state, value) {
    state.dialogs.dialogMapRouteVisible = value;
  },
  SET_DIALOG_FILTER_VISIBLE(state, value) {
    state.dialogs.dialogFilterVisible = value;
  },

  SET_SELECTED_LAT_LONG(state, value) {
    state.selected.latLongRouteArray = value;
  },

  SET_SELECTED(state, value) {
    state.selected = Object.assign(state.selected, value);
  },

  SET_SINGLE_JOB_DROP_CHECK_OPTIONS(state, value) {
    state.singleJobDropCheckOptions = { ...value };
    let plannerFilters = state.plannerFilters;
    state.singleJobDropCheckOptions = Object.assign(
      state.singleJobDropCheckOptions,
      {
        team_id: plannerFilters.team.id, //3,
        start_day: plannerFilters.start_day,
        end_day: plannerFilters.end_day
      }
    );
  },
  SET_PLANNER_FILTERS(state, value) {
    state.plannerFilters = Object.assign(state.plannerFilters, value);
  },
  SET_ENV_LOADED_DATA(state, value) {
    state.global_loaded_data = null;
    state.global_loaded_data = value;
    state.global_worker_dict = null;
    state.global_worker_dict = {};
    state.global_loaded_data.workers_data.forEach(element => {
      state.global_worker_dict[
        element[state.INDEX_CONFIG.POS_WORKER_INDEX_worker_code]
      ] = element[state.INDEX_CONFIG.POS_WORKER_INDEX_worker_index];
    });
  },
  SET_PLANNER_SCORE_STATS(state, value) {
    state.plannerScoresStats = value;
  },

  SET_PLANNER_SCORE_SHOW_FLAG(state, value) {
    state.plannerScoresShowFlag = value;
  },

  SET_JOB_HEALTH_CHECK_RESULT_SHOW_FLAG(state, value) {
    state.plannerHealthCheckResultShowFlag = value;
  },
  SET_SINGLE_JOB_CHECK_RESULT(state, value) {
    state.singleJobDropCheckResult = value;
    state.singleJobDropCheckShowFlag = true;
  },
  SET_SINGLE_JOB_CHECK_API_CALL_IN_PROGRESS_FLAG(state, value) {
    state.singleJobCheckAPICallInProgressFlag = value;
  },
  RESET_SINGLE_JOB_CHECK(state) {
    state.singleJobDropCheckOptions = {};
    state.singleJobDropCheckResult = {};
    state.singleJobDropCheckShowFlag = false;
  },
  SET_TABLE_LOADING(state, value) {
    state.envTableLoading = value;
    //state.singleJobCheckAPICallInProgressFlag = value
  },
  SET_TABLE_ROWS(state, value) {
    state.table.rows = value;
  },
  SET_DIALOG_CREATE_EDIT(state, value) {
    state.dialogs.showCreateEdit = value;
  },
  SET_DIALOG_Action_With_Recommendation_Visible(state, value) {
    state.dialogs.dialogActionWithRecommendationVisible = value;
  },
  /*
  SET_CHANGED_JOB_FLAG(state, value) {
    state.changedJobFlag = value
  },
*/
  SET_DIALOG_DELETE(state, value) {
    state.dialogs.showRemove = value;
  },
  RESET_SELECTED(state) {
    state.selected = getDefaultSelectedState();
  },
  COMMIT_CHANGED_JOB_FLAG(state, job_code) {
    //TODO PERFORMANCE PROBLEM  , if scaned everytime
    for (
      var ii = 0;
      ii < state.global_loaded_data.all_jobs_in_env.length;
      ii++
    ) {
      // Does this cookie string begin with the name we want?
      if (state.global_loaded_data.all_jobs_in_env[ii].job_code == job_code) {
        state.global_loaded_data.all_jobs_in_env[ii].changed_flag = 0;
      }
    }
    //TODO PERFORMANCE PROBLEM  , if scaned everytime
    for (ii = 0; ii < state.global_loaded_data.planned_jobs_data.length; ii++) {
      // Does this cookie string begin with the name we want?
      //       console.log(
      //         ii,
      //         state.global_loaded_data.planned_jobs_data[ii][state.INDEX_CONFIG.POS_JOB_INDEX_job_code],
      //         job_code
      //       )
      if (
        state.global_loaded_data.planned_jobs_data[ii][
          state.INDEX_CONFIG.POS_JOB_INDEX_job_code
        ] == job_code
      ) {
        state.global_loaded_data.planned_jobs_data[ii][
          state.INDEX_CONFIG.POS_JOB_INDEX_changed_flag
        ] = 0;
      }
    }
  },

  MUTATE_JOB_STATUS_BY_CURRENT_ACTION(state) {
    // console.log('selected.')

    if (!state.selected.job) {
      console.log("error, I lost my job. :( ");
      return;
    }
    if (!state.singleJobDropCheckOptions) {
      console.log("error, no state.singleJobDropCheckOptions :( ");
      return;
    }

    let selectedJob = state.selected.job;
    let jobActionOptions = state.singleJobDropCheckOptions;

    selectedJob.scheduled_start_datetime =
      jobActionOptions.scheduled_start_datetime;
    selectedJob.scheduled_duration_minutes =
      jobActionOptions.scheduled_duration_minutes;
    //todo
    selectedJob.scheduled_primary_worker_id =
      jobActionOptions.scheduled_primary_worker_id;
    // selectedJob.scheduled_secondary_worker_ids = jobActionOptions.scheduled_secondary_worker_ids
    selectedJob.scheduled_worker_codes = [
      jobActionOptions.scheduled_primary_worker_id
    ].concat(jobActionOptions.scheduled_secondary_worker_ids);

    selectedJob["changed_flag"] = 1;
    // state.changedJobFlag = true

    if (selectedJob.planning_status == "I") {
      //remove current job from planned array, for both I->I, and I->U. Otherwise it leave redundant traces on chart. 2020-10-01 13:53:15
      for (
        var iii = 0;
        iii < state.global_loaded_data.planned_jobs_data.length;
        iii++
      ) {
        if (
          state.global_loaded_data.planned_jobs_data[iii][
            state.INDEX_CONFIG.POS_JOB_INDEX_job_code
          ] == selectedJob.job_code
        ) {
          state.global_loaded_data.planned_jobs_data.splice(iii, 1);
          state.global_job_dict[selectedJob.job_code].job_index_in_planned = 0;
          //no break, since there may be multiple entries in array for a single job.
        }
      }

      if (jobActionOptions.planning_status == "U") {
        selectedJob["planning_status"] = "U";
        // I will not add it back if it is U.
        return;
      }
    }
    if (selectedJob.planning_status == "U") {
      if (jobActionOptions.planning_status == "U") {
        //remove from array
        console.log("error, U --> U makes no sense :(");
        return;
      }
    }
    // ~Now U --> I, or I --> I (already delted), I add job from env_all_list to planned array
    // TODO, shared multiple jobs.
    selectedJob.planning_status = "I";
    // Check conflict  flightData.length
    var w_index = 0;
    var workerCode = null;
    var newJobCode = null;
    var newJobUnplanned2Inplanning = null;
    var jobType = null;
    for (; w_index < selectedJob.scheduled_worker_codes.length; w_index++) {
      workerCode = selectedJob.scheduled_worker_codes[w_index];
      if (workerCode == selectedJob.scheduled_primary_worker_id) {
        //This is the primary job, job code reamins same
        newJobCode = selectedJob.job_code;
        jobType = "I_1_2_3_4_N";
        if (selectedJob.scheduled_worker_codes.length > 1) {
          jobType = "I_1_2_3_4_P";
        }
      } else {
        newJobCode = selectedJob.job_code + "_S_" + workerCode;
        jobType = "I_1_2_3_4_S";
        state.global_job_dict[newJobCode] = {
          data_latlng: state.global_job_dict[selectedJob.job_code].data_latlng,
          job_index_in_all:
            state.global_job_dict[selectedJob.job_code].job_index_in_all,
          job_index_in_planned: -1
        };
      }

      newJobUnplanned2Inplanning = [
        state.global_worker_dict[workerCode],
        new Date(selectedJob["scheduled_start_datetime"]).getTime(),
        addMinutes(
          new Date(selectedJob["scheduled_start_datetime"]),
          selectedJob["scheduled_duration_minutes"]
        ).getTime(),
        newJobCode,
        jobType,
        10, // POS_JOB_INDEX_travel_minutes_before: 5 + 0,
        "__HOME", // POS_JOB_INDEX_travel_prev_code: 6 + 0,
        0, // POS_JOB_INDEX_conflict_level: 7 + 0,
        workerCode, // POS_JOB_INDEX_worker_code: 8,
        selectedJob["geo_longitude"], // POS_JOB_INDEX_geo_longitude: 9 + 0,
        selectedJob["geo_latitude"], // POS_JOB_INDEX_geo_latitude: 10 + 0,
        1 // POS_JOB_INDEX_changed_flag: 11 + 0,
      ];
      console.log("I will add job to chart: ", newJobUnplanned2Inplanning);

      state.global_job_dict[newJobCode].job_index_in_planned =
        state.global_loaded_data.planned_jobs_data.length;

      state.global_loaded_data.planned_jobs_data.push(
        newJobUnplanned2Inplanning
      );
    }

    let selectedJobEnvIndex =
      state.global_job_dict[selectedJob.job_code].job_index_in_all;
    state.global_loaded_data.all_jobs_in_env[
      selectedJobEnvIndex
    ] = Object.assign(
      state.global_loaded_data.all_jobs_in_env[selectedJobEnvIndex],
      selectedJob
    );

    state.planned_jobs_data_last_upate_date_string = new Date().toISOString();

    //selectedJob["planning_status"] = "I"

    //todo travel time
    //
    //"scheduled_travel_minutes_before": j["scheduled_travel_minutes_before"],
    //"scheduled_travel_prev_code": j["scheduled_travel_prev_code"],
  }
};

export default {
  namespaced: true,
  state,
  getters,
  actions,
  mutations
};
