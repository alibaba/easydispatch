<template>
  <v-dialog v-model="dialogFilterVisible" max-width="600px">
    <v-card>
      <v-card-title>
        <span class="headline">Filters</span>
        <v-spacer></v-spacer>
        <v-btn text color="primary" @click="setDialogFilterVisible(false)">Cancel</v-btn>
        <v-btn text color="primary" @click="fetchData">OK</v-btn>
      </v-card-title>
      <v-list dense>
        <v-list-item>
          <v-list-item-content>
            <team-select v-model="plannerFilters_team" />
          </v-list-item-content>
        </v-list-item>
        <v-list-item>
          <v-list-item-content>
            <v-menu
              ref="menu"
              v-model="menu"
              :close-on-content-click="false"
              :return-value.sync="plannerFilters_windowDates"
              transition="scale-transition"
              offset-y
              max-width="290px"
              min-width="190px"
            >
              <template v-slot:activator="{ on, attrs }">
                <v-text-field
                  v-model="dateRangeText"
                  label="Start and end date for selecting jobs in the planner Env"
                  prepend-icon="event"
                  readonly
                  v-bind="attrs"
                  v-on="on"
                ></v-text-field>
              </template>
              <v-date-picker
                v-model="plannerFilters_windowDates"
                type="date"
                :allowed-dates="allowedDates"
                range
              >
                <v-spacer></v-spacer>
                <v-btn text color="primary" @click="menu = false">Cancel</v-btn>
                <v-btn text color="primary" @click="$refs.menu.save(plannerFilters_windowDates)">OK</v-btn>
              </v-date-picker>
            </v-menu>
          </v-list-item-content>
        </v-list-item>
        <v-list-item>
          <v-list-item-content>
            <v-switch v-model="forceReloadFlag" class="mx-4" label="force reload" disabled></v-switch>
          </v-list-item-content>
        </v-list-item>
      </v-list>
    </v-card>
  </v-dialog>
</template>

<script>
//import GanttApi from "@/gantt/api"

import { map, sum } from "lodash";
import { mapState, mapActions } from "vuex";

// import WorkerCombobox from "@/worker/WorkerCombobox.vue"
//import TagFilterCombobox from "@/tag/TagFilterCombobox.vue"
//import JobTypeCombobox from "@/job_type/JobTypeCombobox.vue"
//import JobPriorityCombobox from "@/job_priority/JobPriorityCombobox.vue"
import TeamSelect from "@/team/TeamSelect.vue";
import { parseISO } from "date-fns"; // addDays,
import { mapFields } from "vuex-map-fields";
//var _that = this
import TeamApi from "@/team/api";

export default {
  name: "DialogFilterGantt",

  methods: {
    ...mapActions("gantt", [
      "getPlannerWorkerJobDataset",
      "getPlannerScoreStats",
    ]),
    setDialogFilterVisible(visibleFlag) {
      this.$store.commit("gantt/SET_DIALOG_FILTER_VISIBLE", visibleFlag);
    },
    addDays(date, days) {
      var result = new Date(date);
      result.setDate(result.getDate() + days);
      return result;
    },
    allowedDates(val) {
      // return parseInt(val.split("-")[2], 10) % 2 === 0
      if (
        val >= this.plannerWindowMinMax[0] &&
        val <= this.plannerWindowMinMax[1]
      ) {
        return true;
      }
      return false;
    },

    fetchData() {
      let filterOptions = {};

      filterOptions = {
        team: { id: 2 },
        start_day: "20200901",
        end_day: "20200902",
      };
      filterOptions.start_day = this.plannerFilters_windowDates[0]
        .replace("-", "")
        .replace("-", "");
      filterOptions.end_day = this.plannerFilters_windowDates[1]
        .replace("-", "")
        .replace("-", "");
      if (this.plannerFilters_team) {
        //filterOptions.team_id = this.plannerFilters_team.id
        filterOptions.team = this.plannerFilters_team;
      } else {
        this.$store.commit(
          "app/SET_SNACKBAR",
          {
            text: "Please choose a Team.",
            color: "red",
          },
          { root: true }
        );
        return false;
      }
      this.$store.commit("gantt/SET_PLANNER_FILTERS", filterOptions);

      this.getPlannerWorkerJobDataset(filterOptions);

      this.getPlannerScoreStats(filterOptions);
    },
    getPlannerWindowDateFromTeam(team) {
      let d = team.flex_form_data.env_start_day;
      let startDateInTeam =
        d.substr(0, 4) + "-" + d.substr(4, 2) + "-" + d.substr(6, 2);
      let endDateInTeam = this.addDays(
        startDateInTeam,
        parseInt(team.flex_form_data.nbr_of_days_planning_window)
      )
        .toISOString()
        .substr(0, 10);
      return [startDateInTeam, endDateInTeam];
    },
  },

  components: {
    // WorkerCombobox,
    // TagFilterCombobox,
    // JobTypeCombobox,
    TeamSelect,
  },
  mounted() {
    this.plannerFilters_windowDates = [this.defaultStart, this.defaultEnd];
    let that = this;
    if (this.userInfo.default_team_id) {
      console.log("dialog mounted, then I am changing default_team_id");
      TeamApi.get(this.userInfo.default_team_id) //
        .then((response) => {
          that.plannerFilters_team = response.data;

          that.plannerFilters_windowDates = that.getPlannerWindowDateFromTeam(
            that.plannerFilters_team
          );
          that.plannerWindowMinMax = that.plannerFilters_windowDates;

          that.fetchData();

          console.log(
            "loaded default team info",
            that.userInfo.default_team_id
          );
        })
        .catch(() => {
          console.log("Failed to load default team");
        });
    } else {
      console.log(
        "dialog mounted but team is not loaded because userInfo has no default_team_id!"
      );
    }
  },
  data() {
    return {
      menu: false,
      plannerWindowMinMax: ["2021-04-27", "2021-05-07"],
      plannerFilters_windowDates: [],
      plannerFilters_team: null,
      forceReloadFlag: false,
      filters: {
        // team: null,
        tag: [],
        job_type: [],
        job_priority: [],
      },
    };
  },

  created: function () {
    // this.plannerFilters_windowDates = this.defaultDates
    // this.fetchData()
  },

  watch: {
    plannerFilters_team(newTeam) {
      if (newTeam) {
        console.log(`plannerFilters_team is changed to ${newTeam.code}`);
        try {
          this.plannerFilters_windowDates =
            this.getPlannerWindowDateFromTeam(newTeam);
        } catch (err) {
          this.$store.commit(
            "app/SET_SNACKBAR",
            {
              text: "This team has no valid plannign window. Please choose a different one.",
            },
            { root: true }
          );
        }
      }
    },
    forceReloadFlag: function (newValue) {
      this.$store.commit("gantt/SET_PLANNER_FILTERS", {
        forceReloadFlag: newValue,
      });
    },
  },

  computed: {
    ...mapFields("gantt", ["dialogs.dialogFilterVisible"]),
    ...mapState("auth", ["userInfo"]),

    numFilters: function () {
      return sum([
        this.filters.job_type.length,
        this.filters.job_priority.length,
        this.filters.tag.length,
      ]);
    },
    queryDates() {
      // adjust for same month
      return map(this.dates, function (item) {
        return parseISO(item).toISOString();
      });
    },
    today() {
      let now = new Date();
      return new Date(now.getFullYear(), now.getMonth(), now.getDate());
    },
    defaultStart() {
      return this.today.toISOString().substr(0, 10);
    },
    defaultEnd() {
      return this.addDays(this.today, 6).toISOString().substr(0, 10);
    },
    dateRangeText() {
      return this.plannerFilters_windowDates.join(" ~ ");
    },
  },
};
</script>
