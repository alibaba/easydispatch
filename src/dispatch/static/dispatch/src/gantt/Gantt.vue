<template>
  <v-layout row wrap>
    <v-flex class="mb-0 pa-0 d-flex justify-end" lg1 sm4 xs6>
      <v-switch v-model="autoCommitFlag" class="mx-2" label="Auto"></v-switch>
    </v-flex>

    <v-flex class="mb-0 pa-0 d-flex justify-end" lg1 sm4 xs6>
      <v-switch
        v-model="plannerScoresShowFlag"
        class="mx-2"
        label="Score"
      ></v-switch>
    </v-flex>
    <v-flex class="mb-0 pa-0 d-flex justify-end" lg1 sm4 xs6>
      <v-switch
        v-model="plannerHealthCheckResultShowFlag"
        class="mx-2"
        label="Rules"
      ></v-switch>
    </v-flex>

    <v-spacer />
    <v-flex class="mb-0 pa-0 d-flex justify-end" lg1 sm4 xs6>
      <v-switch v-model="chartDraggable" class="mx-2" label="Drag"></v-switch>
    </v-flex>
    <v-flex class="mb-0 pa-0 d-flex justify-end" lg1 sm4 xs6>
      <v-switch
        v-model="chartClickShowMapFlag"
        class="mx-2"
        label="map"
        disabled
      ></v-switch>
    </v-flex>

    <v-flex class="mb-0 pa-0 d-flex justify-end" lg1 sm4 xs6>
      <v-switch
        v-model="forceReloadFlag"
        class="mx-2"
        label="Reload"
        disabled
      ></v-switch>
    </v-flex>
    <v-spacer />

    <v-flex class="d-flex justify-end" lg1 sm2 xs3>
      <v-btn color="primary" dark @click="setDialogFilterVisible(true)"
        >Load Data</v-btn
      >
    </v-flex>
    <dialog-filter />
    <v-flex lg12 sm12 xs12>
      <JobsTimelineChart />
    </v-flex>
    <!--
      <v-select v-model="chartClickBehaviour" :items="chartClickOptions"></v-select
    >
    @update="update" @loading="setLoading"
      Widgets Ends    :kandbox_timeline_data="global_"
      <v-flex lg12 sm12 xs12>
        <line-chart :chart-data="lineChartData___" />
      </v-flex>
      <v-flex lg12 sm12 xs12>
        <MapDirect />
      </v-flex>
      <v-flex lg12 sm12 xs12>
        <job-primary-team-bar-chart-card
          v-model="groupedItems"
          :loading="loading"
        ></job-primary-team-bar-chart-card>
      </v-flex>

      -->

    <!-- Statistics -->

    <v-flex xs12>
      <v-layout column>
        <v-flex>
          <v-card>
            <v-card-title>
              <v-text-field
                v-model="job_code_filter"
                append-icon="search"
                label="Search by job code"
                single-line
                hide-details
                clearable
              />
            </v-card-title>
            <v-data-table
              :headers="headers"
              :items="global_loaded_data.all_jobs_in_env"
              :loading="envTableLoading"
              loading-text="Loading data from backend env... Please wait"
            >
              <template v-slot:item.requested_start_datetime="{ item }">{{
                item.requested_start_datetime | formatHHMM
              }}</template>
              <template v-slot:item.scheduled_start_datetime="{ item }">{{
                item.scheduled_start_datetime | formatHHMM
              }}</template>

              <template v-slot:item.data-table-actions="{ item }">
                <v-btn @click="showActionWithRecommendation(item)">
                  <v-icon small class="mr-2"> mdi-pencil </v-icon>
                  Plan
                </v-btn>
              </template>

              <template v-slot:body.append>
                <tr>
                  <td colspan="1"></td>
                  <td colspan="2">
                    <v-select
                      v-model="job_type_filter"
                      :items="job_type_list"
                      menu-props="auto"
                      label="Type Filter"
                      clearable
                    ></v-select>
                  </td>
                  <td colspan="3">
                    <v-select
                      v-model="changed_flag_filter"
                      :items="changed_flag_filter_list"
                      menu-props="auto"
                      label="Changed Filter"
                      clearable
                    ></v-select>
                  </td>
                  <td colspan="3"></td>
                </tr>
              </template>
            </v-data-table>
          </v-card>
        </v-flex>
      </v-layout>
    </v-flex>

    <v-flex lg12 sm12 xs12>
      <DialogActionWithRecommendation />
    </v-flex>

    <v-flex lg12 sm12 xs12>
      <DialogMapRoute />
    </v-flex>

    <!-- Statistics Ends -->
  </v-layout>
</template>

<script>
//import { groupBy, sumBy } from "lodash"
//import differenceInHours from "date-fns/differenceInHours"
//import { parseISO } from "date-fns"
//import addDays from "date-fns/addDays"

import { mapFields } from "vuex-map-fields";
import { mapState } from "vuex";
import { mapActions, mapMutations } from "vuex"; //

import DialogFilter from "./DialogFilter";
import DialogActionWithRecommendation from "./DialogActionWithRecommendation";

// import JobPrimaryTeamBarChartCard from "@/job/JobPrimaryTeamBarChartCard.vue"
// import LineChart from "./LineChart"
import JobsTimelineChart from "./JobsTimelineChart.vue";
import DialogMapRoute from "./DialogMapRoute.vue";
//import MapDirect from "./MapDirect.vue"

// import TeamApi from "@/team/api"
export default {
  name: "Gantt",

  components: {
    DialogFilter,
    // JobPrimaryTeamBarChartCard,
    // LineChart,
    //MapDirect,
    JobsTimelineChart,
    DialogMapRoute,
    DialogActionWithRecommendation,
  },

  data() {
    return {
      // plannerFilters: null,
      planning_status_list: ["P", "I", "U"],
      job_type_list: ["appt", "event", "P", "U", "I", "other"],
      search: null,
      job_code_filter: null,
      job_type_filter: "U",
      status_filter: "U",
      changed_flag_filter: null,
      changed_flag_filter_list: [1, 0],
      headers: [
        {
          text: "Job Code",
          value: "job_code",
          filter: (value) => {
            if (!this.job_code_filter) return true;
            if (!value) return false;
            return value
              .toLowerCase()
              .includes(this.job_code_filter.toLowerCase());
          },
        },
        {
          text: "Type",
          value: "job_type",
          width: "20",
          filter: (value) => {
            if (!this.job_type_filter) return true;
            return value
              .toLowerCase()
              .startsWith(this.job_type_filter.toLowerCase());
            //return value == this.status_filter
          },
        },
        {
          text: "Changed",
          value: "changed_flag",
          width: "20",
          filter: (value) => {
            if (!this.changed_flag_filter) return true;
            return value == this.changed_flag_filter;
          },
        },

        {
          text: "Requested Worker",
          value: "requested_primary_worker_id",
          width: "15",
        },
        { text: "Requested Start", value: "requested_start_datetime" },
        {
          text: "Requested Minutes",
          value: "requested_duration_minutes",
          width: "12",
        },
        {
          text: "Scheduled Worker",
          value: "scheduled_worker_codes",
          width: "15",
        },
        { text: "Scheduled Start", value: "scheduled_start_datetime" },
        {
          text: "",
          value: "data-table-actions",
          sortable: false,
          align: "end",
        },
      ],
      q: null,
      tab: null,
      loading: false,
      items: [],
      // chartClickOptions: ["drag_n_drop", "check_map"],

      forceReloadFlag: false,
      lineChartData___: {
        expectedData: [100, 120, 161, 134, 105, 160, 165],
        actualData: [120, 82, 91, 154, 162, 140, 145],
      },
    };
  },

  mounted() {
    //this.plannerFilters.windowDates = [this.defaultStart(), this.defaultEnd()]
  },

  methods: {
    ...mapActions("gantt", ["showActionWithRecommendation"]),
    ...mapMutations("gantt", ["SET_PLANNER_FILTERS"]),
    defaultTeam() {},
    setDialogFilterVisible(visibleFlag) {
      this.$store.commit("gantt/SET_DIALOG_FILTER_VISIBLE", visibleFlag);
    },
    refreshChartClickBehaviour() {
      if (this.chartDraggable) {
        this.chartClickBehaviour = "drag_n_drop";
      } else {
        if (this.chartClickShowMapFlag) {
          this.chartClickBehaviour = "check_map";
        } else {
          this.chartClickBehaviour = "show_job";
        }
      }
    },
    /*
    update(data) {
      //this.global_loaded_data = data

      this.$store.commit("gantt/SET_ENV_LOADED_DATA", data)
      //TODO
      this.$store.commit("gantt/SET_JOB_HEALTH_CHECK_RESULT_SHOW_FLAG", true)
    },
    setLoading(data) {
      console.log(data)
      this.loading = data
    } */
  },
  beforeRouteLeave(to, from, next) {
    this.$store.commit("gantt/SET_JOB_HEALTH_CHECK_RESULT_SHOW_FLAG", false);
    next();
    /*
    const answer = window.confirm("Do you really want to leave? you have unsaved changes!")
    if (answer) {
      this.$store.commit("gantt/SET_JOB_HEALTH_CHECK_RESULT_SHOW_FLAG", false)
      next()
    } else {
      next(false)
    }
    */
  },
  watch: {
    chartDraggable: function() {
      this.refreshChartClickBehaviour();
    },

    chartClickShowMapFlag: function() {
      this.refreshChartClickBehaviour();
    },

    forceReloadFlag: function(newValue) {
      this.$store.commit("gantt/SET_PLANNER_FILTERS", {
        forceReloadFlag: newValue,
      });
    },
    plannerHealthCheckResultShowFlag: function(newValue) {
      this.$store.commit("gantt/SET_PLANNER_SCORE_SHOW_FLAG", !newValue);
    },
    /*
    userInfo: function() {
      if (this.userInfo.default_team_id) {
        console.log("userInfo changed, then I am changing default_team_id")
        TeamApi.get(this.userInfo.default_team_id)
          .then(response => {
            this.plannerFilters.team = response.data
            console.log("loaded default team info", this.userInfo.default_team_id)
          })
          .catch(() => {
            console.log("Failed to load default team")
          })
      } else {
        console.log("userInfo changed, but no default_team_id")
      }

      //this.fetchData()
    }*/
  },
  computed: {
    ...mapState("auth", ["userInfo"]),

    ...mapFields("gantt", [
      //"INDEX_CONFIG",
      "global_loaded_data",
      "global_job_dict",
      "chartClickBehaviour",
      "envTableLoading",
      "autoCommitFlag",
      "chartDraggable",
      "chartClickShowMapFlag",
      "plannerHealthCheckResultShowFlag",
      "plannerScoresShowFlag",
      //"plannerFilters.forceReloadFlag"
      //"plannerFilters"
    ]),
  },
};
</script>
