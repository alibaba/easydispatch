
<template >
  <v-layout row wrap style="z-index: 0">
    <v-flex>
      <v-layout column class="myJobMap">
        <l-map ref="myJobMap" :zoom="zoom" :center="latLongCenter">
          <!-- jobs -->
          <l-marker
            v-for="marker in all_jobs"
            :key="marker.location_code_from"
            :lat-lng.sync="marker.position_from"
            :visible="marker.visible_from"
            @click="onchange_route([marker.position_from,marker.position_to,marker.tooltip])"
            :icon="fromIcon"
          >
            <l-tooltip :content="marker.tooltip" />
          </l-marker>
          <l-control :position="'topright'" class="legend-custom-control">
            <template>
              <v-card flat style="width:120px; height:50px">
                <v-card-text style="padding:0">
                  <v-row class="d-flex justify-space-around mb-5">
                    <v-col cols="12" sm="5" md="5">
                      <v-checkbox
                        v-model="selected_marker"
                        label="start"
                        color="indigo"
                        value="start"
                        hide-details
                        style="margin:0;"
                        @change="onchange_checkbox('start')"
                      >
                        <template v-slot:label>
                          <v-icon color="#1EB300" dense>{{job_icon}}</v-icon>
                        </template>
                      </v-checkbox>
                    </v-col>

                    <v-col cols="12" sm="5" md="5" style="margin-right:20px">
                      <v-checkbox
                        v-model="selected_marker"
                        label="heat_layer_job"
                        color="indigo"
                        value="heat_layer_job"
                        hide-details
                        style="margin:0; "
                        @change="onchange_checkbox('heat_layer_job')"
                      >
                        <template v-slot:label>
                          <v-icon color="#00ABDC" dense>fa-cloud</v-icon>
                        </template>
                      </v-checkbox>
                    </v-col>
                  </v-row>
                </v-card-text>
              </v-card>
            </template>
          </l-control>
          <l-tile-layer :url="osmUrl" :attribution="attribution" />
        </l-map>
      </v-layout>
    </v-flex>
  </v-layout>
</template>
<script>
// https://stackoverflow.com/questions/42816517/cant-load-leaflet-inside-vue-component/56114797
// height: 200px; width: 300px
import { mapFields } from "vuex-map-fields";
import { mapActions, mapState, mapMutations } from "vuex";
// https://juejin.im/post/5cc192976fb9a032092e8e0a#heading-1
import {
  LMap,
  LTileLayer,
  LMarker,
  LControl,
  LIcon,
  LPopup,
  LTooltip,
} from "vue2-leaflet";
import "leaflet/dist/leaflet.css";
// import Vue2LeafletCanvas from "@skinnyjames/vue2-leaflet-canvas";

import "beautifymarker/leaflet-beautify-marker-icon.js";
import "beautifymarker/leaflet-beautify-marker-icon.css";
import LheatLayer from "../live_map/leaflet.heat.js";

export default {
  name: "JobMpa",

  components: {
    LMap,
    LTileLayer,
    LMarker,
    LControl,
    LIcon,
    LPopup,
    LTooltip,
    L,
  },

  destroyed() {},
  data() {
    return {
      map: null,
      heatLayer_job: null,
      zoom: 12,
      // osmUrl: "http://{s}.tile.osm.org/{z}/{x}/{y}.png",
      osmUrl: "http://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      attribution:
        '&copy; <a href="http://osm.org/copyright">OpenStreetMap</a>',
      plannerFilters_windowDates: [],
      plannerFilters_team: null,
      fromIcon: L.BeautifyIcon.icon({
        icon: "user",
        iconShape: "marker",
        iconSize: [21, 21],
        innerIconAnchor: [0, 1],
      }),
      cfg_job: {
        radius: 25,
        minOpacity: 0.3,
        maxOpacity: 0.9,
        gradient: { 0.4: "#7FFD26", 0.65: "#FFF51D", 1: "#FFF51D" },
      },
    };
  },
  // https://cn.vuejs.org/v2/guide/components-edge-cases.html
  mounted() {
    if (this.userInfo.default_team_id) {
      if (this.code) {
        this.get_live_map_job({
          team_id: this.userInfo.default_team_id,
          worker_code: this.code,
        });
      }

      this.init_icon(this.userInfo.default_team_id);
      this.map = this.$refs.myJobMap.mapObject;
    }
  },

  computed: {
    ...mapFields("worker", [
      "selected.code",
      "selected_point.latLongCenter",
      "selected_marker",
      "selected_point.all_jobs",
    ]),
    ...mapState("auth", ["userInfo"]),
    ...mapFields("team", ["worker_icon", "job_icon"]),
  },
  methods: {
    ...mapActions("worker", ["get_live_map_job", "onchange_route"]),
    ...mapActions("team", ["init_icon"]),

    ...mapMutations("worker", ["SET_SELECTED_VISIBLE"]),
    onchange_checkbox: function (type) {
      let flag = false;
      if (this.selected_marker.indexOf(type) >= 0) {
        flag = true;
      }
      this.SET_SELECTED_VISIBLE({ type: type, flag: flag });

      if (type == "heat_layer_job" && flag) {
        this.delete_heatLayer("job");
        this.add_heatLayer(this.all_jobs, "job");
      } else if (type == "heat_layer_job" && !flag) {
        this.delete_heatLayer("job");
      }
    },
    delete_heatLayer(type) {
      const mapObject = this.$refs.myJobMap.mapObject;
      if (type == "job" && this.heatLayer_job) {
        mapObject.removeControl(this.heatLayer_job);
        this.heatLayer_job = null;
      }
    },
    add_heatLayer(newVal, type) {
      const mapObject = this.$refs.myJobMap.mapObject;
      try {
        if (type == "job") {
          let workerHotMapData = Object.values(newVal).reduce(
            (pre, cur, index) => {
              return [
                ...pre,
                [cur["position_from"]["lat"], cur["position_from"]["lng"], 0.3],
              ];
            },
            []
          );
          this.heatLayer_job = new LHeatLayer(workerHotMapData, this.cfg_job);
          this.heatLayer_job.addTo(mapObject);
        }
      } catch (e) {
        console.error(e);
      }
    },
  },
  watch: {
    code: function (newVal, oldVal) {
      if (newVal) {
        this.get_live_map_job({
          team_id: this.userInfo.default_team_id,
          worker_code: newVal,
        });
      }
    },
    all_jobs: function (newVal, oldVal) {
      try {
        this.delete_heatLayer("job");
        this.add_heatLayer(newVal, "job");
      } catch (e) {
        console.error(e);
      }
    },
    job_icon: function (newVal, oldVal) {
      try {
        console.log("job_icon:" + newVal);
        this.fromIcon = L.BeautifyIcon.icon({
          icon: newVal.replace("fa-", ""),
          iconShape: "marker",
          iconSize: [21, 21],
          innerIconAnchor: [0, 1],
        });
      } catch (e) {
        console.error(e);
      }
    },
    latLongCenter: function (newValue, oldValue) {
      this.map.setView(newValue, 13);
    },
  },
};
</script>
<style>
.leaflet-routing-container {
  opacity: 0.8;
}
.container {
  max-width: 2000px !important;
  margin: 0;
}
.myJobMap {
  height: calc(100vh - 190px);
  width: 100%;
  margin-top: 8px !important;
}
.icon_btn {
  width: 30px;
  height: 30px !important;
  border-bottom-left-radius: 2px;
  border-bottom-right-radius: 2px;
  line-height: 30px;
  color: #1976d2;
}
.leaflet-pane {
  z-index: 0 !important;
}
.leaflet-top,
.leaflet-bottom {
  z-index: 0 !important;
}
</style>

<style>
@import "https://maxcdn.bootstrapcdn.com/font-awesome/4.5.0/css/font-awesome.min.css";
@import "https://fonts.googleapis.com/icon?family=Material+Icons";
</style>