<template>
  <v-app-bar clipped-left clipped-right app color="primary" dark height="70">
    <CreateRegister />
    <v-app-bar-nav-icon @click="handleDrawerToggle" />
    <router-link :to="{ path: '/gantt' }" style="text-decoration: none">
      <span class="button font-weight-bold title ml-3 mr-5" style="color:#FFFFFF;">EasyDispatch</span>
    </router-link>
    <!-- <v-text-field
      v-model="queryString"
      flat
      hide-details
      solo-inverted
      prepend-inner-icon="search"
      label="Search"
      clearable
      class="search"
      @keyup.enter="performSearch()"
    />-->

    <v-spacer />
    <v-toolbar-items>
      <v-tooltip bottom>
        <template v-slot:activator="{ on }">
          <v-btn icon v-on="on" @click="handleFullScreen()">
            <v-icon>mdi-fullscreen</v-icon>
          </v-btn>
        </template>
        <span>Fullscreen</span>
      </v-tooltip>
      <v-menu bottom left transition="scale-transition" origin="top right">
        <template v-slot:activator="{ on }">
          <v-btn icon large text v-on="on">
            <v-avatar size="30px">
              <img
                v-if="userInfo && userInfo.thumbnail_photo_url"
                :src="userInfo.thumbnail_photo_url"
                :alt="userInfo.full_name"
              />
              <v-icon v-else>account_circle</v-icon>
            </v-avatar>
          </v-btn>
        </template>
        <v-card width="400">
          <v-list>
            <v-list-item class="px-2">
              <v-list-item-avatar>
                <v-icon size="30px">account_circle</v-icon>
              </v-list-item-avatar>
              <v-list-item-content>
                <v-list-item-title
                  class="title"
                  v-text="userInfo&&userInfo.email?userInfo.email:'NAN'"
                ></v-list-item-title>
                <v-list-item-subtitle>{{ userInfo&& userInfo.role?userInfo.role:"NAN" }}</v-list-item-subtitle>
              </v-list-item-content>
              <v-list-item-action>
                <v-tooltip bottom>
                  <template v-slot:activator="{ on }">
                    <v-btn icon v-on="on" @click="logout()">
                      <v-icon>logout</v-icon>
                    </v-btn>
                  </template>
                  <span>Logout</span>
                </v-tooltip>
              </v-list-item-action>
            </v-list-item>
            <v-divider></v-divider>
            <!-- <v-subheader>Organizations</v-subheader> -->
            <v-list-item>
              <v-divider vertical></v-divider>
              <v-list-item-content>
                <v-list-item-title>Default Team:</v-list-item-title>
                <v-list-item-subtitle>{{ defaultTeam ? defaultTeam.code : "NAN" }}</v-list-item-subtitle>
              </v-list-item-content>
              <v-divider vertical></v-divider>
              <v-list-item-content>
                <v-list-item-title>ORG Owner</v-list-item-title>
                <v-list-item-subtitle>{{userInfo? userInfo.is_org_owner:"NAN" }}</v-list-item-subtitle>
              </v-list-item-content>
              <v-divider vertical></v-divider>
              <v-list-item-content>
                <v-list-item-title>Team Owner</v-list-item-title>
                <v-list-item-subtitle>{{ userInfo?userInfo.is_team_owner:"NAN" }}</v-list-item-subtitle>
              </v-list-item-content>
              <!-- <v-list-item-action>
                <v-tooltip bottom>
                  <template v-slot:activator="{ on }">
                    <v-btn icon v-on="on" @click="showCreateEditDialog(item)">
                      <v-icon>mdi-pencil-outline</v-icon>
                    </v-btn>
                  </template>
                  <span>Edit Organization</span>
                </v-tooltip>
              </v-list-item-action>
              <v-list-item-action>
                <v-tooltip bottom>
                  <template v-slot:activator="{ on }">
                    <v-btn @click="switchOrganizations(item.slug)" icon v-on="on">
                      <v-icon>mdi-swap-horizontal</v-icon>
                    </v-btn>
                  </template>
                  <span>Switch Organization</span>
                </v-tooltip>
              </v-list-item-action>-->
            </v-list-item>
            <v-divider></v-divider>
          </v-list>
          <v-list-item
            v-show=" userInfo && userInfo.role=='Owner' "
            @click="showCreateEditDialog()"
            :disabled="!userInfo || userInfo.role!='Owner' "
          >
            <v-list-item-avatar>
              <v-icon size="30px">mdi-plus</v-icon>
            </v-list-item-avatar>
            <v-list-item-content>
              <v-list-item-title>Create Invitation Code</v-list-item-title>
            </v-list-item-content>
          </v-list-item>
        </v-card>
      </v-menu>
    </v-toolbar-items>
  </v-app-bar>
</template>
<script>
//

import { mapActions, mapMutations } from "vuex";
import { mapFields } from "vuex-map-fields";

import CreateRegister from "@/org/CreateRegister.vue";
import { mapState } from "vuex";

import Util from "@/util";
export default {
  name: "AppToolbar",
  data() {
    return {};
  },
  components: {
    CreateRegister,
  },
  computed: {
    ...mapState("gantt", ["plannerHealthCheckResultShowFlag"]),
    ...mapState("auth", ["userInfo", "defaultTeam"]),
    toolbarColor() {
      return "primary"; // this.$vuetify.options.extra.mainNav
    },
    queryString: {
      set(query) {
        this.$store.dispatch("search/setQuery", query);
      },
      get() {
        return this.$store.state.query;
      },
    },
    ...mapFields("org", ["selected.code"]),
  },
  methods: {
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
    ...mapMutations("gantt", ["SET_JOB_HEALTH_CHECK_RESULT_SHOW_FLAG"]),
    ...mapActions("org", ["showCreateEditDialog"]),
  },
};
</script>

<style lang="stylus" scoped>
.theme--light.v-divider {
  border-color: rgba(0, 0, 0, 0) !important;
}
</style>
