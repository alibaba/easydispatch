
<template >
  <v-layout row wrap style="z-index: 0">
    <v-flex>
      <v-layout column class="myRoutingMap">
        <l-map ref="myRoutingMap" :zoom="zoom" :center="latLongCenter">
          <l-routing-machine
            v-if="!job_address_flag"
            :waypoints="latLongWayPoints"
            :selected_marker="selected_marker"
          />
          <!-- worker -->

          <l-marker
            v-for="marker in all_worker"
            :key="marker.code"
            :lat-lng.sync="marker.position"
            :icon="marker.icon"
            :visible="marker.visible"
            @click="mark_change_worker(marker)"
            :zIndexOffset="marker.zindex"
          >
            <!-- <l-popup :content="marker.tooltip" v-if="marker.select" /> -->
            <l-tooltip :content="marker.tooltip" />
          </l-marker>
          <!-- jobs -->
          <l-marker
            v-for="marker in all_jobs"
            :key="marker.code"
            :lat-lng.sync="marker.position"
            :visible="marker.visible"
            :icon="marker.icon"
            :zIndexOffset="marker.zindex"
          >
            <l-tooltip :content="marker.tooltip" />
          </l-marker>

          <l-control :position="'topleft'" class="example-custom-control">
            <template>
              <v-btn
                tile
                color="indigo"
                class="icon_btn"
                outlined
                x-small
                @click="change_show(true,false)"
              >
                <v-icon>mdi-finance</v-icon>
              </v-btn>
              <br />
              <v-btn
                tile
                color="indigo"
                class="icon_btn"
                outlined
                x-small
                @click="dispatch_car(!dispatch_car_model_visible)"
              >
                <v-icon>mdi-flag-variant</v-icon>
              </v-btn>
            </template>
          </l-control>
          <l-control :position="'topright'" class="legend-custom-control">
            <template>
              <v-row align="center" style="max-width:335px;max-height:60px">
                <v-flex xs6>
                  <team-select v-model="select_team" label="Team" hint="The team" clearable></team-select>
                </v-flex>
                <v-flex xs6>
                  <worker-select
                    v-model="select_worker"
                    label="Worker"
                    hint="The job's current commander"
                    clearable
                    required
                  ></worker-select>
                </v-flex>
              </v-row>
              <v-card flat style="width:320px; height:50px">
                <v-card-text style="padding:0">
                  <v-row class="d-flex justify-space-around mb-6">
                    <v-col cols="10" sm="2" md="2">
                      <v-checkbox
                        v-model="selected_marker"
                        label="taix"
                        color="indigo"
                        value="taix"
                        hide-details
                        style="margin:0;"
                        @change="onchange_checkbox('taix')"
                      >
                        <template v-slot:label>
                          <v-icon color="#b3334f" dense>{{worker_icon}}</v-icon>
                        </template>
                      </v-checkbox>
                    </v-col>
                    <v-col cols="10" sm="2" md="2">
                      <v-checkbox
                        v-model="selected_marker"
                        label="pick"
                        color="indigo"
                        value="pick"
                        hide-details
                        style="margin:0;"
                        @change="onchange_checkbox('pick')"
                      >
                        <template v-slot:label>
                          <v-icon color="#1EB300" dense>{{job_icon}}</v-icon>
                        </template>
                      </v-checkbox>
                    </v-col>
                    <v-col v-if="!job_address_flag" cols="10" sm="2" md="2">
                      <v-checkbox
                        v-model="selected_marker"
                        label="drop"
                        color="indigo"
                        value="drop"
                        hide-details
                        style="margin:0;"
                        @change="onchange_checkbox('drop')"
                      >
                        <template v-slot:label>
                          <v-icon color="#00ABDC" dense>fa-user</v-icon>
                        </template>
                      </v-checkbox>
                    </v-col>

                    <v-col cols="10" sm="2" md="2">
                      <v-checkbox
                        v-model="selected_marker"
                        label="heat_layer_worker"
                        color="indigo"
                        value="heat_layer_worker"
                        hide-details
                        style="margin:0;"
                        @change="onchange_checkbox('heat_layer_worker')"
                      >
                        <template v-slot:label>
                          <v-icon color="#00ABDC" dense>mdi-card-account-details-outline</v-icon>
                        </template>
                      </v-checkbox>
                    </v-col>

                    <v-col cols="10" sm="2" md="2" style="margin-right:20px">
                      <v-checkbox
                        v-model="selected_marker"
                        label="heat_layer_job"
                        color="indigo"
                        value="heat_layer_job"
                        hide-details
                        style="margin:0;"
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
          <!-- <Vue2LeafletCanvas :locations="locations_job_from" @l-drawing="drawing"></Vue2LeafletCanvas> -->
        </l-map>
        <ModelCarInfo />
      </v-layout>
    </v-flex>
  </v-layout>
</template>
<script>
// https://stackoverflow.com/questions/42816517/cant-load-leaflet-inside-vue-component/56114797
// height: 200px; width: 300px
import { mapGetters } from "vuex";
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
import LRoutingMachine from "./LRoutingMachine";
import ModelCarInfo from "./ModelCarInfo";
// import Vue2LeafletCanvas from "@skinnyjames/vue2-leaflet-canvas";

import "beautifymarker/leaflet-beautify-marker-icon.js";
import "beautifymarker/leaflet-beautify-marker-icon.css";
import LheatLayer from "./leaflet.heat.js";
import WorkerSelect from "@/worker/WorkerSelect.vue";
import TeamSelect from "@/team/TeamSelect.vue";

export default {
  name: "LiveMap",

  components: {
    LMap,
    LTileLayer,
    LMarker,
    LRoutingMachine,
    LControl,
    LIcon,
    LPopup,
    LTooltip,
    L,
    ModelCarInfo,
    WorkerSelect,
    TeamSelect,
    // Vue2LeafletCanvas,
  },

  data() {
    return {
      select_team: null,
      select_worker: null,
      select_job_code_list: [],
      select_worker_code: null,
      new_all_job: [],
      map: null,
      locations_job_from: [],
      heatLayer: null,
      heatLayer_job: null,
      zoom: 10,
      // osmUrl: "http://{s}.tile.osm.org/{z}/{x}/{y}.png",
      osmUrl: "http://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      attribution:
        '&copy; <a href="http://osm.org/copyright">OpenStreetMap</a>',
      plannerFilters_windowDates: [],
      plannerFilters_team: null,
      worker_icon_option: {
        icon: "taxi",
        iconShape: "marker",
        borderColor: "#b3334f",
        textColor: "#b3334f",
        iconSize: [23, 23],
        innerIconAnchor: [0, 0],
      },
      worker_select_icon_option: {
        icon: "taxi",
        iconShape: "marker",
        borderColor: "pink",
        textColor: "#b3334f",
        iconSize: [32, 32],
        innerIconAnchor: [0, 8],
      },
      job_pick_select_option: {
        isAlphaNumericIcon: true,
        text: "1",
        iconSize: [28, 28],
        innerIconAnchor: [0, 2],
        iconShape: "marker",
        textColor: "black",
        borderWidth: 2,
        backgroundColor: "#72CF5F",
        innerIconStyle: "font-size:11px;padding-top:1px;",
      },
      job_drop_select_option: {
        isAlphaNumericIcon: true,
        text: "1",
        iconSize: [28, 28],
        innerIconAnchor: [0, 2],
        iconShape: "marker",
        backgroundColor: "#88D8EE",
        borderColor: "#00ABDC",
        borderWidth: 2,
        textColor: "black",
        innerIconStyle: "font-size:11px;padding-top:1px;",
      },
      job_pick_option: {
        icon: "shopping-cart",
        iconShape: "marker",
        iconSize: [21, 21],
        innerIconAnchor: [0, 1],
      },
      job_drop_option: {
        icon: "user",
        iconShape: "marker",
        borderColor: "#00ABDC",
        textColor: "#00ABDC",
        iconSize: [21, 21],
        innerIconAnchor: [0, 1],
      },
      cfg: {
        // radius should be small ONLY if scaleRadius is true (or small radius is intended)
        // if scaleRadius is false it will be the constant radius used in pixels
        radius: 25,
        minOpacity: 0.3,
        maxOpacity: 0.9,
        // max: 8,
        gradient: { 0.4: "blue", 0.65: "lime", 1: "red" },
      },
      cfg_job: {
        // radius should be small ONLY if scaleRadius is true (or small radius is intended)
        // if scaleRadius is false it will be the constant radius used in pixels
        radius: 25,
        minOpacity: 0.3,
        maxOpacity: 0.9,
        // max: 8,
        gradient: { 0.4: "#7FFD26", 0.65: "#FFF51D", 1: "#FFF51D" },
      },
    };
  },
  // https://cn.vuejs.org/v2/guide/components-edge-cases.html
  provide: function () {
    return {
      getMap: this.getMap,
    };
  },
  mounted() {
    this.getUserInfo();
    let that = this;
    if (this.userInfo.default_team_id) {
      that.map = this.$refs.myRoutingMap.mapObject;
      this.SET_PLANNER_SCORE_SHOW_FLAG(true);
      that.init_icon(this.userInfo.default_team_id);
    } else {
      console.log(
        "dialog mounted but team is not loaded because userInfo has no default_team_id!"
      );
    }

    if (this.select_mark_worker) {
      let that = this;
      setTimeout(function () {
        that.mark_change_worker(that.select_mark_worker);
      }, 200);
    }
  },
  destroyed: function () {
    this.SET_TAIX_SHOWFLAG(false);
    this.SET_PLANNER_SCORE_SHOW_FLAG(false);
  },

  computed: {
    ...mapFields("live_map", [
      "selected.latLongWayPoints",
      "selected.latLongCenter",
      "selected.job",
      "selected_marker",
      "select_mark_worker",
      "pick_drop_list",
      "kpi.taxi",
      "kpi.orders",
      "kpi.plannerScoresStats.score",
      "kpi.plannerScoresStats.total_travel_minutes",
      "dispatch_car.dispatch_car_model_visible",
      "job_address_flag",
    ]),
    ...mapState("auth", ["userInfo", "defaultTeam"]),
    ...mapFields("team", ["worker_icon", "job_icon"]),
    all_worker: {
      get() {
        return Object.values(this.pick_drop_list).reduce((pre, cur, index) => {
          let option = {};
          let zindex = 101;
          if (this.select_worker_code == cur.code) {
            zindex = 1002;
            option = this.worker_select_icon_option;
          } else {
            option = this.worker_icon_option;
          }

          return [
            ...pre,
            {
              ...cur,
              icon: L.BeautifyIcon.icon(option),
              zindex: zindex,
            },
          ];
        }, []);
      },
    },
    all_jobs: {
      get() {
        return Object.values(this.pick_drop_list).reduce((pre, cur, index) => {
          const job_list = Object.values(cur.jobs).reduce(
            (pre_job, cur_job, index) => {
              let zindex = 101;
              let option = {};
              if (this.select_job_code_list.indexOf(cur_job.code) >= 0) {
                zindex = 1002;
                option =
                  cur_job.type == "pick"
                    ? { ...this.job_pick_select_option, text: cur_job.index }
                    : { ...this.job_drop_select_option, text: cur_job.index };
              } else {
                option =
                  cur_job.type == "pick"
                    ? this.job_pick_option
                    : this.job_drop_option;
              }

              return [
                ...pre_job,
                {
                  ...cur_job,
                  icon: L.BeautifyIcon.icon(option),
                  zindex: zindex,
                },
              ];
            },
            []
          );

          return [...pre, ...job_list];
        }, []);
      },
    },
  },
  methods: {
    ...mapMutations("gantt", ["SET_PLANNER_SCORE_SHOW_FLAG"]),
    ...mapActions("auth", ["getUserInfo"]),
    ...mapActions("live_map", [
      "select_car",
      "get_job_pick_drop",
      "get_score_state",
      "dispatch_car",
    ]),
    ...mapActions("team", ["init_icon"]),
    ...mapMutations("live_map", [
      "SET_COMPANY_SHOWFLAG",
      "SET_TAIX_SHOWFLAG",
      "SET_SELECTED_VISIBLE",
      "SET_SELECTED_MSG",
      "SET_ROUTE",
      "SET_DISPATCH_CAT_VISIBLE",
      "SET_SERVICE_URL",
      "SET_SELECT_MARK_WORKER",
    ]),
    getMap: function (found) {
      var vm = this;
      function checkForMap() {
        if (vm.$refs.myRoutingMap) {
          found(vm.$refs.myRoutingMap.mapObject);
        } else {
          setTimeout(checkForMap, 150);
        }
      }
      checkForMap();
    },
    onchange_checkbox: function (type) {
      let flag = false;
      if (this.selected_marker.indexOf(type) >= 0) {
        flag = true;
      }
      this.SET_SELECTED_VISIBLE({ type: type, flag: flag });
      if (type == "heat_layer_worker" && flag) {
        this.delete_heatLayer("worker");
        this.add_heatLayer(this.all_worker, "worker");
      } else if (type == "heat_layer_worker" && !flag) {
        this.delete_heatLayer("worker");
      }
      if (type == "heat_layer_job" && flag) {
        this.delete_heatLayer("job");
        this.add_heatLayer(this.all_jobs, "job");
      } else if (type == "heat_layer_job" && !flag) {
        this.delete_heatLayer("job");
      }
    },
    mark_change_worker: function (mark_worker) {
      try {
        this.SET_SELECT_MARK_WORKER(mark_worker);
        let _that = this;
        this.all_worker.forEach(function (worker, index) {
          if (mark_worker.code == worker.code) {
            _that.select_worker = worker.worker_obj;
          }
        });
      } catch (e) {
        console.error(e);
      }
    },
    select_worker_marker: function (worker) {
      this.select_car(worker.kpi);
      this.SET_SELECTED_MSG(worker.code);
      this.SET_ROUTE(worker);
      this.SET_PLANNER_SCORE_SHOW_FLAG(false);
      this.select_job_code_list = Object.values(worker.jobs).reduce(
        (pre, cur, index) => {
          return [...pre, cur.code];
        },
        []
      );
      this.select_worker_code = worker.code;
    },
    change_show: function (con_visible, taix_visible) {
      this.SET_PLANNER_SCORE_SHOW_FLAG(con_visible);
      this.SET_TAIX_SHOWFLAG(taix_visible);
    },
    delete_heatLayer(type) {
      const mapObject = this.$refs.myRoutingMap.mapObject;
      if (type == "worker" && this.heatLayer) {
        mapObject.removeControl(this.heatLayer);
        this.heatLayer = null;
      }
      if (type == "job" && this.heatLayer_job) {
        mapObject.removeControl(this.heatLayer_job);
        this.heatLayer_job = null;
      }
    },
    add_heatLayer(newVal, type) {
      const mapObject = this.$refs.myRoutingMap.mapObject;
      try {
        if (type == "worker") {
          let workerHotMapData = Object.values(newVal).reduce(
            (pre, cur, index) => {
              return [
                ...pre,
                [cur["position"]["lat"], cur["position"]["lng"], 0.3],
              ];
            },
            []
          );
          this.heatLayer = new LHeatLayer(workerHotMapData, this.cfg);
          this.heatLayer.addTo(mapObject);
        } else if (type == "job") {
          let workerHotMapData = Object.values(newVal).reduce(
            (pre, cur, index) => {
              return [
                ...pre,
                [cur["position"]["lat"], cur["position"]["lng"], 0.3],
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
    drawing(info) {
      let canvas = info.canvas;
      let ctx = canvas.getContext("2d");
      let mapa = this.$refs.myRoutingMap.mapObject;
      let bounds = mapa.getBounds();

      ctx.fillStyle = "rgb(106, 158, 242)";

      for (let i = 0; i < this.all_jobs.length; i++) {
        if (bounds.contains(this.all_jobs[i].position_from)) {
          var dot = mapa.latLngToContainerPoint(
            this.locations_job_from[i].latlng
          );
          ctx.beginPath();
          ctx.arc(dot.x, dot.y, 3, 0, Math.PI * 2);
          ctx.fill();
          ctx.closePath();
        }
      }
    },
  },
  watch: {
    all_worker: function (newVal, oldVal) {
      try {
        this.delete_heatLayer("worker");
        this.add_heatLayer(newVal, "worker");
      } catch (e) {
        console.error(e);
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
    worker_icon: function (newVal, oldVal) {
      try {
        this.workerIcon = L.BeautifyIcon.icon({
          icon: newVal.replace("fa-", ""),
          iconShape: "marker",
          borderColor: "#b3334f",
          textColor: "#b3334f",
          iconSize: [23, 23],
          innerIconAnchor: [0, 0],
        });
      } catch (e) {
        console.error(e);
      }
    },
    job_icon: function (newVal, oldVal) {
      try {
        this.job_pick_option = {
          icon: newVal.replace("fa-", ""),
          iconShape: "marker",
          iconSize: [21, 21],
          innerIconAnchor: [0, 1],
        };
      } catch (e) {
        console.error(e);
      }
    },
    defaultTeam: function (newVal, oldVal) {
      try {
        this.select_team = newVal;
      } catch (e) {
        console.error(e);
      }
    },
    select_team: function (newVal, oldVal) {
      try {
        if (newVal != "") {
          this.get_job_pick_drop({ team_id: newVal.id });
          if (
            newVal.flex_form_data.routing_service_path != null &&
            newVal.flex_form_data.routing_service_path != undefined &&
            newVal.flex_form_data.routing_service_path != ""
          ) {
            this.SET_SERVICE_URL(newVal.flex_form_data.routing_service_path);
          }
        }
      } catch (e) {
        console.error(e);
      }
    },
    select_worker: function (newVal, oldVal) {
      try {
        if (newVal != "") {
          let _that = this;
          this.all_worker.forEach(function (worker, index) {
            if (newVal.code == worker.code) {
              _that.select_worker_marker(worker);
            }
          });
        }
      } catch (e) {
        console.error(e);
      }
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
.myRoutingMap {
  height: calc(100vh - 130px);
  width: 100%;
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