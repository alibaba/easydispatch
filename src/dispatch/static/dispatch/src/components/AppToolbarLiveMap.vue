<template>
  <v-app-bar clipped-left clipped-right class="ma-0 pa-0" app color="white" height="70">
    <v-card class="ma-0" min-width="130" max-width="130" height="55">
      <v-tooltip bottom>
        <template v-slot:activator="{ on, attrs }">
          <v-card-title v-bind="attrs" v-on="on">
            <v-icon size="30px" color="indigo" class="mr-3">mdi-finance</v-icon>
            <div>
              <span class="font-weight-black" v-text="plannerScoresStats.score"></span>
            </div>
          </v-card-title>
        </template>
      </v-tooltip>
    </v-card>

    <v-card class="ma-1 pa-1" min-width="300" max-width="600" height="55" d-xs-none>
      <p class="text--primary">
        taxi: {{ taxi }} ,
        orders:{{ orders }} ,
        total_travel_minutes:{{ plannerScoresStats.total_travel_minutes }}
      </p>
    </v-card>
    <v-card class="ma-1 pa-1" min-width="300" max-width="600" height="55" d-xs-none>
      <p class="text--primary">select msg: {{ name }}</p>
    </v-card>
    <v-spacer />

    <v-btn icon @click="closeScoreShowFlag()">
      <v-icon>mdi-close</v-icon>
    </v-btn>
  </v-app-bar>
</template>
<script>
// class="ml-2 pl-3"   extended extension-height="40"
// color="ruleOverallStatusStyle[getResultByScore(singleJobDropCheckResult.messages[ind].score)].color"

import { mapActions, mapMutations } from "vuex";
//import { mapGetters } from "vuex"

import { mapFields } from "vuex-map-fields";
import Util from "@/util";
export default {
  name: "AppToolbarLiveMap",
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
        Warning: { icon: "mdi-information-outline", color: "yellow" },
        Error: { icon: "info", color: "red" },
      },
    };
  },
  computed: {
    ...mapFields("live_map", [
      "kpi.plannerScoresStats",
      "kpi.taxi",
      "kpi.orders",
      "kpi.company",
      "selected.msg.name",
    ]),
  },
  methods: {
    closeScoreShowFlag() {
      this.SET_COMPANY_SHOWFLAG(false);
    },
    ...mapMutations("live_map", ["SET_COMPANY_SHOWFLAG"]),
  },
};
</script>

<style lang="stylus" scoped></style>
