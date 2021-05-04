<template>
  <v-app id="dispatch">
    <!--<loading />-->
    <app-toolbar v-if="noPlannerShowing" />
    <app-toolbar-planner-score v-if="plannerScoresShowFlag" />
    <app-toolbar-health-check v-if="plannerHealthCheckResultShowFlag" />
    <app-drawer />
    <snackbar />
    <refresh />
    <v-content>
      <!-- Page Header -->
      <page-header />
      <div class="page-wrapper">
        <v-container pa-4 grid-list-lg>
          <router-view />
        </v-container>
      </div>
      <!-- App Footer -->
      <v-footer height="auto" class="pa-3 app--footer">
        <span class="caption"
          >Kandbox Planner &copy; {{ new Date().getFullYear() }}</span
        >
        <v-spacer />
        <span class="caption mr-1">Dispatching by AI</span>
        <v-icon color="pink" small>favorite</v-icon>
      </v-footer>
    </v-content>
    <!-- Go to top -->
  </v-app>
</template>

<script>
import AppDrawer from "@/components/AppDrawer";
import AppToolbar from "@/components/AppToolbar";
import AppToolbarHealthCheck from "@/components/AppToolbarHealthCheck";
import AppToolbarPlannerScore from "@/components/AppToolbarPlannerScore";

import PageHeader from "@/components/PageHeader";
import Snackbar from "@/components/Snackbar.vue";
import Refresh from "@/components/Refresh.vue";
import { mapActions } from "vuex";
import { mapState } from "vuex";

export default {
  components: {
    AppDrawer,
    AppToolbar,
    AppToolbarHealthCheck,
    AppToolbarPlannerScore,
    PageHeader,
    Snackbar,
    Refresh
  },

  created() {
    this.$vuetify.theme.light = true;
    this.getUserInfo();
  },
  computed: {
    ...mapState("gantt", [
      "plannerHealthCheckResultShowFlag",
      "plannerScoresShowFlag"
    ]),
    noPlannerShowing: function() {
      return (
        !this.plannerHealthCheckResultShowFlag && !this.plannerScoresShowFlag
      );
    }
  },

  methods: {
    ...mapActions("auth", ["getUserInfo"])
  }
};
</script>

<style scoped>
.page-wrapper {
  min-height: calc(100vh - 64px - 50px - 81px);
}
</style>
