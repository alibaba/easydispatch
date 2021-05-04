<template>
  <v-app-bar
    clipped-left
    clipped-right
    class="ma-0 pa-0"
    app
    color="white"
    height="75"
  >
    <v-card class="ma-0" max-width="200" max-height="60">
      <v-list-item class="ma-0" dense>
        <v-list-item-content>
          <v-list-item-title>
            <v-icon small>mdi-account-multiple</v-icon> Team:
            {{ localFilterTeamEmail }}
          </v-list-item-title>
          <v-list-item-title>
            <v-icon small>mdi-calendar</v-icon>
            Env: {{ plannerScoresStats.planning_window }}
          </v-list-item-title>
        </v-list-item-content>
      </v-list-item>
    </v-card>
    <v-card class="ml-1 pr-1" width="210" max-height="60">
      <v-tooltip bottom>
        <template v-slot:activator="{ on, attrs }">
          <v-card-title v-bind="attrs" v-on="on">
            <v-icon size="30px" color="indigo" class="mr-3">mdi-finance</v-icon>
            Score:
            <div>
              <span
                class="font-weight-black"
                v-text="plannerScoresStats.score"
              ></span>
            </div>
          </v-card-title>
        </template>
        <span>
          score = ( onsite_working_minutes / (total_travel_minutes +
          onsite_working_minutes) ) + (inplanning_job_count /
          (inplanning_job_count + unplanned_job_count)) -
          (total_overtime_minutes/onsite_working_minutes)</span
        >
      </v-tooltip>
    </v-card>

    <v-card class="ma-1  pa-1" width="550" max-height="60">
      <p class="text--primary">
        Travel Minutes: {{ plannerScoresStats.total_travel_minutes }}, Onsite
        Working Minutes:{{ plannerScoresStats.onsite_working_minutes }},
        Inplanning Count: {{ plannerScoresStats.inplanning_job_count }},
        Unplanned Count:{{ plannerScoresStats.unplanned_job_count }}, Overtime
        Minutes: {{ plannerScoresStats.total_overtime_minutes }}
      </p>
    </v-card>

    <v-spacer />
    <v-progress-circular
      v-if="plannerScoresAPICallInProgressFlag"
      indeterminate
      color="primary"
    ></v-progress-circular>

    <v-btn icon @click="closePlannerScoreShowFlag()">
      <v-icon>mdi-close</v-icon>
    </v-btn>
  </v-app-bar>
</template>
<script>
// class="ml-2 pl-3"   extended extension-height="40"
// color="ruleOverallStatusStyle[getResultByScore(singleJobDropCheckResult.messages[ind].score)].color"

import { mapActions, mapMutations } from "vuex";
//import { mapGetters } from "vuex"

import { mapState } from "vuex";
import Util from "@/util";
export default {
  name: "AppToolbarHealthCheck",
  data() {
    return {
      ruleIcons: {
        "Within Working Hour": "mdi-av-timer",
        "Enough Travel": "mdi-train-car",
        "Lunch Break": "mdi-food",
        "Requested Skills": "mdi-tools",
        "DateTime Tolerance": "mdi-ray-start-end",
        "Retain Tech": "mdi-pin",
        "Shared Visit": "mdi-calendar-multiple",
        "Permanent Pair": "mdi-account-multiple-check"
      },
      ruleOverallStatusStyle: {
        OK: { icon: "mdi-checkbox-marked-circle", color: "green" },
        Warning: { icon: "mdi-information-outline", color: "yellow" },
        Error: { icon: "info", color: "red" }
      }
    };
  },
  computed: {
    ...mapState("gantt", [
      "plannerScoresAPICallInProgressFlag",
      "plannerFilters",
      "plannerScoresStats"
    ]),
    ...mapState("auth", ["userInfo"]),
    toolbarColor() {
      return "primary"; // this.$vuetify.options.extra.mainNav
    },

    localFilterDate: {
      get() {
        if (this.plannerFilters.start_day) {
          return `${this.plannerFilters.start_day.substring(
            4,
            8
          )} ~ ${this.plannerFilters.end_day.substring(4, 8)}`;
        } else {
          return `N/A`;
        }
      }
    },
    localFilterTeamEmail: {
      get() {
        if (this.plannerFilters.team) {
          return `${this.plannerFilters.team.code}`;
        } else {
          return `N/A`;
        }
      }
    },

    queryString: {
      set(query) {
        this.$store.dispatch("search/setQuery", query);
      },
      get() {
        return this.$store.state.query;
      }
    }
  },
  methods: {
    getResultByScore(score) {
      if (score == 1) {
        return "OK";
      } else if (score == -1) {
        return "Error";
      } else {
        return "Warning";
      }
    },
    closePlannerScoreShowFlag() {
      this.$store.commit("gantt/SET_PLANNER_SCORE_SHOW_FLAG", false);
    },
    handleDrawerToggle() {
      this.$store.dispatch("app/toggleDrawer");
    },
    handleFullScreen() {
      Util.toggleFullScreen();
    },
    performSearch() {
      this.$store.dispatch("search/getResults", this.$store.state.query);
      this.$router.push("/search");
    },

    ...mapActions("auth", ["logout"]),
    ...mapActions("search", ["setQuery"]),
    ...mapMutations("search", ["SET_QUERY"]),
    ...mapActions("gantt", ["commitChangedJobs"]),
    ...mapMutations("gantt", ["SET_JOB_HEALTH_CHECK_RESULT_SHOW_FLAG"])
  }
};
</script>

<style lang="stylus" scoped></style>
