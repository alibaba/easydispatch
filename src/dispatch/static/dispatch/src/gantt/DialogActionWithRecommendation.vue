<template>
  <v-dialog
    v-model="dialogActionWithRecommendationVisible"
    max-width="800px"
    v-if="selected.job !== null"
  >
    <v-card>
      <v-card-title>
        <span class="headline">Job: {{ selected.job.job_code }}</span>
        <v-spacer></v-spacer>
        <v-btn text color="warning" @click="createUnplanJobAction()"
          >Unplan</v-btn
        >
        <v-btn
          text
          color="secondary"
          @click="closeDialogActionWithRecommendation()"
          >Cancel</v-btn
        >
        <v-btn text color="primary" @click="checkCurrentJobAction()">OK</v-btn>
      </v-card-title>

      <v-container grid-list-md>
        <v-layout wrap>
          <v-flex xs4 lg4>
            <v-text-field
              v-model="selected.job.requested_primary_worker_id"
              prepend-icon="mdi-account"
              label="Requested Worker"
              disabled
            />
          </v-flex>

          <v-flex xs3 lg3>
            <v-text-field
              v-model="selected.job.requested_duration_minutes"
              label="Requested Duration (Minutes)"
              type="number"
              hint="Enter an value indicating number of Minutes, i.e. 120 for 2 hours."
              disabled
            />
          </v-flex>

          <v-flex xs5 lg5>
            <v-text-field
              v-model="selected.job.requested_start_datetime"
              label="Requested Start Time"
              hint="Start date"
              disabled
            />
          </v-flex>

          <v-flex xs6 lg6>
            <WorkerCombo
              prepend-icon="mdi-account"
              v-model="scheduled_workers"
              label="Scheduled Workers"
              clearable
            />
          </v-flex>

          <v-flex xs6 lg6>
            <v-text-field
              v-model="scheduled_duration_minutes"
              type="number"
              prepend-icon="account"
              label="Scheduled Duration Minutes"
              clearable
            />
          </v-flex>

          <v-flex xs12>
            <v-row>
              <v-col cols="6">
                <date-picker-menu
                  v-model="scheduled_start_datetime"
                ></date-picker-menu>
              </v-col>
              <v-col cols="6">
                <time-picker-menu
                  v-model="scheduled_start_datetime"
                ></time-picker-menu>
              </v-col>
            </v-row>
          </v-flex>

          <v-flex xs12 lg12>
            <v-layout column>
              <v-flex>
                <v-card>
                  <v-data-table
                    :headers="headers"
                    :items="selected.recommendationedActions"
                    :loading="loading"
                    loading-text="Loading... Please wait"
                  >
                    <template v-slot:item.scheduled_start_datetime="{ item }">{{
                      item.scheduled_start_datetime | formatHHMM
                    }}</template>
                    <template v-slot:item.data-table-actions="{ item }">
                      <v-btn @click="selectAction(item)">
                        <v-icon>
                          mdi-check
                        </v-icon>
                        Choose
                      </v-btn>
                    </template>
                  </v-data-table>
                </v-card>
              </v-flex>
            </v-layout>
          </v-flex>
        </v-layout>
      </v-container>
    </v-card>
  </v-dialog>
</template>

<script>
import { forEach } from "lodash";
// import GanttApi from "@/gantt/api"
import { mapGetters } from "vuex";
import { mapState, mapActions, mapMutations } from "vuex";
import { mapFields } from "vuex-map-fields";
import DatePickerMenu from "@/components/DatePickerMenu.vue";
import TimePickerMenu from "@/components/TimePickerMenu.vue";

import WorkerCombo from "@/worker/WorkerCombobox.vue"; // ee-eslint-disable-line no-unused-vars

//import TagFilterCombobox from "@/tag/TagFilterCombobox.vue"
//import JobTypeCombobox from "@/job_type/JobTypeCombobox.vue"
//import JobPriorityCombobox from "@/job_priority/JobPriorityCombobox.vue"
// import WorkerSelect from "@/worker/WorkerSelect.vue"
// import differenceInMinutes from 'date-fns/difference_in_minutes'

// import format from "date-fns/format"

export default {
  name: "DialogActionWithRecommendation",

  methods: {
    ...mapActions("gantt", [
      "setConfirmedJobActionAndCheck",
      "commitSingleJob"
    ]),
    ...mapMutations("gantt", ["SET_DIALOG_Action_With_Recommendation_Visible"]),

    closeDialogActionWithRecommendation() {
      this.$store.commit(
        "gantt/SET_DIALOG_Action_With_Recommendation_Visible",
        false
      );
    },
    selectAction(item) {
      this.scheduled_workers = [];
      let _that = this;
      forEach(item.scheduled_worker_codes, function(w) {
        _that.scheduled_workers.push({ code: w });
      });

      // this.scheduled_primary_worker_id = item.scheduled_worker_codes[0]
      // this.scheduled_secondary_worker_ids = item.scheduled_worker_codes.slice(
      //   1,
      //   item.scheduled_worker_codes.length
      // )

      this.scheduled_start_datetime = item.scheduled_start_datetime;
      this.scheduled_duration_minutes = item.scheduled_duration_minutes;
    },

    checkCurrentJobAction() {
      console.log("to check action  for jobCode: ", this.selected.job.job_code);

      var jobActionOptions = { ...this.getPlannerFilters };
      jobActionOptions.job_code = this.selected.job.job_code;

      jobActionOptions.scheduled_start_datetime = this.scheduled_start_datetime;
      jobActionOptions.scheduled_duration_minutes = this.scheduled_duration_minutes;
      jobActionOptions.scheduled_primary_worker_id = this.scheduled_workers[0].code;
      jobActionOptions.scheduled_secondary_worker_ids = [];
      for (let i = 1; i < this.scheduled_workers.length; i++) {
        jobActionOptions.scheduled_secondary_worker_ids.push(
          this.scheduled_workers[i].code
        );
      }

      console.log(jobActionOptions);

      this.setConfirmedJobActionAndCheck(jobActionOptions);
    },

    createUnplanJobAction() {
      console.log("to check action  for jobCode: ", this.selected.job.job_code);

      var jobActionOptions = { ...this.getPlannerFilters() };
      jobActionOptions.job_code = this.selected.job.job_code;
      jobActionOptions.planning_status = "U";

      jobActionOptions.scheduled_duration_minutes = 10;
      jobActionOptions.scheduled_start_datetime = this.selected.job.requested_start_datetime; //new Date().toISOString()

      jobActionOptions.scheduled_worker_codes = [];

      console.log(jobActionOptions);

      this.commitSingleJob(jobActionOptions);
      this.closeDialogActionWithRecommendation();
    }
  },

  components: {
    WorkerCombo,
    // TagFilterCombobox,
    // JobTypeCombobox,
    // WorkerSelect
    DatePickerMenu,
    TimePickerMenu
  },
  mounted() {
    // if (this.selected.recommendationedActions.length > 0) {
    //   this.selectAction(this.selected.recommendationedActions[0])
    // } else {
    //   this.selectAction(this.selected.job)
    // }
  },
  watch: {
    dialogActionWithRecommendationVisible: function(newValue) {
      console.log(
        `dialogActionWithRecommendationVisible, selection action auto, this.selected.recommendationedActions.length = ${this.selected.recommendationedActions.length}, newValue = ${newValue}`
      );
      // newValue means this is becoming visible
      if (newValue) {
        if (
          this.selected.recommendationedActions.length > 0 &&
          this.selected.job.planning_status == "U"
        ) {
          this.selectAction(this.selected.recommendationedActions[0]);
        } else {
          this.selectAction(this.selected.job);
        }
      }
    }
  },

  data() {
    return {
      scheduled_start_datetime: null,
      scheduled_workers: null,
      scheduled_duration_minutes: 0,
      headers: [
        { text: "score", value: "score" },
        { text: "Workers", value: "scheduled_worker_codes" },
        //{ text: "Secondary", value: "scheduled_secondary_worker_ids" },
        { text: "Scheduled Start", value: "scheduled_start_datetime" },
        { text: "Duration Minutes", value: "scheduled_duration_minutes" },
        { text: "", value: "data-table-actions", sortable: false, align: "end" }
      ],
      q: null,
      loading: false
    };
  },

  created: function() {
    // this.plannerFilters.windowDates = this.defaultDates
    // this.fetchData()
  },
  computed: {
    //...mapFields("gantt", ["plannerFilters"]),
    ...mapState("auth", ["userInfo"]),
    ...mapFields("gantt", [
      "selected",
      "plannerFilters",
      "dialogs.dialogActionWithRecommendationVisible"
    ]),
    ...mapGetters("gantt", [
      "getPlannerFilters"
      // ...
    ])
  }
};
</script>
