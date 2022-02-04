<template>
  <v-app-bar
    clipped-left
    clipped-right
    class="ma-0 pa-0"
    app
    color="white"
    height="70"
    max-height="70px"
  >
    <v-card class="ma-0 pa-0" max-width="240" style="margin-right:20px !important;height:68px;">
      <v-list-item class="ma-0" dense>
        <v-list-item-content class="text-xs-caption">
          <v-list-item-title class="text-xs-caption">
            <v-icon small>mdi-home-currency-usd</v-icon>
            {{ company_show_flag ? "Company":"Worker" }} :{{company_show_flag ? "company-name":name }}
          </v-list-item-title>
          <v-list-item-subtitle class="text-xs">
            <v-icon small>mdi-account</v-icon>
            taxi count:{{taxi}}
          </v-list-item-subtitle>
          <v-list-item-subtitle>
            <v-icon small>mdi-av-timer</v-icon>
            order ount:{{orders}}
          </v-list-item-subtitle>
        </v-list-item-content>
      </v-list-item>
    </v-card>

    <!-- <v-chip-group v-if="company_show_flag" column>
      <v-tooltip bottom v-for="(val, key, index) in company" :key="index">
        <template v-slot:activator="{ on, attrs }">
          <v-chip
            small
            :color="colorMapping[val.color]"
            v-bind="attrs"
            v-on="on"
            text-color="white"
          >
            {{key}}:
            {{ val.value }}
          </v-chip>
        </template>
      </v-tooltip>
    </v-chip-group>-->

    <v-chip-group v-if="taxi_kpi_show_flag" column>
      <v-tooltip bottom v-for="(val, key, index) in taxi_kpi" :key="index">
        <template v-slot:activator="{ on, attrs }">
          <v-chip
            small
            :color="colorMapping[val.color]"
            v-bind="attrs"
            v-on="on"
            text-color="white"
          >
            <!-- <v-avatar small left>
              <v-icon small>{{ ruleIcons[res.score_type] }}</v-icon>
            </v-avatar>-->
            {{key}}:
            {{ val.value }}
          </v-chip>
        </template>
      </v-tooltip>
    </v-chip-group>
    <v-spacer />

    <v-btn icon @click="closeLiveMapInfo()">
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
import { mapFields } from "vuex-map-fields";

export default {
  name: "AppToolbarLiveMapTaixInfo",
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
        "Permanent Pair": "mdi-account-multiple-check",
      },
      ruleOverallStatusStyle: {
        OK: { icon: "mdi-checkbox-marked-circle", color: "green" },
        Warning: { icon: "mdi-information-outline", color: "rgb(255, 193, 7)" },
        Error: { icon: "mdi-close-circle", color: "red" },
      },
      colorMapping: {
        green: "green",
        red: "red",
        orange: "rgb(255, 193, 7)",
        // orange: "orange",
      },
    };
  },
  components: {},
  computed: {
    ...mapFields("live_map", [
      "company_show_flag",
      "taxi_kpi_show_flag",
      "kpi.company",
      "kpi.taxi_kpi",
      "selected.msg.name",
      "kpi.taxi",
      "kpi.orders",
    ]),
  },
  methods: {
    ...mapMutations("gantt", ["SET_PLANNER_SCORE_SHOW_FLAG"]),
    ...mapMutations("live_map", ["SET_COMPANY_SHOWFLAG", "SET_TAIX_SHOWFLAG"]),
    closeLiveMapInfo: function () {
      if (this.taxi_kpi_show_flag) {
        this.SET_TAIX_SHOWFLAG(false);
        this.SET_PLANNER_SCORE_SHOW_FLAG(true);
      } else {
        this.SET_TAIX_SHOWFLAG(false);
        this.SET_PLANNER_SCORE_SHOW_FLAG(false);
      }
    },
  },
};
</script>

<style lang="stylus" scoped></style>
